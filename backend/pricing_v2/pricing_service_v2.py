from typing import List, Optional

from .dataclasses_v2 import BuyMenu, BuyOffer, QuoteContext


import os
from .adapters.ratecard_adapter import RateCardAdapter
from .adapters.spot_adapter import SpotAdapter

import pybreaker

rate_card_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)
spot_adapter_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)

def build_buy_menu(context: QuoteContext) -> BuyMenu:
    """Builds a menu of all available BUY offers from all adapters."""
    offers = []

    if os.environ.get("RATECARD_ADAPTER_ENABLED", "False").lower() == "true":
        try:
            rate_card_adapter = RateCardAdapter()
            offers.extend(rate_card_breaker.call(rate_card_adapter.collect, context))
        except pybreaker.CircuitBreakerError:
            # Log that the circuit breaker is open
            pass

    if os.environ.get("SPOT_ADAPTER_ENABLED", "False").lower() == "true":
        try:
            spot_adapter = SpotAdapter()
            offers.extend(spot_adapter_breaker.call(spot_adapter.collect, context))
        except pybreaker.CircuitBreakerError:
            # Log that the circuit breaker is open
            pass

    return BuyMenu(offers=offers)


def select_best_offer(context: QuoteContext, menu: BuyMenu) -> Optional[BuyOffer]:
    """Selects the best offer from the menu based on business rules."""
    if not menu.offers:
        return None
    # Placeholder: just return the first offer
    return menu.offers[0]
