# backend/quotes/pdf_service.py
"""
PDF Generation Service for Quote Export using fpdf2

Generates professional PDF quotes using pure Python fpdf2 library.
Clean table-style layout matching customer requirements.
"""

import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import timezone

from fpdf import FPDF

from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from .public_links import build_public_quote_url

logger = logging.getLogger(__name__)


class QuotePDFGenerationError(Exception):
    """Raised when PDF generation fails."""
    pass


def format_currency(amount) -> str:
    """Format currency amount with thousand separators."""
    if amount is None:
        return "0.00"
    try:
        return f"{float(amount):,.2f}"
    except (ValueError, TypeError):
        return "0.00"


class QuotePDF(FPDF):
    """Custom PDF class for quote generation."""
    
    def __init__(self, quote, show_watermark=False):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.quote = quote
        self.show_watermark = show_watermark
        self.set_auto_page_break(auto=True, margin=15)
        
        # Colors
        self.dark_blue = (15, 42, 86)  # #0F2A56
        self.red = (215, 25, 32)  # #D71920
        self.gray = (71, 85, 105)  # #475569
        self.light_gray = (241, 245, 249)  # #F1F5F9
        self.white = (255, 255, 255)
        self.light_border = (203, 213, 225)  # #CBD5E1
    
    def header(self):
        """Draw DRAFT watermark if needed."""
        if self.show_watermark:
            self.set_font('Helvetica', 'B', 80)
            self.set_text_color(200, 200, 200)
            self.rotate(45, self.w / 2, self.h / 2)
            self.text(60, 140, 'DRAFT')
            self.rotate(0)
            self.set_text_color(0, 0, 0)


def generate_quote_pdf(
    quote_id: str,
    version_number: Optional[int] = None,
    summary_only: bool = False,
) -> bytes:
    """Generate a PDF for the specified quote using fpdf2."""
    try:
        # Fetch quote with related data
        quote = Quote.objects.select_related(
            'customer', 'contact', 'origin_location', 'destination_location'
        ).get(id=quote_id)
        
        # Get the version to display
        if version_number:
            version = quote.versions.filter(version_number=version_number).first()
        else:
            version = quote.versions.order_by('-version_number').first()
        
        if not version:
            raise QuotePDFGenerationError("No version found for this quote")
        
        # Get data
        origin_code, origin_name = _extract_location_info(quote, 'origin')
        destination_code, destination_name = _extract_location_info(quote, 'destination')
        charge_buckets = _get_charge_buckets(version)
        totals = _get_totals(version)
        cargo_type = _get_cargo_type(quote, version)
        chargeable_weight = _get_chargeable_weight(quote, version)
        
        # Determine if watermark should be shown
        show_watermark = quote.status in ['DRAFT', 'INCOMPLETE']
        
        logger.info(f"Generating PDF for quote {quote.quote_number}")
        
        # Create PDF
        pdf = QuotePDF(quote, show_watermark)
        pdf.add_page()
        
        # Build PDF sections
        _build_header(pdf, quote)
        _build_divider_bar(pdf)  # Dark blue horizontal divider
        _build_customer_section(pdf, quote)
        _build_shipment_bar(pdf, quote, cargo_type, origin_code, origin_name, 
                           destination_code, destination_name, chargeable_weight)
        _build_pricing_section(pdf, quote, charge_buckets)
        _build_totals_section(pdf, quote, totals)
        _build_footer(pdf, quote, version)
        
        # Generate bytes
        pdf_output = pdf.output()
        pdf_bytes = bytes(pdf_output)
        
        logger.info(f"Generated PDF for quote {quote.quote_number} ({len(pdf_bytes)} bytes)")
        return pdf_bytes
        
    except Quote.DoesNotExist:
        raise
    except QuotePDFGenerationError:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate PDF for quote {quote_id}")
        raise QuotePDFGenerationError(f"PDF generation failed: {str(e)}")


