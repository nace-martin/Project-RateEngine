from decimal import Decimal, ROUND_HALF_UP

from django.core.files.base import ContentFile
from django.db import IntegrityError
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


def get_or_create_shipment_settings(organization, *, for_update: bool = False):
    settings_obj, _ = ShipmentSettings.objects.get_or_create(organization=organization)
    if for_update:
        settings_obj = ShipmentSettings.objects.select_for_update().get(pk=settings_obj.pk)
    return settings_obj


def generate_connote_number(shipment: Shipment) -> str:
    settings_obj = get_or_create_shipment_settings(shipment.organization, for_update=True)
    shipment_day = shipment.shipment_date or timezone.localdate()
    prefix = f"{settings_obj.connote_station_code}-{settings_obj.connote_mode_code}-{shipment_day.strftime('%Y%m%d')}"
    existing_numbers = Shipment.objects.select_for_update().filter(
        organization=shipment.organization,
        connote_number__startswith=prefix,
    ).values_list("connote_number", flat=True)
    next_sequence = 1
    for connote_number in existing_numbers:
        try:
            suffix = int(str(connote_number).rsplit("-", 1)[-1])
        except (TypeError, ValueError):
            continue
        next_sequence = max(next_sequence, suffix + 1)
    return f"{prefix}-{next_sequence:04d}"


@transaction.atomic
def finalize_shipment(shipment: Shipment, user=None) -> Shipment:
    locked_shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
    if locked_shipment.status == Shipment.Status.FINALIZED and locked_shipment.connote_number:
        return locked_shipment

    if locked_shipment.status != Shipment.Status.DRAFT:
        raise ValueError("Only draft shipments can be finalized.")

    if not locked_shipment.connote_number:
        last_error = None
        for _ in range(3):
            locked_shipment.connote_number = generate_connote_number(locked_shipment)
            try:
                locked_shipment.status = Shipment.Status.FINALIZED
                locked_shipment.finalized_at = timezone.now()
                locked_shipment.finalized_by = user
                locked_shipment.updated_by = user
                locked_shipment.save(
                    update_fields=[
                        "connote_number",
                        "status",
                        "finalized_at",
                        "finalized_by",
                        "updated_by",
                        "updated_at",
                    ]
                )
                break
            except IntegrityError as exc:
                last_error = exc
                locked_shipment.connote_number = None
        else:
            raise last_error
    else:
        locked_shipment.status = Shipment.Status.FINALIZED
        locked_shipment.finalized_at = timezone.now()
        locked_shipment.finalized_by = user
        locked_shipment.updated_by = user
        locked_shipment.save(
            update_fields=["status", "finalized_at", "finalized_by", "updated_by", "updated_at"]
        )
    create_shipment_event(
        locked_shipment,
        ShipmentEvent.EventType.FINALIZED,
        f"Shipment finalized with connote number {locked_shipment.connote_number}.",
        user=user,
    )
    return locked_shipment


@transaction.atomic
def cancel_shipment(shipment: Shipment, reason: str = "", user=None) -> Shipment:
    locked_shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
    if locked_shipment.status == Shipment.Status.CANCELLED:
        return locked_shipment
    if locked_shipment.status == Shipment.Status.REISSUED:
        raise ValueError("Reissued shipments cannot be cancelled.")
    if locked_shipment.status not in {Shipment.Status.DRAFT, Shipment.Status.FINALIZED}:
        raise ValueError("Only draft or finalized shipments can be cancelled.")
    if locked_shipment.status == Shipment.Status.FINALIZED and not str(reason or "").strip():
        raise ValueError("Cancellation reason is required for finalized shipments.")

    locked_shipment.status = Shipment.Status.CANCELLED
    locked_shipment.cancelled_reason = reason or ""
    locked_shipment.cancelled_at = timezone.now()
    locked_shipment.updated_by = user
    locked_shipment.save(update_fields=["status", "cancelled_reason", "cancelled_at", "updated_by", "updated_at"])
    create_shipment_event(
        locked_shipment,
        ShipmentEvent.EventType.CANCELLED,
        "Shipment cancelled.",
        user=user,
        metadata={"reason": locked_shipment.cancelled_reason},
    )
    return locked_shipment


