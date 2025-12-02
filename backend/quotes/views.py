# backend/quotes/views.py

import copy
import json
import logging
from decimal import Decimal
from dataclasses import replace

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, viewsets, status, serializers
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from .serializers import QuoteComputeRequestSerializer, QuoteModelSerializerV3
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import (
    QuoteInput,
    QuoteCharges,
    ShipmentDetails,
    Piece,
    ManualOverride,
    LocationRef,
)
from core.models import FxSnapshot, Policy, Location, Airport, Country, City
from parties.models import Company, Contact, Address
from ratecards.models import PartnerRateCard
from services.models import ServiceComponent

STATION_ID_BYTES = 4


def _encode_station_identifier(code: str) -> int:
    cleaned = (code or '').upper().strip()
    if not cleaned:
        raise ValueError("Station code is empty")
    data = cleaned.encode('ascii', errors='ignore')
    if not data:
        raise ValueError("Station code must be ASCII")
    if len(data) > STATION_ID_BYTES:
        data = data[:STATION_ID_BYTES]
    padded = data.ljust(STATION_ID_BYTES, b'\0')
    return int.from_bytes(padded, byteorder='big')


def _decode_station_identifier(identifier: int) -> str:
    if identifier is None or identifier <= 0:
        raise ValueError("Invalid station identifier")
    raw = identifier.to_bytes(STATION_ID_BYTES, byteorder='big').rstrip(b'\0')
    if not raw:
        raise ValueError("Unable to decode station identifier")
    return raw.decode('ascii')


class ManualChargeSerializer(serializers.Serializer):
    service_component_id = serializers.PrimaryKeyRelatedField(queryset=ServiceComponent.objects.all())
    cost_fcy = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    unit = serializers.CharField(max_length=20)
    min_charge_fcy = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)


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


logger = logging.getLogger(__name__)

class QuoteComputeV3APIView(generics.CreateAPIView):
    """
    The main V3 compute endpoint.
    Receives a quote request, calculates charges, and saves the quote.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = QuoteComputeRequestSerializer
    
    # Note: We override 'create' behavior by implementing 'post'
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            
            # --- MVP CHECK: Block DG ---
            if validated_data.get('is_dangerous_goods'):
                return Response(
                    {"detail": "Dangerous Goods (DG) shipments are not yet supported."},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            origin_location: Location = validated_data.get('origin_location')
            destination_location: Location = validated_data.get('destination_location')

            try:
                shipment_type = _classify_shipment_type(
                    validated_data.get('mode'),
                    origin_location,
                    destination_location,
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            try:
                # 1. Prepare input for PricingServiceV3
                quote_input = self._build_quote_input(
                    validated_data,
                    shipment_type,
                    origin_location,
                    destination_location,
                )
                
                # 2. Call the pricing service
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
                    validated_data, 
                    shipment_type, # <-- Pass calculated type
                    calculated_charges, 
                    service.get_fx_snapshot(),
                    service.get_policy(),
                    derived_output_currency,
                    quote_status,
                )
                
                # 4. Serialize and return the created quote
                response_serializer = QuoteModelSerializerV3(quote)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                # Log the full exception
                print(f"Error during quote computation: {e}")
                return Response(
                    {"detail": f"An unexpected error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        logger.warning("V3 quote compute validation failed", extra={"errors": serializer.errors})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _build_quote_input(self, data, shipment_type, origin_location: Location, destination_location: Location):
        """Helper to convert serializer data to PricingService dataclasses."""

        origin_ref = self._location_to_ref(origin_location)
        destination_ref = self._location_to_ref(destination_location)
        
        shipment_details = ShipmentDetails(
            mode=data['mode'],
            shipment_type=shipment_type,
            incoterm=data['incoterm'],
            payment_term=data['payment_term'],
            is_dangerous_goods=data['is_dangerous_goods'],
            pieces=[Piece(**p) for p in data['dimensions']],
            service_scope=data.get('service_scope'),
            direction=shipment_type,
            origin_location=origin_ref,
            destination_location=destination_ref,
        )
        
        overrides = [ManualOverride(**o) for o in data.get('overrides', [])]
        
        return QuoteInput(
            customer_id=data['customer_id'],
            contact_id=data['contact_id'],
            output_currency='PGK',
            shipment=shipment_details,
            overrides=overrides
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

    @transaction.atomic
    def _save_quote_v3(self, request, validated_data, shipment_type, charges: QuoteCharges, snapshot: FxSnapshot, policy: Policy, output_currency: str, initial_status: str):
        """
        Helper to save the quote, version, lines, and totals to the database.
        """
        customer = get_object_or_404(Company, id=validated_data['customer_id'])
        contact = get_object_or_404(Contact, id=validated_data['contact_id'])
        
        # --- UPDATED: Create the Quote object ---
        quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode=validated_data['mode'],
            shipment_type=shipment_type, # <-- Save calculated type
            incoterm=validated_data['incoterm'],
            payment_term=validated_data['payment_term'],
            service_scope=validated_data.get('service_scope'),
            output_currency=output_currency or 'PGK',
            origin_location=validated_data.get('origin_location'),
            destination_location=validated_data.get('destination_location'),
            policy=policy,
            fx_snapshot=snapshot,
            is_dangerous_goods=validated_data['is_dangerous_goods'],
            status=initial_status,
            request_details_json=request.data,
            created_by=request.user
        )
        # --- END UPDATE ---

        # Create the first QuoteVersion
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            payload_json=request.data,
            policy=policy,
            fx_snapshot=snapshot,
            status=initial_status,
            reason="Initial Draft",
            created_by=request.user
        )
        
        # Create QuoteLines
        for line_charge in charges.lines:
            QuoteLine.objects.create(
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
                is_rate_missing=line_charge.is_rate_missing
            )
            
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


class QuoteV3ViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Provides read-only (list and retrieve) endpoints for V3 Quotes.
    """
    queryset = Quote.objects.all().order_by('-created_at')
    serializer_class = QuoteModelSerializerV3
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Prefetch related data to optimize query
        return super().get_queryset().prefetch_related(
            'versions__lines__service_component',
            'versions__totals'
        )

    def retrieve(self, request, *args, **KWARGS):
        """
        Custom retrieve to ensure we always fetch the 'latest_version'.
        """
        instance = self.get_object()
        # Find the latest version
        latest_version = instance.versions.order_by('-version_number').first()
        instance.latest_version = latest_version
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """
        Custom list to add 'latest_version' to each quote.
        """
        queryset = self.get_queryset()
        
        # This is less efficient than retrieve, but fine for a list view.
        # A more optimized way would be to use Subquery or Annotation.
        for quote in queryset:
             latest_version = quote.versions.order_by('-version_number').first()
             quote.latest_version = latest_version

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


