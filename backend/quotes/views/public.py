import re
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from quotes.models import Quote, QuoteLine, QuoteTotal
from quotes.public_links import get_public_quote_id_from_token

def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return format(value, ".2f")


def _parse_location_label(location) -> tuple[str, str]:
    """Parse location into code and simplified city name (no airport names)."""
    if not location:
        return "N/A", "Unknown"

    loc_str = str(location)
    
    # Try to find IATA code in parentheses like "Brisbane (BNE), AU"
    match = re.search(r'\(([A-Z]{3})\)', loc_str)
    if match:
        code = match.group(1)
        # Remove code and clean up
        name = re.sub(r'\s*\([A-Z]{3}\)', '', loc_str).strip()
        # Remove country suffix like ", AU"
        name = re.sub(r',\s*[A-Z]{2}$', '', name).strip()
        # Remove airport name suffix (after a hyphen or common airport words)
        name = re.sub(r'\s*[-–]\s*.*$', '', name).strip()
        name = re.sub(r'\s+(International|Intl|Airport|Changi|Jacksons|Kingsford Smith).*$', '', name, flags=re.IGNORECASE).strip()
        return code, name if name else code

    if len(loc_str) == 3 and loc_str.isupper():
        return loc_str, loc_str

    return loc_str[:3].upper() if len(loc_str) >= 3 else loc_str, loc_str


def _build_public_charge_buckets(lines, currency: str) -> list[dict]:
    buckets = {
        'ORIGIN': {'name': 'Origin Charges', 'lines': [], 'subtotal': Decimal('0')},
        'MAIN': {'name': 'Freight', 'lines': [], 'subtotal': Decimal('0')},
        'DESTINATION': {'name': 'Destination Charges', 'lines': [], 'subtotal': Decimal('0')},
    }

    for line in lines:
        if line.service_component:
            leg = getattr(line.service_component, 'leg', 'MAIN')
            description = line.cost_source_description or line.service_component.description
            source = line.cost_source or ''
        else:
            leg = 'MAIN'
            description = line.cost_source_description or 'Manual Charge'
            source = ''

        if leg not in buckets:
            leg = 'MAIN'

        if currency != 'PGK' and line.sell_fcy:
            sell = line.sell_fcy
        else:
            sell = line.sell_pgk

        sell_value = sell or Decimal('0')
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

        quote = get_object_or_404(Quote, id=quote_id)
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
                'incoterm': quote.incoterm,
                'payment_term': quote.payment_term,
            },
            'route': {
                'origin_code': origin_code,
                'origin_name': origin_name,
                'destination_code': destination_code,
                'destination_name': destination_name,
            },
            'currency': currency,
            'totals': _calculate_public_totals(totals, currency),
            'charge_buckets': _build_public_charge_buckets(lines, currency),
        }

        return Response(response_data)
