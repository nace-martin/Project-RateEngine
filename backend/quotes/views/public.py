import re
from decimal import Decimal
from uuid import UUID

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from quotes.branding import get_quote_branding
from quotes.buckets import (
    PUBLIC_CHARGE_SUBCATEGORY_ORDER,
    classify_quote_line_public_subcategory,
    resolve_quote_line_leg,
    resolve_quote_line_sell_value,
    should_display_quote_line,
    should_include_quote_line_in_subtotal,
)
from parties.models import Contact
from quotes.models import Quote, QuoteLine, QuoteTotal
from quotes.public_links import get_public_quote_id_from_token

VALID_SERVICE_SCOPES = {"D2D", "D2A", "A2D", "A2A", "P2P"}


class PublicQuoteRateThrottle(ScopedRateThrottle):
    scope = "public_quote"


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


def _iter_payloads(quote: Quote, version):
    for payload in (getattr(version, "payload_json", None), quote.request_details_json):
        if isinstance(payload, dict):
            yield payload


def _coerce_uuid(value) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _payload_get(payload: dict, *path):
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _extract_payload_contact_id(payload: dict) -> UUID | None:
    for candidate in (
        payload.get("contact_id"),
        _payload_get(payload, "quote_request", "contact_id"),
        _payload_get(payload, "customer", "contact_id"),
    ):
        contact_id = _coerce_uuid(candidate)
        if contact_id:
            return contact_id
    return None


def _resolve_public_contact(quote: Quote, version) -> Contact | None:
    if quote.contact_id:
        return quote.contact

    for payload in _iter_payloads(quote, version):
        contact_id = _extract_payload_contact_id(payload)
        if not contact_id:
            continue
        contact = Contact.objects.filter(id=contact_id, company_id=quote.customer_id).first()
        if contact:
            return contact

    return None


def _format_contact_name(contact: Contact | None) -> str | None:
    if not contact:
        return None
    name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
    return name or contact.email or None


def _to_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _extract_piece_list(payload: dict) -> list[dict]:
    candidates = (
        _payload_get(payload, "shipment", "pieces"),
        payload.get("pieces"),
        payload.get("dimensions"),
        _payload_get(payload, "cargo", "pieces"),
    )
    for candidate in candidates:
        if isinstance(candidate, list):
            return [piece for piece in candidate if isinstance(piece, dict)]
    return []


def _piece_value(piece: dict, *keys) -> Decimal | None:
    for key in keys:
        value = _to_decimal(piece.get(key))
        if value is not None:
            return value
    return None


def _calculate_chargeable_weight_from_pieces(pieces: list[dict]) -> Decimal | None:
    if not pieces:
        return None

    gross_total = Decimal("0")
    volumetric_total = Decimal("0")
    has_weight = False
    has_dimensions = False

    for piece in pieces:
        count = _piece_value(piece, "pieces", "quantity", "qty") or Decimal("1")
        gross = _piece_value(piece, "gross_weight_kg", "weight_kg", "weight")
        if gross is not None:
            gross_total += gross * count
            has_weight = True

        length = _piece_value(piece, "length_cm", "length")
        width = _piece_value(piece, "width_cm", "width")
        height = _piece_value(piece, "height_cm", "height")
        if length is not None and width is not None and height is not None and length > 0 and width > 0 and height > 0:
            volumetric_total += (length * width * height * count) / Decimal("6000")
            has_dimensions = True

    if has_weight or has_dimensions:
        return max(gross_total, volumetric_total)
    return None


def _resolve_chargeable_weight(quote: Quote, version) -> Decimal | None:
    chargeable_paths = (
        ("chargeable_weight_kg",),
        ("chargeable_weight",),
        ("total_chargeable_weight_kg",),
        ("shipment", "chargeable_weight_kg"),
        ("shipment", "chargeable_weight"),
    )
    gross_weight_fallback_paths = (
        ("total_weight_kg",),
        ("shipment", "total_weight_kg"),
        ("shipment_context", "total_weight_kg"),
    )

    for payload in _iter_payloads(quote, version):
        for path in chargeable_paths:
            value = _to_decimal(_payload_get(payload, *path))
            if value is not None:
                return value
        piece_weight = _calculate_chargeable_weight_from_pieces(_extract_piece_list(payload))
        if piece_weight is not None:
            return piece_weight
        for path in gross_weight_fallback_paths:
            value = _to_decimal(_payload_get(payload, *path))
            if value is not None:
                return value

    return None