def _build_header(pdf: QuotePDF, quote):
    """Build header with logo anchored at the very top, quote info to the right."""
    # LOGO - anchored at absolute top of page
    logo_y = 10  # Start 10mm from top margin
    logo_path = _get_logo_path()
    
    # Cropped logo is 608x205 pixels (aspect ratio ~3:1)
    # At 55mm width, height will be ~18.5mm
    logo_width = 55
    logo_height = 19  # Approximate height based on aspect ratio
    
    if logo_path:
        # Only specify width - FPDF will calculate height to maintain aspect ratio
        pdf.image(logo_path, x=15, y=logo_y, w=logo_width)
    else:
        # Fallback text logo
        pdf.set_font('Helvetica', 'B', 24)
        pdf.set_text_color(*pdf.dark_blue)
        pdf.text(15, logo_y + 10, 'EFM')
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(*pdf.red)
        pdf.text(47, logo_y + 10, 'EXPRESS')
        pdf.text(47, logo_y + 14, 'AIR CARGO')
    
    # Quote number & status (right side, aligned with top of logo)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(*pdf.dark_blue)
    pdf.set_xy(200, logo_y)
    pdf.cell(0, 10, quote.quote_number, align='R')
    
    # Dates
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(200, logo_y + 10)
    date_text = f"Created {quote.created_at.strftime('%d %b %Y')} | Valid until {quote.valid_until.strftime('%d %b %Y')}"
    pdf.cell(0, 5, date_text, align='R')
    
    # Status
    pdf.set_font('Helvetica', 'B', 9)
    if quote.status in ['DRAFT', 'INCOMPLETE']:
        pdf.set_text_color(217, 119, 6)
    else:
        pdf.set_text_color(5, 150, 105)
    pdf.set_xy(200, logo_y + 16)
    pdf.cell(0, 5, quote.status.upper(), align='R')
    
    # Set Y position below the header for next section
    # Add more space before the divider and customer section
    pdf.set_y(logo_y + logo_height + 10)


def _build_divider_bar(pdf: QuotePDF):
    """Build a dark blue horizontal divider bar."""
    start_y = pdf.get_y()
    
    # Draw a dark blue horizontal bar matching the shipment bar
    # Width matches shipment bar: 65+65+65+72 = 267mm
    # Height matches the CARGO TYPE header row: 7mm
    bar_width = 267
    bar_height = 7  # Same height as CARGO TYPE header row
    pdf.set_fill_color(*pdf.dark_blue)
    pdf.rect(x=15, y=start_y, w=bar_width, h=bar_height, style='F')
    
    # Add some spacing after the divider
    pdf.set_y(start_y + bar_height + 3)


def _build_shipment_bar(pdf: QuotePDF, quote, cargo_type, origin_code, origin_name, 
                        dest_code, dest_name, chargeable_weight):
    """Build the shipment info bar - table style header with dark blue labels."""
    start_y = pdf.get_y()
    col_widths = [65, 65, 65, 72]  # CARGO TYPE, ORIGIN, DESTINATION, Charge Wt
    total_width = sum(col_widths)
    
    # Header row - dark blue background with white text
    pdf.set_fill_color(*pdf.dark_blue)
    pdf.set_text_color(*pdf.white)
    pdf.set_font('Helvetica', 'B', 8)
    
    x = 15
    pdf.set_xy(x, start_y)
    pdf.cell(col_widths[0], 7, 'CARGO TYPE:', border=0, fill=True)
    x += col_widths[0]
    pdf.set_xy(x, start_y)
    pdf.cell(col_widths[1], 7, 'ORIGIN:', border=0, fill=True)
    x += col_widths[1]
    pdf.set_xy(x, start_y)
    pdf.cell(col_widths[2], 7, 'DESTINATION:', border=0, fill=True)
    x += col_widths[2]
    pdf.set_xy(x, start_y)
    pdf.cell(col_widths[3], 7, 'Charge Wt (kgs):', border=0, align='R', fill=True)
    
    # Data row - light gray background with dark text
    pdf.set_fill_color(*pdf.light_gray)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font('Helvetica', '', 10)
    
    data_y = start_y + 7
    x = 15
    pdf.set_xy(x, data_y)
    pdf.cell(col_widths[0], 8, cargo_type, border=0, fill=True)
    x += col_widths[0]
    
    # Origin with country code
    origin_display = f"{_extract_city_name(origin_name)}, AU"
    pdf.set_xy(x, data_y)
    pdf.cell(col_widths[1], 8, origin_display, border=0, fill=True)
    x += col_widths[1]
    
    # Destination with country code
    dest_display = f"{_extract_city_name(dest_name)}, PG"
    pdf.set_xy(x, data_y)
    pdf.cell(col_widths[2], 8, dest_display, border=0, fill=True)
    x += col_widths[2]
    
    pdf.set_xy(x, data_y)
    pdf.cell(col_widths[3], 8, str(chargeable_weight), border=0, align='R', fill=True)
    
    pdf.set_y(data_y + 12)


