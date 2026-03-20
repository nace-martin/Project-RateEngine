import re
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from quotes.branding import get_quote_branding
from quotes.models import Quote, QuoteLine, QuoteTotal
from quotes.public_links import get_public_quote_id_from_token

VALID_SERVICE_SCOPES = {"D2D", "D2A", "A2D", "A2A", "P2P"}


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return format(value, ".2f")


def _parse_location_label(location) -> tuple[str, str]:
    """Parse location into display code/name without dropping airport references."""
    if not location:
        return "N/A", "Unknown"

    code = getattr(location, "code", None)
    name = getattr(location, "name", None)
    if code and name:
        return str(code).upper(), str(name)

    loc_str = str(location).strip()

    # Match "CODE - Name" (Location.__str__).
    if " - " in loc_str:
        left, right = loc_str.split(" - ", 1)
        if len(left) == 3 and left.isalpha():
            return left.upper(), right.strip() or left.upper()

    # Match "Name (CODE)".
    match = re.search(r"\(([A-Z]{3})\)", loc_str)
    if match:
        parsed_code = match.group(1)
        parsed_name = re.sub(r"\s*\([A-Z]{3}\)", "", loc_str).strip()
        return parsed_code, parsed_name or parsed_code

    if len(loc_str) == 3 and loc_str.isalpha():
        return loc_str.upper(), loc_str.upper()

    guessed_code = loc_str[:3].upper() if len(loc_str) >= 3 else loc_str.upper()
    return guessed_code, loc_str


def _normalize_service_scope(raw_value) -> str | None:
    if raw_value is None:
        return None

    value = str(raw_value).strip().upper()
    if not value:
        return None

    if value == "P2P":
        return "A2A"

    return value if value in VALID_SERVICE_SCOPES else None