@transaction.atomic
def duplicate_shipment(shipment: Shipment, user=None, *, reissue=False) -> Shipment:
    locked_shipment = Shipment.objects.select_for_update().get(pk=shipment.pk)
    if reissue:
        if locked_shipment.status != Shipment.Status.FINALIZED:
            raise ValueError("Only finalized shipments can be reissued.")
    else:
        if locked_shipment.status != Shipment.Status.DRAFT:
            raise ValueError("Only draft shipments can be duplicated directly. Use reissue for finalized shipments.")

    new_shipment = Shipment.objects.create(
        organization=locked_shipment.organization,
        created_by=user,
        updated_by=user,
        shipment_type=locked_shipment.shipment_type,
        branch=locked_shipment.branch,
        shipment_date=timezone.localdate(),
        reference_number=locked_shipment.reference_number,
        shipper_company_name=locked_shipment.shipper_company_name,
        shipper_contact_name=locked_shipment.shipper_contact_name,
        shipper_email=locked_shipment.shipper_email,
        shipper_phone=locked_shipment.shipper_phone,
        shipper_address_line_1=locked_shipment.shipper_address_line_1,
        shipper_address_line_2=locked_shipment.shipper_address_line_2,
        shipper_city=locked_shipment.shipper_city,
        shipper_state=locked_shipment.shipper_state,
        shipper_postal_code=locked_shipment.shipper_postal_code,
        shipper_country_code=locked_shipment.shipper_country_code,
        consignee_company_name=locked_shipment.consignee_company_name,
        consignee_contact_name=locked_shipment.consignee_contact_name,
        consignee_email=locked_shipment.consignee_email,
        consignee_phone=locked_shipment.consignee_phone,
        consignee_address_line_1=locked_shipment.consignee_address_line_1,
        consignee_address_line_2=locked_shipment.consignee_address_line_2,
        consignee_city=locked_shipment.consignee_city,
        consignee_state=locked_shipment.consignee_state,
        consignee_postal_code=locked_shipment.consignee_postal_code,
        consignee_country_code=locked_shipment.consignee_country_code,
        origin_location=locked_shipment.origin_location,
        destination_location=locked_shipment.destination_location,
        cargo_type=locked_shipment.cargo_type,
        service_product=locked_shipment.service_product,
        service_scope=locked_shipment.service_scope,
        payment_term=locked_shipment.payment_term,
        cargo_description=locked_shipment.cargo_description,
        is_dangerous_goods=locked_shipment.is_dangerous_goods,
        dangerous_goods_details=locked_shipment.dangerous_goods_details,
        is_perishable=locked_shipment.is_perishable,
        perishable_details=locked_shipment.perishable_details,
        handling_notes=locked_shipment.handling_notes,
        declaration_notes=locked_shipment.declaration_notes,
        declared_value=locked_shipment.declared_value,
        currency=locked_shipment.currency,
        metadata=locked_shipment.metadata,
        source_shipment=locked_shipment,
        reissued_from=locked_shipment if reissue else None,
    )
    sync_location_snapshot(new_shipment)

    for index, piece in enumerate(locked_shipment.pieces.all(), start=1):
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

    recalculate_shipment_totals(new_shipment)
    event_type = ShipmentEvent.EventType.REISSUED if reissue else ShipmentEvent.EventType.DUPLICATED
    event_label = "Shipment reissued into a new draft." if reissue else "Shipment duplicated into a new draft."
    create_shipment_event(
        new_shipment,
        event_type,
        event_label,
        user=user,
        metadata={"source_shipment_id": str(locked_shipment.id)},
    )
    if reissue:
        locked_shipment.status = Shipment.Status.REISSUED
        locked_shipment.updated_by = user
        locked_shipment.save(update_fields=["status", "updated_by", "updated_at"])
        create_shipment_event(
            locked_shipment,
            ShipmentEvent.EventType.REISSUED,
            f"Shipment reissued into draft {new_shipment.id}.",
            user=user,
            metadata={"reissue_shipment_id": str(new_shipment.id)},
        )
    return new_shipment


def persist_generated_pdf(shipment: Shipment, pdf_bytes: bytes, file_name: str, user=None) -> ShipmentDocument:
    prior_pdf_count = shipment.documents.filter(
        document_type=ShipmentDocument.DocumentType.CONNOTE_PDF
    ).count()
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
    is_reprint = prior_pdf_count > 0
    create_shipment_event(
        shipment,
        ShipmentEvent.EventType.REPRINTED if is_reprint else ShipmentEvent.EventType.PDF_GENERATED,
        "Connote PDF reprinted." if is_reprint else "Connote PDF generated.",
        user=user,
        metadata={
            "document_id": str(document.id),
            "print_sequence": prior_pdf_count + 1,
            "is_reprint": is_reprint,
        },
    )
    return document
