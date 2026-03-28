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
from quotes.selectors import get_quote_for_user
from quotes.state_machine import (
    QuoteImmutableError,
    assert_quote_mutable_for_action,
    is_quote_editable,
)
from quotes.currency_rules import determine_quote_currency

from services.models import ServiceComponent
from core.models import FxSnapshot, Policy, Location
from core.commodity import DEFAULT_COMMODITY_CODE
from parties.models import Company, Contact

# Pricing Dispatcher - Single Entry Point
from quotes.services.dispatcher import PricingDispatcher, RoutingError
from core.dataclasses import (
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
            # SECURITY FIX: Enforce IDOR protection
            existing_quote = get_quote_for_user(request.user, payload.quote_id)

            try:
                assert_quote_mutable_for_action(
                    existing_quote,
                    action="recalculate_quote",
                    user=request.user,
                )
            except QuoteImmutableError as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_403_FORBIDDEN,
                )
             
            if existing_quote.is_archived:
                if existing_quote.status in (Quote.Status.DRAFT, Quote.Status.INCOMPLETE):
                    return Response(
                        {"detail": "Draft quote was deleted and can no longer be edited."},
                        status=status.HTTP_410_GONE,
                    )
                return Response(
                    {"detail": "Cannot recalculate. Quote is archived and locked for editing."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Block recalculation for locked quotes (FINALIZED or SENT)
            if not is_quote_editable(existing_quote):
                return Response(
                    {"detail": f"Cannot recalculate. Quote is {existing_quote.status} and locked for editing."},
                    status=status.HTTP_403_FORBIDDEN,
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

        customer = get_object_or_404(Company, id=payload.customer_id)

        if payload.commodity_code != DEFAULT_COMMODITY_CODE:
            from quotes.spot_services import CommodityRateRuleService, SpotTriggerEvaluator

            commodity_coverage = CommodityRateRuleService.evaluate_coverage(
                origin_airport=origin_location.code,
                destination_airport=destination_location.code,
                direction=shipment_type,
                service_scope=payload.service_scope,
                commodity_code=payload.commodity_code,
                payment_term=payload.payment_term,
            )
            commodity_trigger = SpotTriggerEvaluator.build_commodity_trigger(commodity_coverage)
            if commodity_trigger:
                return Response(
                    {
                        "detail": commodity_trigger.text,
                        "spot_trigger": {
                            "code": commodity_trigger.code,
                            "text": commodity_trigger.text,
                            "missing_product_codes": commodity_trigger.missing_product_codes,
                            "spot_required_product_codes": commodity_trigger.spot_required_product_codes,
                            "manual_required_product_codes": commodity_trigger.manual_required_product_codes,
                        },
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            # 1. Enforce Business Rules for EXPORT Incoterms
            if shipment_type == Quote.ShipmentType.EXPORT:
                # D2A (Prepaid/Collect) -> Always FCA
                if payload.service_scope == 'D2A':
                    payload.incoterm = 'FCA'
                # D2D (Prepaid) -> Always DAP
                elif payload.service_scope == 'D2D' and payload.payment_term == 'PREPAID':
                    payload.incoterm = 'DAP'

            # 2. Prepare input for the pricing pipeline (V4-only dispatcher)
            quote_input = self._build_quote_input(
                payload,
                shipment_type,
                origin_location,
                destination_location,
            )
            
            # 3. Call the pricing dispatcher (single entry point)
            dispatcher = PricingDispatcher()
            result = dispatcher.calculate(quote_input)
            calculated_charges = result.charges
            engine_version = 'V4'
            
            # Get derived values from the adapter (via charges)
            from pricing_v4.adapter import PricingServiceV4Adapter
            adapter = PricingServiceV4Adapter(quote_input)
            derived_output_currency = adapter.get_output_currency()
            
            has_missing_rates = calculated_charges.totals.has_missing_rates
            quote_status = (
                Quote.Status.INCOMPLETE if has_missing_rates else Quote.Status.DRAFT
            )

            # 4. Save to DB with engine version from dispatcher
            quote = self._save_quote_v3(
                request, 
                payload, 
                shipment_type,
                calculated_charges, 
                adapter.get_fx_snapshot(),
                adapter.get_policy(),
                derived_output_currency,
                quote_status,
                existing_quote,
                engine_version,  # Pass engine version from dispatcher
            )
            
            # 4. Serialize and return the created quote
            # Ensure contact has company_name for Pydantic schema
            if quote.contact:
                quote.contact.company_name = quote.contact.company.name

            return Response(QuoteModelSerializerV3(quote).data, status=status.HTTP_201_CREATED)

        except RoutingError as e:
            # Dispatcher routing errors -> 400 Bad Request
            logger.warning(f"Pricing dispatcher routing error: {e}")
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
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
            commodity_code=data.commodity_code,
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
        """Determine output currency using global shipment/payment/country rules only."""
        origin_country_code = origin_location.country.code if origin_location.country else None
        destination_country_code = destination_location.country.code if destination_location.country else None
        return determine_quote_currency(
            shipment_type=shipment_type,
            payment_term=payment_term,
            origin_country_code=origin_country_code,
            destination_country_code=destination_country_code,
        )

    @transaction.atomic
    def _save_quote_v3(self, request, validated_data: QuoteComputeRequest, shipment_type, charges: QuoteCharges, snapshot: FxSnapshot, policy: Policy, output_currency: str, initial_status: str, quote: Quote = None, engine_version: str = 'V4'):
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
                commodity_code=validated_data.commodity_code,
                output_currency=output_currency or 'PGK',
                origin_location_id=validated_data.origin_location_id,
                destination_location_id=validated_data.destination_location_id,
                policy=policy,
                fx_snapshot=snapshot,
                is_dangerous_goods=validated_data.is_dangerous_goods,
                status=initial_status,
                request_details_json=validated_data.model_dump(mode='json'),
                created_by=request.user,
                organization=getattr(request.user, 'organization', None),
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
            quote.commodity_code = validated_data.commodity_code
            quote.output_currency = output_currency or 'PGK'
            quote.origin_location_id = validated_data.origin_location_id
            quote.destination_location_id = validated_data.destination_location_id
            quote.policy = policy
            quote.fx_snapshot = snapshot
            quote.is_dangerous_goods = validated_data.is_dangerous_goods
            quote.status = initial_status
            quote.request_details_json = validated_data.model_dump(mode='json')
            if quote.organization_id is None and getattr(request.user, 'organization_id', None):
                quote.organization = request.user.organization
            quote.save(update_fields=[
                'customer',
                'contact',
                'mode',
                'shipment_type',
                'incoterm',
                'payment_term',
                'service_scope',
                'commodity_code',
                'output_currency',
                'origin_location',
                'destination_location',
                'policy',
                'fx_snapshot',
                'is_dangerous_goods',
                'status',
                'request_details_json',
                'organization',
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
            created_by=request.user,
            engine_version=engine_version,  # From dispatcher result
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
            notes=charges.totals.notes,
            engine_version=engine_version,  # From dispatcher result
        )

        # Attach latest version for serializers expecting the attribute
        quote.latest_version = version
        return quote
