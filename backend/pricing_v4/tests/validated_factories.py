from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Type, TypeVar

from django.db import models
from pricing_v4.models import (
    LocalSellRate, LocalCOGSRate,
    ExportSellRate, ExportCOGS,
    ImportSellRate, ImportCOGS,
    DomesticSellRate, DomesticCOGS,
    Surcharge, ProductCode, Carrier, Agent
)
from pricing_v4.services.pricing_domain_service import PricingDomainService

T = TypeVar('T', bound=models.Model)

def create_validated_rate(model_cls: Type[T], **kwargs) -> T:
    """
    Standardized helper to create a V4 pricing row through the PricingDomainService.
    Ensures full_clean() is called and all commercial rules (overlaps, domains) are enforced.
    """
    # Ensure mandatory fields have defaults if not provided to reduce test boilerplate
    if 'valid_from' not in kwargs:
        kwargs['valid_from'] = date.today()
    if 'valid_until' not in kwargs:
        kwargs['valid_until'] = kwargs['valid_from'] + timedelta(days=365)
    
    instance = model_cls(**kwargs)
    return PricingDomainService.save_rate(instance)

def create_validated_local_sell(**kwargs) -> LocalSellRate:
    return create_validated_rate(LocalSellRate, **kwargs)

def create_validated_local_cogs(**kwargs) -> LocalCOGSRate:
    return create_validated_rate(LocalCOGSRate, **kwargs)

def create_validated_export_sell(**kwargs) -> ExportSellRate:
    return create_validated_rate(ExportSellRate, **kwargs)

def create_validated_export_cogs(**kwargs) -> ExportCOGS:
    return create_validated_rate(ExportCOGS, **kwargs)

def create_validated_import_sell(**kwargs) -> ImportSellRate:
    return create_validated_rate(ImportSellRate, **kwargs)

def create_validated_import_cogs(**kwargs) -> ImportCOGS:
    return create_validated_rate(ImportCOGS, **kwargs)

def create_validated_domestic_sell(**kwargs) -> DomesticSellRate:
    return create_validated_rate(DomesticSellRate, **kwargs)

def create_validated_domestic_cogs(**kwargs) -> DomesticCOGS:
    return create_validated_rate(DomesticCOGS, **kwargs)

def create_validated_surcharge(**kwargs) -> Surcharge:
    return create_validated_rate(Surcharge, **kwargs)

def get_or_create_test_product(id: int, code: str, domain: str, category: str = "FREIGHT", **overrides) -> ProductCode:
    """Helper to ensure a ProductCode exists with correct metadata for V4 validation."""
    defaults = {
        "code": code,
        "description": f"Test {code}",
        "category": category,
        "domain": domain,
        "is_gst_applicable": True,
        "gst_treatment": "ZERO_RATED",
        "gl_revenue_code": "REV-TEST",
        "gl_cost_code": "COST-TEST"
    }
    defaults.update(overrides)
    
    obj, created = ProductCode.objects.get_or_create(
        id=id,
        defaults=defaults
    )
    if not created:
        # Update fields if explicitly requested in overrides
        for key, value in overrides.items():
            setattr(obj, key, value)
        obj.save()
    return obj