def _serialize_overrides_for_payload(overrides):
    serialized = []
    for override in overrides or []:
        serialized.append({
            'service_component_id': str(override.service_component_id),
            'cost_fcy': str(override.cost_fcy),
            'currency': override.currency,
            'unit': override.unit,
            'min_charge_fcy': str(override.min_charge_fcy) if override.min_charge_fcy is not None else None,
            'valid_until': override.valid_until,
        })
    return serialized


def _create_quote_version_from_service(quote: Quote, payload: dict, charges: QuoteCharges, service: PricingServiceV3, user):
    latest_version = quote.versions.order_by('-version_number').first()
    version_number = 1
    if latest_version:
        version_number = latest_version.version_number + 1

    version = QuoteVersion.objects.create(
        quote=quote,
        version_number=version_number,
        payload_json=payload,
        policy=service.get_policy(),
        fx_snapshot=service.get_fx_snapshot(),
        status=Quote.Status.DRAFT,
        reason="Manual recalculation",
        created_by=user,
    )

    for line_charge in charges.lines:
        QuoteLine.objects.create(
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
        )

    totals = charges.totals
    QuoteTotal.objects.create(
        quote_version=version,
        total_cost_pgk=totals.total_cost_pgk,
        total_sell_pgk=totals.total_sell_pgk,
        total_sell_pgk_incl_gst=totals.total_sell_pgk_incl_gst,
        total_sell_fcy=totals.total_sell_fcy,
        total_sell_fcy_incl_gst=totals.total_sell_fcy_incl_gst,
        total_sell_fcy_currency=totals.total_sell_fcy_currency,
        has_missing_rates=totals.has_missing_rates,
        notes=totals.notes,
    )

    quote.request_details_json = payload
    quote.latest_version = version
    quote.output_currency = service.get_output_currency()
    quote.save(update_fields=['request_details_json', 'output_currency'])

    return version


