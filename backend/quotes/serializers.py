from __future__ import annotations
from decimal import Decimal
from django.db import connection
from rest_framework import serializers

from .models import Quotation, QuoteVersion, ShipmentPiece, Charge


# ---------- TOTALS (read-only projection from SQL VIEW) ----------
class QuoteVersionTotalsSerializer(serializers.Serializer):
    sell_origin     = serializers.DecimalField(max_digits=18, decimal_places=2)
    sell_air        = serializers.DecimalField(max_digits=18, decimal_places=2)
    sell_destination= serializers.DecimalField(max_digits=18, decimal_places=2)
    sell_total      = serializers.DecimalField(max_digits=18, decimal_places=2)
    buy_total       = serializers.DecimalField(max_digits=18, decimal_places=2)
    tax_total       = serializers.DecimalField(max_digits=18, decimal_places=2)
    grand_total     = serializers.DecimalField(max_digits=18, decimal_places=2)
    margin_abs      = serializers.DecimalField(max_digits=18, decimal_places=2)
    margin_pct      = serializers.DecimalField(max_digits=6,  decimal_places=2)


# ---------- NESTED WRITE/READ SERIALIZERS ----------
class ShipmentPieceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentPiece
        exclude = ("version",)

class ChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Charge
        exclude = ("version",)


# ---------- VERSION SERIALIZER (write nested, read totals) ----------
class QuoteVersionSerializer(serializers.ModelSerializer):
    pieces = ShipmentPieceSerializer(many=True, read_only=True)
    charges = ChargeSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = QuoteVersion
        fields = [
            "id", "quotation", "version_no",
            "created_by", "locked_at",
            "origin", "destination",
            "volumetric_divisor", "volumetric_weight_kg", "chargeable_weight_kg",
            "carrier_code", "service_level", "transit_time_days", "routing_details",
            "fx_snapshot", "policy_snapshot", "rate_provenance",
            "sell_currency", "valid_from", "valid_to",
            "calc_version", "created_at",
            "pieces", "charges", "totals",
            "idempotency_key",   # optional, keep if you want to see it in responses
        ]
        # 👇 critical: we set quotation (and others) as read-only so the serializer
        # doesn't demand them in the POST payload you validate before create().
        read_only_fields = ("quotation", "version_no", "created_at", "locked_at", "created_by", "idempotency_key")

    def get_totals(self, obj):
        # Pull from the SQL view quotes_quoteversion_totals
        with connection.cursor() as cur:
            cur.execute("""
                SELECT sell_origin, sell_air, sell_destination, sell_total,
                       buy_total, tax_total, grand_total, margin_abs, margin_pct
                FROM quotes_quoteversion_totals WHERE quote_version_id=%s
            """, [obj.id])
            row = cur.fetchone()
            if not row:
                return None
            keys = ["sell_origin","sell_air","sell_destination","sell_total",
                    "buy_total","tax_total","grand_total","margin_abs","margin_pct"]
            return dict(zip(keys, row))


# ---------- QUOTATION SERIALIZER (read with nested versions) ----------
class QuotationSerializer(serializers.ModelSerializer):
    # Read-only nested versions (created via dedicated endpoint)
    versions = QuoteVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Quotation
        fields = "__all__"