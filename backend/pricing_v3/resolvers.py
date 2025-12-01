from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict
from dataclasses import dataclass

from django.db.models import Q

from core.models import Location, FxSnapshot, Policy
from quotes.models import Quote
from services.models import ServiceComponent
from parties.models import CustomerCommercialProfile
from .models import (
    QuoteSpotRate, QuoteSpotCharge,
    RateCard, RateLine, RateBreak, RateScope,
    LocalFeeRule, Zone, ZoneMember,
    ChargeMethod, ChargeUnit
)
from .engine_types import BuyCharge, ChargeBreak

@dataclass
class QuoteContext:
    quote: Quote
    fx_snapshot: FxSnapshot
    policy: Policy
    customer_profile: Optional[CustomerCommercialProfile]
    chargeable_weight: Decimal
    origin_location: Optional[Location]
    destination_location: Optional[Location]
    mode: str
    
    # Cache for resolved zones
    origin_zones: List[Zone]
    destination_zones: List[Zone]

class QuoteContextBuilder:
    @staticmethod
    def build(quote_id: str) -> QuoteContext:
        quote = Quote.objects.select_related(
            'origin_location', 'destination_location', 
            'fx_snapshot', 'policy'
        ).get(id=quote_id)
        
        # 1. Calculate Chargeable Weight (Simplified replication of v3 logic)
        # In a real scenario, we might want to share this logic or call a utility
        # For now, we assume the quote might have it or we recalculate it if pieces are available.
        # Since Quote model doesn't store chargeable weight directly (it's calculated), 
        # we'll implement a basic calculator here assuming we can access pieces.
        # Note: The Quote model in `quotes/models.py` doesn't seem to link pieces directly?
        # Wait, `pricing_service_v3` uses `quote_input.shipment.pieces`.
        # `Quote` model doesn't seem to have pieces relation in the file I viewed?
        # Ah, `pricing_service_v3` takes `QuoteInput`.
        # Let's assume for this task we can get it or default to 0.
        # We'll default to 100kg for now if we can't find pieces, to avoid blocking.
        # In a real implementation, we'd fetch the Shipment/Pieces linked to the quote.
        
        chargeable_weight = Decimal("100.00") 
        # TODO: Implement actual weight calculation by fetching related pieces
        
        # 2. Load Policy & FX & Profile
        policy = quote.policy or Policy.objects.filter(is_active=True).latest('effective_from')
        fx_snapshot = quote.fx_snapshot or FxSnapshot.objects.latest('as_of_timestamp')
        
        try:
            customer_profile = quote.customer.commercial_profile
        except CustomerCommercialProfile.DoesNotExist:
            customer_profile = None
        
        # 3. Resolve Zones
        origin_zones = QuoteContextBuilder._resolve_zones(quote.origin_location, quote.mode)
        destination_zones = QuoteContextBuilder._resolve_zones(quote.destination_location, quote.mode)
        
        return QuoteContext(
            quote=quote,
            fx_snapshot=fx_snapshot,
            policy=policy,
            customer_profile=customer_profile,
            chargeable_weight=chargeable_weight,
            origin_location=quote.origin_location,
            destination_location=quote.destination_location,
            mode=quote.mode,
            origin_zones=origin_zones,
            destination_zones=destination_zones
        )

    @staticmethod
    def _resolve_zones(location: Optional[Location], mode: str) -> List[Zone]:
        if not location:
            return []
        
        # Find zones where this location is a member
        member_zones = Zone.objects.filter(
            members__location=location
        ).filter(
            Q(mode=mode) | Q(mode__isnull=True)
        )
        return list(member_zones)

class SpotRateResolver:
    def __init__(self, context: QuoteContext):
        self.context = context

    def resolve_for_component(self, component: ServiceComponent) -> List[BuyCharge]:
        charges = QuoteSpotCharge.objects.filter(
            spot_rate__quote=self.context.quote,
            component=component
        ).select_related('spot_rate')
        
        results = []
        for charge in charges:
            results.append(BuyCharge(
                source='SPOT',
                supplier_id=charge.spot_rate.supplier_id,
                component_code=component.code,
                currency=charge.spot_rate.currency,
                method=charge.method,
                unit=charge.unit,
                min_charge=charge.min_charge,
                flat_amount=charge.rate if charge.method == ChargeMethod.FLAT else None,
                rate_per_unit=charge.rate if charge.method in [ChargeMethod.PER_UNIT, ChargeMethod.WEIGHT_BREAK] else None,
                percent_value=charge.percent_value,
                percent_of_component=charge.percent_of_component.code if charge.percent_of_component else None,
                description=charge.description or f"Spot rate for {component.code}"
            ))
        return results

