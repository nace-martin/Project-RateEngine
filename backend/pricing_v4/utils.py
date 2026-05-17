from django.core.exceptions import ValidationError
from django.db import models
from typing import Type, TypeVar, Any

T = TypeVar('T', bound=models.Model)

def safe_save_v4_rate(instance: T) -> T:
    """
    Perform full_clean() and save() on a V4 rate instance to ensure
    overlap prevention and domain validation are enforced.
    """
    instance.full_clean()
    instance.save()
    return instance

def safe_update_or_create_v4_rate(model_cls: Type[T], lookup: dict[str, Any], defaults: dict[str, Any]) -> tuple[T, bool]:
    """
    Safe alternative to update_or_create that triggers full_clean() for validation.
    """
    try:
        obj = model_cls.objects.get(**lookup)
        for key, value in defaults.items():
            setattr(obj, key, value)
        safe_save_v4_rate(obj)
        return obj, False
    except model_cls.DoesNotExist:
        params = {**lookup, **defaults}
        obj = model_cls(**params)
        safe_save_v4_rate(obj)
        return obj, True
