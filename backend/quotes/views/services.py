import logging
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from parties.models import Address, Company, Contact, CustomerCommercialProfile
from accounts.scope import scoped_queryset_for_user
from core.models import Airport, City, Country, Currency
from core.security import validate_csv_upload
from ratecards.models import PartnerRateCard

# RBAC permissions
from accounts.permissions import QuoteAccessPermission
from accounts.permissions import IsAdmin, IsManagerOrAdmin
from quotes.selectors import get_quote_for_user
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from pricing_v4.adapter import PricingServiceV4Adapter

logger = logging.getLogger(__name__)

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


class CustomerDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    VALID_AUDIENCE_TYPES = {
        Company.AUDIENCE_LOCAL_PNG,
        Company.AUDIENCE_OVERSEAS_AU,
        Company.AUDIENCE_OVERSEAS_NON_AU,
    }

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdmin()]

    def get(self, request, customer_id):
        company = self._get_company(customer_id)
        return Response(self._serialize_customer(company))

    def put(self, request, customer_id):
        company = self._get_company(customer_id)
        data = request.data
        audience_type = data.get('audience_type')
        if audience_type is not None and audience_type not in self.VALID_AUDIENCE_TYPES:
            return Response(
                {
                    'error': (
                        "audience_type must be one of "
                        "LOCAL_PNG_CUSTOMER, OVERSEAS_PARTNER_AU, OVERSEAS_PARTNER_NON_AU"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                name = data.get('company_name')
                if name:
                    company.name = name
                if audience_type is not None:
                    company.audience_type = audience_type
                if data.get('address_description') is not None:
                    company.address_description = (data.get('address_description') or '').strip()
                company.save(update_fields=['name', 'audience_type', 'address_description'])
                self._sync_contact(company, data)
                self._sync_primary_address(company, data.get('primary_address'))
                self._sync_commercial_profile(company, data.get('commercial_profile'))
        except ValidationError as exc:
            return Response({'error': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._serialize_customer(company))

    def patch(self, request, customer_id):
        company = self._get_company(customer_id)
        is_active = request.data.get('is_active')
        if not isinstance(is_active, bool):
            return Response(
                {'error': 'is_active is required and must be boolean'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company.is_active = is_active
        company.save(update_fields=['is_active'])
        return Response(self._serialize_customer(company))

    def delete(self, request, customer_id):
        company = self._get_company(customer_id)
        try:
            company.delete()
        except ProtectedError as exc:
            protected_models = sorted({
                obj.__class__.__name__
                for obj in exc.protected_objects
            })
            model_list = ", ".join(protected_models) if protected_models else "related records"
            return Response(
                {
                    "error": (
                        "Cannot delete customer because it is referenced by existing records. "
                        f"Protected by: {model_list}."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _get_company(self, company_id):
        base_filter = Q(is_customer=True) | Q(company_type='CUSTOMER')
        queryset = Company.objects.filter(base_filter)
        queryset = scoped_queryset_for_user(queryset, self.request.user)
        queryset = queryset.select_related(
            'commercial_profile__preferred_quote_currency'
        ).prefetch_related('contacts', 'addresses__city__country')
        return get_object_or_404(queryset, pk=company_id)

    def _serialize_commercial_profile(self, company: Company) -> dict:
        profile = getattr(company, 'commercial_profile', None)
        preferred_currency = getattr(profile, 'preferred_quote_currency', None)
        return {
            'preferred_quote_currency': preferred_currency.code if preferred_currency else '',
            'default_margin_percent': self._format_decimal(getattr(profile, 'default_margin_percent', None)),
            'min_margin_percent': self._format_decimal(getattr(profile, 'min_margin_percent', None)),
            'payment_term_default': getattr(profile, 'payment_term_default', '') or '',
        }

    def _serialize_customer(self, company: Company) -> dict:
        contact = company.contacts.filter(is_active=True).order_by('-is_primary', 'last_name').first()
        address = company.addresses.filter(is_primary=True).select_related(
            'city__country'
        ).first()
        primary_address = None
        if address:
            primary_address = {
                'address_line_1': address.address_line_1,
                'address_line_2': address.address_line_2,
                'city_id': str(address.city.id) if address.city else '',
                'city': address.city.name if address.city else '',
                'state_province': '',
                'postcode': address.postal_code,
                'country': address.country.code if address.country else '',
                'country_name': address.country.name if address.country else '',
            }

        contact_name = None
        if contact:
            contact_name = f"{contact.first_name} {contact.last_name}".strip()

        return {
            'id': str(company.id),
            'company_name': company.name,
            'is_active': company.is_active,
            'audience_type': company.audience_type,
            'address_description': company.address_description,
            'primary_address': primary_address,
            'contact_person_name': contact_name or '',
            'contact_person_email': contact.email if contact else '',
            'contact_person_phone': contact.phone if contact else '',
            'commercial_profile': self._serialize_commercial_profile(company),
        }

    def _sync_commercial_profile(self, company: Company, payload: dict | None) -> None:
        if payload is None:
            return

        profile, _ = CustomerCommercialProfile.objects.get_or_create(company=company)

        preferred_quote_currency = (payload.get('preferred_quote_currency') or '').strip().upper()
        default_margin_percent = payload.get('default_margin_percent')
        min_margin_percent = payload.get('min_margin_percent')
        payment_term_default = (payload.get('payment_term_default') or '').strip().upper()

        if preferred_quote_currency:
            currency = Currency.objects.filter(code=preferred_quote_currency).first()
            if not currency:
                raise ValidationError({'commercial_profile.preferred_quote_currency': 'Currency not found in reference data'})
            profile.preferred_quote_currency = currency
        else:
            profile.preferred_quote_currency = None

        profile.default_margin_percent = self._parse_optional_decimal(
            default_margin_percent,
            'commercial_profile.default_margin_percent',
        )
        profile.min_margin_percent = self._parse_optional_decimal(
            min_margin_percent,
            'commercial_profile.min_margin_percent',
        )

        if payment_term_default and payment_term_default not in {'PREPAID', 'COLLECT'}:
            raise ValidationError(
                {'commercial_profile.payment_term_default': 'Payment term default must be PREPAID or COLLECT'}
            )
        profile.payment_term_default = payment_term_default or None
        profile.updated_by = self.request.user
        profile.save()

    def _parse_optional_decimal(self, raw_value, error_key: str):
        if raw_value in (None, ''):
            return None
        try:
            return Decimal(str(raw_value))
        except Exception as exc:
            raise ValidationError({error_key: 'Must be a valid decimal number'}) from exc

    def _format_decimal(self, value: Decimal | None) -> str:
        if value is None:
            return ''
        normalized = value.quantize(Decimal('0.01'))
        return format(normalized, 'f')

    def _sync_contact(self, company: Company, data: dict) -> None:
        name = (data.get('contact_person_name') or '').strip()
        email = (data.get('contact_person_email') or '').strip()
        phone = (data.get('contact_person_phone') or '').strip()
        if not any([name, email, phone]):
            return

        first_name, last_name = (name, '') if ' ' not in name else name.split(' ', 1)
        contact = company.contacts.filter(is_active=True).order_by('-is_primary', 'last_name').first()
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
        country_code = (payload.get('country') or '').strip()
        city_id = (payload.get('city_id') or '').strip()
        city_name = (payload.get('city') or '').strip()
        if not (line1 and (city_id or city_name) and country_code):
            return

        country_code = country_code.upper()
        if len(country_code) != 2:
            raise ValidationError({'primary_address.country': 'Country must be a 2-letter ISO code'})

        country = Country.objects.filter(code=country_code).first()
        if not country:
            raise ValidationError({'primary_address.country': 'Country not found in reference data'})

        city = None
        if city_id:
            city = City.objects.select_related('country').filter(pk=city_id).first()
            if not city:
                raise ValidationError({'primary_address.city_id': 'City not found in reference data'})
            if city.country_id != country.code:
                raise ValidationError({'primary_address.city_id': 'City does not belong to selected country'})
        else:
            city = City.objects.filter(name=city_name, country=country).first()
            if not city:
                raise ValidationError({'primary_address.city': 'City not found in reference data'})

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
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]

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
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload_file = request.FILES.get('file')
        supplier_id = request.data.get('supplier_id')
        if not upload_file:
            return Response({'detail': 'File is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not supplier_id:
            return Response({'detail': 'supplier_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_csv_upload(upload_file)
        except DjangoValidationError as exc:
            return Response({'detail': '; '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

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


def clone_quote(original_quote, user):
    """
    Clone a quote with all its versions, lines, and totals.
    Only allowed for DRAFT quotes.
    """
    if original_quote.status != Quote.Status.DRAFT:
        raise ValidationError(f'Cannot clone quote with status "{original_quote.status}". Only DRAFT quotes can be cloned.')

    # Create new quote
    cloned_quote = Quote.objects.create(
        customer=original_quote.customer,
        contact=original_quote.contact,
        opportunity=original_quote.opportunity,
        mode=original_quote.mode,
        service_scope=original_quote.service_scope,
        shipment_type=original_quote.shipment_type,
        origin_location=original_quote.origin_location,
        destination_location=original_quote.destination_location,
        payment_term=original_quote.payment_term,
        buy_currency=original_quote.buy_currency,
        agent=original_quote.agent,
        carrier=original_quote.carrier,
        status=Quote.Status.DRAFT,
        created_by=user,
        request_details_json=original_quote.request_details_json.copy() if original_quote.request_details_json else {}
    )

    # Copy all versions
    for original_version in original_quote.versions.all():
        new_version = QuoteVersion.objects.create(
            quote=cloned_quote,
            version_number=original_version.version_number,
            payload_json=original_version.payload_json,
            policy=original_version.policy,
            fx_snapshot=original_version.fx_snapshot,
            status=original_version.status,
            reason=original_version.reason,
            created_by=user,
            engine_version=original_version.engine_version
        )

        # Copy all lines for this version
        for original_line in original_version.lines.all():
            QuoteLine.objects.create(
                quote_version=new_version,
                service_component=original_line.service_component,
                cost_pgk=original_line.cost_pgk,
                cost_fcy=original_line.cost_fcy,
                cost_fcy_currency=original_line.cost_fcy_currency,
                sell_pgk=original_line.sell_pgk,
                sell_pgk_incl_gst=original_line.sell_pgk_incl_gst,
                sell_fcy=original_line.sell_fcy,
                sell_fcy_incl_gst=original_line.sell_fcy_incl_gst,
                sell_fcy_currency=original_line.sell_fcy_currency,
                exchange_rate=original_line.exchange_rate,
                cost_source=original_line.cost_source,
                cost_source_description=original_line.cost_source_description,
                is_rate_missing=original_line.is_rate_missing,
                leg=original_line.leg,
                bucket=original_line.bucket,
                gst_category=original_line.gst_category,
                gst_rate=original_line.gst_rate,
                gst_amount=original_line.gst_amount,
                product_code=original_line.product_code,
                component=original_line.component,
                basis=original_line.basis,
                rule_family=original_line.rule_family,
                service_family=original_line.service_family,
                unit_type=original_line.unit_type,
                rate=original_line.rate,
                rate_source=original_line.rate_source,
                canonical_cost_source=original_line.canonical_cost_source,
                is_spot_sourced=original_line.is_spot_sourced,
                is_manual_override=original_line.is_manual_override,
                calculation_notes=original_line.calculation_notes,
            )

        # Copy totals for this version
        original_totals = getattr(original_version, 'totals', None)
        if original_totals:
            QuoteTotal.objects.create(
                quote_version=new_version,
                total_cost_pgk=original_totals.total_cost_pgk,
                total_sell_pgk=original_totals.total_sell_pgk,
                total_sell_pgk_incl_gst=original_totals.total_sell_pgk_incl_gst,
                total_sell_fcy=original_totals.total_sell_fcy,
                total_sell_fcy_incl_gst=original_totals.total_sell_fcy_incl_gst,
                total_sell_fcy_currency=original_totals.total_sell_fcy_currency,
                has_missing_rates=original_totals.has_missing_rates,
                notes=original_totals.notes,
                engine_version=original_totals.engine_version,
                service_notes=original_totals.service_notes,
                customer_notes=original_totals.customer_notes,
                internal_notes=original_totals.internal_notes,
                warnings_json=original_totals.warnings_json,
                audit_metadata_json=original_totals.audit_metadata_json,
            )

    # Update the latest version reference
    latest_version = cloned_quote.versions.order_by('-version_number').first()
    cloned_quote.latest_version = latest_version
    cloned_quote.save(update_fields=['latest_version'])

    return cloned_quote


def create_quote_version(quote, payload, user):
    """
    Create a new version of a quote based on the given payload.
    This function creates a new version by re-running the calculation with the new payload.
    """
    from quotes.models import QuoteVersion
    from django.utils import timezone

    latest_version = quote.versions.order_by('-version_number').first()
    new_version_number = (latest_version.version_number if latest_version else 0) + 1

    # Create new version with the new payload
    new_version = QuoteVersion.objects.create(
        quote=quote,
        version_number=new_version_number,
        payload_json=payload,
        policy={},  # Default empty policy
        fx_snapshot={},  # Default empty fx snapshot
        status=Quote.Status.DRAFT,  # Default to draft
        reason="Manual version created",
        created_by=user,
        engine_version='V4'  # Default to V4
    )

    # Update the latest version reference
    quote.latest_version = new_version
    quote.save(update_fields=['latest_version'])

    return new_version


class QuotePDFAPIView(APIView):
    """
    GET: Generate and return a PDF for a quote.

    Returns:
    - PDF binary with appropriate headers for download
    - Includes DRAFT watermark for non-finalized quotes
    """
    permission_classes = [QuoteAccessPermission]  # Same as view quote permission

    def get(self, request, quote_id):
        from django.http import HttpResponse
        from quotes.pdf_service import generate_quote_pdf, QuotePDFGenerationError

        # Get quote to validate access and get quote number
        # SECURITY FIX: Enforce IDOR protection
        quote = get_quote_for_user(request.user, quote_id)

        try:
            # Optional: Allow specifying version number via query param
            version_number = request.query_params.get('version')
            if version_number:
                try:
                    version_number = int(version_number)
                except ValueError:
                    return Response(
                        {'detail': 'Invalid version number'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if not quote.versions.filter(version_number=version_number).exists():
                    return Response(
                        {'detail': 'Quote version not found.'},
                        status=status.HTTP_404_NOT_FOUND
                    )

            summary_param = request.query_params.get('summary', '')
            summary_only = str(summary_param).lower() in ['1', 'true', 'yes']

            # Generate PDF
            pdf_bytes = generate_quote_pdf(str(quote_id), version_number, summary_only=summary_only)

            # Build filename
            suffix = "-summary" if summary_only else ""
            filename = f"{quote.quote_number}{suffix}.pdf"

            # Return PDF response
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = len(pdf_bytes)

            logger.info(f"PDF downloaded for quote {quote.quote_number} by {request.user}")
            return response

        except QuotePDFGenerationError as e:
            logger.error(f"PDF generation failed for quote {quote_id}: {e}")
            return Response(
                {'detail': 'Quote PDF generation failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception:
            # Catch any unexpected errors and log them
            logger.exception(f"Unexpected error generating PDF for quote {quote_id}")
            return Response(
                {'detail': 'Quote PDF generation failed.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )