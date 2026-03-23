import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


def shipment_document_upload_to(instance, filename: str) -> str:
    organization = getattr(instance.shipment, "organization", None)
    org_slug = getattr(organization, "slug", None) or "default"
    return f"shipments/{org_slug}/{instance.shipment_id}/{filename}"


class ShipmentAddressBookEntry(models.Model):
    class PartyRole(models.TextChoices):
        SHIPPER = "SHIPPER", "Shipper"
        CONSIGNEE = "CONSIGNEE", "Consignee"
        BOTH = "BOTH", "Both"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "parties.Organization",
        on_delete=models.CASCADE,
        related_name="shipment_address_book_entries",
    )
    company = models.ForeignKey(
        "parties.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipment_address_book_entries",
    )
    contact = models.ForeignKey(
        "parties.Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipment_address_book_entries",
    )
    label = models.CharField(max_length=120)
    party_role = models.CharField(max_length=12, choices=PartyRole.choices, default=PartyRole.BOTH)
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=120, blank=True, default="")
    postal_code = models.CharField(max_length=32, blank=True, default="")
    country_code = models.CharField(max_length=2)
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label", "company_name"]

    def __str__(self) -> str:
        return f"{self.label} ({self.company_name})"


class ShipmentTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "parties.Organization",
        on_delete=models.CASCADE,
        related_name="shipment_templates",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    shipper_defaults = models.JSONField(default=dict, blank=True)
    consignee_defaults = models.JSONField(default=dict, blank=True)
    shipment_defaults = models.JSONField(default=dict, blank=True)
    pieces_defaults = models.JSONField(default=list, blank=True)
    charges_defaults = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("organization", "name")

    def __str__(self) -> str:
        return self.name


class ShipmentSettings(models.Model):
    organization = models.OneToOneField(
        "parties.Organization",
        on_delete=models.CASCADE,
        related_name="shipment_settings",
    )
    connote_station_code = models.CharField(max_length=8, default="POM")
    connote_mode_code = models.CharField(max_length=8, default="AF")
    default_disclaimer = models.TextField(
        default="Prepared for internal operational use. Verify final cargo and compliance details before uplift."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Shipment settings for {self.organization.name}"


class Shipment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        FINALIZED = "FINALIZED", "Finalized"
        CANCELLED = "CANCELLED", "Cancelled"
        REISSUED = "REISSUED", "Reissued"

    class PaymentTerm(models.TextChoices):
        PREPAID = "PREPAID", "Prepaid"
        COLLECT = "COLLECT", "Collect"
        THIRD_PARTY = "THIRD_PARTY", "Third Party"

    class CargoType(models.TextChoices):
        GENERAL_CARGO = "GENERAL_CARGO", "General Cargo"
        VALUABLE_CARGO = "VALUABLE_CARGO", "Valuable Cargo"
        PERISHABLE = "PERISHABLE", "Perishable"
        LIVE_ANIMALS = "LIVE_ANIMALS", "Live Animals"
        DANGEROUS_GOODS = "DANGEROUS_GOODS", "Dangerous Goods"

    class ServiceProduct(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        EXPRESS = "EXPRESS", "Express"
        DOCUMENTS = "DOCUMENTS", "Documents"
        SMALL_PARCELS = "SMALL_PARCELS", "Small Parcels"
        CHARTER = "CHARTER", "Charter"

    class ServiceScope(models.TextChoices):
        DOOR_TO_DOOR = "D2D", "Door-to-Door"
        DOOR_TO_AIRPORT = "D2A", "Door-to-Airport"
        AIRPORT_TO_DOOR = "A2D", "Airport-to-Door"
        AIRPORT_TO_AIRPORT = "A2A", "Airport-to-Airport"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "parties.Organization",
        on_delete=models.CASCADE,
        related_name="shipments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_updated",
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_finalized",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    connote_number = models.CharField(max_length=32, unique=True, null=True, blank=True, db_index=True)
    shipment_date = models.DateField()
    reference_number = models.CharField(max_length=120, blank=True, default="")

    shipper_company_name = models.CharField(max_length=255)
    shipper_contact_name = models.CharField(max_length=255, blank=True, default="")
    shipper_email = models.EmailField(blank=True, default="")
    shipper_phone = models.CharField(max_length=64, blank=True, default="")
    shipper_address_line_1 = models.CharField(max_length=255)
    shipper_address_line_2 = models.CharField(max_length=255, blank=True, default="")
    shipper_city = models.CharField(max_length=120)
    shipper_state = models.CharField(max_length=120, blank=True, default="")
    shipper_postal_code = models.CharField(max_length=32, blank=True, default="")
    shipper_country_code = models.CharField(max_length=2)

    consignee_company_name = models.CharField(max_length=255)
    consignee_contact_name = models.CharField(max_length=255, blank=True, default="")
    consignee_email = models.EmailField(blank=True, default="")
    consignee_phone = models.CharField(max_length=64, blank=True, default="")
    consignee_address_line_1 = models.CharField(max_length=255)
    consignee_address_line_2 = models.CharField(max_length=255, blank=True, default="")
    consignee_city = models.CharField(max_length=120)
    consignee_state = models.CharField(max_length=120, blank=True, default="")
    consignee_postal_code = models.CharField(max_length=32, blank=True, default="")
    consignee_country_code = models.CharField(max_length=2)

    origin_location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="origin_shipments",
    )
    destination_location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="destination_shipments",
    )
    origin_code = models.CharField(max_length=16, blank=True, default="")
    origin_name = models.CharField(max_length=255, blank=True, default="")
    origin_country_code = models.CharField(max_length=2, blank=True, default="")
    destination_code = models.CharField(max_length=16, blank=True, default="")
    destination_name = models.CharField(max_length=255, blank=True, default="")
    destination_country_code = models.CharField(max_length=2, blank=True, default="")

    cargo_type = models.CharField(max_length=24, choices=CargoType.choices, default=CargoType.GENERAL_CARGO)
    service_product = models.CharField(max_length=20, choices=ServiceProduct.choices, default=ServiceProduct.STANDARD)
    service_scope = models.CharField(max_length=3, choices=ServiceScope.choices, default=ServiceScope.AIRPORT_TO_AIRPORT)
    payment_term = models.CharField(max_length=16, choices=PaymentTerm.choices, default=PaymentTerm.PREPAID)
    cargo_description = models.CharField(max_length=255, blank=True, default="")
    is_dangerous_goods = models.BooleanField(default=False)
    dangerous_goods_details = models.TextField(blank=True, default="")
    is_perishable = models.BooleanField(default=False)
    perishable_details = models.TextField(blank=True, default="")
    handling_notes = models.TextField(blank=True, default="")
    declaration_notes = models.TextField(blank=True, default="")
    declared_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="PGK")

    total_pieces = models.PositiveIntegerField(default=0)
    total_gross_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_volumetric_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_chargeable_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_charges_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    source_shipment = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicate_shipments",
    )
    reissued_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reissued_shipments",
    )
    cancelled_reason = models.TextField(blank=True, default="")
    finalized_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    last_pdf_generated_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-shipment_date", "-created_at"]

    def __str__(self) -> str:
        return self.connote_number or f"Draft Shipment {self.id}"


