from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date

from django.db.models import Q

from core.commodity import DEFAULT_COMMODITY_CODE
from pricing_v4.commodity_rules import get_auto_product_code_ids, is_product_code_enabled
from pricing_v4.models import ProductCode
from pricing_v4.models import DomesticCOGS, DomesticSellRate, Surcharge
from pricing_v4.services.rate_selector import (
    RateNotFoundError,
    RateSelectionContext,
    select_domestic_cogs_rate,
    select_domestic_sell_rate,
)
from core.charge_rules import (
    CALCULATION_LOOKUP_RATE,
    RuleEvaluation,
    evaluate_rate_lookup_rule,
)
from quotes.quote_result_contract import (
    QuoteComponent,
    QuoteCostSource,
    QuoteRateSource,
    basis_for_unit,
)
from pricing_v4.engine.result_types import QuoteLineItem, QuoteResult, build_tax_breakdown

@dataclass
class BillableCharge:
    description: str
    amount: Decimal
    product_code: str = ''
    is_gst_applicable: bool = True
    agent_name: Optional[str] = None
    rule_family: str = CALCULATION_LOOKUP_RATE
    is_rate_missing: bool = False

class DomesticPricingEngine:
    """
    Engine for Domestic Air Freight (within PNG).
    
    Principles:
    - Route-specific Freight Rates (via DomesticCOGS/DomesticSellRate)
    - Global Surcharges (via Surcharge model, filtered by ServiceType)
    - Simple additions (Cost + Surcharges, Sell + Surcharges)
    - GST added at end for Domestic
    """

    def __init__(
        self,
        cogs_origin,
        destination,
        weight_kg,
        service_scope='A2A',
        quote_date: Optional[date] = None,
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        preferred_agent_id: Optional[int] = None,
        preferred_carrier_id: Optional[int] = None,
        buy_currency: Optional[str] = None,
    ):
        self.origin = cogs_origin  # e.g., 'POM'
        self.destination = destination  # e.g., 'LAE'
        self.weight = Decimal(str(weight_kg))
        self.service_scope = service_scope  # D2D, D2A, A2D, A2A
        self.service_type = 'DOMESTIC_AIR'
        self.quote_date = quote_date or date.today()
        self.commodity_code = commodity_code
        self.preferred_agent_id = preferred_agent_id
        self.preferred_carrier_id = preferred_carrier_id
        self.buy_currency = (buy_currency or "").strip().upper() or None
        
        # Validation: Door service only available in specific ports
        self.DOOR_PORTS = ['POM', 'LAE']
        self._validate_service_scope()

    def _validate_service_scope(self):
        """
        Enforce Cartage Restrictions:
        - Origin Door (Pickup) allowed only if Origin is in DOOR_PORTS
        - Destination Door (Delivery) allowed only if Destination is in DOOR_PORTS
        """
        is_origin_door = self.service_scope in ['D2D', 'D2A']
        is_dest_door = self.service_scope in ['D2D', 'A2D']
        
        if is_origin_door and self.origin not in self.DOOR_PORTS:
            raise ValueError(f"Pickup not available for {self.origin}. Door service only in {self.DOOR_PORTS}")
            
        if is_dest_door and self.destination not in self.DOOR_PORTS:
            raise ValueError(f"Delivery not available for {self.destination}. Door service only in {self.DOOR_PORTS}")

    @staticmethod
    def get_requested_product_code_ids(
        service_scope: str = 'A2A',
        commodity_code: str = DEFAULT_COMMODITY_CODE,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        quote_date: Optional[date] = None,
    ) -> List[int]:
        codes: list[int] = []
        freight_id = ProductCode.objects.filter(code='DOM-FRT-AIR').values_list('id', flat=True).first()
        if freight_id:
            codes.append(freight_id)
        codes.extend(get_auto_product_code_ids(
            shipment_type='DOMESTIC',
            service_scope=service_scope,
            commodity_code=commodity_code,
            origin_code=origin,
            destination_code=destination,
            quote_date=quote_date,
        ))
        return sorted(list(set(codes)))

    def calculate_quote(self) -> QuoteResult:
        cogs_breakdown: List[BillableCharge] = []
        sell_breakdown: List[BillableCharge] = []
        
        # 1. Calculate Freight (Route Specific)
        self._calculate_freight(cogs_breakdown, sell_breakdown)
        
        # 2. Calculate Surcharges (Global)
        self._calculate_surcharges(cogs_breakdown, sell_breakdown)

        line_items = self._build_line_items(cogs_breakdown, sell_breakdown)
        
        return QuoteResult(
            line_items=line_items,
            total_cost_pgk=sum((item.cost_amount for item in line_items), Decimal('0.00')),
            total_sell_pgk=sum((item.sell_amount for item in line_items), Decimal('0.00')),
            fx_applied=False,
            tax_breakdown=build_tax_breakdown(line_items, default_labels=['service_in_PNG']),
            origin=self.origin,
            destination=self.destination,
            quote_date=self.quote_date,
            chargeable_weight_kg=self.weight,
            direction='DOMESTIC',
            service_scope=self.service_scope,
            quote_currency='PGK',
            currency='PGK',
            total_margin=sum((item.margin_amount for item in line_items), Decimal('0.00')),
            total_gst=sum((item.gst_amount for item in line_items), Decimal('0.00')),
            total_sell_incl_gst=sum((item.sell_incl_gst for item in line_items), Decimal('0.00')),
        )

    def _calculate_freight(self, cogs_breakdown: List[BillableCharge], sell_breakdown: List[BillableCharge]):
        # COGS – deterministic: latest valid_from wins
        freight_pc = ProductCode.objects.filter(code='DOM-FRT-AIR').values_list('id', flat=True).first()
        cogs = None
        if freight_pc:
            try:
                cogs = select_domestic_cogs_rate(
                    RateSelectionContext(
                        product_code_id=freight_pc,
                        quote_date=self.quote_date,
                        origin_zone=self.origin,
                        destination_zone=self.destination,
                        currency=self.buy_currency or 'PGK',
                        agent_id=self.preferred_agent_id,
                        carrier_id=self.preferred_carrier_id,
                    )
                ).record
            except RateNotFoundError:
                cogs = None
        if cogs:
            if not is_product_code_enabled(
                shipment_type='DOMESTIC',
                service_scope=self.service_scope,
                commodity_code=self.commodity_code,
                product_code_id=cogs.product_code_id,
                origin_code=self.origin,
                destination_code=self.destination,
                quote_date=self.quote_date,
            ):
                cogs = None
        if cogs:
            cost_eval = self._evaluate_rate_record(cogs)
            if cost_eval.amount > 0:
                agent_name = cogs.agent.name if cogs.agent else None
                cogs_breakdown.append(
                    BillableCharge(
                        "Air Freight (Cost)",
                        cost_eval.amount,
                        product_code='DOM-FRT-AIR',
                        agent_name=agent_name,
                        rule_family=cost_eval.rule_family,
                    )
                )
            
        # SELL – deterministic: latest valid_from wins
        sell = None
        if freight_pc:
            try:
                sell = select_domestic_sell_rate(
                    RateSelectionContext(
                        product_code_id=freight_pc,
                        quote_date=self.quote_date,
                        origin_zone=self.origin,
                        destination_zone=self.destination,
                        currency='PGK',
                    )
                ).record
            except RateNotFoundError:
                sell = None
        if sell:
            if not is_product_code_enabled(
                shipment_type='DOMESTIC',
                service_scope=self.service_scope,
                commodity_code=self.commodity_code,
                product_code_id=sell.product_code_id,
                origin_code=self.origin,
                destination_code=self.destination,
                quote_date=self.quote_date,
            ):
                sell = None
        if sell:
            sell_eval = self._evaluate_rate_record(sell)
            if sell_eval.amount > 0:
                sell_breakdown.append(
                    BillableCharge(
                        "Air Freight",
                        sell_eval.amount,
                        product_code='DOM-FRT-AIR',
                        rule_family=sell_eval.rule_family,
                    )
                )

        # [FIX 🔴] Emit missing-rate placeholder if no COGS AND no Sell found
        has_cogs = any(c.product_code == 'DOM-FRT-AIR' for c in cogs_breakdown)
        has_sell = any(c.product_code == 'DOM-FRT-AIR' for c in sell_breakdown)
        if not has_cogs and not has_sell:
            placeholder = BillableCharge(
                description="Air Freight",
                amount=Decimal('0'),
                product_code='DOM-FRT-AIR',
                is_rate_missing=True,
            )
            cogs_breakdown.append(placeholder)
            sell_breakdown.append(placeholder)

    def _calculate_surcharges(self, cogs_breakdown: List[BillableCharge], sell_breakdown: List[BillableCharge]):
        cogs_freight_basis = sum(
            (c.amount for c in cogs_breakdown if c.product_code == 'DOM-FRT-AIR'),
            Decimal('0.00'),
        )
        sell_freight_basis = sum(
            (c.amount for c in sell_breakdown if c.product_code == 'DOM-FRT-AIR'),
            Decimal('0.00'),
        )

        # COGS Surcharges (prefetch product_code to avoid N+1)
        cogs_surcharges = Surcharge.objects.filter(
            service_type=self.service_type, 
            rate_side='COGS',
            is_active=True,
            valid_from__lte=self.quote_date,
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=self.quote_date)
        ).select_related('product_code')
        for sur in cogs_surcharges:
            if not is_product_code_enabled(
                shipment_type='DOMESTIC',
                service_scope=self.service_scope,
                commodity_code=self.commodity_code,
                product_code_id=sur.product_code_id,
                origin_code=self.origin,
                destination_code=self.destination,
                quote_date=self.quote_date,
            ):
                continue
            surcharge_eval = self._calc_surcharge_amount(sur, basis_amount=cogs_freight_basis)
            cogs_breakdown.append(
                BillableCharge(
                    f"{sur.product_code.description} (Cost)",
                    surcharge_eval.amount,
                    product_code=sur.product_code.code,
                    rule_family=surcharge_eval.rule_family,
                )
            )

        # SELL Surcharges (prefetch product_code to avoid N+1)
        sell_surcharges = Surcharge.objects.filter(
            service_type=self.service_type, 
            rate_side='SELL',
            is_active=True,
            valid_from__lte=self.quote_date,
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=self.quote_date)
        ).select_related('product_code')
        for sur in sell_surcharges:
            if not is_product_code_enabled(
                shipment_type='DOMESTIC',
                service_scope=self.service_scope,
                commodity_code=self.commodity_code,
                product_code_id=sur.product_code_id,
                origin_code=self.origin,
                destination_code=self.destination,
                quote_date=self.quote_date,
            ):
                continue
            surcharge_eval = self._calc_surcharge_amount(sur, basis_amount=sell_freight_basis)
            sell_breakdown.append(
                BillableCharge(
                    sur.product_code.description,
                    surcharge_eval.amount,
                    product_code=sur.product_code.code,
                    rule_family=surcharge_eval.rule_family,
                )
            )

    def _build_line_items(
        self,
        cogs_breakdown: List[BillableCharge],
        sell_breakdown: List[BillableCharge],
    ) -> List[QuoteLineItem]:
        indexed: Dict[str, QuoteLineItem] = {}

        for charge in cogs_breakdown:
            item = indexed.setdefault(
                charge.product_code,
                QuoteLineItem(
                    product_code=charge.product_code,
                    description=charge.description.replace(" (Cost)", ""),
                    component=QuoteComponent.FREIGHT if charge.product_code == 'DOM-FRT-AIR' else QuoteComponent.ORIGIN_LOCAL,
                    basis=basis_for_unit('KG' if charge.product_code == 'DOM-FRT-AIR' else 'SHIPMENT'),
                    rule_family=charge.rule_family or CALCULATION_LOOKUP_RATE,
                    unit_type='KG' if charge.product_code == 'DOM-FRT-AIR' else 'SHIPMENT',
                    quantity=Decimal('1.00'),
                    currency='PGK',
                    category='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'SURCHARGE',
                    leg='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'ORIGIN',
                    is_rate_missing=charge.is_rate_missing,
                ),
            )
            item.cost_amount += charge.amount
            item.cost_currency = 'PGK'
            item.cost_source = QuoteCostSource.DB_TARIFF if not charge.is_rate_missing else 'N/A'
            item.rate_source = QuoteRateSource.DB_TARIFF if not charge.is_rate_missing else 'N/A'
            item.agent_name = charge.agent_name
            item.rule_family = charge.rule_family
            if charge.is_rate_missing:
                item.is_rate_missing = True
                item.included_in_total = False
                item.notes = f"Rate missing for DOM-FRT-AIR {self.origin}→{self.destination}"

        for charge in sell_breakdown:
            item = indexed.setdefault(
                charge.product_code,
                QuoteLineItem(
                    product_code=charge.product_code,
                    description=charge.description,
                    component=QuoteComponent.FREIGHT if charge.product_code == 'DOM-FRT-AIR' else QuoteComponent.ORIGIN_LOCAL,
                    basis=basis_for_unit('KG' if charge.product_code == 'DOM-FRT-AIR' else 'SHIPMENT'),
                    rule_family=charge.rule_family or CALCULATION_LOOKUP_RATE,
                    unit_type='KG' if charge.product_code == 'DOM-FRT-AIR' else 'SHIPMENT',
                    quantity=Decimal('1.00'),
                    currency='PGK',
                    category='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'SURCHARGE',
                    leg='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'ORIGIN',
                    is_rate_missing=charge.is_rate_missing,
                ),
            )
            item.sell_amount += charge.amount
            item.sell_currency = 'PGK'
            item.tax_code = 'service_in_PNG'
            item.rule_family = charge.rule_family or item.rule_family
            item.gst_category = 'service_in_PNG'
            item.gst_rate = Decimal('0.10')
            item.gst_amount = item.sell_amount * Decimal('0.10')
            item.tax_amount = item.gst_amount
            item.sell_incl_gst = item.sell_amount + item.gst_amount
            item.margin_amount = item.sell_amount - item.cost_amount
            if item.cost_amount > 0:
                item.margin_percent = (item.margin_amount / item.cost_amount * Decimal('100')).quantize(Decimal('0.01'))

        return list(indexed.values())

    def _calc_surcharge_amount(self, surcharge: Surcharge, basis_amount: Decimal = Decimal('0.00')) -> RuleEvaluation:
        return evaluate_rate_lookup_rule(
            rate=surcharge,
            quantity=self.weight,
            base_amount=basis_amount,
        )

    def _evaluate_rate_record(self, rate) -> RuleEvaluation:
        return evaluate_rate_lookup_rule(
            rate=rate,
            quantity=self.weight,
        )
