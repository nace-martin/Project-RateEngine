from __future__ import annotations

import logging
from typing import Sequence
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class OverlapPreventionMixin:
    """
    Mixin to provide model-level overlap prevention for V4 pricing tables.
    """
    
    overlap_identity_fields: Sequence[str] = []
    overlap_date_fields: tuple[str, str] = ('valid_from', 'valid_until')

    def clean(self):
        super().clean()
        self.validate_overlaps()

    def validate_overlaps(self):
        if not self.overlap_identity_fields:
            return

        from_field, to_field = self.overlap_date_fields
        valid_from = getattr(self, from_field)
        valid_until = getattr(self, to_field)

        if not valid_from or not valid_until:
            return

        lookup = {
            f"{from_field}__lte": valid_until,
            f"{to_field}__gte": valid_from,
        }
        
        for field in self.overlap_identity_fields:
            lookup[field] = getattr(self, field)

        overlaps = self.__class__.objects.filter(**lookup).exclude(id=self.id)
        
        # Allow overlap with the row this instance supersedes (commercial continuity)
        if hasattr(self, 'supersedes_rate_id') and self.supersedes_rate_id:
            overlaps = overlaps.exclude(id=self.supersedes_rate_id)


        if overlaps.exists():
            conflicting = overlaps.first()
            msg = (
                f"OVERLAP_CONFLICT: Overlapping active row exists (ID #{conflicting.id}) "
                f"for this commercial identity. Validity: {getattr(conflicting, from_field)} "
                f"to {getattr(conflicting, to_field)}."
            )
            logger.warning(
                "%s in %s. Identity: %s",
                msg, 
                self.__class__.__name__,
                {f: getattr(self, f) for f in self.overlap_identity_fields}
            )
            raise ValidationError(msg)
