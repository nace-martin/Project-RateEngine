from abc import ABC, abstractmethod
from typing import List

from ..dataclasses_v2 import BuyOffer, QuoteContext


class BaseBuyAdapter(ABC):
    """Abstract base class for a BUY-side pricing adapter."""

    @abstractmethod
    def collect(self, context: QuoteContext) -> List[BuyOffer]:
        """Given a quote context, return a list of applicable BuyOffers."""
        raise NotImplementedError
