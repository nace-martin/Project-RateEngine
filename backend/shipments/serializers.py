from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from core.models import Location

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
from .services import (
    calculate_piece_metrics,
    create_shipment_event,
    recalculate_shipment_totals,
    sync_location_snapshot,
)


class ShipmentAddressBookEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentAddressBookEntry
        fields = [
            "id",
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

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value


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
    pieces = ShipmentPieceSerializer(many=True)
    charges = ShipmentChargeSerializer(many=True)
    documents = ShipmentDocumentSerializer(many=True, read_only=True)
    events = ShipmentEventSerializer(many=True, read_only=True)
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
            "shipment_date",
            "reference_number",
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
            "service_level",
            "payment_term",
            "commodity_description",
            "goods_description",
            "is_dangerous_goods",
            "dangerous_goods_details",
            "is_perishable",
            "perishable_details",
            "handling_notes",
            "declaration_notes",
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

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        pieces = attrs.get("pieces")
        charges = attrs.get("charges")

        raw_shipper_name = attrs.get("shipper_company_name", getattr(instance, "shipper_company_name", ""))
        raw_consignee_name = attrs.get("consignee_company_name", getattr(instance, "consignee_company_name", ""))
        raw_shipper_address = attrs.get("shipper_address_line_1", getattr(instance, "shipper_address_line_1", ""))
        raw_consignee_address = attrs.get("consignee_address_line_1", getattr(instance, "consignee_address_line_1", ""))
        raw_shipper_city = attrs.get("shipper_city", getattr(instance, "shipper_city", ""))
        raw_consignee_city = attrs.get("consignee_city", getattr(instance, "consignee_city", ""))
        raw_shipper_country = attrs.get("shipper_country_code", getattr(instance, "shipper_country_code", ""))
        raw_consignee_country = attrs.get("consignee_country_code", getattr(instance, "consignee_country_code", ""))

        if not raw_shipper_name or not raw_shipper_address or not raw_shipper_city or not raw_shipper_country:
            raise serializers.ValidationError("Shipper details are mandatory.")
        if not raw_consignee_name or not raw_consignee_address or not raw_consignee_city or not raw_consignee_country:
            raise serializers.ValidationError("Consignee details are mandatory.")

        origin = attrs.get("origin_location", getattr(instance, "origin_location", None))
        destination = attrs.get("destination_location", getattr(instance, "destination_location", None))
        if not origin or not destination:
            raise serializers.ValidationError("Origin and destination are mandatory.")

        is_dg = attrs.get("is_dangerous_goods", getattr(instance, "is_dangerous_goods", False))
        dg_details = attrs.get("dangerous_goods_details", getattr(instance, "dangerous_goods_details", ""))
        if is_dg and not str(dg_details).strip():
            raise serializers.ValidationError({"dangerous_goods_details": "Dangerous goods details are required."})

        is_perishable = attrs.get("is_perishable", getattr(instance, "is_perishable", False))
        perishable_details = attrs.get("perishable_details", getattr(instance, "perishable_details", ""))
        if is_perishable and not str(perishable_details).strip():
            raise serializers.ValidationError({"perishable_details": "Perishable handling details are required."})

        if instance is None and (not pieces or len(pieces) == 0):
            raise serializers.ValidationError({"pieces": "At least one piece line is required."})
        if pieces is not None and len(pieces) == 0:
            raise serializers.ValidationError({"pieces": "At least one piece line is required."})

        if charges is not None:
            for charge in charges:
                try:
                    amount = Decimal(str(charge.get("amount", "0")))
                except (InvalidOperation, TypeError, ValueError):
                    amount = Decimal("0")
                if amount <= 0:
                    raise serializers.ValidationError({"charges": "Charge amounts must be greater than 0."})

        return attrs

    def create(self, validated_data):
        pieces_data = validated_data.pop("pieces", [])
        charges_data = validated_data.pop("charges", [])
        request = self.context.get("request")
        user = getattr(request, "user", None)
        organization = getattr(user, "organization", None)

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
            charge_instances = []
            for index, charge_data in enumerate(charges_data, start=1):
                charge_instances.append(
                    ShipmentCharge(
                        shipment=shipment,
                        line_number=index,
                        charge_type=charge_data.get("charge_type", ShipmentCharge.ChargeType.OTHER),
                        description=charge_data["description"],
                        amount=charge_data["amount"],
                        currency=charge_data.get("currency", shipment.currency or "PGK"),
                        payment_by=charge_data.get("payment_by", ShipmentCharge.PaymentBy.SHIPPER),
                        notes=charge_data.get("notes", ""),
                    )
                )
            ShipmentCharge.objects.bulk_create(charge_instances)


class ShipmentListSerializer(serializers.ModelSerializer):
    origin_location_display = serializers.CharField(source="origin_location.display_name", read_only=True)
    destination_location_display = serializers.CharField(source="destination_location.display_name", read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "status",
            "connote_number",
            "shipment_date",
            "reference_number",
            "shipper_company_name",
            "consignee_company_name",
            "origin_location_display",
            "destination_location_display",
            "origin_code",
            "destination_code",
            "service_level",
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