class ShipmentPiece(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="pieces")
    line_number = models.PositiveIntegerField(default=1)
    piece_count = models.PositiveIntegerField(default=1)
    package_type = models.CharField(max_length=64, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    length_cm = models.DecimalField(max_digits=10, decimal_places=2)
    width_cm = models.DecimalField(max_digits=10, decimal_places=2)
    height_cm = models.DecimalField(max_digits=10, decimal_places=2)
    gross_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    volumetric_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    chargeable_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["line_number", "id"]

    def __str__(self) -> str:
        return f"{self.piece_count} x {self.package_type or 'Pieces'}"


class ShipmentCharge(models.Model):
    class ChargeType(models.TextChoices):
        FREIGHT = "FREIGHT", "Freight"
        HANDLING = "HANDLING", "Handling"
        SECURITY = "SECURITY", "Security"
        DOCUMENTATION = "DOCUMENTATION", "Documentation"
        FUEL = "FUEL", "Fuel"
        OTHER = "OTHER", "Other"

    class PaymentBy(models.TextChoices):
        SHIPPER = "SHIPPER", "Shipper"
        CONSIGNEE = "CONSIGNEE", "Consignee"
        THIRD_PARTY = "THIRD_PARTY", "Third Party"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="charges")
    line_number = models.PositiveIntegerField(default=1)
    charge_type = models.CharField(max_length=20, choices=ChargeType.choices, default=ChargeType.OTHER)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="PGK")
    payment_by = models.CharField(max_length=16, choices=PaymentBy.choices, default=PaymentBy.SHIPPER)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["line_number", "id"]

    def __str__(self) -> str:
        return f"{self.description} {self.amount} {self.currency}"


class ShipmentDocument(models.Model):
    class DocumentType(models.TextChoices):
        CONNOTE_PDF = "CONNOTE_PDF", "Connote PDF"
        ATTACHMENT = "ATTACHMENT", "Attachment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=20, choices=DocumentType.choices)
    file = models.FileField(upload_to=shipment_document_upload_to, max_length=255)
    file_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=120, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ShipmentEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED = "UPDATED", "Updated"
        FINALIZED = "FINALIZED", "Finalized"
        PDF_GENERATED = "PDF_GENERATED", "PDF Generated"
        DUPLICATED = "DUPLICATED", "Duplicated"
        CANCELLED = "CANCELLED", "Cancelled"
        REISSUED = "REISSUED", "Reissued"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
