from decimal import Decimal, ROUND_HALF_UP

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import Shipment, ShipmentDocument, ShipmentEvent, ShipmentSettings


WEIGHT_DIVISOR = Decimal("6000")


def calculate_piece_metrics(piece_data):
    piece_count = Decimal(str(piece_data.get("piece_count", 0)))
    length_cm = Decimal(str(piece_data.get("length_cm", 0)))
    width_cm = Decimal(str(piece_data.get("width_cm", 0)))
    height_cm = Decimal(str(piece_data.get("height_cm", 0)))
    gross_weight_kg = Decimal(str(piece_data.get("gross_weight_kg", 0)))

    gross_total = piece_count * gross_weight_kg
    volumetric_weight = (piece_count * length_cm * width_cm * height_cm / WEIGHT_DIVISOR).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    chargeable_weight = max(gross_total, volumetric_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return volumetric_weight, chargeable_weight


def sync_location_snapshot(shipment: Shipment) -> Shipment:
    if shipment.origin_location:
        shipment.origin_code = shipment.origin_location.code or ""
        shipment.origin_name = shipment.origin_location.display_name or shipment.origin_location.name or ""
        shipment.origin_country_code = getattr(getattr(shipment.origin_location, "country", None), "code", "") or ""
    if shipment.destination_location:
        shipment.destination_code = shipment.destination_location.code or ""
        shipment.destination_name = shipment.destination_location.display_name or shipment.destination_location.name or ""
        shipment.destination_country_code = getattr(getattr(shipment.destination_location, "country", None), "code", "") or ""
    shipment.save(update_fields=[
        "origin_code",
        "origin_name",
        "origin_country_code",
        "destination_code",
        "destination_name",
        "destination_country_code",
        "updated_at",
    ])
    return shipment


def recalculate_shipment_totals(shipment: Shipment) -> Shipment:
    pieces = list(shipment.pieces.all())
    charges = list(shipment.charges.all())
    shipment.total_pieces = sum(piece.piece_count for piece in pieces)
    shipment.total_gross_weight_kg = sum(
        (Decimal(piece.piece_count) * piece.gross_weight_kg for piece in pieces),
        Decimal("0.00"),
    )
    shipment.total_volumetric_weight_kg = sum((piece.volumetric_weight_kg for piece in pieces), Decimal("0.00"))
    shipment.total_chargeable_weight_kg = sum((piece.chargeable_weight_kg for piece in pieces), Decimal("0.00"))
    shipment.total_charges_amount = sum((charge.amount for charge in charges), Decimal("0.00"))
    shipment.save(update_fields=[
        "total_pieces",
        "total_gross_weight_kg",
        "total_volumetric_weight_kg",
        "total_chargeable_weight_kg",
        "total_charges_amount",
        "updated_at",
    ])
    return shipment


def create_shipment_event(shipment: Shipment, event_type: str, description: str, user=None, metadata=None):
    return ShipmentEvent.objects.create(
        shipment=shipment,
        event_type=event_type,
        description=description,
        created_by=user,
        metadata=metadata or {},
    )


def get_or_create_shipment_settings(organization):
    settings_obj, _ = ShipmentSettings.objects.get_or_create(organization=organization)
    return settings_obj


def generate_connote_number(shipment: Shipment) -> str:
    settings_obj = get_or_create_shipment_settings(shipment.organization)
    shipment_day = shipment.shipment_date or timezone.localdate()
    prefix = f"{settings_obj.connote_station_code}-{settings_obj.connote_mode_code}-{shipment_day.strftime('%Y%m%d')}"
    existing_count = Shipment.objects.filter(
        organization=shipment.organization,
        connote_number__startswith=prefix,
    ).count()
    return f"{prefix}-{existing_count + 1:04d}"


@transaction.atomic
def finalize_shipment(shipment: Shipment, user=None) -> Shipment:
    if shipment.status == Shipment.Status.FINALIZED and shipment.connote_number:
        return shipment

    if not shipment.connote_number:
        shipment.connote_number = generate_connote_number(shipment)
    shipment.status = Shipment.Status.FINALIZED
    shipment.finalized_at = timezone.now()
    shipment.finalized_by = user
    shipment.updated_by = user
    shipment.save(update_fields=["connote_number", "status", "finalized_at", "finalized_by", "updated_by", "updated_at"])
    create_shipment_event(
        shipment,
        ShipmentEvent.EventType.FINALIZED,
        f"Shipment finalized with connote number {shipment.connote_number}.",
        user=user,
    )
    return shipment


@transaction.atomic
def cancel_shipment(shipment: Shipment, reason: str = "", user=None) -> Shipment:
    shipment.status = Shipment.Status.CANCELLED
    shipment.cancelled_reason = reason or ""
    shipment.cancelled_at = timezone.now()
    shipment.updated_by = user
    shipment.save(update_fields=["status", "cancelled_reason", "cancelled_at", "updated_by", "updated_at"])
    create_shipment_event(
        shipment,
        ShipmentEvent.EventType.CANCELLED,
        "Shipment cancelled.",
        user=user,
        metadata={"reason": shipment.cancelled_reason},
    )
    return shipment


@transaction.atomic
def duplicate_shipment(shipment: Shipment, user=None, *, reissue=False) -> Shipment:
    new_shipment = Shipment.objects.create(
        organization=shipment.organization,
        created_by=user,
        updated_by=user,
        shipment_date=timezone.localdate(),
        reference_number=shipment.reference_number,
        shipper_company_name=shipment.shipper_company_name,
        shipper_contact_name=shipment.shipper_contact_name,
        shipper_email=shipment.shipper_email,
        shipper_phone=shipment.shipper_phone,
        shipper_address_line_1=shipment.shipper_address_line_1,
        shipper_address_line_2=shipment.shipper_address_line_2,
        shipper_city=shipment.shipper_city,
        shipper_state=shipment.shipper_state,
        shipper_postal_code=shipment.shipper_postal_code,
        shipper_country_code=shipment.shipper_country_code,
        consignee_company_name=shipment.consignee_company_name,
        consignee_contact_name=shipment.consignee_contact_name,
        consignee_email=shipment.consignee_email,
        consignee_phone=shipment.consignee_phone,
        consignee_address_line_1=shipment.consignee_address_line_1,
        consignee_address_line_2=shipment.consignee_address_line_2,
        consignee_city=shipment.consignee_city,
        consignee_state=shipment.consignee_state,
        consignee_postal_code=shipment.consignee_postal_code,
        consignee_country_code=shipment.consignee_country_code,
        origin_location=shipment.origin_location,
        destination_location=shipment.destination_location,
        service_level=shipment.service_level,
        payment_term=shipment.payment_term,
        cargo_description=shipment.cargo_description,
        is_dangerous_goods=shipment.is_dangerous_goods,
        dangerous_goods_details=shipment.dangerous_goods_details,
        is_perishable=shipment.is_perishable,
        perishable_details=shipment.perishable_details,
        handling_notes=shipment.handling_notes,
        declaration_notes=shipment.declaration_notes,
        declared_value=shipment.declared_value,
        currency=shipment.currency,
        source_shipment=shipment,
        reissued_from=shipment if reissue else None,
    )
    sync_location_snapshot(new_shipment)

    for index, piece in enumerate(shipment.pieces.all(), start=1):
        new_shipment.pieces.create(
            line_number=index,
            piece_count=piece.piece_count,
            package_type=piece.package_type,
            description=piece.description,
            length_cm=piece.length_cm,
            width_cm=piece.width_cm,
            height_cm=piece.height_cm,
            gross_weight_kg=piece.gross_weight_kg,
            volumetric_weight_kg=piece.volumetric_weight_kg,
            chargeable_weight_kg=piece.chargeable_weight_kg,
        )

    for index, charge in enumerate(shipment.charges.all(), start=1):
        new_shipment.charges.create(
            line_number=index,
            charge_type=charge.charge_type,
            description=charge.description,
            amount=charge.amount,
            currency=charge.currency,
            payment_by=charge.payment_by,
            notes=charge.notes,
        )

    recalculate_shipment_totals(new_shipment)
    event_type = ShipmentEvent.EventType.REISSUED if reissue else ShipmentEvent.EventType.DUPLICATED
    event_label = "Shipment reissued into a new draft." if reissue else "Shipment duplicated into a new draft."
    create_shipment_event(
        new_shipment,
        event_type,
        event_label,
        user=user,
        metadata={"source_shipment_id": str(shipment.id)},
    )
    return new_shipment


def persist_generated_pdf(shipment: Shipment, pdf_bytes: bytes, file_name: str, user=None) -> ShipmentDocument:
    document = ShipmentDocument(
        shipment=shipment,
        document_type=ShipmentDocument.DocumentType.CONNOTE_PDF,
        file_name=file_name,
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        created_by=user,
    )
    document.file.save(file_name, ContentFile(pdf_bytes), save=False)
    document.save()
    shipment.last_pdf_generated_at = timezone.now()
    shipment.save(update_fields=["last_pdf_generated_at", "updated_at"])
    create_shipment_event(
        shipment,
        ShipmentEvent.EventType.PDF_GENERATED,
        "Connote PDF generated.",
        user=user,
        metadata={"document_id": str(document.id)},
    )
    return document