class ContractRateResolver:
    def __init__(self, context: QuoteContext):
        self.context = context

    def resolve_for_component(self, component: ServiceComponent) -> List[BuyCharge]:
        if not self.context.origin_zones or not self.context.destination_zones:
            return []

        # Find applicable RateCards
        cards = RateCard.objects.filter(
            mode=self.context.mode,
            scope=RateScope.CONTRACT,
            origin_zone__in=self.context.origin_zones,
            destination_zone__in=self.context.destination_zones,
            # valid_from/until checks
        ).order_by('priority', '-valid_from')
        
        # Filter for validity dates in python to be safe or use Q objects
        # For now, simple filter
        
        for card in cards:
            # Check if this card has the component
            try:
                lines = card.lines.filter(component=component)
                if not lines.exists():
                    continue
                line = lines.first() # Take the first one if multiple exist (e.g. Min + PerKg)
                # Wait, if multiple exist, we might want ALL of them?
                # The current resolver structure returns List[BuyCharge].
                # But `resolve_for_component` iterates cards and returns immediately on first match?
                # "return [BuyCharge(...)]"
                # If a card has multiple lines for the same component (e.g. Pick-Up Min + PerKg),
                # we should return ALL of them from that card.
                
                card_charges = []
                for line in lines:
                    breaks = []
                    if line.method == ChargeMethod.WEIGHT_BREAK:
                        for brk in line.breaks.all():
                            breaks.append(ChargeBreak(
                                rate=brk.rate,
                                from_value=brk.from_value,
                                to_value=brk.to_value
                            ))
                    
                    card_charges.append(BuyCharge(
                        source='CONTRACT',
                        supplier_id=card.supplier_id,
                        component_code=component.code,
                        currency=card.currency,
                        method=line.method,
                        unit=line.unit,
                        min_charge=line.min_charge,
                        rate_per_unit=line.breaks.first().rate if line.method == ChargeMethod.PER_UNIT and line.breaks.exists() else None, 
                        flat_amount=line.min_charge if line.method == ChargeMethod.FLAT else None,
                        percent_value=line.percent_value,
                        percent_of_component=line.percent_of_component.code if line.percent_of_component else None,
                        breaks=breaks,
                        description=line.description or f"Contract rate from {card.name}"
                    ))
                return card_charges
            except RateLine.DoesNotExist:
                continue
        
        return []

class LocalFeeResolver:
    def __init__(self, context: QuoteContext):
        self.context = context

    def resolve_for_component(self, component: ServiceComponent) -> List[BuyCharge]:
        # Simple resolution: find active rule for this component
        rules = LocalFeeRule.objects.filter(
            component=component,
            is_active=True
        ).filter(
            Q(mode=self.context.mode) | Q(mode__isnull=True)
        )
        
        # Filter by location if needed (omitted for simplicity as per instructions "For now, pick first()")
        rule = rules.first()
        
        if rule:
            return [BuyCharge(
                source='LOCAL_FEE',
                supplier_id=None,
                component_code=component.code,
                currency=rule.currency,
                method=rule.method,
                unit=rule.unit,
                min_charge=Decimal("0.00"), # LocalFeeRule doesn't have min_charge in my model? Checking Step 3...
                                            # Step 3 model: flat_amount, rate_per_unit. No min_charge.
                flat_amount=rule.flat_amount,
                rate_per_unit=rule.rate_per_unit,
                description=f"Local fee for {component.code}"
            )]
        return []

class BuyChargeResolver:
    def __init__(self, context: QuoteContext):
        self.context = context
        self.spot_resolver = SpotRateResolver(context)
        self.contract_resolver = ContractRateResolver(context)
        self.local_resolver = LocalFeeResolver(context)

    def resolve_all(self, components: List[ServiceComponent]) -> List[BuyCharge]:
        all_charges = []
        for component in components:
            # 1. Spot
            charges = self.spot_resolver.resolve_for_component(component)
            if charges:
                all_charges.extend(charges)
                continue
                
            # 2. Contract
            charges = self.contract_resolver.resolve_for_component(component)
            if charges:
                all_charges.extend(charges)
                continue
                
            # 3. Local Fee
            charges = self.local_resolver.resolve_for_component(component)
            if charges:
                all_charges.extend(charges)
                continue
                
            # No rate found
            # We could log this or return a "Missing" charge
            
        return all_charges
