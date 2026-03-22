from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.utils import timezone

from fpdf import FPDF

from .models import Shipment
from .services import get_or_create_shipment_settings


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "replace").decode("latin-1")


def _format_weight(value) -> str:
    return f"{float(value or 0):,.2f} kg"


def _format_money(value, currency: str) -> str:
    return f"{currency} {float(value or 0):,.2f}"


def _build_shipment_record_url(shipment: Shipment) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/shipments/{shipment.id}"


def _build_qr_image(url: str) -> BytesIO:
    import qrcode

    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class ConnotePDF(FPDF):
    def __init__(self, shipment: Shipment):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.shipment = shipment
        self.set_auto_page_break(auto=True, margin=12)


def generate_shipment_pdf(shipment: Shipment) -> bytes:
    settings_obj = get_or_create_shipment_settings(shipment.organization)
    branding = getattr(shipment.organization, "branding", None)
    record_url = _build_shipment_record_url(shipment)
    qr_image = _build_qr_image(record_url)

    pdf = ConnotePDF(shipment)
    pdf.add_page()
    pdf.set_fill_color(15, 42, 86)
    pdf.set_text_color(255, 255, 255)
    pdf.rect(10, 10, 190, 28, style="F")

    if branding and getattr(branding, "logo_primary", None):
        try:
            pdf.image(branding.logo_primary.path, x=14, y=14, w=36)
        except Exception:
            pass

    pdf.set_xy(54, 14)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(92, 7, _clean_text((branding.display_name if branding else "") or "EFM Air Freight"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(54)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(92, 5, "AIR FREIGHT CONNOTE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(54)
    pdf.cell(92, 5, _clean_text(shipment.connote_number or "Draft"), new_x="LMARGIN", new_y="NEXT")

    pdf.image(qr_image, x=170, y=13, w=24, h=24, link=record_url)
    pdf.set_xy(142, 40)
    pdf.set_text_color(71, 85, 105)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(52, 4, _clean_text(f"Shipment Date: {shipment.shipment_date:%d %b %Y}"), align="R", new_x="LMARGIN", new_y="NEXT")

    def party_block(x, values):
        pdf.set_xy(x, 52)
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(203, 213, 225)
        pdf.rect(x, 52, 92, 34, style="DF")
        pdf.set_xy(x + 3, 55)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(86, 5, _clean_text(values[0]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(x + 3)
        pdf.set_font("Helvetica", "", 8)
        for line in values[1:]:
            pdf.multi_cell(86, 4, _clean_text(line))
            pdf.set_x(x + 3)

    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(10, 46)
    pdf.cell(92, 6, "Shipper")
    pdf.set_xy(108, 46)
    pdf.cell(92, 6, "Consignee")
    party_block(
        10,
        [
            shipment.shipper_company_name,
            shipment.shipper_contact_name,
            shipment.shipper_address_line_1,
            " ".join(
                part
                for part in [
                    shipment.shipper_address_line_2,
                    shipment.shipper_city,
                    shipment.shipper_state,
                    shipment.shipper_postal_code,
                ]
                if part
            ).strip(),
            shipment.shipper_country_code,
        ],
    )
    party_block(
        108,
        [
            shipment.consignee_company_name,
            shipment.consignee_contact_name,
            shipment.consignee_address_line_1,
            " ".join(
                part
                for part in [
                    shipment.consignee_address_line_2,
                    shipment.consignee_city,
                    shipment.consignee_state,
                    shipment.consignee_postal_code,
                ]
                if part
            ).strip(),
            shipment.consignee_country_code,
        ],
    )

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(10, 92)
    pdf.cell(190, 6, "Shipment Details")
    pdf.set_fill_color(248, 250, 252)
    pdf.rect(10, 98, 190, 20, style="DF")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(13, 102)
    pdf.cell(60, 4, _clean_text(f"Origin: {shipment.origin_code} {shipment.origin_name}".strip()))
    pdf.set_xy(75, 102)
    pdf.cell(60, 4, _clean_text(f"Destination: {shipment.destination_code} {shipment.destination_name}".strip()))
    pdf.set_xy(137, 102)
    pdf.cell(60, 4, _clean_text(f"Service: {shipment.service_level.title()}"))
    pdf.set_xy(13, 109)
    pdf.cell(60, 4, _clean_text(f"Payment: {shipment.payment_term.replace('_', ' ').title()}"))
    pdf.set_xy(75, 109)
    pdf.cell(60, 4, _clean_text(f"Commodity: {shipment.commodity_description or 'General Cargo'}"))
    pdf.set_xy(137, 109)
    pdf.cell(60, 4, _clean_text(f"Ref: {shipment.reference_number or '-'}"))

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(10, 124)
    pdf.cell(190, 6, "Cargo Details")
    pdf.set_fill_color(15, 42, 86)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(10, 132)
    headers = [("Pieces", 18), ("Type", 28), ("Dims (cm)", 44), ("Gross", 24), ("Volumetric", 30), ("Chargeable", 30), ("Description", 16)]
    for label, width in headers:
        pdf.cell(width, 7, label, border=0, align="C", fill=True)
    pdf.ln(7)
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "", 8)

    for piece in shipment.pieces.all():
        pdf.set_x(10)
        pdf.cell(18, 7, str(piece.piece_count), border=1, align="C")
        pdf.cell(28, 7, _clean_text(piece.package_type or "PCS"), border=1)
        pdf.cell(44, 7, _clean_text(f"{piece.length_cm} x {piece.width_cm} x {piece.height_cm}"), border=1)
        pdf.cell(24, 7, _clean_text(_format_weight(Decimal(piece.piece_count) * piece.gross_weight_kg).replace(" kg", "")), border=1, align="R")
        pdf.cell(30, 7, _clean_text(_format_weight(piece.volumetric_weight_kg).replace(" kg", "")), border=1, align="R")
        pdf.cell(30, 7, _clean_text(_format_weight(piece.chargeable_weight_kg).replace(" kg", "")), border=1, align="R")
        pdf.cell(16, 7, _clean_text((piece.description or "")[:10]), border=1)
        pdf.ln(7)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 6, "Handling / Declaration Notes", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    notes = [
        f"Dangerous Goods: {'Yes' if shipment.is_dangerous_goods else 'No'}",
        f"Perishable: {'Yes' if shipment.is_perishable else 'No'}",
        shipment.dangerous_goods_details,
        shipment.perishable_details,
        shipment.handling_notes,
        shipment.declaration_notes,
    ]
    pdf.multi_cell(190, 4.5, _clean_text("\n".join(line for line in notes if line)))

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 6, "Charges", new_x="LMARGIN", new_y="NEXT")
    charges = list(shipment.charges.all())
    pdf.set_fill_color(248, 250, 252)
    pdf.rect(10, pdf.get_y(), 190, max(12, 8 + (len(charges) * 6)), style="DF")
    y = pdf.get_y() + 2
    for charge in charges:
        pdf.set_xy(13, y)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(120, 5, _clean_text(f"{charge.description} ({charge.payment_by.replace('_', ' ').title()})"))
        pdf.cell(64, 5, _clean_text(_format_money(charge.amount, charge.currency)), align="R")
        y += 6
    if not charges:
        pdf.set_xy(13, y)
        pdf.cell(180, 5, "No charge lines recorded.")

    pdf.set_xy(10, 270)
    pdf.set_draw_color(203, 213, 225)
    pdf.line(10, 270, 200, 270)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(71, 85, 105)
    footer_lines = [
        f"Generated by {getattr(shipment.created_by, 'username', 'system')} on {timezone.now():%d %b %Y %H:%M}",
        settings_obj.default_disclaimer,
        f"Internal record: {record_url}",
    ]
    pdf.set_xy(10, 273)
    pdf.multi_cell(190, 3.6, _clean_text("\n".join(footer_lines)))

    output = pdf.output(dest="S")
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    return output.encode("latin-1")
