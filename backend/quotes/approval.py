from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.conf import settings
from django.db.models import Q

from core.commodity import DEFAULT_COMMODITY_CODE, commodity_label, normalize_commodity_code
from pricing_v4.models import CommodityApprovalRule


DEFAULT_APPROVAL_COMMODITIES = ['SCR', 'DG', 'AVI', 'PER', 'HVC', 'HUM', 'OOG', 'VUL', 'TTS']
DEFAULT_MARGIN_THRESHOLD_PCT = Decimal("15.00")


@dataclass(frozen=True)
class QuoteApprovalDecision:
    approval_required: bool
    reason: str
    margin_percent: Optional[Decimal]


class QuoteApprovalPolicy:
    """
    Evaluates manager-approval requirements for standard quotes.

    DB rules take precedence. When no DB rule matches, we fall back to the
    existing approval-policy settings so special cargo remains protected even
    before commodity approval rows are seeded.
    """

    @classmethod
    def evaluate(
        cls,
        *,
        shipment_type: str,
        service_scope: Optional[str],
        commodity_code: Optional[str],
        total_cost_pgk: Decimal,
        total_sell_pgk: Decimal,
        quote_date: Optional[date] = None,
    ) -> QuoteApprovalDecision:
        quote_date = quote_date or date.today()
        commodity = normalize_commodity_code(commodity_code)
        margin_percent = cls._calculate_margin_percent(total_cost_pgk, total_sell_pgk)

        matched_rules = list(
            cls._matching_rules(
                shipment_type=shipment_type,
                service_scope=service_scope,
                commodity_code=commodity,
                quote_date=quote_date,
            )
        )
        reasons = cls._reasons_from_rules(matched_rules, commodity, margin_percent)
        if matched_rules:
            return QuoteApprovalDecision(
                approval_required=bool(reasons),
                reason=" ".join(reasons),
                margin_percent=margin_percent,
            )

        fallback_reasons = cls._fallback_reasons(commodity, margin_percent)
        return QuoteApprovalDecision(
            approval_required=bool(fallback_reasons),
            reason=" ".join(fallback_reasons),
            margin_percent=margin_percent,
        )

    @classmethod
    def _matching_rules(
        cls,
        *,
        shipment_type: str,
        service_scope: Optional[str],
        commodity_code: str,
        quote_date: date,
    ):
        qs = CommodityApprovalRule.objects.filter(
            shipment_type=shipment_type,
            commodity_code=commodity_code,
            is_active=True,
            effective_from__lte=quote_date,
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=quote_date)
        )
        if service_scope:
            qs = qs.filter(
                Q(service_scope=service_scope)
                | Q(service_scope__isnull=True)
                | Q(service_scope='')
            )
        else:
            qs = qs.filter(Q(service_scope__isnull=True) | Q(service_scope=''))
        return qs.order_by('-service_scope', 'effective_from', 'id')

    @classmethod
    def _reasons_from_rules(
        cls,
        matched_rules,
        commodity_code: str,
        margin_percent: Optional[Decimal],
    ) -> list[str]:
        reasons: list[str] = []
        label = commodity_label(commodity_code)
        for rule in matched_rules:
            if rule.requires_manager_approval:
                reasons.append(f"{label} requires manager approval.")
            if rule.margin_below_pct is not None and margin_percent is not None and margin_percent < rule.margin_below_pct:
                reasons.append(
                    f"Margin {cls._format_pct(margin_percent)} is below the "
                    f"{cls._format_pct(rule.margin_below_pct)} threshold for {label}."
                )
        return cls._dedupe(reasons)

    @classmethod
    def _fallback_reasons(
        cls,
        commodity_code: str,
        margin_percent: Optional[Decimal],
    ) -> list[str]:
        config = getattr(settings, 'STANDARD_QUOTE_APPROVAL_POLICY', None)
        if config is None:
            config = getattr(settings, 'SPOT_APPROVAL_POLICY', {})

        reasons: list[str] = []
        approval_commodities = config.get('approval_required_commodities', DEFAULT_APPROVAL_COMMODITIES)
        special_cargo_requires_approval = config.get('special_cargo_requires_approval', True)
        margin_threshold = Decimal(str(config.get('margin_below_pct', DEFAULT_MARGIN_THRESHOLD_PCT)))

        if (
            commodity_code != DEFAULT_COMMODITY_CODE
            and special_cargo_requires_approval
            and commodity_code in approval_commodities
        ):
            reasons.append(f"{commodity_label(commodity_code)} requires manager approval.")

        if margin_percent is not None and margin_percent < margin_threshold:
            reasons.append(
                f"Margin {cls._format_pct(margin_percent)} is below the "
                f"{cls._format_pct(margin_threshold)} threshold."
            )

        return cls._dedupe(reasons)

    @staticmethod
    def _calculate_margin_percent(total_cost_pgk: Decimal, total_sell_pgk: Decimal) -> Optional[Decimal]:
        total_sell = Decimal(total_sell_pgk or 0)
        if total_sell <= 0:
            return None
        total_cost = Decimal(total_cost_pgk or 0)
        margin = ((total_sell - total_cost) / total_sell) * Decimal("100")
        return margin.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _format_pct(value: Decimal) -> str:
        return f"{Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result
