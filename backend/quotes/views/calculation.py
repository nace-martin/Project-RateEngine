import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from pydantic import ValidationError
from pydantic_core import ValidationError as PydanticCoreValidationError

from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from quotes.serializers import QuoteComputeRequestSerializer, QuoteModelSerializerV3
from quotes.schemas import QuoteComputeRequest
from accounts.permissions import QuoteAccessPermission

from services.models import ServiceComponent
from core.models import FxSnapshot, Policy, Location
from parties.models import Company, Contact

# from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v4.adapter import PricingServiceV4Adapter as PricingServiceV3 # Using V4 Adapter
from pricing_v2.dataclasses_v3 import (
    QuoteInput,
    QuoteCharges,
    ShipmentDetails,
    Piece,
    ManualOverride,
    LocationRef,
)

logger = logging.getLogger(__name__)

def _classify_shipment_type(mode: str, origin_location: Location, destination_location: Location) -> str:
    if not origin_location or not destination_location:
        raise ValueError("Origin and destination locations are required.")

    mode = (mode or '').upper()
    if mode == 'AIR':
        org_country = origin_location.country.code if origin_location.country else None
        dest_country = destination_location.country.code if destination_location.country else None
        if not org_country or not dest_country:
            raise ValueError("Origin and destination locations must include countries for AIR mode.")

        if org_country == 'PG' and dest_country == 'PG':
            return Quote.ShipmentType.DOMESTIC
        if org_country != 'PG' and dest_country == 'PG':
            return Quote.ShipmentType.IMPORT
        if org_country == 'PG' and dest_country != 'PG':
            return Quote.ShipmentType.EXPORT
        raise ValueError("Cross-border shipments not involving PNG are not yet supported.")

    if mode == 'SEA':
        raise ValueError("SEA mode is not yet supported.")

    raise ValueError(f"Mode '{mode}' is not supported.")