def _build_customer_section(pdf: QuotePDF, quote):
    """Build customer info section."""
    start_y = pdf.get_y()
    
    # Customer box
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(*pdf.light_border)
    pdf.set_line_width(0.3)
    pdf.rect(15, start_y, 130, 18, 'DF')
    
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(18, start_y + 2)
    pdf.cell(0, 4, 'CUSTOMER')
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(18, start_y + 7)
    pdf.cell(0, 5, quote.customer.name[:40])
    
    if quote.contact:
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(*pdf.gray)
        pdf.set_xy(18, start_y + 12)
        pdf.cell(0, 4, f"Attn: {quote.contact.first_name} {quote.contact.last_name}"[:45])
    
    # Shipment details box
    pdf.rect(150, start_y, 132, 18, 'DF')
    
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(153, start_y + 2)
    pdf.cell(0, 4, 'SHIPMENT DETAILS')
    
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(153, start_y + 7)
    pdf.cell(60, 4, f"Mode: {quote.mode}")
    pdf.set_xy(213, start_y + 7)
    pdf.cell(60, 4, f"Service: {quote.shipment_type}")
    pdf.set_xy(153, start_y + 12)
    pdf.cell(60, 4, f"Payment: {quote.payment_term}")
    pdf.set_xy(213, start_y + 12)
    incoterm = quote.incoterm if quote.incoterm else "N/A"
    pdf.cell(60, 4, f"Incoterm: {incoterm}")
    
    pdf.set_y(start_y + 22)


def _build_pricing_section(pdf: QuotePDF, quote, charge_buckets):
    """Build pricing summary table."""
    start_y = pdf.get_y()
    
    # Section header
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(15, start_y)
    pdf.cell(0, 6, 'PRICING SUMMARY')
    
    # Header underline
    pdf.set_draw_color(*pdf.dark_blue)
    pdf.set_line_width(0.5)
    pdf.line(15, start_y + 7, 282, start_y + 7)
    
    # Table header
    pdf.set_fill_color(*pdf.light_gray)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(15, start_y + 9)
    pdf.cell(200, 6, 'Charge Category', border=0, fill=True)
    pdf.cell(67, 6, f'Subtotal ({quote.output_currency})', border=0, align='R', fill=True)
    
    # Table rows
    pdf.set_draw_color(*pdf.light_border)
    pdf.set_line_width(0.1)
    row_y = start_y + 16
    
    for bucket in charge_buckets:
        if bucket['subtotal'] > 0:
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(15, 23, 42)
            pdf.set_xy(15, row_y)
            pdf.cell(200, 6, bucket['name'])
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(67, 6, format_currency(bucket['subtotal']), align='R')
            pdf.line(15, row_y + 6, 282, row_y + 6)
            row_y += 7
    
    if not charge_buckets or all(b['subtotal'] == 0 for b in charge_buckets):
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(*pdf.gray)
        pdf.set_xy(15, row_y)
        pdf.cell(0, 6, 'No charges available')
        row_y += 7
    
    pdf.set_y(row_y + 3)


def _build_totals_section(pdf: QuotePDF, quote, totals):
    """Build clean right-aligned totals section."""
    start_y = pdf.get_y()
    
    # Light background
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(*pdf.dark_blue)
    pdf.set_line_width(0.3)
    pdf.rect(15, start_y, 267, 20, 'DF')
    
    # Right-aligned totals
    right_x = 275
    
    # Total (Excl. GST)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(180, start_y + 2)
    pdf.cell(50, 5, 'Total (Excl. GST):', align='R')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(230, start_y + 2)
    pdf.cell(right_x - 230, 5, f"{quote.output_currency} {format_currency(totals['sell_excl_gst'])}", align='R')
    
    # GST
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(180, start_y + 7)
    pdf.cell(50, 5, 'GST (10%):', align='R')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(230, start_y + 7)
    pdf.cell(right_x - 230, 5, f"{quote.output_currency} {format_currency(totals['gst'])}", align='R')
    
    # Grand Total
    pdf.set_draw_color(*pdf.dark_blue)
    pdf.line(200, start_y + 12, right_x + 5, start_y + 12)
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(*pdf.dark_blue)
    pdf.set_xy(180, start_y + 13)
    pdf.cell(50, 6, 'GRAND TOTAL:', align='R')
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_xy(230, start_y + 13)
    pdf.cell(right_x - 230, 6, f"{quote.output_currency} {format_currency(totals['sell_incl_gst'])}", align='R')
    
    pdf.set_y(start_y + 24)


