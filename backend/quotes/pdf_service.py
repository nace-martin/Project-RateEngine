# backend/quotes/pdf_service.py
"""
PDF Generation Service for Quote Export

Uses xhtml2pdf to generate professional quote PDFs with:
- Company branding (EFM Express Air Cargo logo)
- Quote details and routing information
- Pricing breakdown by bucket
- Terms & conditions
- DRAFT watermark for non-finalized quotes
"""

import logging
import re
import base64
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from xhtml2pdf import pisa

from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from .public_links import build_public_quote_url

logger = logging.getLogger(__name__)


class QuotePDFGenerationError(Exception):
    """Raised when PDF generation fails."""
    pass


def generate_quote_pdf(
    quote_id: str,
    version_number: Optional[int] = None,
    summary_only: bool = False,
) -> bytes:
    """
    Generate a PDF for the specified quote.
    
    Args:
        quote_id: UUID of the quote
        version_number: Optional specific version number. If None, uses latest version.
        summary_only: If True, generate simplified summary PDF.
        
    Returns:
        PDF file as bytes
        
    Raises:
        Quote.DoesNotExist: If quote not found
        QuotePDFGenerationError: If PDF generation fails
    """
    try:
        quote = Quote.objects.select_related(
            'customer', 'contact', 'origin_location', 'destination_location'
        ).get(id=quote_id)
        
        # Get the requested version or latest
        if version_number:
            version = QuoteVersion.objects.get(quote=quote, version_number=version_number)
        else:
            version = quote.versions.order_by('-version_number').first()
        
        if not version:
            raise QuotePDFGenerationError("Quote has no versions")
        
        # Build context for template
        context = _build_pdf_context(quote, version, summary_only)
        
        # Render HTML
        html_content = render_to_string('quotes/quote_pdf.html', context)
        
        # Generate PDF using xhtml2pdf
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html_content.encode('utf-8')), result)
        
        if pdf.err:
            raise QuotePDFGenerationError(f"PDF generation failed with {pdf.err} errors")
        
        pdf_bytes = result.getvalue()
        
        logger.info(f"Generated PDF for quote {quote.quote_number}")
        return pdf_bytes
        
    except Quote.DoesNotExist:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate PDF for quote {quote_id}")
        raise QuotePDFGenerationError(f"PDF generation failed: {str(e)}")


def _build_pdf_context(quote: Quote, version: QuoteVersion, summary_only: bool) -> dict:
    """Build template context for PDF rendering."""
    
    # Get lines and totals
    lines = QuoteLine.objects.select_related('service_component').filter(
        quote_version=version
    ).order_by('service_component__category', 'id')
    
    try:
        totals = QuoteTotal.objects.get(quote_version=version)
    except QuoteTotal.DoesNotExist:
        totals = None
    
    # Parse origin/destination (simplified - no airport names)
    origin_code, origin_name = _parse_location(quote.origin_location)
    destination_code, destination_name = _parse_location(quote.destination_location)
    
    # Build charge buckets (grouped by leg)
    charge_buckets = _build_charge_buckets(lines, quote.output_currency)
    
    # Calculate totals
    totals_data = _calculate_totals(totals, quote.output_currency)
    
    # Extract cargo details from request JSON if available
    cargo_details = _extract_cargo_details(quote)
    
    # Determine watermark
    show_watermark = quote.status not in [Quote.Status.FINALIZED, Quote.Status.SENT]
    
    # Logo - use absolute path for xhtml2pdf compatibility
    logo_path = _get_logo_path()
    
    return {
        'quote': quote,
        'version': version,
        'origin_code': origin_code,
        'origin_name': origin_name,
        'destination_code': destination_code,
        'destination_name': destination_name,
        'charge_buckets': charge_buckets,
        'totals': totals_data,
        'cargo_details': cargo_details,
        'currency': quote.output_currency,
        'show_watermark': show_watermark,
        'logo_path': logo_path,
        'public_quote_url': build_public_quote_url(str(quote.id)),
        'summary_only': summary_only,
        'generated_at': timezone.now(),
    }


