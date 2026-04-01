from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date

from django.db.models import Q

from core.commodity import DEFAULT_COMMODITY_CODE
from pricing_v4.commodity_rules import get_auto_product_code_ids, is_product_code_enabled
from pricing_v4.models import ProductCode
from pricing_v4.models import DomesticCOGS, DomesticSellRate, Surcharge
from core.charge_rules import evaluate_charge_rule
from pricing_v4.engine.result_types import QuoteLineItem, QuoteResult, build_tax_breakdown

@dataclass
class BillableCharge:
    description: str
    amount: Decimal
    product_code: str = ''
    is_gst_applicable: bool = True
    agent_name: Optional[str] = None  # NEW

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
    ):
        self.origin = cogs_origin  # e.g., 'POM'
        self.destination = destination  # e.g., 'LAE'
        self.weight = Decimal(str(weight_kg))
        self.service_scope = service_scope  # D2D, D2A, A2D, A2A
        self.service_type = 'DOMESTIC_AIR'
        self.quote_date = quote_date or date.today()
        self.commodity_code = commodity_code
        
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
        # COGS
        cogs = (
            DomesticCOGS.objects.filter(
                origin_zone=self.origin,
                destination_zone=self.destination,
                product_code__code='DOM-FRT-AIR',
                valid_from__lte=self.quote_date,
                valid_until__gte=self.quote_date,
            )
            .select_related('agent')
            .order_by('-valid_from')
            .first()
        )
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
            cost = self._calc_weight_based_amount(cogs.rate_per_kg, cogs.weight_breaks, cogs.min_charge)
            if cost > 0:
                agent_name = cogs.agent.name if cogs.agent else None
                cogs_breakdown.append(BillableCharge("Air Freight (Cost)", cost, product_code='DOM-FRT-AIR', agent_name=agent_name))
            
        # SELL
        sell = (
            DomesticSellRate.objects.filter(
                origin_zone=self.origin,
                destination_zone=self.destination,
                product_code__code='DOM-FRT-AIR',
                valid_from__lte=self.quote_date,
                valid_until__gte=self.quote_date,
            )
            .order_by('-valid_from')
            .first()
        )
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
            amt = self._calc_weight_based_amount(sell.rate_per_kg, sell.weight_breaks, sell.min_charge)
            if amt > 0:
                sell_breakdown.append(BillableCharge("Air Freight", amt, product_code='DOM-FRT-AIR'))

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
            amount = self._calc_surcharge_amount(sur, basis_amount=cogs_freight_basis)
            cogs_breakdown.append(BillableCharge(f"{sur.product_code.description} (Cost)", amount, product_code=sur.product_code.code))

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
            amount = self._calc_surcharge_amount(sur, basis_amount=sell_freight_basis)
            sell_breakdown.append(BillableCharge(sur.product_code.description, amount, product_code=sur.product_code.code))

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
                    category='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'SURCHARGE',
                    leg='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'ORIGIN',
                ),
            )
            item.cost_amount += charge.amount
            item.cost_currency = 'PGK'
            item.cost_source = 'COGS'
            item.agent_name = charge.agent_name

        for charge in sell_breakdown:
            item = indexed.setdefault(
                charge.product_code,
                QuoteLineItem(
                    product_code=charge.product_code,
                    description=charge.description,
                    category='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'SURCHARGE',
                    leg='FREIGHT' if charge.product_code == 'DOM-FRT-AIR' else 'ORIGIN',
                ),
            )
            item.sell_amount += charge.amount
            item.sell_currency = 'PGK'
            item.gst_category = 'service_in_PNG'
            item.gst_rate = Decimal('0.10')
            item.gst_amount = item.sell_amount * Decimal('0.10')
            item.sell_incl_gst = item.sell_amount + item.gst_amount
            item.margin_amount = item.sell_amount - item.cost_amount
            if item.cost_amount > 0:
                item.margin_percent = (item.margin_amount / item.cost_amount * Decimal('100')).quantize(Decimal('0.01'))

        return list(indexed.values())

    def _calc_surcharge_amount(self, surcharge: Surcharge, basis_amount: Decimal = Decimal('0.00')) -> Decimal:
        amount = Decimal('0.00')
        shipment_ctx = {
            'chargeable_weight_kg': self.weight,
            'shipment_count': Decimal('1'),
            'basis_amounts': {'freight': basis_amount},
        }
        
        if surcharge.rate_type == 'FLAT':
            amount = evaluate_charge_rule(
                {'calculation_type': 'FLAT', 'rate': surcharge.amount, 'min_amount': surcharge.min_charge},
                shipment_ctx,
            )
        elif surcharge.rate_type == 'PER_KG':
            calc_type = 'MIN_OR_PER_UNIT' if surcharge.min_charge else 'PER_UNIT'
            amount = evaluate_charge_rule(
                {
                    'calculation_type': calc_type,
                    'unit_type': 'KG',
                    'rate': surcharge.amount,
                    'min_amount': surcharge.min_charge,
                },
                shipment_ctx,
            )
        elif surcharge.rate_type == 'PERCENT':
            amount = evaluate_charge_rule(
                {
                    'calculation_type': 'PERCENT_OF',
                    'percent': surcharge.amount,
                    'percent_basis': 'freight',
                    'min_amount': surcharge.min_charge,
                    'max_amount': surcharge.max_charge,
                },
                shipment_ctx,
            )
            
        return amount

    def _calc_weight_based_amount(self, rate_per_kg: Optional[Decimal], weight_breaks: Optional[List[Dict]], min_charge: Optional[Decimal]) -> Decimal:
        """
        Calculate amount using weight breaks when provided; fallback to flat rate_per_kg.
        """
        amount = Decimal('0.00')
        if weight_breaks:
            # Expect list of {"min_kg": x, "rate": y}; take highest min_kg the weight qualifies for
            sorted_breaks = sorted(weight_breaks, key=lambda b: Decimal(str(b.get('min_kg', 0))), reverse=True)
            for tier in sorted_breaks:
                min_kg = Decimal(str(tier.get('min_kg', 0)))
                if self.weight >= min_kg:
                    amount = self.weight * Decimal(str(tier.get('rate', 0)))
                    break
        elif rate_per_kg:
            calc_type = 'MIN_OR_PER_UNIT' if min_charge else 'PER_UNIT'
            amount = evaluate_charge_rule(
                {
                    'calculation_type': calc_type,
                    'unit_type': 'KG',
                    'rate': rate_per_kg,
                    'min_amount': min_charge,
                },
                {'chargeable_weight_kg': self.weight},
            )
        elif min_charge:
            amount = evaluate_charge_rule(
                {'calculation_type': 'FLAT', 'rate': amount, 'min_amount': min_charge},
                {'shipment_count': Decimal('1')},
            )
        
        return amount