def _build_quote_input_from_payload(payload: dict):
    serializer = QuoteComputeRequestSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    origin_location: Location = validated.get('origin_location')
    destination_location: Location = validated.get('destination_location')
    shipment_type = _classify_shipment_type(
        validated.get('mode'),
        origin_location,
        destination_location,
    )
    compute_view = QuoteComputeV3APIView()
    quote_input = compute_view._build_quote_input(
        validated,
        shipment_type,
        origin_location,
        destination_location,
    )
    return quote_input, validated


class CustomerDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id):
        company = self._get_company(customer_id)
        return Response(self._serialize_customer(company))

    def put(self, request, customer_id):
        company = self._get_company(customer_id)
        data = request.data
        with transaction.atomic():
            name = data.get('company_name')
            if name:
                company.name = name
                company.save(update_fields=['name'])
            self._sync_contact(company, data)
            self._sync_primary_address(company, data.get('primary_address'))
        return Response(self._serialize_customer(company))

    def _get_company(self, company_id):
        return get_object_or_404(
            Company.objects.prefetch_related('contacts', 'addresses__city__country'),
            pk=company_id,
            company_type='CUSTOMER',
        )

    def _serialize_customer(self, company: Company) -> dict:
        contact = company.contacts.order_by('-is_primary', 'last_name').first()
        address = company.addresses.filter(is_primary=True).select_related(
            'city__country'
        ).first()
        primary_address = None
        if address:
            primary_address = {
                'address_line_1': address.address_line_1,
                'address_line_2': address.address_line_2,
                'city': address.city.name if address.city else '',
                'state_province': '',
                'postcode': address.postal_code,
                'country': address.country.code if address.country else '',
            }

        contact_name = None
        if contact:
            contact_name = f"{contact.first_name} {contact.last_name}".strip()

        return {
            'id': str(company.id),
            'company_name': company.name,
            'audience_type': 'LOCAL_PNG_CUSTOMER',
            'address_description': '',
            'primary_address': primary_address,
            'contact_person_name': contact_name,
            'contact_person_email': contact.email if contact else '',
            'contact_person_phone': contact.phone if contact else '',
        }

    def _sync_contact(self, company: Company, data: dict) -> None:
        name = (data.get('contact_person_name') or '').strip()
        email = (data.get('contact_person_email') or '').strip()
        phone = (data.get('contact_person_phone') or '').strip()
        if not any([name, email, phone]):
            return

        first_name, last_name = (name, '') if ' ' not in name else name.split(' ', 1)
        contact = company.contacts.order_by('-is_primary', 'last_name').first()
        if not contact:
            contact = Contact(company=company)

        if first_name:
            contact.first_name = first_name
        if last_name:
            contact.last_name = last_name
        if email:
            contact.email = email
        contact.phone = phone
        contact.is_primary = True
        contact.save()

    def _sync_primary_address(self, company: Company, payload: dict | None) -> None:
        if not payload:
            return
        line1 = (payload.get('address_line_1') or '').strip()
        city_name = (payload.get('city') or '').strip()
        country_code = (payload.get('country') or '').strip()
        if not (line1 and city_name and country_code):
            return

        country_code = country_code.upper()
        if len(country_code) != 2:
            country_code = country_code[:2].upper().ljust(2, 'X')
        country, _ = Country.objects.get_or_create(
            code=country_code,
            defaults={'name': country_code},
        )
        city, _ = City.objects.get_or_create(
            name=city_name,
            country=country,
        )

        address = company.addresses.filter(is_primary=True).first()
        if not address:
            address = Address(company=company, is_primary=True)
        address.address_line_1 = line1
        address.address_line_2 = (payload.get('address_line_2') or '').strip()
        address.city = city
        address.country = country
        address.postal_code = (payload.get('postcode') or '').strip()
        address.is_primary = True
        address.save()


class RatecardListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cards = (
            PartnerRateCard.objects.select_related('supplier')
            .order_by('-created_at')
        )
        data = [self._serialize(card) for card in cards]
        return Response(data)

    def _serialize(self, card: PartnerRateCard) -> dict:
        today = timezone.now().date()
        if card.valid_from and card.valid_from > today:
            status_label = 'PENDING'
        elif card.valid_until and card.valid_until < today:
            status_label = 'EXPIRED'
        else:
            status_label = 'ACTIVE'
        return {
            'id': str(card.id),
            'name': card.name,
            'supplier_name': card.supplier.name,
            'currency_code': card.currency_code,
            'valid_from': card.valid_from.isoformat() if card.valid_from else None,
            'valid_until': card.valid_until.isoformat() if card.valid_until else None,
            'status': status_label,
            'created_at': card.created_at.isoformat(),
            'file_type': 'CSV',
        }


class RatecardUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload_file = request.FILES.get('file')
        supplier_id = request.data.get('supplier_id')
        if not upload_file:
            return Response({'detail': 'File is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not supplier_id:
            return Response({'detail': 'supplier_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        supplier = get_object_or_404(Company, pk=supplier_id)
        name = upload_file.name or 'Ratecard'
        unique_name = name
        counter = 1
        while PartnerRateCard.objects.filter(name=unique_name).exists():
            unique_name = f"{name}-{counter}"
            counter += 1

        card = PartnerRateCard.objects.create(
            supplier=supplier,
            name=unique_name,
            currency_code=request.data.get('currency_code') or 'PGK',
            valid_from=timezone.now().date(),
        )

        data = RatecardListAPIView()._serialize(card)
        return Response(data, status=status.HTTP_201_CREATED)


class StationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('search') or request.query_params.get('q') or ''
        airports = Airport.objects.select_related('city__country')
        if query:
            airports = airports.filter(
                Q(iata_code__icontains=query)
                | Q(name__icontains=query)
                | Q(city__name__icontains=query)
            )
        airports = airports.order_by('iata_code')[:50]
        data = []
        for airport in airports:
            try:
                identifier = _encode_station_identifier(airport.iata_code)
            except ValueError:
                continue
            city_country = None
            if airport.city and airport.city.country:
                city_country = f"{airport.city.name}, {airport.city.country.code}"
            elif airport.city:
                city_country = airport.city.name
            data.append({
                'id': identifier,
                'iata_code': airport.iata_code,
                'name': airport.name,
                'city_country': city_country,
            })
        return Response(data)


class QuoteVersionCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        """
        Creates a new QuoteVersion by re-running the PricingServiceV3 with manual overrides.
        """
        quote_id = self.kwargs.get("quote_id")
        original_quote = get_object_or_404(Quote, id=quote_id)
        
        # 1. Load original payload
        original_payload = original_quote.request_details_json
        if not original_payload:
            return Response({"detail": "Original quote payload is missing."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Rebuild the QuoteInput
        try:
            quote_input, _ = _build_quote_input_from_payload(original_payload)
        except Exception as e:
            return Response({"detail": f"Error building input: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Parse & Merge Manual Overrides
        # Validate incoming data
        serializer = ManualChargeSerializer(data=request.data.get("charges", []), many=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Because QuoteInput is a frozen dataclass, we must build a new list of overrides
        # and then create a new QuoteInput instance.
        
        # Start with existing overrides, keyed by component ID for easy replacement
        # The list comprehension at the end handles the case where quote_input.overrides is None
        current_overrides = {
            str(o.service_component_id): o for o in (quote_input.overrides or [])
        }

        # Add or update with the new overrides from the request
        for charge in serializer.validated_data:
            new_override = ManualOverride(
                service_component_id=charge["service_component_id"].id,
                cost_fcy=charge["cost_fcy"],
                currency=charge["currency"].upper(),
                unit=charge["unit"],
                min_charge_fcy=charge.get("min_charge_fcy") or Decimal("0.0"),
                valid_until=charge.get("valid_until")
            )
            current_overrides[str(new_override.service_component_id)] = new_override
        
        # Create a new QuoteInput with the updated overrides list
        final_overrides = list(current_overrides.values())
        quote_input = replace(quote_input, overrides=final_overrides)

        # 4. Run the REAL Pricing Engine
        # This applies FX, CAF, and Margins based on the Policy
        try:
            service = PricingServiceV3(quote_input)
            charges = service.calculate_charges()
        except Exception as e:
            logger.error(f"Pricing engine failed: {e}", exc_info=True)
            return Response({"detail": f"Pricing Error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 5. Save Result as New Version
        new_version = _create_quote_version_from_service(
            quote=original_quote,
            payload=original_payload, # We reuse original payload structure
            charges=charges,
            service=service,
            user=request.user
        )
        
        # Update the payload on the quote itself so next time we have these overrides
        # (We need to serialize the overrides back to JSON)
        updated_payload = copy.deepcopy(original_payload)
        updated_payload['overrides'] = _serialize_overrides_for_payload(quote_input.overrides)
        original_quote.request_details_json = updated_payload
        original_quote.save(update_fields=['request_details_json'])
        
        original_quote.latest_version = new_version

        # 6. Return Response
        return Response(
            QuoteModelSerializerV3(original_quote, context={'request': request}).data, 
            status=status.HTTP_201_CREATED
        )
