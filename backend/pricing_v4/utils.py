from __future__ import annotations

from typing import Type, TypeVar, Any
from django.db import models
from .services.pricing_domain_service import PricingDomainService

T = TypeVar('T', bound=models.Model)

def safe_save_v4_rate(instance: T) -> T:
    """
    DEPRECATED: Use PricingDomainService.save_rate instead.
    """
    return PricingDomainService.save_rate(instance)

def safe_update_or_create_v4_rate(model_cls: Type[T], lookup: dict[str, Any], defaults: dict[str, Any]) -> tuple[T, bool]:
    """
    DEPRECATED: Use PricingDomainService.update_or_create_rate instead.
    """
    return PricingDomainService.update_or_create_rate(model_cls, lookup, defaults)