def _build_footer(pdf: QuotePDF, quote, version):
    """Build footer with contact info and terms."""
    start_y = pdf.get_y()
    
    # Separator
    pdf.set_draw_color(*pdf.light_border)
    pdf.set_line_width(0.3)
    pdf.line(15, start_y, 282, start_y)
    
    # Company contact (left)
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(15, start_y + 3)
    pdf.cell(0, 4, 'EFM EXPRESS AIR CARGO')
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(*pdf.gray)
    pdf.set_xy(15, start_y + 7)
    pdf.cell(0, 4, 'Phone: +675 325 8500 | Email: quotes@efmexpress.com')
    pdf.set_xy(15, start_y + 11)
    pdf.cell(0, 4, 'PO Box 1791, Port Moresby, Papua New Guinea')
    
    # Terms (right)
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(140, start_y + 3)
    pdf.cell(0, 4, 'TERMS & CONDITIONS')
    
    pdf.set_font('Helvetica', '', 6)
    pdf.set_text_color(*pdf.gray)
    terms = [
        f"Valid until {quote.valid_until.strftime('%d %b %Y')}",
        "Space subject to availability",
        "Final charges based on actual/volumetric weight",
    ]
    terms_y = start_y + 7
    for term in terms:
        pdf.set_xy(140, terms_y)
        pdf.cell(0, 3, f"- {term}")
        terms_y += 3
    
    # Generated timestamp
    pdf.set_font('Helvetica', 'I', 6)
    pdf.set_text_color(148, 163, 184)
    pdf.set_xy(15, start_y + 18)
    pdf.cell(0, 4, f"Generated by RateEngine v{version.version_number} | {timezone.now().strftime('%d %b %Y %H:%M')}")


# Helper functions

def _extract_city_name(full_name: str) -> str:
    """Extract city name by removing airport suffixes."""
    if not full_name:
        return ''
    
    suffixes = [
        ' International Airport', ' Intl Airport', ' International',
        ' Jacksons Intl', ' Jacksons Int', ' Intl', ' Int', ' Airport',
    ]
    
    result = full_name
    for suffix in suffixes:
        if result.lower().endswith(suffix.lower()):
            result = result[:-len(suffix)]
            break
    
    return result.strip()


def _extract_location_info(quote, location_type: str) -> tuple[str, str]:
    """Extract location code and name from quote."""
    location_field = f"{location_type}_location"
    location = getattr(quote, location_field, None)
    
    if location:
        if hasattr(location, 'iata_code') and location.iata_code:
            code = location.iata_code
        elif hasattr(location, 'code') and location.code:
            code = location.code
        else:
            code = str(location)[:3].upper()
        name = getattr(location, 'name', str(location))
        return code, name
    
    if location_type == 'origin':
        return 'ORG', 'Origin'
    return 'DST', 'Destination'


def _get_charge_buckets(version) -> list[dict]:
    """Get charge summary grouped by leg."""
    buckets = {
        'Origin Charges': Decimal('0'),
        'International Freight': Decimal('0'),
        'Destination Charges': Decimal('0'),
    }
    
    for line in version.lines.select_related('service_component').all():
        leg = None
        if line.service_component:
            leg = getattr(line.service_component, 'leg', None)
        if not leg:
            leg = line.leg
        
        if leg == 'ORIGIN':
            bucket_name = 'Origin Charges'
        elif leg == 'MAIN':
            bucket_name = 'International Freight'
        elif leg == 'DESTINATION':
            bucket_name = 'Destination Charges'
        else:
            bucket_name = 'International Freight'
        
        buckets[bucket_name] += line.sell_pgk or Decimal('0')
    
    result = []
    for name in ['Origin Charges', 'International Freight', 'Destination Charges']:
        if buckets[name] > 0:
            result.append({'name': name, 'subtotal': buckets[name]})
    
    return result


