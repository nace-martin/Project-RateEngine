from __future__ import annotations

import logging
from typing import Type, TypeVar, Any
from django.db import models, transaction
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=models.Model)

class PricingDomainService:
    """
    Centralized persistence layer for V4 pricing writes.
    Ensures all V4 pricing models follow commercial rules (overlaps, domain matching)
    by strictly enforcing full_clean() before any database write.
    """

    @staticmethod
    def validate_rate(instance: T) -> None:
        """
        Trigger model-level validation (clean and full_clean).
        """
        instance.full_clean()

    @staticmethod
    def save_rate(instance: T) -> T:
        """
        Safe persistence for a V4 rate instance.
        """
        try:
            PricingDomainService.validate_rate(instance)
            instance.save()
            return instance
        except ValidationError as exc:
            logger.warning(
                "PRICING_VALIDATION_FAILED: Failed to save %s (ID: %s). Errors: %s",
                instance.__class__.__name__,
                getattr(instance, 'id', 'NEW'),
                exc.message_dict
            )
            raise

    @staticmethod
    def update_or_create_rate(
        model_cls: Type[T], 
        lookup_kwargs: dict[str, Any],
        defaults: dict[str, Any] | None = None,
    ) -> tuple[T, bool]:
        """
        Safe alternative to update_or_create that triggers full_clean() for validation.
        """
        defaults = defaults or {}
        with transaction.atomic():
            try:
                # Use select_for_update to prevent race conditions in future high-concurrency writes
                obj = model_cls.objects.select_for_update().get(**lookup_kwargs)
                for key, value in defaults.items():
                    setattr(obj, key, value)
                PricingDomainService.save_rate(obj)
                return obj, False
            except model_cls.DoesNotExist:
                params = {**lookup_kwargs, **defaults}
                obj = model_cls(**params)
                PricingDomainService.save_rate(obj)
                return obj, True
            except Exception as exc:
                if not isinstance(exc, ValidationError):
                    logger.error(
                        "PRICING_UPSERT_FAILED: Failed to update_or_create %s. Lookup: %s. Error: %s",
                        model_cls.__name__,
                        lookup_kwargs,
                        str(exc)
                    )
                raise
