from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import date  # Added for date checks

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
# Import the new Buy-Side Adapter models
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate

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
        # 1. Try to resolve using new Partner Rate Cards (Airport-to-Airport Lanes)
        partner_charges = self._resolve_partner_rates(component)
        if partner_charges:
            return partner_charges

        # 2. Fallback to Zone-based Contract Rates (Legacy/Generic)
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
        
        for card in cards:
            # Check if this card has the component
            try:
                lines = card.lines.filter(component=component)
                if not lines.exists():
                    continue
                
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

    def _resolve_partner_rates(self, component: ServiceComponent) -> List[BuyCharge]:
        """
        Resolves rates from the new PartnerRateCard system (feat-003) which uses
        direct Airport/Port lanes instead of Zones.
        """
        origin_loc = self.context.origin_location
        dest_loc = self.context.destination_location

        # Ensure we have locations
        if not origin_loc or not dest_loc:
            return []
            
        # Extract direct airport references
        # Note: getattr handles cases where the relation might be missing on the model instance temporarily
        origin_airport = getattr(origin_loc, 'airport', None)
        dest_airport = getattr(dest_loc, 'airport', None)

        # Fallback: If location is a City (or has no direct airport link), try to resolve via City
        if not origin_airport and origin_loc.city:
            # Find the primary airport for this city (or just the first one found)
            # In a real system, we might need more logic to pick the "main" airport
            from core.models import Airport
            origin_airport = Airport.objects.filter(city=origin_loc.city).first()

        if not dest_airport and dest_loc.city:
            from core.models import Airport
            dest_airport = Airport.objects.filter(city=dest_loc.city).first()

        if not origin_airport or not dest_airport:
            return []

        today = date.today()

        # Find matching lanes for these airports
        # We query lanes directly as they hold the location logic
        lanes = PartnerRateLane.objects.filter(
            mode='AIR', # Currently strictly AIR as per model spec
            origin_airport=origin_airport,
            destination_airport=dest_airport,
        ).select_related('rate_card', 'rate_card__supplier')

        # Filter lanes by Rate Card validity
        valid_lanes = []
        for lane in lanes:
            card = lane.rate_card
            if card.valid_from and card.valid_from > today:
                continue
            if card.valid_until and card.valid_until < today:
                continue
            valid_lanes.append(lane)

        # Iterate through valid lanes to find one that has a rate for this component
        for lane in valid_lanes:
            # Check for rates matching the component
            partner_rates = lane.rates.filter(service_component=component)
            
            if not partner_rates.exists():
                continue

            results = []
            for rate in partner_rates:
                # Map PartnerRate (New Model) to BuyCharge (Engine Types)
                
                # Determine Charge Method based on Unit
                method = 'PER_UNIT'
                rate_val = Decimal("0.00")
                flat_val = None

                if rate.unit == 'PER_KG':
                    method = 'PER_UNIT'
                    rate_val = rate.rate_per_kg_fcy or Decimal("0.00")
                elif rate.unit == 'SHIPMENT':
                    method = 'FLAT'
                    flat_val = rate.rate_per_shipment_fcy or Decimal("0.00")
                
                results.append(BuyCharge(
                    source='CONTRACT', # We map this to CONTRACT so it's treated as a standard rate
                    supplier_id=lane.rate_card.supplier.id,
                    component_code=component.code,
                    currency=lane.rate_card.currency_code,
                    method=method,
                    unit=rate.unit,
                    min_charge=rate.min_charge_fcy or Decimal("0.00"),
                    rate_per_unit=rate_val,
                    flat_amount=flat_val,
                    description=f"Partner Rate: {lane.rate_card.name}",
                    breaks=[] # No breaks in this simple model yet
                ))
            
            return results # Return rates from the first matching lane found

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
                min_charge=Decimal("0.00"), 
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
                
            # 2. Contract (Zones OR Partner Lanes)
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
            
        return all_charges
