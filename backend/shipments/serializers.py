from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers

from core.models import Location
from parties.models import Company, Contact

from .models import (
    Shipment,
    ShipmentAddressBookEntry,
    ShipmentCharge,
    ShipmentDocument,
    ShipmentEvent,
    ShipmentPiece,
    ShipmentSettings,
    ShipmentTemplate,
)
from .services import calculate_piece_metrics, create_shipment_event, recalculate_shipment_totals, sync_location_snapshot


DOMESTIC_COUNTRY_CODE = "PG"
ALLOWED_NEW_SHIPMENT_TYPES = {
    Shipment.ShipmentType.DOMESTIC,
    Shipment.ShipmentType.EXPORT,
}
ALLOWED_PAYMENT_TERMS = {
    Shipment.PaymentTerm.PREPAID,
    Shipment.PaymentTerm.COLLECT,
}
METADATA_TEXT_FIELDS = (
    "booking_reference",
    "flight_reference",
    "export_reference",
    "invoice_reference",
    "permit_reference",
    "customs_notes",
)


def _is_domestic_png_route(origin, destination) -> bool:
    if not origin or not destination:
        return False
    origin_country = getattr(getattr(origin, "country", None), "code", "") or ""
    destination_country = getattr(getattr(destination, "country", None), "code", "") or ""
    return origin_country.upper() == DOMESTIC_COUNTRY_CODE and destination_country.upper() == DOMESTIC_COUNTRY_CODE


def _is_export_route(origin, destination) -> bool:
    if not origin or not destination:
        return False
    origin_country = getattr(getattr(origin, "country", None), "code", "") or ""
    destination_country = getattr(getattr(destination, "country", None), "code", "") or ""
    return origin_country.upper() == DOMESTIC_COUNTRY_CODE and destination_country.upper() != DOMESTIC_COUNTRY_CODE