class QuoteComputeV3APIView(generics.CreateAPIView):
    """
    The main V3 compute endpoint.
    Receives a quote request, calculates charges, and saves the quote.
    """
    permission_classes = [QuoteAccessPermission]  # Sales/Manager/Admin can create; Finance read-only
    serializer_class = QuoteComputeRequestSerializer
    
    # Note: We override 'create' behavior by implementing 'post'
    def post(self, request, *args, **kwargs):
        try:
            payload = QuoteComputeRequest(**request.data)
        except (ValidationError, PydanticCoreValidationError) as e:
            return Response(e.errors(), status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Fallback for any other validation-like errors
            if hasattr(e, 'errors'):
                return Response(e.errors(), status=status.HTTP_400_BAD_REQUEST)
            raise e

        existing_quote = None
        if payload.quote_id:
            existing_quote = get_object_or_404(Quote, id=payload.quote_id)
            
            # Block recalculation for locked quotes (FINALIZED or SENT)
            from quotes.state_machine import is_quote_editable
            if not is_quote_editable(existing_quote):
                return Response(
                    {"detail": f"Cannot recalculate. Quote is {existing_quote.status} and locked for editing."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            
            if existing_quote.created_by_id and existing_quote.created_by_id != request.user.id:
                return Response(
                    {"detail": "You do not have permission to update this quote."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        
        # --- MVP CHECK: Block DG ---
        if payload.is_dangerous_goods:
            return Response(
                {"detail": "Dangerous Goods (DG) shipments are not yet supported."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        origin_location = get_object_or_404(Location, pk=payload.origin_location_id, is_active=True)
        destination_location = get_object_or_404(Location, pk=payload.destination_location_id, is_active=True)

        try:
            shipment_type = _classify_shipment_type(
                payload.mode,
                origin_location,
                destination_location,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Enforce Business Rules for EXPORT Incoterms
            if shipment_type == Quote.ShipmentType.EXPORT:
                # D2A (Prepaid/Collect) -> Always FCA
                if payload.service_scope == 'D2A':
                    payload.incoterm = 'FCA'
                # D2D (Prepaid) -> Always DAP
                elif payload.service_scope == 'D2D' and payload.payment_term == 'PREPAID':
                    payload.incoterm = 'DAP'

            # 2. Prepare input for PricingServiceV3
            quote_input = self._build_quote_input(
                payload,
                shipment_type,
                origin_location,
                destination_location,
            )
            
            # 3. Call the pricing service
            service = PricingServiceV3(quote_input)
            calculated_charges = service.calculate_charges()
            derived_output_currency = service.get_output_currency()
            has_missing_rates = calculated_charges.totals.has_missing_rates
            quote_status = (
                Quote.Status.INCOMPLETE if has_missing_rates else Quote.Status.DRAFT
            )

            # 3. Save to DB
            quote = self._save_quote_v3(
                request, 
                payload, 
                shipment_type, # <-- Pass calculated type
                calculated_charges, 
                service.get_fx_snapshot(),
                service.get_policy(),
                derived_output_currency,
                quote_status,
                existing_quote,
            )
            
            # 4. Serialize and return the created quote
            # Ensure contact has company_name for Pydantic schema
            if quote.contact:
                quote.contact.company_name = quote.contact.company.name

            return Response(QuoteModelSerializerV3(quote).data, status=status.HTTP_201_CREATED)

        except (ValueError, NotImplementedError) as e:
            # Domain logic errors (e.g., "Unsupported shipment type") -> 400 Bad Request
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        except ServiceComponent.DoesNotExist:
            # Configuration error -> 500 but with specific message
            logger.exception("Missing service component configuration")
            return Response(
                {"detail": "Configuration Error: Missing required Service Components. Please contact support."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except Exception as e:
            # Unexpected errors (bugs) -> Log and 500, but do NOT mask the stack trace in dev
            logger.exception(f"Unexpected error during quote computation: {e}")
            # Re-raise so Django's exception handler can do its job (or return generic 500)
            raise

    def _build_quote_input(self, data: QuoteComputeRequest, shipment_type, origin_location: Location, destination_location: Location):
        """Helper to convert Pydantic model to PricingService dataclasses."""

        origin_ref = self._location_to_ref(origin_location)
        destination_ref = self._location_to_ref(destination_location)
        
        shipment_details = ShipmentDetails(
            mode=data.mode,
            shipment_type=shipment_type,
            incoterm=data.incoterm,
            payment_term=data.payment_term,
            is_dangerous_goods=data.is_dangerous_goods,
            pieces=[Piece(**p.model_dump()) for p in data.dimensions],
            service_scope=data.service_scope,
            direction=shipment_type,
            origin_location=origin_ref,
            destination_location=destination_ref,
        )
        
        overrides = [ManualOverride(**o.model_dump()) for o in (data.overrides or [])]

        output_currency = self._derive_output_currency(
            shipment_type,
            data.payment_term,
            origin_location,
            destination_location,
        )

        return QuoteInput(
            customer_id=data.customer_id,
            contact_id=data.contact_id,
            output_currency=output_currency,
            quote_date=date.today(),
            shipment=shipment_details,
            overrides=overrides,
            spot_rates=data.spot_rates or {}
        )

    def _location_to_ref(self, location: Location):
        country_code = location.country.code if location.country else None
        currency_code = None
        if location.country and location.country.currency:
            currency_code = location.country.currency.code

        return LocationRef(
            id=location.id,
            code=location.code,
            name=location.name,
            country_code=country_code,
            currency_code=currency_code,
        )

    def _derive_output_currency(self, shipment_type: str, payment_term: str, origin_location: Location, destination_location: Location) -> str:
        """
        Determine the correct output currency based on shipment type and payment term.
        Import PREPAID should surface FCY (origin currency) while COLLECT stays PGK.
        """
        if shipment_type == Quote.ShipmentType.IMPORT:
            if payment_term == Quote.PaymentTerm.PREPAID:
                if origin_location.country and origin_location.country.currency:
                    return origin_location.country.currency.code
                return 'AUD'  # Fallback FCY for prepaid imports
            return 'PGK'
        
        # Default to PGK for other shipment types
        return 'PGK'

    @transaction.atomic
    def _save_quote_v3(self, request, validated_data: QuoteComputeRequest, shipment_type, charges: QuoteCharges, snapshot: FxSnapshot, policy: Policy, output_currency: str, initial_status: str, quote: Quote = None):
        """
        Helper to save the quote, version, lines, and totals to the database.
        When an existing quote is provided, we append a new version instead of creating a duplicate quote.
        """
        customer = get_object_or_404(Company, id=validated_data.customer_id)
        contact = get_object_or_404(Contact, id=validated_data.contact_id)

        is_new_quote = quote is None
        if is_new_quote:
            # --- Create the Quote object ---
            quote = Quote.objects.create(
                customer=customer,
                contact=contact,
                mode=validated_data.mode,
                shipment_type=shipment_type, # <-- Save calculated type
                incoterm=validated_data.incoterm,
                payment_term=validated_data.payment_term,
                service_scope=validated_data.service_scope,
                output_currency=output_currency or 'PGK',
                origin_location_id=validated_data.origin_location_id,
                destination_location_id=validated_data.destination_location_id,
                policy=policy,
                fx_snapshot=snapshot,
                is_dangerous_goods=validated_data.is_dangerous_goods,
                status=initial_status,
                request_details_json=validated_data.model_dump(mode='json'),
                created_by=request.user
            )
            version_number = 1
        else:
            # Update the existing quote details and append a new version
            quote.customer = customer
            quote.contact = contact
            quote.mode = validated_data.mode
            quote.shipment_type = shipment_type
            quote.incoterm = validated_data.incoterm
            quote.payment_term = validated_data.payment_term
            quote.service_scope = validated_data.service_scope
            quote.output_currency = output_currency or 'PGK'
            quote.origin_location_id = validated_data.origin_location_id
            quote.destination_location_id = validated_data.destination_location_id
            quote.policy = policy
            quote.fx_snapshot = snapshot
            quote.is_dangerous_goods = validated_data.is_dangerous_goods
            quote.status = initial_status
            quote.request_details_json = validated_data.model_dump(mode='json')
            quote.save(update_fields=[
                'customer',
                'contact',
                'mode',
                'shipment_type',
                'incoterm',
                'payment_term',
                'service_scope',
                'output_currency',
                'origin_location',
                'destination_location',
                'policy',
                'fx_snapshot',
                'is_dangerous_goods',
                'status',
                'request_details_json',
            ])

            latest_version = quote.versions.order_by('-version_number').first()
            version_number = 1 if latest_version is None else latest_version.version_number + 1

        # Create the QuoteVersion
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=version_number,
            payload_json=validated_data.model_dump(mode='json'),
            policy=policy,
            fx_snapshot=snapshot,
            status=initial_status,
            reason="Initial Draft" if is_new_quote else "Recalculated with spot rates",
            created_by=request.user
        )

        # Create QuoteLines (bulk insert for performance)
        lines_to_create = [
            QuoteLine(
                quote_version=version,
                service_component_id=line_charge.service_component_id,
                cost_pgk=line_charge.cost_pgk,
                cost_fcy=line_charge.cost_fcy,
                cost_fcy_currency=line_charge.cost_fcy_currency,
                sell_pgk=line_charge.sell_pgk,
                sell_pgk_incl_gst=line_charge.sell_pgk_incl_gst,
                sell_fcy=line_charge.sell_fcy,
                sell_fcy_incl_gst=line_charge.sell_fcy_incl_gst,
                sell_fcy_currency=line_charge.sell_fcy_currency,
                exchange_rate=line_charge.exchange_rate,
                cost_source=line_charge.cost_source,
                cost_source_description=line_charge.cost_source_description,
                is_rate_missing=line_charge.is_rate_missing,
                leg=line_charge.leg,
                bucket=line_charge.bucket
            )
            for line_charge in charges.lines
        ]
        QuoteLine.objects.bulk_create(lines_to_create)
            
        # Create QuoteTotal
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=charges.totals.total_cost_pgk,
            total_sell_pgk=charges.totals.total_sell_pgk,
            total_sell_pgk_incl_gst=charges.totals.total_sell_pgk_incl_gst,
            total_sell_fcy=charges.totals.total_sell_fcy,
            total_sell_fcy_incl_gst=charges.totals.total_sell_fcy_incl_gst,
            total_sell_fcy_currency=charges.totals.total_sell_fcy_currency,
            has_missing_rates=charges.totals.has_missing_rates,
            notes=charges.totals.notes
        )

        # Attach latest version for serializers expecting the attribute
        quote.latest_version = version
        return quote