def _resolve_line_sell_value(line, quote_currency: str) -> Decimal:
    return resolve_quote_line_sell_value(line, quote_currency)


def _should_include_public_line(line, quote_currency: str) -> bool:
    return should_display_quote_line(line, quote_currency)


def _public_group_line_sort_key(group_name: str, line_data: dict) -> tuple[int, str]:
    description = str(line_data.get("description") or "").lower()
    priority = 10

    if group_name == "Customs / Regulatory":
        if "customs" in description or "clearance" in description:
            priority = 0
        elif "agency fee" in description:
            priority = 1
    elif group_name == "Local Transport / Cartage":
        if "cartage fuel surcharge" in description:
            priority = 1
        elif "fuel surcharge" in description:
            priority = 2
        else:
            priority = 0

    return priority, description


def _build_public_charge_buckets(lines, currency: str) -> list[dict]:
    buckets = {
        'ORIGIN': {'name': 'Origin Charges', 'lines': [], 'groups': {}, 'subtotal': Decimal('0')},
        'MAIN': {'name': 'Freight', 'lines': [], 'groups': {}, 'subtotal': Decimal('0')},
        'DESTINATION': {'name': 'Destination Charges', 'lines': [], 'groups': {}, 'subtotal': Decimal('0')},
    }

    for line in lines:
        if not _should_include_public_line(line, currency):
            continue
        leg = resolve_quote_line_leg(line)
        if line.service_component:
            description = line.cost_source_description or line.service_component.description
        else:
            description = line.cost_source_description or 'Manual Charge'
        source = line.cost_source or ''

        if leg not in buckets:
            leg = 'MAIN'
        sell_value = _resolve_line_sell_value(line, currency)
        
        pcode = getattr(line, "product_code", None) or (line.service_component.code if line.service_component else None) or ""
        tax_code = getattr(line, "gst_category", None) or (line.service_component.tax_code if line.service_component else None) or "GST"
        line_data = {
            'description': description,
            'source': source[:20] if source else '-',
            'sell': _format_decimal(sell_value),
            'is_informational': line.is_informational,
            'product_code': pcode,
            'currency': (line.sell_fcy_currency or currency or "PGK").upper(),
            'tax_code': tax_code,
            '_sell_decimal': sell_value,
            '_grouping_product_code': getattr(line, "product_code", None) or "",
            '_include_in_subtotal': should_include_quote_line_in_subtotal(line, currency),
        }
        subcategory = classify_quote_line_public_subcategory(line)
        line_data['subcategory'] = subcategory

        buckets[leg]['lines'].append(line_data)
        if should_include_quote_line_in_subtotal(line, currency):
            buckets[leg]['subtotal'] += sell_value
            group = buckets[leg]['groups'].setdefault(
                subcategory,
                {'name': subcategory, 'lines': [], 'subtotal': Decimal('0')},
            )
            group['subtotal'] += sell_value
            group['lines'].append(line_data)
        else:
            group = buckets[leg]['groups'].setdefault(
                subcategory,
                {'name': subcategory, 'lines': [], 'subtotal': Decimal('0')},
            )
            group['lines'].append(line_data)

    # Perform grouping of compatible lines per subcategory
    for leg in buckets:
        for subcategory in buckets[leg]['groups']:
            group = buckets[leg]['groups'][subcategory]
            
            orig_lines = group['lines']
            grouped_lines_map = {}
            other_lines = []
            
            for ld in orig_lines:
                pc = ld.get('_grouping_product_code', '')
                is_subtotal = ld.get('_include_in_subtotal', False)
                if not pc or not is_subtotal:
                    other_lines.append(ld)
                    continue
                
                key = (pc, ld.get('currency'), ld.get('tax_code'))
                if key not in grouped_lines_map:
                    grouped_lines_map[key] = {
                        **ld,
                        '_original': [ld]
                    }
                else:
                    grouped_lines_map[key]['_original'].append(ld)
            
            new_lines = []
            # We preserve the order of the first occurrences
            for ld in orig_lines:
                pc = ld.get('_grouping_product_code', '')
                is_subtotal = ld.get('_include_in_subtotal', False)
                if not pc or not is_subtotal:
                    continue
                key = (pc, ld.get('currency'), ld.get('tax_code'))
                if key in grouped_lines_map:
                    g_ld = grouped_lines_map.pop(key)
                    orig_list = g_ld['_original']
                    if len(orig_list) == 1:
                        g_ld.pop('_original')
                        g_ld.pop('_sell_decimal', None)
                        g_ld.pop('_grouping_product_code', None)
                        g_ld.pop('_include_in_subtotal', None)
                        new_lines.append(g_ld)
                        continue
                    
                    sell_sum = sum(x['_sell_decimal'] for x in orig_list)
                    
                    from pricing_v4.models import ProductCode
                    pcode_obj = ProductCode.objects.filter(code=key[0]).first()
                    if pcode_obj and pcode_obj.description:
                        g_ld['description'] = pcode_obj.description
                    
                    g_ld['sell'] = _format_decimal(sell_sum)
                    g_ld['is_grouped'] = True
                    g_ld['grouped_source_count'] = len(orig_list)
                    g_ld.pop('_original')
                    g_ld.pop('_sell_decimal', None)
                    g_ld.pop('_grouping_product_code', None)
                    g_ld.pop('_include_in_subtotal', None)
                    new_lines.append(g_ld)
            
            # Add back items that didn't have a product code or were excluded
            for ld in other_lines:
                ld.pop('_sell_decimal', None)
                ld.pop('_grouping_product_code', None)
                ld.pop('_include_in_subtotal', None)
                new_lines.append(ld)
                
            group['lines'] = new_lines

    response_buckets = []
    for bucket in buckets.values():
        if not bucket['lines']:
            continue

        groups = []
        bucket_lines = []
        for group_name in PUBLIC_CHARGE_SUBCATEGORY_ORDER:
            group = bucket['groups'].get(group_name)
            if not group:
                continue
            sorted_lines = sorted(group['lines'], key=lambda line: _public_group_line_sort_key(group_name, line))
            bucket_lines.extend(sorted_lines)
            groups.append(
                {
                    'name': group['name'],
                    'lines': sorted_lines,
                    'subtotal': _format_decimal(group['subtotal']),
                }
            )

        response_buckets.append(
            {
                'name': bucket['name'],
                'lines': bucket_lines,
                'groups': groups,
                'subtotal': _format_decimal(bucket['subtotal']),
            }
        )

    return response_buckets


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
    throttle_classes = [PublicQuoteRateThrottle]

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
        ).order_by('id')

        totals = QuoteTotal.objects.filter(quote_version=version).first()
        currency = quote.output_currency or 'PGK'
        origin_code, origin_name = _parse_location_label(quote.origin_location)
        destination_code, destination_name = _parse_location_label(quote.destination_location)
        resolved_service_scope = _resolve_service_scope(quote, version)
        selected_contact = _resolve_public_contact(quote, version)
        chargeable_weight = _resolve_chargeable_weight(quote, version)
        branding = get_quote_branding(quote, request=request)

        response_data = {
            'quote_number': quote.quote_number,
            'status': quote.status,
            'created_at': quote.created_at.isoformat(),
            'valid_until': quote.valid_until.isoformat() if quote.valid_until else None,
            'customer': {
                'name': quote.customer.name if quote.customer else 'Customer',
                'contact': _format_contact_name(selected_contact),
                'contact_id': str(selected_contact.id) if selected_contact else None,
            },
            'shipment': {
                'mode': quote.mode,
                'direction': quote.shipment_type,
                'service_scope': resolved_service_scope,
                'incoterm': quote.incoterm,
                'payment_term': quote.payment_term,
                'chargeable_weight_kg': _format_decimal(chargeable_weight) if chargeable_weight is not None else None,
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
