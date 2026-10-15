"""
Import Pricing Engine V4
========================
Implements pricing logic per PricingPolicy.md

Key Rules:
1. CAF adjusts the FX rate, not the amount
2. FX conversion before margin
3. Margin applied last
4. FSC only on Pickup/Cartage
5. Direction determines CAF direction (Import = subtract)
6. Payment Term determines quote currency
7. Service Scope determines which legs are chargeable
8. PNG GST: Proper classification using get_png_gst_category()
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from enum import Enum
import logging

from core.commodity import DEFAULT_COMMODITY_CODE
from pricing_v4.services.commercial_policy import MissingCommercialPolicyError, require_standard_gst_rate
from pricing_v4.models import (
    ProductCode,
    LocalSellRate
)
from pricing_v4.category_rules import (
    is_import_destination_local_code,
    is_import_origin_local_code,
    is_local_rate_category,
)
from pricing_v4.commodity_rules import get_auto_product_code_ids, is_product_code_enabled
from pricing_v4.services.rate_selector import (
    RateNotFoundError,
    RateSelectionContext,
    select_import_cogs_rate,
    select_import_sell_rate,
    select_local_cogs_rate,
    select_local_sell_rate,
)
from core.charge_rules import (
    CALCULATION_FLAT,
    CALCULATION_LOOKUP_RATE,
    RuleEvaluation,
    evaluate_rate_lookup_rule,
)
from quotes.tax_policy import get_png_gst_category
from quotes.quote_result_contract import (
    QuoteComponent,
    basis_for_unit,
    normalize_cost_source,
    normalize_rate_source,
)
from pricing_v4.engine.result_types import QuoteLineItem, QuoteResult, build_tax_breakdown

logger = logging.getLogger(__name__)

# Policy-versioned calculation conventions (CommercialTermsPolicy.caf_method / fx_side_convention).
from pricing_v4.services import fx_conventions  # noqa: E402

class PaymentTerm(Enum):
    COLLECT = "COLLECT"
    PREPAID = "PREPAID"


class ServiceScope(Enum):
    A2A = "A2A"  # Airport to Airport
    A2D = "A2D"  # Airport to Door
    D2A = "D2A"  # Door to Airport
    D2D = "D2D"  # Door to Door


@dataclass
class ChargeLine:
    """Single charge line result."""
    product_code_id: int
    product_code: str
    description: str
    category: str
    leg: str  # 'ORIGIN', 'FREIGHT', 'DESTINATION'
    
    # Cost in original currency
    cost_amount: Decimal
    cost_currency: str
    cost_source: str = 'N/A'
    agent_name: Optional[str] = None  # Rate Provider
    
    # Sell in quote currency
    sell_amount: Decimal = Decimal('0')
    sell_currency: str = 'PGK'
    
    # Margin info
    margin_amount: Decimal = Decimal('0')
    margin_percent: Decimal = Decimal('0')
    
    # Flags
    fx_applied: bool = False
    caf_applied: bool = False
    margin_applied: bool = False
    
    # PNG GST Classification
    gst_category: str = ''  # service_in_PNG, export_service, offshore_service, imported_goods
    gst_rate: Decimal = Decimal('0')
    gst_amount: Decimal = Decimal('0')
    sell_incl_gst: Decimal = Decimal('0')
    
    notes: str = ""
    rule_family: str = CALCULATION_LOOKUP_RATE

    # Canonical PGK equivalents from the engine's own conversions (approved conventions only).
    # None means no PGK equivalent exists because no conversion to or from PGK took place.
    cost_pgk: Optional[Decimal] = None
    sell_pgk: Optional[Decimal] = None
    sell_pgk_incl_gst: Optional[Decimal] = None


_POLICY_DEFAULT = object()


class ImportPricingEngine:
    """
    Import Pricing Engine following PricingPolicy.md
    
    Scenario Matrix (Import only):
    | Term | Scope | Quote | Active Legs | FX Applied To |
    |------|-------|-------|-------------|---------------|
    | PREP | A2D   | FCY   | Dest        | Dest: PGK→FCY |
    | COLL | A2D   | PGK   | Dest        | None          |
    | COLL | D2D   | PGK   | O+F+D       | O+F: FCY→PGK  |
    """
    
    # FSC rates on local handling
    ORIGIN_FSC_RATE = Decimal('0.20') # 20% on Pickup
    DEST_FSC_RATE = Decimal('0.10')   # 10% on Cartage
    
    def __init__(
        self,
        quote_date: date,
        origin: str,
        destination: str,
        chargeable_weight_kg: Decimal,
        payment_term: PaymentTerm,
        service_scope: ServiceScope,
        tt_buy: Optional[Decimal] = None,
        tt_sell: Optional[Decimal] = None,
        caf_rate: Any = _POLICY_DEFAULT,
        margin_rate: Any = _POLICY_DEFAULT,
        margin_method: Optional[str] = None,
        fx_rates: Optional[Dict] = None,
        quote_currency: Optional[str] = None,
        preferred_agent_id: Optional[int] = None,
        preferred_carrier_id: Optional[int] = None,
        buy_currency: Optional[str] = None,
        caf_method: Optional[str] = None,
        fx_side_convention: Optional[str] = None,
        export_caf_rate: Any = _POLICY_DEFAULT,
    ):
        self.quote_date = quote_date
        self.origin = origin
        self.destination = destination
        self.weight = chargeable_weight_kg
        self.payment_term = payment_term
        self.service_scope = service_scope
        
        # FX rates - no fabricated defaults; missing required FX fails closed
        self.tt_buy = tt_buy
        self.tt_sell = tt_sell
        resolved_policy = None
        if caf_rate is _POLICY_DEFAULT or margin_rate is _POLICY_DEFAULT:
            from pricing_v4.services.commercial_policy import require_commercial_terms_policy
            policy = require_commercial_terms_policy(quote_date)
            resolved_policy = policy
            if caf_rate is _POLICY_DEFAULT:
                caf_rate = policy.import_caf_rate
            if margin_rate is _POLICY_DEFAULT:
                margin_rate = policy.margin_rate
                margin_method = policy.margin_method
        self.caf_rate = caf_rate
        # PGK to FCY under the approved BSP rule carries the export CAF (uplift after conversion). Resolved
        # from the policy on first use unless stated explicitly.
        self._export_caf_rate = export_caf_rate
        self.margin_rate = margin_rate
        self.margin_method = margin_method or 'MARKUP_ON_COST'
        self.fx_rates = fx_rates or {}
        # Calculation conventions come from the policy row; direct engine callers that pass explicit
        # CAF and margin values keep the legacy conventions unless they state otherwise.
        self.caf_method = caf_method or (
            getattr(resolved_policy, 'caf_method', None) if resolved_policy is not None else None
        ) or 'LEGACY_RATE_ADJUSTMENT'
        self.fx_side_convention = fx_side_convention or (
            getattr(resolved_policy, 'fx_side_convention', None) if resolved_policy is not None else None
        ) or 'LEGACY_COST_AT_TT_BUY'
        self._pair_cache: Dict[str, Any] = {}
        self._conversions: List[dict] = []
        self._gst_rate_cache: Optional[Decimal] = None
        self._warnings: List[str] = []
        self._audit_metadata: Dict[str, Any] = {
            "fx_fallbacks": [],
            "conversions": self._conversions,
            "commercial_convention": {"caf_method": self.caf_method, "fx_side_convention": self.fx_side_convention},
        }
        
        # Determine quote currency (prefer explicit override, else derive)
        self.quote_currency = quote_currency or self._determine_quote_currency()
        self.preferred_agent_id = preferred_agent_id
        self.preferred_carrier_id = preferred_carrier_id
        self.buy_currency = (buy_currency or "").strip().upper() or None
        
        # Cache for FSC calculations
        self._cost_cache: Dict[str, Decimal] = {}
    
    def _determine_quote_currency(self) -> str:
        """
        Payment Term determines quote currency.
        Import COLLECT = PGK (consignee in PNG pays)
        Import PREPAID = FCY (shipper abroad pays), default USD.

        Note: In production flow, adapter/view passes explicit quote_currency
        derived from canonical country/payment rules.
        """
        if self.payment_term == PaymentTerm.COLLECT:
            return 'PGK'
        return 'USD'
    
    def _get_active_legs(self) -> List[str]:
        """
        Service Scope determines which legs are in scope.
        """
        if self.service_scope == ServiceScope.A2D:
            return ['DESTINATION']
        elif self.service_scope == ServiceScope.D2A:
            return ['ORIGIN', 'FREIGHT']
        elif self.service_scope == ServiceScope.D2D:
            return ['ORIGIN', 'FREIGHT', 'DESTINATION']
        else:  # A2A
            return ['FREIGHT']
    
    def _needs_fx_conversion(self, leg: str) -> bool:
        """
        Determine if a leg needs FX conversion based on scenario matrix.
        """
        if self.payment_term == PaymentTerm.COLLECT:
            # PGK quote - Origin/Freight (FCY) need conversion
            if self.service_scope == ServiceScope.D2D:
                return leg in ['ORIGIN', 'FREIGHT']
            elif self.service_scope == ServiceScope.A2D:
                return False  # Dest already in PGK
        else:  # PREPAID
            # FCY quote - Destination (PGK) needs conversion
            if self.service_scope == ServiceScope.A2D:
                return leg == 'DESTINATION'
            elif self.service_scope == ServiceScope.D2D:
                return leg == 'DESTINATION'
        return False
    
    # ------------------------------------------------------------------ FX, CAF and conversions

    @property
    def _approved_caf(self) -> bool:
        """Conversions are performed and recorded by ``_convert_with_caf`` (not the legacy rate adjustment)."""
        return fx_conventions.uses_engine_conversions(self.caf_method)

    @property
    def _approved_fx_sides(self) -> bool:
        """FCY to PGK at TT BUY; PGK to FCY at TT SELL (BSP calculator)."""
        return self.fx_side_convention == fx_conventions.FX_APPROVED

    @property
    def _standard_gst_rate(self) -> Decimal:
        """Standard GST rate from the resolved commercial policy. Missing or ambiguous policy fails closed."""
        if self._gst_rate_cache is None:
            self._gst_rate_cache = require_standard_gst_rate(self.quote_date)
        return self._gst_rate_cache

    def _pair(self, currency: str):
        """Market FX pair for currency/PGK on the quote date, resolved once per currency."""
        if currency not in self._pair_cache:
            from pricing_v4.services.fx_resolver import resolve_market_fx_pair
            self._pair_cache[currency] = resolve_market_fx_pair(currency, 'PGK', self.quote_date)
        return self._pair_cache[currency]

    def _leg_evidence(self, currency: str, side: str, rate: Decimal) -> dict:
        """Provenance of one FX leg. Never triggers FX resolution that has not already happened."""
        pair = self._pair_cache.get(currency)
        evidence = {"pair": f"{currency}/PGK", "side": side, "rate": str(rate)}
        if pair is not None:
            evidence.update({
                "source": pair.source, "effective_date": pair.effective_date.isoformat(),
                "is_inverse": pair.is_inverse, "is_cross": pair.is_cross, "source_role": pair.source_role,
                "age_days": pair.age_days, "max_age_days": pair.max_age_days, "policy_code": pair.policy_code,
            })
        return evidence

    def _record_conversion(self, **evidence) -> None:
        self._conversions.append(evidence)

    def _get_rate_for_currency(self, currency: str, rate_type: str = 'tt_sell') -> Decimal:
        """Get FX rate for specific currency."""
        if currency == 'PGK':
            return Decimal('1.0')

        # Check standard rates
        if currency == self.quote_currency:
            rate = self.tt_buy if rate_type == 'tt_buy' else self.tt_sell
            if rate is not None:
                return rate

        pair = self._pair(currency)
        return pair.tt_buy if rate_type == 'tt_buy' else pair.tt_sell

    def _convert_with_caf(
        self, amount: Decimal, from_curr: str, to_curr: str, *, role: str, product_code: str = ""
    ) -> Decimal:
        """Approved BSP conversion (see ``pricing_v4.services.fx_conventions``).

        FCY to PGK uses the stored TT BUY; the import CAF reduces the published TT Buy, so the PGK amount
        is ``FCY x TT BUY / (1 - import CAF)``. PGK to FCY uses the stored TT SELL and the export CAF is a
        separate uplift after pure conversion: ``(PGK / TT SELL) x (1 + export CAF)``. CAF applies only
        because a conversion happened. A policy that still carries the superseded sides, an FCY amount that
        is not a supplier cost, and FCY to FCY (no approved single CAF treatment) all fail closed.
        """
        if from_curr == to_curr or amount == Decimal('0'):
            return Decimal('0.00') if amount == Decimal('0') else amount
        fx_conventions.require_approved_convention(self.caf_method, self.fx_side_convention)
        if from_curr != 'PGK' and to_curr != 'PGK':
            raise MissingCommercialPolicyError(
                f"No approved FX rule converts {from_curr} directly to {to_curr}; calculation fails closed."
            )
        from pricing_v4.services.fx_resolver import MissingFxMarketRateError
        if from_curr != 'PGK':
            if role != 'COST':
                raise MissingCommercialPolicyError(
                    f"No approved FX side converts a {from_curr} sell amount to {to_curr}; calculation fails closed."
                )
            caf_rate = self.caf_rate
            if caf_rate is None:
                raise MissingCommercialPolicyError(
                    "Import CAF rate is required when an FCY amount converts to PGK; calculation fails closed."
                )
            rate = self._get_rate_for_currency(from_curr, 'tt_buy')
            if rate is None or rate <= 0:
                raise MissingFxMarketRateError("FX rate must be strictly positive.")
            pure = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            effective = fx_conventions.fcy_to_pgk_rate(rate, caf_rate)
            commercial = (amount * effective).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            leg = self._leg_evidence(from_curr, fx_conventions.SIDE_FCY_TO_PGK, rate)
            caf_operation = fx_conventions.CAF_OPERATION_TO_PGK
            effective_rate = str(effective.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP))
        else:
            caf_rate = self._pgk_to_fcy_caf_rate()
            rate = self._get_rate_for_currency(to_curr, 'tt_sell')
            if rate is None or rate <= 0:
                raise MissingFxMarketRateError("FX rate must be strictly positive.")
            pure = (amount / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            commercial = (pure * (Decimal('1') + caf_rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            leg = self._leg_evidence(to_curr, fx_conventions.SIDE_PGK_TO_FCY, rate)
            caf_operation = fx_conventions.CAF_OPERATION_FROM_PGK
            effective_rate = None
        self._record_conversion(
            product_code=product_code, role=role, from_currency=from_curr, to_currency=to_curr,
            amount_in=str(amount), pure_market_amount=str(pure), caf_percent=str(caf_rate * 100),
            caf_amount=str(commercial - pure), commercial_amount=str(commercial), caf_operation=caf_operation,
            effective_rate_after_caf=effective_rate,
            caf_method=self.caf_method, fx_side_convention=self.fx_side_convention, legs=[leg],
        )
        return commercial

    def _pgk_to_fcy_caf_rate(self) -> Decimal:
        """Export CAF for a PGK to FCY conversion (approved BSP rule). Missing fails closed."""
        if self._export_caf_rate is _POLICY_DEFAULT:
            from pricing_v4.services.commercial_policy import require_commercial_terms_policy
            self._export_caf_rate = require_commercial_terms_policy(self.quote_date).export_caf_rate
        if self._export_caf_rate is None:
            raise MissingCommercialPolicyError(
                "Export CAF rate is required when a PGK amount converts to FCY; calculation fails closed."
            )
        return self._export_caf_rate

    def _convert_fcy_to_pgk(self, amount: Decimal, currency: Optional[str] = None) -> Decimal:
        """
        FCY → PGK conversion (Import).
        Legacy convention: TT BUY in PGK per FCY, CAF subtracted from the rate, MULTIPLY.
        Approved convention: see ``_convert_with_caf``.
        """
        if amount == Decimal('0'):
            return Decimal('0.00')
        if self._approved_caf:
            return self._convert_with_caf(amount, currency or self.buy_currency or 'UNKNOWN', 'PGK', role='COST')
        if self.caf_rate is None:
            raise MissingCommercialPolicyError(
                "Import CAF rate is required for FCY conversion; calculation fails closed."
            )
        rate = None
        if currency:
            rate = self._get_rate_for_currency(currency, 'tt_buy')
        elif self.tt_buy is not None:
            rate = self.tt_buy
        elif self.buy_currency and self.buy_currency != 'PGK':
            rate = self._get_rate_for_currency(self.buy_currency, 'tt_buy')

        if rate is None:
            from pricing_v4.services.fx_resolver import MissingFxMarketRateError
            raise MissingFxMarketRateError(
                "Missing TT BUY FX rate for Import FCY to PGK conversion; calculation fails closed."
            )

        effective_rate = rate * (Decimal('1') - self.caf_rate)
        if effective_rate <= 0:
            from pricing_v4.services.fx_resolver import MissingFxMarketRateError
            raise MissingFxMarketRateError("Effective FX rate must be strictly positive.")

        pgk = amount * effective_rate
        pgk = pgk.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self._record_conversion(
            product_code="", role='COST', from_currency=currency or self.buy_currency, to_currency='PGK',
            amount_in=str(amount), commercial_amount=str(pgk), caf_percent=str(self.caf_rate * 100),
            caf_method=self.caf_method, fx_side_convention=self.fx_side_convention,
            legs=[self._leg_evidence(currency or self.buy_currency or '', 'TT_BUY', rate)],
        )
        return pgk

    def _convert_pgk_to_fcy(self, amount: Decimal, target_currency: Optional[str] = None) -> Decimal:
        """
        PGK → FCY conversion.
        Legacy convention: TT SELL in PGK per FCY, CAF subtracted from the rate, DIVIDE.
        Approved convention: see ``_convert_with_caf`` (TT SELL, then CAF uplift).
        """
        if amount == Decimal('0'):
            return Decimal('0.00')
        if self._approved_caf:
            return self._convert_with_caf(amount, 'PGK', target_currency or self.quote_currency, role='SELL')
        if self.caf_rate is None:
            raise MissingCommercialPolicyError(
                "Import CAF rate is required for PGK to FCY conversion; calculation fails closed."
            )
        rate = None
        if target_currency:
            rate = self._get_rate_for_currency(target_currency, 'tt_sell')
        elif self.tt_sell is not None:
            rate = self.tt_sell
        elif self.quote_currency != 'PGK':
            rate = self._get_rate_for_currency(self.quote_currency, 'tt_sell')

        if rate is None:
            from pricing_v4.services.fx_resolver import MissingFxMarketRateError
            raise MissingFxMarketRateError(
                "Missing TT SELL FX rate for Import PGK to FCY conversion; calculation fails closed."
            )

        effective_rate = rate * (Decimal('1') - self.caf_rate)
        if effective_rate <= 0:
            from pricing_v4.services.fx_resolver import MissingFxMarketRateError
            raise MissingFxMarketRateError("Effective FX rate must be strictly positive.")
        fcy = amount / effective_rate
        fcy = fcy.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self._record_conversion(
            product_code="", role='SELL', from_currency='PGK', to_currency=target_currency or self.quote_currency,
            amount_in=str(amount), commercial_amount=str(fcy), caf_percent=str(self.caf_rate * 100),
            caf_method=self.caf_method, fx_side_convention=self.fx_side_convention,
            legs=[self._leg_evidence(target_currency or self.quote_currency or '', 'TT_SELL', rate)],
        )
        return fcy

    def _convert_cross_currency(
        self, amount: Decimal, from_curr: str, to_curr: str, *, role: str = 'COST', product_code: str = ""
    ) -> Decimal:
        """Convert any currency to any currency via PGK."""
        if from_curr == to_curr or amount == Decimal('0'):
            return amount
        if self._approved_caf:
            return self._convert_with_caf(amount, from_curr, to_curr, role=role, product_code=product_code)

        # 1. Convert source to PGK (using TT BUY)
        if from_curr == 'PGK':
            amount_pgk = amount
        else:
            amount_pgk = self._convert_fcy_to_pgk(amount, from_curr)

        # 2. Convert PGK to target (using TT SELL)
        if to_curr == 'PGK':
            return amount_pgk
        else:
            return self._convert_pgk_to_fcy(amount_pgk, to_curr)

    def _apply_margin(self, amount: Decimal) -> Decimal:
        """Apply margin (always last)."""
        if self.margin_rate is None:
            raise MissingCommercialPolicyError(
                "Missing margin in CommercialTermsPolicy for cost-derived calculation; "
                "calculation fails closed."
            )
        if self.margin_method == "TARGET_GROSS_MARGIN":
            if self.margin_rate >= Decimal(1):
                from django.core.exceptions import ValidationError
                raise ValidationError("Target gross margin rate must be < 1.00.")
            return (amount / (Decimal('1') - self.margin_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        elif self.margin_method == "MARKUP_ON_COST":
            return (amount * (Decimal('1') + self.margin_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        else:
            raise MissingCommercialPolicyError(
                f"Unsupported margin_method '{self.margin_method}'; calculation fails closed."
            )
    
    def _calculate_cogs_amount(self, cogs, pc: ProductCode) -> RuleEvaluation:
        """Calculate COGS amount for a rate record."""
        base_amount = Decimal('0.00')
        if cogs.percent_rate:
            base_pc = pc.percent_of_product_code
            if base_pc and base_pc.code in self._cost_cache:
                base_amount = self._cost_cache[base_pc.code]
        return evaluate_rate_lookup_rule(
            rate=cogs,
            quantity=self.weight,
            base_amount=base_amount,
        )
    
    def _get_leg_for_product_code(self, pc: ProductCode) -> str:
        """Determine which leg a ProductCode belongs to."""
        code = pc.code.upper()
        description = pc.description.upper()
        
        if 'FRT' in code or 'FREIGHT' in code:
            return 'FREIGHT'
        elif is_import_origin_local_code(code, description):
            return 'ORIGIN'
        elif is_import_destination_local_code(code, description):
            return 'DESTINATION'
        elif pc.domain == 'IMPORT' and '-SPECIAL' in code:
            return 'DESTINATION'
        else:
            # Default based on category
            if pc.category in ['CARTAGE', 'CLEARANCE']:
                return 'DESTINATION'
            return 'ORIGIN'
    
    def calculate_quote(self, commodity_code: str = DEFAULT_COMMODITY_CODE) -> QuoteResult:
        """
        Calculate complete import quote.
        """
        active_legs = self._get_active_legs()
        payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
        requested_product_code_ids = self.get_requested_product_code_ids(
            is_dg=False,
            service_scope=self.service_scope.value,
            commodity_code=commodity_code,
            origin=self.origin,
            destination=self.destination,
            payment_term=payment_term_value,
            quote_date=self.quote_date,
        )
        
        result = QuoteResult(
            origin=self.origin,
            destination=self.destination,
            quote_date=self.quote_date,
            chargeable_weight_kg=self.weight,
            direction='IMPORT',
            payment_term=self.payment_term.value,
            service_scope=self.service_scope.value,
            quote_currency=self.quote_currency,
            currency=self.quote_currency,
            fx_rate_used=self.tt_buy if self.payment_term == PaymentTerm.COLLECT else self.tt_sell,
            caf_rate=self.caf_rate,
            warnings=list(self._warnings),
            audit_metadata=self._audit_metadata,
        )
        
        # Calculate effective FX rate
        if self.payment_term == PaymentTerm.COLLECT:
            result.effective_fx_rate = (
                self.tt_buy * (Decimal('1') - self.caf_rate)
                if self.caf_rate is not None and self.tt_buy is not None
                else None
            )
        else:
            if self.tt_sell is not None:
                if self.caf_rate is None:
                    raise MissingCommercialPolicyError(
                        "Import CAF rate is required for PREPAID quote; calculation fails closed."
                    )
                result.effective_fx_rate = self.tt_sell * (Decimal('1') - self.caf_rate)
            else:
                result.effective_fx_rate = None
        
        # Get all Import ProductCodes
        import_pcs = ProductCode.objects.filter(domain='IMPORT').order_by('id')

        # First pass: Calculate base costs (for FSC dependencies)
        for pc in import_pcs:
            if not is_product_code_enabled(
                shipment_type='IMPORT',
                service_scope=self.service_scope.value,
                commodity_code=commodity_code,
                product_code_id=pc.id,
                origin_code=self.origin,
                destination_code=self.destination,
                payment_term=payment_term_value,
                quote_date=self.quote_date,
            ):
                continue
            leg = self._get_leg_for_product_code(pc)
            if leg not in active_legs:
                continue
            
            # Skip percentage-based codes in first pass
            if pc.default_unit == 'PERCENT':
                continue
            
            try:
                cogs = select_import_cogs_rate(
                    RateSelectionContext(
                        product_code_id=pc.id,
                        quote_date=self.quote_date,
                        origin_airport=self.origin,
                        destination_airport=self.destination,
                        currency=self.buy_currency,
                        agent_id=self.preferred_agent_id,
                        carrier_id=self.preferred_carrier_id,
                    )
                ).record
            except RateNotFoundError:
                cogs = None

            if cogs:
                cost_eval = self._calculate_cogs_amount(cogs, pc)
                self._cost_cache[pc.code] = cost_eval.amount
        
        # Second pass: Calculate all charges including FSC
        for pc in import_pcs:
            if not is_product_code_enabled(
                shipment_type='IMPORT',
                service_scope=self.service_scope.value,
                commodity_code=commodity_code,
                product_code_id=pc.id,
                origin_code=self.origin,
                destination_code=self.destination,
                payment_term=payment_term_value,
                quote_date=self.quote_date,
            ):
                continue
            leg = self._get_leg_for_product_code(pc)
            if leg not in active_legs:
                continue
            
            line = self._calculate_charge_line(pc, leg)
            
            # If no line but the engine explicitly requested this ProductCode,
            # create a missing-rate placeholder so the gap remains visible.
            if not line and pc.id in requested_product_code_ids:
                line = self._missing_rate_line(pc, leg)

            if line:
                if leg == 'ORIGIN':
                    result.line_items.append(self._to_quote_line_item(line))
                elif leg == 'FREIGHT':
                    result.line_items.append(self._to_quote_line_item(line))
                else:
                    result.line_items.append(self._to_quote_line_item(line))
        
        # Calculate totals
        all_lines = result.line_items
        if self._approved_caf:
            # PGK equivalents are summed from the canonical per-line conversion results. A line with no
            # conversion to or from PGK has none, and no FX is resolved to invent one.
            result.total_cost_pgk = sum((line.cost_pgk or Decimal('0.00') for line in all_lines), Decimal('0.00'))
            result.total_sell_pgk = sum((line.sell_pgk or Decimal('0.00') for line in all_lines), Decimal('0.00'))
            self._audit_metadata["pgk_equivalent_complete"] = all(
                line.sell_pgk is not None or not line.sell_amount for line in all_lines
            )
        else:
            # Legacy conventions: PGK equivalents are a reporting conversion. When FX is available they are
            # exactly as before. When it is not, and the quote itself needed no conversion, the quote still
            # prices and the equivalents are reported as unavailable instead of failing.
            from pricing_v4.services.fx_resolver import FxResolutionError

            def pgk_equivalent(line, amount, currency):
                try:
                    return self._convert_cross_currency(amount, currency, 'PGK'), True
                except FxResolutionError:
                    if line.fx_applied:
                        raise
                    return Decimal('0.00'), False

            total_cost = total_sell = Decimal('0.00')
            complete = True
            for line in all_lines:
                cost_value, cost_ok = pgk_equivalent(line, line.cost_amount, line.cost_currency)
                sell_value, sell_ok = pgk_equivalent(line, line.sell_amount, line.sell_currency)
                total_cost += cost_value
                total_sell += sell_value
                complete = complete and cost_ok and sell_ok
            result.total_cost_pgk = total_cost
            result.total_sell_pgk = total_sell
            self._audit_metadata["pgk_equivalent_complete"] = complete
        result.total_margin = sum(line.margin_amount for line in all_lines)
        result.total_gst = sum(line.gst_amount for line in all_lines)
        result.total_sell_incl_gst = sum(line.sell_incl_gst for line in all_lines)
        result.fx_applied = any(line.fx_applied for line in all_lines)
        if self._approved_caf:
            result.tax_breakdown = build_tax_breakdown(all_lines, converter=lambda amount, currency: amount)
        else:
            result.tax_breakdown = build_tax_breakdown(
                all_lines,
                converter=lambda amount, currency: self._convert_cross_currency(amount, currency, 'PGK'),
            )
        
        return result

    @staticmethod
    def get_requested_product_code_ids(
        is_dg: bool = False,
        service_scope: str = 'A2A',
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        payment_term: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> List[int]:
        """
        Returns ProductCode IDs the import engine should actively try to price
        or represent with explicit missing-rate placeholders.
        """
        service_scope = service_scope.upper()
        if service_scope == 'P2P': service_scope = 'A2A'

        codes = []
        
        # Freight is requested for all scopes involving linehaul
        if service_scope in ('A2A', 'D2A', 'D2D'):
            codes.append(2001)  # IMP-FRT-AIR

        # Origin local requested for D2A and D2D
        if service_scope in ('D2A', 'D2D'):
            codes.extend([
                2010,  # IMP-DOC-ORIGIN
                2011,  # IMP-AWB-ORIGIN
                2012,  # IMP-AGENCY-ORIGIN
                2030,  # IMP-CTO-ORIGIN
                2040,  # IMP-SCREEN-ORIGIN
                2050,  # IMP-PICKUP
                2060,  # IMP-FSC-PICKUP
            ])

        # Destination local requested for A2D and D2D
        if service_scope in ('A2D', 'D2D'):
            codes.extend([
                2020,  # IMP-CLEAR
                2021,  # IMP-AGENCY-DEST
                2022,  # IMP-DOC-DEST
                2070,  # IMP-HANDLING-DEST
                2071,  # IMP-LOADING-DEST
                2072,  # IMP-CARTAGE-DEST
                2080,  # IMP-FSC-CARTAGE-DEST
            ])

        codes.extend(get_auto_product_code_ids(
            shipment_type='IMPORT',
            service_scope=service_scope,
            commodity_code=commodity_code,
            origin_code=origin,
            destination_code=destination,
            payment_term=payment_term,
            quote_date=quote_date,
        ))

        return sorted(list(set(codes)))
    
    def _calculate_charge_line(self, pc: ProductCode, leg: str) -> Optional[ChargeLine]:
        """Calculate a single charge line."""
        
        # Get COGS - route to local table for destination local categories
        cogs = self._get_cogs(pc, leg)
        
        # Get explicit Sell (for destination) - route to local table for local categories
        if leg == 'DESTINATION':
            sell_rate = self._get_destination_sell_rate(pc)
        else:
            sell_rate = self._get_sell_rate(pc, leg)
        
        # Skip if no rates found
        if not cogs and not sell_rate:
            return None
        
        # Calculate cost
        cost_amount = Decimal('0')
        cost_currency = 'AUD'  # Default for origin
        cost_eval = RuleEvaluation(CALCULATION_LOOKUP_RATE, Decimal('0.00'))
        
        if cogs:
            cost_eval = self._calculate_cogs_amount(cogs, pc)
            cost_amount = cost_eval.amount
            cost_currency = cogs.currency
            self._cost_cache[pc.code] = cost_amount
        
        # Determine sell amount based on leg and payment term
        sell_amount = Decimal('0')
        sell_currency = self.quote_currency
        pgk_basis: Optional[Decimal] = None
        cost_in_quote_for_margin: Optional[Decimal] = None
        fx_applied = False
        caf_applied = False
        margin_applied = False
        sell_eval = RuleEvaluation(CALCULATION_LOOKUP_RATE, Decimal('0.00'))
        
        if leg == 'DESTINATION' and sell_rate:
            # Destination: Use explicit sell rate
            base_sell = Decimal('0.00')
            if sell_rate.percent_rate:
                base_pc = pc.percent_of_product_code
                if base_pc:
                    base_sell = self._get_dest_sell_amount(base_pc)
            sell_eval = self._calculate_sell_amount(sell_rate, base_amount=base_sell)
            sell_amount = sell_eval.amount
            
            # Currency handling for destination charges
            # If sell rate currency != quote currency, we must convert.
            if sell_rate.currency == 'PGK':
                pgk_basis = sell_amount
            if sell_rate.currency != self.quote_currency:
                sell_amount = self._convert_cross_currency(
                    sell_amount, sell_rate.currency, self.quote_currency, role='SELL', product_code=pc.code
                )
                fx_applied = True
                caf_applied = True
            
            sell_currency = self.quote_currency
            
        else:
            # Origin/Freight: Cost-Plus
            sell_amount = cost_amount
            sell_eval = cost_eval
            
            # FX conversion if needed
            if cost_currency != self.quote_currency:
                sell_amount = self._convert_cross_currency(
                    cost_amount, cost_currency, self.quote_currency, role='COST', product_code=pc.code
                )
                fx_applied = True
                caf_applied = True
            cost_in_quote_for_margin = sell_amount
            
            # Apply margin
            sell_amount = self._apply_margin(sell_amount)
            margin_applied = True
            sell_currency = self.quote_currency
        
        # Calculate margin
        margin_amount = sell_amount - (cost_amount if not fx_applied else Decimal('0'))
        margin_percent = Decimal('0')
        if cost_amount > 0:
            # For proper margin calc, need to compare in same currency
            if fx_applied and cost_currency != sell_currency:
                # Convert cost to sell currency for comparison
                cost_in_quote_curr = (
                    cost_in_quote_for_margin if self._approved_caf and cost_in_quote_for_margin is not None
                    else self._convert_cross_currency(cost_amount, cost_currency, sell_currency)
                )
                margin_amount = sell_amount - cost_in_quote_curr
                if cost_in_quote_curr > 0:
                    margin_percent = (margin_amount / cost_in_quote_curr * 100).quantize(Decimal('0.1'))
            else:
                margin_amount = sell_amount - cost_amount
                margin_percent = (margin_amount / cost_amount * 100).quantize(Decimal('0.1'))
        
        # Calculate GST using PNG classification
        gst_category, gst_rate = get_png_gst_category(
            product_code=pc,
            shipment_type='IMPORT',
            leg=leg,
            standard_rate=self._standard_gst_rate,
        )
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        sell_incl_gst = sell_amount + gst_amount

        # Canonical PGK equivalents come only from conversions the engine performed or from native PGK.
        cost_pgk = sell_pgk = sell_pgk_incl_gst = None
        if self._approved_caf:
            if cost_amount == Decimal('0') or cost_currency == 'PGK':
                cost_pgk = cost_amount
            elif self.quote_currency == 'PGK' and cost_in_quote_for_margin is not None:
                cost_pgk = cost_in_quote_for_margin
            if sell_currency == 'PGK':
                sell_pgk = sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                sell_pgk_incl_gst = sell_incl_gst
            elif pgk_basis is not None:
                sell_pgk = pgk_basis
                sell_pgk_incl_gst = pgk_basis + (pgk_basis * gst_rate).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
        
        return ChargeLine(
            product_code_id=pc.id,
            product_code=pc.code,
            description=pc.description,
            category=pc.category,
            leg=leg,
            cost_amount=cost_amount,
            cost_currency=cost_currency,
            cost_source='COGS' if cogs else 'N/A',
            agent_name=cogs.agent.name if cogs and cogs.agent else None,
            sell_amount=sell_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            sell_currency=sell_currency,
            margin_amount=margin_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            margin_percent=margin_percent,
            fx_applied=fx_applied,
            caf_applied=caf_applied,
            margin_applied=margin_applied,
            gst_category=gst_category,
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            sell_incl_gst=sell_incl_gst,
            rule_family=sell_eval.rule_family if sell_eval.amount > 0 else cost_eval.rule_family,
            cost_pgk=cost_pgk,
            sell_pgk=sell_pgk,
            sell_pgk_incl_gst=sell_pgk_incl_gst,
        )

    def _missing_rate_placeholder(self, pc: ProductCode, leg: str) -> ChargeLine:
        """A visible missing-rate line: no amount, no FX, no CAF."""
        line = ChargeLine(
            product_code_id=pc.id,
            product_code=pc.code,
            description=pc.description,
            category=pc.category,
            leg=leg,
            cost_amount=Decimal('0'),
            cost_currency='PGK',
            cost_source='N/A',
            agent_name=None,
            sell_amount=Decimal('0'),
            sell_currency=self.quote_currency,
            margin_amount=Decimal('0'),
            margin_percent=Decimal('0'),
            notes=f"Requested rate missing for {pc.code}",
            rule_family=CALCULATION_LOOKUP_RATE,
        )
        line.is_rate_missing = True # Dynamically added for adapter detection
        return line

    def _missing_rate_line(self, pc: ProductCode, leg: str) -> ChargeLine:
        """Line for a requested ProductCode with no rate. Legacy: the PGK 300 customs brokerage default."""
        # [AMENDMENT] Requested Customs Brokerage Fee Default (PGK 300.00)
        if pc.id != 2020:
            return self._missing_rate_placeholder(pc, leg)
        line = ChargeLine(
            product_code_id=pc.id, product_code=pc.code, description=pc.description,
            category=pc.category, leg=leg, cost_amount=Decimal('0'),
            cost_currency='PGK', cost_source='Default', agent_name=None, sell_amount=Decimal('300.00'),
            sell_currency=self.quote_currency, margin_amount=Decimal('300.00'),
            margin_percent=Decimal('100.00'), notes="Default Customs Brokerage Fee applied.",
            rule_family=CALCULATION_FLAT,
        )
        # Handle FCY conversion for PREPAID quotes
        if self.quote_currency != 'PGK':
            line.sell_amount = self._convert_pgk_to_fcy(Decimal('300.00'))
            line.fx_applied = True
            line.caf_applied = True
        
        # Apply GST Classification
        gst_cat, gst_r = get_png_gst_category(
            product_code=pc, shipment_type='IMPORT', leg=leg, standard_rate=self._standard_gst_rate
        )
        line.gst_category = gst_cat
        line.gst_rate = gst_r
        # Force GST to 0 if rate is missing to prevent AUD 0.00 base with non-zero GST
        line.gst_amount = Decimal('0.00')
        line.sell_incl_gst = Decimal('0.00')
        return line

    @staticmethod
    def _to_quote_line_item(line: ChargeLine) -> QuoteLineItem:
        component = QuoteComponent.ORIGIN_LOCAL
        if line.leg == 'FREIGHT':
            component = QuoteComponent.FREIGHT
        elif line.leg == 'DESTINATION':
            component = QuoteComponent.DESTINATION_LOCAL
        unit_type = 'KG' if line.leg == 'FREIGHT' else 'SHIPMENT'
        is_spot_sourced = 'SPOT' in str(line.cost_source or '').upper()
        is_manual_override = any(token in str(line.cost_source or '').upper() for token in ['MANUAL', 'OVERRIDE'])
        return QuoteLineItem(
            product_code_id=line.product_code_id,
            product_code=line.product_code,
            description=line.description,
            component=component,
            basis=basis_for_unit(unit_type),
            rule_family=line.rule_family,
            unit_type=unit_type,
            quantity=Decimal('1.00'),
            currency=line.sell_currency,
            category=line.category,
            leg=line.leg,
            cost_amount=line.cost_amount,
            cost_currency=line.cost_currency,
            cost_source=normalize_cost_source(
                line.cost_source,
                is_spot_sourced=is_spot_sourced,
                is_manual_override=is_manual_override,
            ),
            agent_name=line.agent_name,
            sell_amount=line.sell_amount,
            sell_currency=line.sell_currency,
            margin_amount=line.margin_amount,
            margin_percent=line.margin_percent,
            tax_code=line.gst_category or 'GST',
            tax_amount=line.gst_amount,
            gst_category=line.gst_category,
            gst_rate=line.gst_rate,
            gst_amount=line.gst_amount,
            sell_incl_gst=line.sell_incl_gst,
            rate_source=normalize_rate_source(
                line.cost_source,
                is_spot_sourced=is_spot_sourced,
                is_manual_override=is_manual_override,
            ),
            calculation_notes=line.notes or None,
            is_spot_sourced=is_spot_sourced,
            is_manual_override=is_manual_override,
            is_rate_missing=getattr(line, 'is_rate_missing', False),
            notes=line.notes,
            fx_applied=line.fx_applied,
            caf_applied=line.caf_applied,
            margin_applied=line.margin_applied,
            cost_pgk=line.cost_pgk,
            sell_pgk=line.sell_pgk,
            sell_pgk_incl_gst=line.sell_pgk_incl_gst,
        )
    
    def _calculate_sell_amount(self, sell_rate, *, base_amount: Decimal = Decimal('0.00')) -> RuleEvaluation:
        """Calculate sell amount from explicit sell rate."""
        return evaluate_rate_lookup_rule(
            rate=sell_rate,
            quantity=self.weight,
            base_amount=base_amount,
        )
    
    def _get_dest_sell_amount(self, pc: ProductCode) -> Decimal:
        """Get destination sell amount for FSC base calculation."""
        sell_rate = self._get_destination_sell_rate(pc)
        
        if sell_rate:
            sell_amount = self._calculate_sell_amount(sell_rate).amount
            if sell_rate.currency != self.quote_currency:
                sell_amount = self._convert_cross_currency(
                    sell_amount, sell_rate.currency, self.quote_currency, role='SELL', product_code=pc.code
                )
            return sell_amount
        return Decimal('0')

    def _get_destination_sell_rate(self, pc: ProductCode):
        """
        Get destination sell rate.
        Routes to LocalSellRate for local categories, ImportSellRate for freight.
        """
        if is_local_rate_category(pc.category):
            return self._get_local_sell_rate(pc)
        
        try:
            return select_import_sell_rate(
                RateSelectionContext(
                    product_code_id=pc.id,
                    quote_date=self.quote_date,
                    origin_airport=self.origin,
                    destination_airport=self.destination,
                    currency=self.quote_currency,
                ),
                allow_pgk_fallback=self.payment_term == PaymentTerm.PREPAID and self.quote_currency != 'PGK',
            ).record
        except RateNotFoundError:
            return None
    
    def _get_cogs(self, pc: ProductCode, leg: Optional[str] = None):
        """
        Get COGS for a product code.
        Destination-local import charges live in LocalCOGSRate.
        Origin-local and freight import charges remain lane-based in ImportCOGS.
        """
        if leg == 'DESTINATION' and is_local_rate_category(pc.category):
            return self._get_local_cogs(pc, leg)

        metadata = {}
        if leg in {'ORIGIN', 'DESTINATION', 'LANE'}:
            metadata['rate_scope'] = leg

        try:
            return select_import_cogs_rate(
                RateSelectionContext(
                    product_code_id=pc.id,
                    quote_date=self.quote_date,
                    origin_airport=self.origin,
                    destination_airport=self.destination,
                    currency=self.buy_currency,
                    agent_id=self.preferred_agent_id,
                    carrier_id=self.preferred_carrier_id,
                    metadata=metadata,
                )
            ).record
        except RateNotFoundError:
            lane_cogs = None

        if leg == 'ORIGIN' and is_local_rate_category(pc.category):
            return self._get_local_cogs(pc, leg)

        return lane_cogs
    
    def _get_sell_rate(self, pc: ProductCode, leg: str):
        """
        Get sell rate for non-destination legs.
        Uses lane-based ImportSellRate (origin/freight sell is cost-plus).
        """
        try:
            return select_import_sell_rate(
                RateSelectionContext(
                    product_code_id=pc.id,
                    quote_date=self.quote_date,
                    origin_airport=self.origin,
                    destination_airport=self.destination,
                    currency=self.quote_currency,
                ),
                allow_pgk_fallback=False,
            ).record
        except RateNotFoundError:
            return None
    
    def _get_local_cogs(self, pc: ProductCode, leg: str):
        """
        Lookup local COGS from centralized table for IMPORT.

        Lookup order:
        - DESTINATION leg: destination station first.
        - ORIGIN leg: origin station first.
        """
        location_candidates = [self.origin] if leg == 'ORIGIN' else [self.destination]

        for location in location_candidates:
            try:
                return select_local_cogs_rate(
                    RateSelectionContext(
                        product_code_id=pc.id,
                        quote_date=self.quote_date,
                        location=location,
                        direction='IMPORT',
                        currency=self.buy_currency,
                        agent_id=self.preferred_agent_id,
                        carrier_id=self.preferred_carrier_id,
                    )
                ).record
            except RateNotFoundError:
                continue

        return None
    
    def _get_local_sell_rate(self, pc: ProductCode):
        """
        Lookup local sell rate from centralized table.
        
        Priority: Exact payment_term match first, then fallback to 'ANY'.
        
        Currency Rules for Import Destination Charges:
        - COLLECT: PGK (consignee in PNG pays in local currency)
        - PREPAID from AU: AUD 
        - PREPAID from other: USD
        """
        payment_term_value = self.payment_term.value if hasattr(self.payment_term, 'value') else str(self.payment_term)
        
        base_qs = LocalSellRate.objects.filter(
            product_code=pc,
            location=self.destination,
            direction='IMPORT',
            payment_term__in=[payment_term_value, 'ANY'],
            valid_from__lte=self.quote_date,
            valid_until__gte=self.quote_date
        )
        # Enforce rate-type compatibility for percentage ProductCodes.
        if pc.default_unit == ProductCode.UNIT_PERCENT:
            base_qs = base_qs.filter(
                rate_type='PERCENT',
                percent_of_product_code__isnull=False,
            )
        else:
            base_qs = base_qs.exclude(rate_type='PERCENT')

        try:
            return select_local_sell_rate(
                RateSelectionContext(
                    product_code_id=pc.id,
                    quote_date=self.quote_date,
                    location=self.destination,
                    direction='IMPORT',
                    payment_term=payment_term_value,
                    currency=self.quote_currency,
                ),
                queryset_override=base_qs,
                allow_pgk_fallback=self.payment_term == PaymentTerm.PREPAID and self.quote_currency != 'PGK',
            ).record
        except RateNotFoundError:
            return None