def _parse_location(location) -> tuple[str, str]:
    """Parse location into code and simplified city name (no airport references)."""
    if not location:
        return 'N/A', 'Unknown'
    
    loc_str = str(location)
    
    # Try to find IATA code in parentheses like "Brisbane (BNE), AU"
    match = re.search(r'\(([A-Z]{3})\)', loc_str)
    if match:
        code = match.group(1)
        # Remove code and clean up
        name = re.sub(r'\s*\([A-Z]{3}\)', '', loc_str).strip()
        # Remove country suffix like ", AU"
        name = re.sub(r',\s*[A-Z]{2}$', '', name).strip()
        # Remove airport name suffix
        name = re.sub(r'\s*[-–]\s*.*$', '', name).strip()
        name = re.sub(r'\s+(International|Intl|Airport|Changi|Jacksons|Kingsford Smith).*$', '', name, flags=re.IGNORECASE).strip()
        return code, name if name else code
    
    # If no code found, use first 3 chars or full string
    if len(loc_str) == 3 and loc_str.isupper():
        return loc_str, loc_str
    
    return loc_str[:3].upper() if len(loc_str) >= 3 else loc_str, loc_str


def _build_charge_buckets(lines, currency: str) -> list[dict]:
    """Group charge lines by leg/bucket."""
    
    buckets = {
        'ORIGIN': {'name': 'Origin Charges', 'lines': [], 'subtotal': Decimal('0')},
        'MAIN': {'name': 'Freight', 'lines': [], 'subtotal': Decimal('0')},
        'DESTINATION': {'name': 'Destination Charges', 'lines': [], 'subtotal': Decimal('0')},
    }
    
    for line in lines:
        # Determine bucket from service component
        if line.service_component:
            leg = getattr(line.service_component, 'leg', 'MAIN')
            # Use cost_source_description for actual charge name (e.g., "Customs Clearance")
            description = line.cost_source_description or line.service_component.description
        else:
            leg = 'MAIN'
            description = line.cost_source_description or 'Manual Charge'
        
        # Normalize leg name
        if leg not in buckets:
            leg = 'MAIN'
        
        # Use FCY values if available, else PGK
        if currency != 'PGK' and line.sell_fcy:
            sell = line.sell_fcy
        else:
            sell = line.sell_pgk
        
        line_data = {
            'description': description,
            'sell': sell,
            'is_informational': line.is_informational,
        }
        
        buckets[leg]['lines'].append(line_data)
        
        # Only add to subtotal if not informational
        if not line.is_informational:
            buckets[leg]['subtotal'] += sell or Decimal('0')
    
    # Return buckets in specific order: Origin, Freight, Destination
    ordered_buckets = []
    for key in ['ORIGIN', 'MAIN', 'DESTINATION']:
        if buckets[key]['lines']:
            ordered_buckets.append(buckets[key])
            
    return ordered_buckets


def _calculate_totals(totals: Optional[QuoteTotal], currency: str) -> dict:
    """Calculate totals for display."""
    if not totals:
        return {
            'sell_excl_gst': Decimal('0'),
            'gst': Decimal('0'),
            'sell_incl_gst': Decimal('0'),
            'fcy': None,
            'fcy_currency': None,
            'fcy_amount': None,
        }
    
    # Use FCY values if currency is not PGK
    if currency != 'PGK' and totals.total_sell_fcy:
        sell_excl_gst = totals.total_sell_fcy
        sell_incl_gst = totals.total_sell_fcy_incl_gst
        gst = sell_incl_gst - sell_excl_gst
        
        # PGK as secondary
        fcy = True
        fcy_currency = 'PGK'
        fcy_amount = totals.total_sell_pgk_incl_gst
    else:
        sell_excl_gst = totals.total_sell_pgk
        sell_incl_gst = totals.total_sell_pgk_incl_gst
        gst = sell_incl_gst - sell_excl_gst
        
        # FCY as secondary if available
        if totals.total_sell_fcy and totals.total_sell_fcy_currency != 'PGK':
            fcy = True
            fcy_currency = totals.total_sell_fcy_currency
            fcy_amount = totals.total_sell_fcy_incl_gst
        else:
            fcy = None
            fcy_currency = None
            fcy_amount = None
    
    return {
        'sell_excl_gst': sell_excl_gst,
        'gst': gst,
        'sell_incl_gst': sell_incl_gst,
        'fcy': fcy,
        'fcy_currency': fcy_currency,
        'fcy_amount': fcy_amount,
    }


def _extract_cargo_details(quote: Quote) -> dict:
    """Extract cargo details from quote request JSON."""
    request_data = quote.request_details_json or {}
    
    return {
        'gross_weight': request_data.get('gross_weight_kg'),
        'chargeable_weight': request_data.get('chargeable_weight_kg'),
        'pieces': request_data.get('pieces'),
    }


def _get_logo_path() -> Optional[str]:
    """Get absolute path to company logo for xhtml2pdf."""
    logo_path = Path(settings.BASE_DIR) / 'static' / 'images' / 'efm_logo.png'
    if logo_path.exists():
        return str(logo_path)
    return None
