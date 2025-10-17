import json
from typing import Any, Dict
from rest_framework import serializers
from .models import Quote


class QuoteLegacyListSerializer(serializers.ModelSerializer):
    """
    Shapes the modern Quote model so the legacy frontend screens keep working.
    """

    client = serializers.SerializerMethodField()
    origin = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    mode = serializers.SerializerMethodField()
    chargeable_weight_kg = serializers.SerializerMethodField()
    base_cost = serializers.SerializerMethodField()
    total_sell = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = (
            "id",
            "client",
            "origin",
            "destination",
            "mode",
            "status",
            "chargeable_weight_kg",
            "base_cost",
            "total_sell",
            "created_at",
        )

    # --- Helpers -----------------------------------------------------------------
    def _request_details(self, obj: Quote) -> Dict[str, Any]:
        data = obj.request_details
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return {}
        return data or {}

    # --- Field serializers -------------------------------------------------------
    def get_client(self, obj: Quote) -> Dict[str, Any]:
        company = obj.bill_to
        if not company:
            return {
                "id": None,
                "name": "Unknown",
                "company_name": "Unknown",
            }
        return {
            "id": str(company.id),
            "name": company.name,
            "company_name": company.name,
        }

    def get_origin(self, obj: Quote) -> str:
        details = self._request_details(obj)
        return details.get("origin_code") or details.get("origin_iata") or ""

    def get_destination(self, obj: Quote) -> str:
        details = self._request_details(obj)
        return details.get("destination_code") or details.get("dest_iata") or ""

    def get_mode(self, obj: Quote) -> str:
        details = self._request_details(obj)
        return details.get("mode") or "AIR"

    def get_chargeable_weight_kg(self, obj: Quote) -> str:
        details = self._request_details(obj)
        value = details.get("chargeable_kg") or details.get("chargeable_weight_kg")
        return str(value) if value is not None else ""

    def get_base_cost(self, obj: Quote) -> str:
        totals = getattr(obj, "totals", None)
        if not totals or totals.subtotal_pgk is None:
            return "0"
        return str(totals.subtotal_pgk)

    def get_total_sell(self, obj: Quote) -> str:
        totals = getattr(obj, "totals", None)
        if not totals:
            return "0"
        # Prefer the output currency total if present (v2 agent quotes), else PGK grand total.
        if totals.grand_total_output_currency is not None:
            return str(totals.grand_total_output_currency)
        if totals.grand_total_pgk is not None:
            return str(totals.grand_total_pgk)
        return "0"