def _get_totals(version) -> dict:
    """Get totals for the version."""
    try:
        total = version.totals
        if total:
            sell_excl = total.total_sell_pgk or Decimal('0')
            sell_incl = total.total_sell_pgk_incl_gst or Decimal('0')
            gst = sell_incl - sell_excl
            return {
                'sell_excl_gst': sell_excl,
                'gst': gst,
                'sell_incl_gst': sell_incl,
            }
    except Exception:
        pass
    
    sell_total = sum((line.sell_pgk or Decimal('0')) for line in version.lines.all())
    gst = sell_total * Decimal('0.10')
    return {'sell_excl_gst': sell_total, 'gst': gst, 'sell_incl_gst': sell_total + gst}


def _get_cargo_type(quote, version) -> str:
    """Get cargo type from quote data."""
    quote_input = getattr(quote, 'quote_input', None) or {}
    if isinstance(quote_input, dict):
        cargo_type = quote_input.get('cargo_type')
        if cargo_type:
            return cargo_type
    
    cargo_data = getattr(version, 'cargo_data', None) or {}
    if isinstance(cargo_data, dict):
        cargo_type = cargo_data.get('cargo_type')
        if cargo_type:
            return cargo_type
    
    is_dg = getattr(quote, 'is_dangerous_goods', False)
    if is_dg:
        return 'Dangerous Goods'
    
    return 'General Cargo'


def _get_chargeable_weight(quote, version) -> str:
    """Get chargeable weight from quote data.
    
    Chargeable weight is the maximum of:
    - Gross weight (sum of all packages)
    - Volumetric weight (L * W * H / 6000 for each package, summed)
    """
    try:
        # Try request_details_json first
        request_details = getattr(quote, 'request_details_json', None) or {}
        if isinstance(request_details, dict):
            dimensions = request_details.get('dimensions', [])
            if dimensions and isinstance(dimensions, list):
                total_gross = 0.0
                total_volumetric = 0.0
                
                for dim in dimensions:
                    if not isinstance(dim, dict):
                        continue
                    
                    # Get gross weight
                    gross = dim.get('gross_weight_kg')
                    if gross:
                        try:
                            total_gross += float(gross)
                        except (ValueError, TypeError):
                            pass
                    
                    # Calculate volumetric weight (L * W * H / 6000)
                    try:
                        length = float(dim.get('length_cm', 0))
                        width = float(dim.get('width_cm', 0))
                        height = float(dim.get('height_cm', 0))
                        pieces = int(dim.get('pieces', 1))
                        vol_weight = (length * width * height / 6000) * pieces
                        total_volumetric += vol_weight
                    except (ValueError, TypeError):
                        pass
                
                # Chargeable weight is the maximum of gross and volumetric
                chargeable = max(total_gross, total_volumetric)
                if chargeable > 0:
                    return f"{chargeable:.1f}"
        
        # Try payload_json on version
        payload = getattr(version, 'payload_json', None) or {}
        if isinstance(payload, dict):
            dimensions = payload.get('dimensions', [])
            if dimensions and isinstance(dimensions, list):
                total_gross = sum(
                    float(d.get('gross_weight_kg', 0)) 
                    for d in dimensions if isinstance(d, dict)
                )
                if total_gross > 0:
                    return f"{total_gross:.1f}"
        
        # Fallback: check quote_input and cargo_data
        quote_input = getattr(quote, 'quote_input', None) or {}
        if isinstance(quote_input, dict):
            cw = quote_input.get('chargeable_weight')
            if cw:
                return str(cw)
        
        cargo_data = getattr(version, 'cargo_data', None) or {}
        if isinstance(cargo_data, dict):
            cw = cargo_data.get('chargeable_weight')
            if cw:
                return str(cw)
    
    except Exception as e:
        logger.warning(f"Error calculating chargeable weight: {e}")
    
    return '0.0'


def _get_logo_path() -> Optional[str]:
    """Get logo file path."""
    try:
        # Try the cropped logo first (no padding, proper aspect ratio)
        logo_path = finders.find('images/efm_logo_cropped.png')
        if logo_path and Path(logo_path).exists():
            return logo_path
        
        # Fallback to cropped logo in static folder
        fallback = Path(settings.BASE_DIR) / 'static' / 'images' / 'efm_logo_cropped.png'
        if fallback.exists():
            return str(fallback)
        
        # Second fallback - original new logo
        new_logo = finders.find('images/efm_logo_new.png')
        if new_logo and Path(new_logo).exists():
            return new_logo
        
        # Old logo fallback
        old_logo = finders.find('images/eac_logo.png')
        if old_logo and Path(old_logo).exists():
            return old_logo
    except Exception as e:
        logger.warning(f"Could not load logo: {e}")
    return None