class ShipmentAddressBookEntrySerializer(serializers.ModelSerializer):
    company_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(Q(is_customer=True) | Q(company_type="CUSTOMER")).order_by("name"),
        source="company",
        allow_null=True,
        required=False,
    )
    contact_id = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.filter(is_active=True).select_related("company").order_by("last_name", "first_name"),
        source="contact",
        allow_null=True,
        required=False,
    )

    class Meta:
        model = ShipmentAddressBookEntry
        fields = [
            "id",
            "company_id",
            "contact_id",
            "label",
            "party_role",
            "company_name",
            "contact_name",
            "email",
            "phone",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "postal_code",
            "country_code",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        company = attrs.get("company", getattr(instance, "company", None))
        contact = attrs.get("contact", getattr(instance, "contact", None))

        if contact and company and contact.company_id != company.id:
            raise serializers.ValidationError({"contact_id": "Selected contact does not belong to the selected company."})

        return attrs

    def create(self, validated_data):
        hydrated_data = self._hydrate_linked_snapshot(validated_data)
        return super().create(hydrated_data)

    def update(self, instance, validated_data):
        hydrated_data = self._hydrate_linked_snapshot(validated_data, instance=instance)
        return super().update(instance, hydrated_data)

    def _hydrate_linked_snapshot(self, validated_data, instance=None):
        company = validated_data.get("company", getattr(instance, "company", None))
        contact = validated_data.get("contact", getattr(instance, "contact", None))

        if contact and not company:
            company = contact.company
            validated_data["company"] = company

        snapshot = {}

        if company:
            address = (
                company.addresses.select_related("city__country", "country")
                .order_by("-is_primary", "id")
                .first()
            )
            snapshot["company_name"] = company.name
            if address:
                snapshot["address_line_1"] = address.address_line_1
                snapshot["address_line_2"] = address.address_line_2
                snapshot["city"] = address.city.name if address.city else ""
                snapshot["state"] = ""
                snapshot["postal_code"] = address.postal_code
                snapshot["country_code"] = (
                    address.country.code
                    if address.country
                    else (address.city.country.code if address.city and address.city.country else "")
                )

        if contact:
            snapshot["contact_name"] = f"{contact.first_name} {contact.last_name}".strip()
            snapshot["email"] = contact.email
            snapshot["phone"] = contact.phone

        for field, value in snapshot.items():
            if value is not None:
                validated_data[field] = value

        return validated_data


class ShipmentTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentTemplate
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "shipper_defaults",
            "consignee_defaults",
            "shipment_defaults",
            "pieces_defaults",
            "charges_defaults",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ShipmentSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentSettings
        fields = ["connote_station_code", "connote_mode_code", "default_disclaimer", "updated_at"]
        read_only_fields = ["updated_at"]


class ShipmentPieceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentPiece
        fields = [
            "id",
            "line_number",
            "piece_count",
            "package_type",
            "description",
            "length_cm",
            "width_cm",
            "height_cm",
            "gross_weight_kg",
            "volumetric_weight_kg",
            "chargeable_weight_kg",
        ]
        read_only_fields = ["id", "volumetric_weight_kg", "chargeable_weight_kg"]

    def validate(self, attrs):
        for field in ("piece_count", "length_cm", "width_cm", "height_cm", "gross_weight_kg"):
            value = attrs.get(field)
            if value is None or value <= 0:
                raise serializers.ValidationError({field: "Value must be greater than 0."})
        return attrs


class ShipmentChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentCharge
        fields = [
            "id",
            "line_number",
            "charge_type",
            "description",
            "amount",
            "currency",
            "payment_by",
            "notes",
        ]
        read_only_fields = ["id"]


class ShipmentDocumentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ShipmentDocument
        fields = [
            "id",
            "document_type",
            "file_name",
            "content_type",
            "size_bytes",
            "created_at",
            "download_url",
        ]

    def get_download_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return None
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class ShipmentEventSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = ShipmentEvent
        fields = [
            "id",
            "event_type",
            "description",
            "metadata",
            "created_by_username",
            "created_at",
        ]


class ShipmentSerializer(serializers.ModelSerializer):
    pieces = ShipmentPieceSerializer(many=True, required=False)
    charges = ShipmentChargeSerializer(many=True, required=False)
    documents = ShipmentDocumentSerializer(many=True, read_only=True)
    events = ShipmentEventSerializer(many=True, read_only=True)
    booking_reference = serializers.CharField(required=False, allow_blank=True)
    flight_reference = serializers.CharField(required=False, allow_blank=True)
    export_reference = serializers.CharField(required=False, allow_blank=True)
    invoice_reference = serializers.CharField(required=False, allow_blank=True)
    permit_reference = serializers.CharField(required=False, allow_blank=True)
    customs_notes = serializers.CharField(required=False, allow_blank=True)
    origin_location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="origin_location",
        allow_null=True,
        required=False,
    )
    destination_location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source="destination_location",
        allow_null=True,
        required=False,
    )
    origin_location_display = serializers.CharField(source="origin_location.display_name", read_only=True)
    destination_location_display = serializers.CharField(source="destination_location.display_name", read_only=True)
    source_shipment_id = serializers.UUIDField(read_only=True)
    reissued_from_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "status",
            "connote_number",
            "shipment_type",
            "branch",
            "shipment_date",
            "reference_number",
            "booking_reference",
            "flight_reference",
            "shipper_company_name",
            "shipper_contact_name",
            "shipper_email",
            "shipper_phone",
            "shipper_address_line_1",
            "shipper_address_line_2",
            "shipper_city",
            "shipper_state",
            "shipper_postal_code",
            "shipper_country_code",
            "consignee_company_name",
            "consignee_contact_name",
            "consignee_email",
            "consignee_phone",
            "consignee_address_line_1",
            "consignee_address_line_2",
            "consignee_city",
            "consignee_state",
            "consignee_postal_code",
            "consignee_country_code",
            "origin_location_id",
            "destination_location_id",
            "origin_location_display",
            "destination_location_display",
            "origin_code",
            "origin_name",
            "origin_country_code",
            "destination_code",
            "destination_name",
            "destination_country_code",
            "cargo_type",
            "service_product",
            "service_scope",
            "payment_term",
            "export_reference",
            "invoice_reference",
            "permit_reference",
            "cargo_description",
            "is_dangerous_goods",
            "dangerous_goods_details",
            "is_perishable",
            "perishable_details",
            "handling_notes",
            "declaration_notes",
            "customs_notes",
            "declared_value",
            "currency",
            "total_pieces",
            "total_gross_weight_kg",
            "total_volumetric_weight_kg",
            "total_chargeable_weight_kg",
            "total_charges_amount",
            "pieces",
            "charges",
            "documents",
            "events",
            "source_shipment_id",
            "reissued_from_id",
            "cancelled_reason",
            "finalized_at",
            "cancelled_at",
            "last_pdf_generated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "connote_number",
            "origin_code",
            "origin_name",
            "origin_country_code",
            "destination_code",
            "destination_name",
            "destination_country_code",
            "total_pieces",
            "total_gross_weight_kg",
            "total_volumetric_weight_kg",
            "total_chargeable_weight_kg",
            "total_charges_amount",
            "documents",
            "events",
            "source_shipment_id",
            "reissued_from_id",
            "finalized_at",
            "cancelled_at",
            "last_pdf_generated_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "branch": {"required": False, "allow_blank": True},
            "reference_number": {"required": False, "allow_blank": True},
            "shipper_company_name": {"required": False, "allow_blank": True},
            "shipper_contact_name": {"required": False, "allow_blank": True},
            "shipper_email": {"required": False, "allow_blank": True},
            "shipper_phone": {"required": False, "allow_blank": True},
            "shipper_address_line_1": {"required": False, "allow_blank": True},
            "shipper_address_line_2": {"required": False, "allow_blank": True},
            "shipper_city": {"required": False, "allow_blank": True},
            "shipper_state": {"required": False, "allow_blank": True},
            "shipper_postal_code": {"required": False, "allow_blank": True},
            "shipper_country_code": {"required": False, "allow_blank": True},
            "consignee_company_name": {"required": False, "allow_blank": True},
            "consignee_contact_name": {"required": False, "allow_blank": True},
            "consignee_email": {"required": False, "allow_blank": True},
            "consignee_phone": {"required": False, "allow_blank": True},
            "consignee_address_line_1": {"required": False, "allow_blank": True},
            "consignee_address_line_2": {"required": False, "allow_blank": True},
            "consignee_city": {"required": False, "allow_blank": True},
            "consignee_state": {"required": False, "allow_blank": True},
            "consignee_postal_code": {"required": False, "allow_blank": True},
            "consignee_country_code": {"required": False, "allow_blank": True},
            "cargo_description": {"required": False, "allow_blank": True},
            "dangerous_goods_details": {"required": False, "allow_blank": True},
            "perishable_details": {"required": False, "allow_blank": True},
            "handling_notes": {"required": False, "allow_blank": True},
            "declaration_notes": {"required": False, "allow_blank": True},
            "currency": {"required": False, "allow_blank": True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        metadata = instance.metadata or {}
        for field in METADATA_TEXT_FIELDS:
            data[field] = metadata.get(field, "")
        return data

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        if instance and instance.status == Shipment.Status.FINALIZED and not self.context.get("allow_finalized_finalize"):
            raise serializers.ValidationError("Finalized shipments are locked and cannot be edited.")

        for_finalize = bool(self.context.get("for_finalize"))
        pieces = attrs.get("pieces")

        raw_shipper_name = attrs.get("shipper_company_name", getattr(instance, "shipper_company_name", ""))
        raw_consignee_name = attrs.get("consignee_company_name", getattr(instance, "consignee_company_name", ""))
        raw_shipper_address = attrs.get("shipper_address_line_1", getattr(instance, "shipper_address_line_1", ""))
        raw_consignee_address = attrs.get("consignee_address_line_1", getattr(instance, "consignee_address_line_1", ""))
        raw_shipper_city = attrs.get("shipper_city", getattr(instance, "shipper_city", ""))
        raw_consignee_city = attrs.get("consignee_city", getattr(instance, "consignee_city", ""))
        raw_shipper_country = attrs.get("shipper_country_code", getattr(instance, "shipper_country_code", ""))
        raw_consignee_country = attrs.get("consignee_country_code", getattr(instance, "consignee_country_code", ""))

        origin = attrs.get("origin_location", getattr(instance, "origin_location", None))
        destination = attrs.get("destination_location", getattr(instance, "destination_location", None))
        shipment_type = attrs.get(
            "shipment_type",
            getattr(instance, "shipment_type", Shipment.ShipmentType.DOMESTIC),
        )
        branch = str(attrs.get("branch", getattr(instance, "branch", "")) or "").strip()
        payment_term = attrs.get(
            "payment_term",
            getattr(instance, "payment_term", Shipment.PaymentTerm.PREPAID),
        )
        cargo_type = attrs.get("cargo_type", getattr(instance, "cargo_type", Shipment.CargoType.GENERAL_CARGO))
        dg_details = attrs.get("dangerous_goods_details", getattr(instance, "dangerous_goods_details", ""))
        perishable_details = attrs.get("perishable_details", getattr(instance, "perishable_details", ""))

        allowed_shipment_types = set(ALLOWED_NEW_SHIPMENT_TYPES)
        allowed_payment_terms = set(ALLOWED_PAYMENT_TERMS)
        if instance is not None:
            allowed_shipment_types.add(getattr(instance, "shipment_type", Shipment.ShipmentType.DOMESTIC))
            allowed_payment_terms.add(getattr(instance, "payment_term", Shipment.PaymentTerm.PREPAID))

        if shipment_type not in allowed_shipment_types:
            raise serializers.ValidationError({"shipment_type": "Shipment type must be Domestic or Export."})

        if payment_term not in allowed_payment_terms:
            raise serializers.ValidationError({"payment_term": "Payment type must be Prepaid or Collect."})

        if origin and destination:
            if shipment_type == Shipment.ShipmentType.DOMESTIC and not _is_domestic_png_route(origin, destination):
                raise serializers.ValidationError({"shipment_type": "Domestic shipments must stay within Papua New Guinea."})
            if shipment_type == Shipment.ShipmentType.EXPORT and not _is_export_route(origin, destination):
                raise serializers.ValidationError({
                    "shipment_type": "Export shipments must depart Papua New Guinea for an overseas destination."
                })

        if for_finalize:
            if pieces is not None and len(pieces) == 0:
                raise serializers.ValidationError({"pieces": "At least one cargo piece is required."})
            if not branch:
                raise serializers.ValidationError({"branch": "Branch is required."})
            if not raw_shipper_name or not raw_shipper_address or not raw_shipper_city or not raw_shipper_country:
                raise serializers.ValidationError("Shipper details are mandatory.")
            if not raw_consignee_name or not raw_consignee_address or not raw_consignee_city or not raw_consignee_country:
                raise serializers.ValidationError("Consignee details are mandatory.")
            if not origin or not destination:
                raise serializers.ValidationError("Origin and destination are mandatory.")
            if pieces is None and instance is not None and not instance.pieces.exists():
                raise serializers.ValidationError({"pieces": "At least one cargo piece is required."})
            if instance is None and (not pieces or len(pieces) == 0):
                raise serializers.ValidationError({"pieces": "At least one cargo piece is required."})
            if cargo_type == Shipment.CargoType.DANGEROUS_GOODS and not str(dg_details).strip():
                raise serializers.ValidationError({"dangerous_goods_details": "Dangerous goods details are required."})
            if cargo_type == Shipment.CargoType.PERISHABLE and not str(perishable_details).strip():
                raise serializers.ValidationError({"perishable_details": "Perishable handling details are required."})

        return attrs

    def create(self, validated_data):
        pieces_data = validated_data.pop("pieces", [])
        charges_data = validated_data.pop("charges", [])
        request = self.context.get("request")
        user = getattr(request, "user", None)
        organization = getattr(user, "organization", None)
        validated_data = self._extract_metadata_fields(validated_data)
        validated_data, charges_data = self._apply_business_rules(validated_data, charges_data)

        shipment = Shipment.objects.create(
            organization=organization,
            created_by=user,
            updated_by=user,
            **validated_data,
        )
        sync_location_snapshot(shipment)
        self._replace_children(shipment, pieces_data, charges_data)
        recalculate_shipment_totals(shipment)
        create_shipment_event(shipment, ShipmentEvent.EventType.CREATED, "Shipment draft created.", user=user)
        return shipment

    def update(self, instance, validated_data):
        pieces_data = validated_data.pop("pieces", None)
        charges_data = validated_data.pop("charges", None)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        validated_data = self._extract_metadata_fields(validated_data, instance=instance)
        validated_data, charges_data = self._apply_business_rules(validated_data, charges_data, instance=instance)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()
        sync_location_snapshot(instance)
        if pieces_data is not None or charges_data is not None:
            self._replace_children(instance, pieces_data, charges_data)
        recalculate_shipment_totals(instance)
        create_shipment_event(instance, ShipmentEvent.EventType.UPDATED, "Shipment updated.", user=user)
        return instance

    def _replace_children(self, shipment, pieces_data, charges_data):
        if pieces_data is not None:
            shipment.pieces.all().delete()
            piece_instances = []
            for index, piece_data in enumerate(pieces_data, start=1):
                volumetric_weight, chargeable_weight = calculate_piece_metrics(piece_data)
                piece_instances.append(
                    ShipmentPiece(
                        shipment=shipment,
                        line_number=index,
                        piece_count=piece_data["piece_count"],
                        package_type=piece_data.get("package_type", ""),
                        description=piece_data.get("description", ""),
                        length_cm=piece_data["length_cm"],
                        width_cm=piece_data["width_cm"],
                        height_cm=piece_data["height_cm"],
                        gross_weight_kg=piece_data["gross_weight_kg"],
                        volumetric_weight_kg=volumetric_weight,
                        chargeable_weight_kg=chargeable_weight,
                    )
                )
            ShipmentPiece.objects.bulk_create(piece_instances)

        if charges_data is not None:
            shipment.charges.all().delete()

    def _apply_business_rules(self, validated_data, charges_data, instance=None):
        cargo_type = validated_data.get("cargo_type", getattr(instance, "cargo_type", Shipment.CargoType.GENERAL_CARGO))
        validated_data["is_dangerous_goods"] = cargo_type == Shipment.CargoType.DANGEROUS_GOODS
        validated_data["is_perishable"] = cargo_type == Shipment.CargoType.PERISHABLE
        validated_data["branch"] = str(validated_data.get("branch", getattr(instance, "branch", "")) or "").strip()

        if instance is None:
            # Charges are intentionally ignored when creating operational shipments.
            return validated_data, []

        # Preserve historical charge lines on existing shipments because the
        # operational workflow no longer edits or clears them.
        return validated_data, None

    def _extract_metadata_fields(self, validated_data, instance=None):
        metadata = dict(getattr(instance, "metadata", {}) or {})
        for field in METADATA_TEXT_FIELDS:
            if field in validated_data:
                metadata[field] = str(validated_data.pop(field, "") or "").strip()
        validated_data["metadata"] = metadata
        return validated_data


class ShipmentListSerializer(serializers.ModelSerializer):
    origin_location_display = serializers.CharField(source="origin_location.display_name", read_only=True)
    destination_location_display = serializers.CharField(source="destination_location.display_name", read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "status",
            "connote_number",
            "shipment_type",
            "branch",
            "shipment_date",
            "reference_number",
            "shipper_company_name",
            "consignee_company_name",
            "origin_location_display",
            "destination_location_display",
            "origin_code",
            "destination_code",
            "cargo_type",
            "service_product",
            "service_scope",
            "payment_term",
            "total_pieces",
            "total_gross_weight_kg",
            "total_volumetric_weight_kg",
            "total_chargeable_weight_kg",
            "total_charges_amount",
            "last_pdf_generated_at",
            "created_at",
            "updated_at",
        ]