def _extract_service_scope(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    quote_request = payload.get("quote_request") if isinstance(payload.get("quote_request"), dict) else {}
    shipment = payload.get("shipment") if isinstance(payload.get("shipment"), dict) else {}
    shipment_context = payload.get("shipment_context") if isinstance(payload.get("shipment_context"), dict) else {}

    candidates = [
        payload.get("service_scope"),
        quote_request.get("service_scope"),
        shipment.get("service_scope"),
        shipment_context.get("service_scope"),
    ]

    for candidate in candidates:
        normalized = _normalize_service_scope(candidate)
        if normalized:
            return normalized

    return None


def _resolve_service_scope(quote: Quote, version) -> str | None:
    return (
        _normalize_service_scope(quote.service_scope)
        or _extract_service_scope(getattr(version, "payload_json", None))
        or _extract_service_scope(quote.request_details_json)
    )


def _normalize_bucket(raw_bucket) -> str | None:
    value = str(raw_bucket or "").strip().lower()
    if value == "origin_charges":
        return "ORIGIN"
    if value == "airfreight":
        return "MAIN"
    if value == "destination_charges":
        return "DESTINATION"
    return None


def _normalize_leg(raw_leg) -> str | None:
    value = str(raw_leg or "").strip().upper()
    if value in {"ORIGIN", "DESTINATION"}:
        return value
    if value in {"MAIN", "FREIGHT"}:
        return "MAIN"
    return None


def _resolve_bucket_key(line) -> str:
    """
    Resolve public bucket from persisted quote-line mapping.
    QuoteLine.bucket/leg is authoritative; component metadata is not.
    """
    return _normalize_bucket(getattr(line, "bucket", None)) or _normalize_leg(getattr(line, "leg", None)) or "MAIN"


def _resolve_line_sell_value(line, quote_currency: str) -> Decimal:
    if quote_currency != "PGK":
        line_currency = str(getattr(line, "sell_fcy_currency", "") or "").upper()
        if line_currency == quote_currency and getattr(line, "sell_fcy", None) is not None:
            return line.sell_fcy
    return line.sell_pgk or Decimal("0")


def _should_include_public_line(line, quote_currency: str) -> bool:
    if getattr(line, "is_informational", False):
        return True
    return _resolve_line_sell_value(line, quote_currency) > Decimal("0")


def _build_public_charge_buckets(lines, currency: str) -> list[dict]:
    buckets = {
        'ORIGIN': {'name': 'Origin Charges', 'lines': [], 'subtotal': Decimal('0')},
        'MAIN': {'name': 'Freight', 'lines': [], 'subtotal': Decimal('0')},
        'DESTINATION': {'name': 'Destination Charges', 'lines': [], 'subtotal': Decimal('0')},
    }

    for line in lines:
        if not _should_include_public_line(line, currency):
            continue
        leg = _resolve_bucket_key(line)
        if line.service_component:
            description = line.cost_source_description or line.service_component.description
        else:
            description = line.cost_source_description or 'Manual Charge'
        source = line.cost_source or ''

        if leg not in buckets:
            leg = 'MAIN'
        sell_value = _resolve_line_sell_value(line, currency)
        line_data = {
            'description': description,
            'source': source[:20] if source else '-',
            'sell': _format_decimal(sell_value),
            'is_informational': line.is_informational,
        }

        buckets[leg]['lines'].append(line_data)
        if not line.is_informational:
            buckets[leg]['subtotal'] += sell_value

    return [
        {
            'name': bucket['name'],
            'lines': bucket['lines'],
            'subtotal': _format_decimal(bucket['subtotal']),
        }
        for bucket in buckets.values() if bucket['lines']
    ]


def _calculate_public_totals(totals: QuoteTotal | None, currency: str) -> dict:
    if not totals:
        return {
            'sell_excl_gst': _format_decimal(Decimal('0')),
            'gst': _format_decimal(Decimal('0')),
            'sell_incl_gst': _format_decimal(Decimal('0')),
            'fcy': None,
            'fcy_currency': None,
            'fcy_amount': None,
        }

    if currency != 'PGK' and totals.total_sell_fcy:
        sell_excl_gst = totals.total_sell_fcy
        sell_incl_gst = totals.total_sell_fcy_incl_gst
        gst = sell_incl_gst - sell_excl_gst
        fcy = True
        fcy_currency = 'PGK'
        fcy_amount = totals.total_sell_pgk_incl_gst
    else:
        sell_excl_gst = totals.total_sell_pgk
        sell_incl_gst = totals.total_sell_pgk_incl_gst
        gst = sell_incl_gst - sell_excl_gst
        if totals.total_sell_fcy and totals.total_sell_fcy_currency != 'PGK':
            fcy = True
            fcy_currency = totals.total_sell_fcy_currency
            fcy_amount = totals.total_sell_fcy_incl_gst
        else:
            fcy = None
            fcy_currency = None
            fcy_amount = None

    return {
        'sell_excl_gst': _format_decimal(sell_excl_gst),
        'gst': _format_decimal(gst),
        'sell_incl_gst': _format_decimal(sell_incl_gst),
        'fcy': fcy,
        'fcy_currency': fcy_currency,
        'fcy_amount': _format_decimal(fcy_amount) if fcy_amount is not None else None,
    }


class QuotePublicDetailAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({'detail': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        quote_id = get_public_quote_id_from_token(token)
        if not quote_id:
            return Response({'detail': 'Link expired or invalid.'}, status=status.HTTP_403_FORBIDDEN)

        quote = get_object_or_404(
            Quote.objects.select_related("customer", "contact", "organization", "organization__branding"),
            id=quote_id,
        )
        if quote.status not in [Quote.Status.FINALIZED, Quote.Status.SENT]:
            return Response({'detail': 'Quote is not available for sharing.'}, status=status.HTTP_403_FORBIDDEN)

        version_param = request.query_params.get('version')
        if version_param:
            try:
                version_number = int(version_param)
            except ValueError:
                return Response({'detail': 'Invalid version number'}, status=status.HTTP_400_BAD_REQUEST)

            version = quote.versions.filter(version_number=version_number).first()
            if not version:
                return Response({'detail': 'Quote version not found.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            version = quote.versions.order_by('-version_number').first()
        if not version:
            return Response({'detail': 'Quote has no versions.'}, status=status.HTTP_404_NOT_FOUND)

        lines = QuoteLine.objects.select_related('service_component').filter(
            quote_version=version
        ).order_by('service_component__category', 'id')

        totals = QuoteTotal.objects.filter(quote_version=version).first()
        currency = quote.output_currency or 'PGK'
        origin_code, origin_name = _parse_location_label(quote.origin_location)
        destination_code, destination_name = _parse_location_label(quote.destination_location)
        resolved_service_scope = _resolve_service_scope(quote, version)
        branding = get_quote_branding(quote, request=request)

        response_data = {
            'quote_number': quote.quote_number,
            'status': quote.status,
            'created_at': quote.created_at.isoformat(),
            'valid_until': quote.valid_until.isoformat() if quote.valid_until else None,
            'customer': {
                'name': quote.customer.name if quote.customer else 'Customer',
                'contact': f"{quote.contact.first_name} {quote.contact.last_name}".strip() if quote.contact else None,
            },
            'shipment': {
                'mode': quote.mode,
                'direction': quote.shipment_type,
                'service_scope': resolved_service_scope,
                'incoterm': quote.incoterm,
                'payment_term': quote.payment_term,
            },
            'route': {
                'origin_code': origin_code,
                'origin_name': origin_name,
                'destination_code': destination_code,
                'destination_name': destination_name,
            },
            'branding': {
                'display_name': branding.display_name,
                'support_email': branding.support_email,
                'support_phone': branding.support_phone,
                'website_url': branding.website_url,
                'address_lines': branding.address_lines,
                'public_quote_tagline': branding.public_quote_tagline,
                'primary_color': branding.primary_color,
                'accent_color': branding.accent_color,
                'logo_url': branding.logo_url,
            },
            'currency': currency,
            'totals': _calculate_public_totals(totals, currency),
            'charge_buckets': _build_public_charge_buckets(lines, currency),
        }

        return Response(response_data)
