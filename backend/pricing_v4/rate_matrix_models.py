"""Permanent target Rate Matrix models for Clean Database Architecture Phase 3.

Hierarchy:
RateSheet -> RateLine -> RateApplicability
                      -> RateTier

This is an isolated schema-only foundation. Active pricing runtime continues
to use legacy COGS/Sell models and RateCard tables.
"""

import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Trim

CURRENCY_CODE_REGEX = re.compile(r"^[A-Z]{3}$")


class RateSheet(models.Model):
    """Container for tariff rates scoped to carrier, customer, or general card."""

    class RateType(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    class TransportMode(models.TextChoices):
        AIR = "AIR", "Air"
        SEA = "SEA", "Sea"
        ROAD = "ROAD", "Road"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    party = models.ForeignKey(
        "parties.PartyMaster",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="customer_rate_sheets",
        help_text="Optional customer scope for SELL tariffs",
    )
    carrier = models.ForeignKey(
        "parties.PartyMaster",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="carrier_rate_sheets",
        help_text="Optional carrier scope for BUY tariffs",
    )
    rate_type = models.CharField(max_length=8, choices=RateType.choices)
    transport_mode = models.CharField(max_length=8, choices=TransportMode.choices)
    currency_code = models.CharField(max_length=3)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "rate_sheet"
        constraints = (
            models.CheckConstraint(
                condition=~models.Q(name="") & models.Q(name=Trim("name")),
                name="rate_sheet_name_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(currency_code__regex=r"^[A-Z]{3}$"),
                name="rate_sheet_currency_format",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="rate_sheet_valid_window",
            ),
            models.CheckConstraint(
                condition=models.Q(rate_type__in=["BUY", "SELL"]),
                name="rate_sheet_rate_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(transport_mode__in=["AIR", "SEA", "ROAD"]),
                name="rate_sheet_transport_mode_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="rate_sheet_version_positive",
            ),
        )

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "RateSheet name cannot be empty."})

        if self.currency_code:
            self.currency_code = self.currency_code.strip().upper()
        if not self.currency_code or not CURRENCY_CODE_REGEX.match(self.currency_code):
            raise ValidationError(
                {
                    "currency_code": (
                        f"Currency code must be exactly 3 uppercase letters [A-Z]{{3}}, "
                        f"got '{self.currency_code}'."
                    )
                }
            )

        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError(
                {"valid_until": "valid_until must be strictly greater than valid_from."}
            )

        if self.version is not None and self.version < 1:
            raise ValidationError({"version": "Version must be an integer >= 1."})

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        if self.currency_code:
            self.currency_code = self.currency_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"RateSheet({self.name} [{self.rate_type}/{self.transport_mode}] "
            f"{self.currency_code} v{self.version})"
        )


class RateLine(models.Model):
    """Individual tariff rate line for a CommercialProductCode."""

    class RateBasis(models.TextChoices):
        FLAT = "FLAT", "Flat"
        PER_KG = "PER_KG", "Per kg"
        PER_CBM = "PER_CBM", "Per cbm"
        PER_UNIT = "PER_UNIT", "Per unit"
        TIERED_WEIGHT = "TIERED_WEIGHT", "Tiered weight"
        PERCENTAGE = "PERCENTAGE", "Percentage"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sheet = models.ForeignKey(
        RateSheet,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product_code = models.ForeignKey(
        "pricing_v4.CommercialProductCode",
        on_delete=models.PROTECT,
        related_name="rate_lines",
    )
    rate_basis = models.CharField(max_length=32, choices=RateBasis.choices)
    unit_rate = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Scalar unit rate for FLAT, PER_KG, PER_CBM, PER_UNIT",
    )
    min_charge = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional minimum charge floor",
    )
    max_charge = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional maximum charge ceiling",
    )
    percentage_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Percentage rate (e.g. 10.00) for PERCENTAGE basis",
    )
    percentage_basis_product_code = models.ForeignKey(
        "pricing_v4.CommercialProductCode",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="percentage_dependent_rate_lines",
        help_text="Reference product code that the percentage applies to",
    )

    class Meta:
        db_table = "rate_line"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(
                    rate_basis__in=[
                        "FLAT",
                        "PER_KG",
                        "PER_CBM",
                        "PER_UNIT",
                        "TIERED_WEIGHT",
                        "PERCENTAGE",
                    ]
                ),
                name="rate_line_basis_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_rate__isnull=True) | models.Q(unit_rate__gte=0),
                name="rate_line_unit_rate_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(min_charge__isnull=True) | models.Q(min_charge__gte=0),
                name="rate_line_min_charge_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(max_charge__isnull=True) | models.Q(max_charge__gte=0),
                name="rate_line_max_charge_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(percentage_rate__isnull=True)
                | models.Q(percentage_rate__gte=0),
                name="rate_line_percentage_rate_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(min_charge__isnull=True)
                | models.Q(max_charge__isnull=True)
                | models.Q(min_charge__lte=models.F("max_charge")),
                name="rate_line_min_lte_max",
            ),
            # Basis-dependent field mutual exclusivity and completeness
            models.CheckConstraint(
                condition=(
                    # Case 1: PERCENTAGE requires percentage_rate + percentage_basis_product_code, forbids unit_rate
                    (
                        models.Q(rate_basis="PERCENTAGE")
                        & models.Q(percentage_rate__isnull=False)
                        & models.Q(percentage_basis_product_code__isnull=False)
                        & models.Q(unit_rate__isnull=True)
                    )
                    # Case 2: TIERED_WEIGHT requires tiers; forbids unit_rate and percentage fields
                    | (
                        models.Q(rate_basis="TIERED_WEIGHT")
                        & models.Q(unit_rate__isnull=True)
                        & models.Q(percentage_rate__isnull=True)
                        & models.Q(percentage_basis_product_code__isnull=True)
                    )
                    # Case 3: Scalar bases require unit_rate; forbid percentage fields
                    | (
                        models.Q(rate_basis__in=["FLAT", "PER_KG", "PER_CBM", "PER_UNIT"])
                        & models.Q(unit_rate__isnull=False)
                        & models.Q(percentage_rate__isnull=True)
                        & models.Q(percentage_basis_product_code__isnull=True)
                    )
                ),
                name="rate_line_basis_integrity",
            ),
        )

    def clean(self):
        super().clean()

        # Non-negative checks
        if self.unit_rate is not None and self.unit_rate < 0:
            raise ValidationError({"unit_rate": "Unit rate must be non-negative."})
        if self.min_charge is not None and self.min_charge < 0:
            raise ValidationError({"min_charge": "Min charge must be non-negative."})
        if self.max_charge is not None and self.max_charge < 0:
            raise ValidationError({"max_charge": "Max charge must be non-negative."})
        if self.percentage_rate is not None and self.percentage_rate < 0:
            raise ValidationError({"percentage_rate": "Percentage rate must be non-negative."})

        # min_charge <= max_charge
        if (
            self.min_charge is not None
            and self.max_charge is not None
            and self.min_charge > self.max_charge
        ):
            raise ValidationError(
                {"min_charge": "Min charge cannot exceed max charge."}
            )

        # Basis-dependent field validation
        if self.rate_basis == self.RateBasis.PERCENTAGE:
            if self.percentage_rate is None:
                raise ValidationError(
                    {"percentage_rate": "PERCENTAGE rate basis requires percentage_rate."}
                )
            if not self.percentage_basis_product_code_id:
                raise ValidationError(
                    {
                        "percentage_basis_product_code": (
                            "PERCENTAGE rate basis requires percentage_basis_product_code."
                        )
                    }
                )
            if self.unit_rate is not None:
                raise ValidationError(
                    {"unit_rate": "PERCENTAGE rate basis must not carry a unit_rate."}
                )
        elif self.rate_basis == self.RateBasis.TIERED_WEIGHT:
            if self.unit_rate is not None:
                raise ValidationError(
                    {
                        "unit_rate": (
                            "TIERED_WEIGHT rate basis must not carry a scalar unit_rate; "
                            "rates must be defined on rate_tier records."
                        )
                    }
                )
            if self.percentage_rate is not None:
                raise ValidationError(
                    {
                        "percentage_rate": (
                            "TIERED_WEIGHT rate basis must not carry a percentage_rate."
                        )
                    }
                )
            if self.percentage_basis_product_code_id:
                raise ValidationError(
                    {
                        "percentage_basis_product_code": (
                            "TIERED_WEIGHT rate basis must not carry percentage_basis_product_code."
                        )
                    }
                )
        elif self.rate_basis in [
            self.RateBasis.FLAT,
            self.RateBasis.PER_KG,
            self.RateBasis.PER_CBM,
            self.RateBasis.PER_UNIT,
        ]:
            if self.unit_rate is None:
                raise ValidationError(
                    {"unit_rate": f"Rate basis '{self.rate_basis}' requires a unit_rate."}
                )
            if self.percentage_rate is not None:
                raise ValidationError(
                    {
                        "percentage_rate": (
                            f"Rate basis '{self.rate_basis}' must not carry percentage_rate."
                        )
                    }
                )
            if self.percentage_basis_product_code_id:
                raise ValidationError(
                    {
                        "percentage_basis_product_code": (
                            f"Rate basis '{self.rate_basis}' must not carry percentage_basis_product_code."
                        )
                    }
                )

        # Cross-validation with tiers when line is persisted
        if self.pk:
            if self.rate_basis == self.RateBasis.TIERED_WEIGHT:
                if not self.tiers.exists():
                    raise ValidationError(
                        {"rate_basis": "TIERED_WEIGHT rate line requires at least one rate tier."}
                    )
            else:
                if self.tiers.exists():
                    raise ValidationError(
                        {
                            "rate_basis": (
                                f"Rate line with basis '{self.rate_basis}' cannot carry rate tiers."
                            )
                        }
                    )

    def validate_tier_requirements(self):
        """Explicit helper to validate that TIERED_WEIGHT lines have tiers and non-tiered lines have none."""
        if self.rate_basis == self.RateBasis.TIERED_WEIGHT:
            if not self.tiers.exists():
                raise ValidationError(
                    {"rate_basis": "TIERED_WEIGHT rate line requires at least one rate tier."}
                )
        else:
            if self.tiers.exists():
                raise ValidationError(
                    {
                        "rate_basis": (
                            f"Rate line with basis '{self.rate_basis}' cannot carry rate tiers."
                        )
                    }
                )

    def __str__(self):
        return f"RateLine({self.sheet.name} -> {self.product_code.code} [{self.rate_basis}])"


class RateApplicability(models.Model):
    """Spatial, corridor, commodity, and service criteria under which a RateLine applies."""

    class ServiceLevel(models.TextChoices):
        EXPRESS = "EXPRESS", "Express"
        STANDARD = "STANDARD", "Standard"
        DEFERRED = "DEFERRED", "Deferred"

    class Direction(models.TextChoices):
        IMPORT = "IMPORT", "Import"
        EXPORT = "EXPORT", "Export"
        DOMESTIC = "DOMESTIC", "Domestic"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rate_line = models.OneToOneField(
        RateLine,
        on_delete=models.CASCADE,
        related_name="applicability",
    )
    origin = models.ForeignKey(
        "core.GeoLocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional origin location filter",
    )
    destination = models.ForeignKey(
        "core.GeoLocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional destination location filter",
    )
    service_level = models.CharField(
        max_length=32,
        blank=True,
        choices=ServiceLevel.choices,
    )
    commodity_category = models.CharField(max_length=64, blank=True)
    direction = models.CharField(
        max_length=32,
        blank=True,
        choices=Direction.choices,
    )
    equipment_type = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "rate_applicability"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(direction__in=["", "IMPORT", "EXPORT", "DOMESTIC"]),
                name="rate_app_direction_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    service_level__in=["", "EXPRESS", "STANDARD", "DEFERRED"]
                ),
                name="rate_app_service_level_valid",
            ),
        )

    def clean(self):
        super().clean()
        if self.direction and self.direction not in self.Direction.values:
            raise ValidationError({"direction": f"Invalid direction '{self.direction}'."})
        if self.service_level and self.service_level not in self.ServiceLevel.values:
            raise ValidationError(
                {"service_level": f"Invalid service_level '{self.service_level}'."}
            )

    def __str__(self):
        orig = self.origin.canonical_name if self.origin else "ANY"
        dest = self.destination.canonical_name if self.destination else "ANY"
        return f"RateApplicability({orig} -> {dest} [{self.direction or 'ALL'}])"


class RateTier(models.Model):
    """Weight or quantity breaks for a TIERED_WEIGHT RateLine."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rate_line = models.ForeignKey(
        RateLine,
        on_delete=models.CASCADE,
        related_name="tiers",
    )
    min_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="Tier quantity lower bound (inclusive)",
    )
    max_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Tier quantity upper bound (exclusive); NULL represents open-ended/infinity",
    )
    unit_rate = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        help_text="Unit rate applicable to this tier quantity bracket",
    )

    class Meta:
        db_table = "rate_tier"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(min_quantity__gte=0),
                name="rate_tier_min_quantity_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(max_quantity__isnull=True)
                | models.Q(max_quantity__gt=models.F("min_quantity")),
                name="rate_tier_max_quantity_gt_min",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_rate__gte=0),
                name="rate_tier_unit_rate_non_negative",
            ),
        )

    def clean(self):
        super().clean()

        # Non-negative checks
        if self.min_quantity is not None and self.min_quantity < 0:
            raise ValidationError(
                {"min_quantity": "Minimum quantity must be non-negative."}
            )
        if self.unit_rate is not None and self.unit_rate < 0:
            raise ValidationError({"unit_rate": "Unit rate must be non-negative."})

        # max_quantity > min_quantity when present
        if (
            self.min_quantity is not None
            and self.max_quantity is not None
            and self.max_quantity <= self.min_quantity
        ):
            raise ValidationError(
                {"max_quantity": "Maximum quantity must be strictly greater than minimum quantity."}
            )

        # Enforce that parent line has TIERED_WEIGHT basis
        if self.rate_line_id:
            try:
                line = self.rate_line
                if line.rate_basis != RateLine.RateBasis.TIERED_WEIGHT:
                    raise ValidationError(
                        {
                            "rate_line": (
                                f"Rate tiers can only be attached to TIERED_WEIGHT rate lines "
                                f"(found '{line.rate_basis}')."
                            )
                        }
                    )
            except RateLine.DoesNotExist:
                pass

        # Python-level tier overlap validation (SQLite parity + early rejection before DB)
        if self.rate_line_id and self.min_quantity is not None:
            existing_tiers = RateTier.objects.filter(rate_line_id=self.rate_line_id)
            if self.pk:
                existing_tiers = existing_tiers.exclude(pk=self.pk)

            for other in existing_tiers:
                # Interval A: [self.min_quantity, self.max_quantity)
                # Interval B: [other.min_quantity, other.max_quantity)
                # They overlap iff A_min < B_max AND B_min < A_max (None acts as +inf)
                self_starts_before_other_ends = (
                    other.max_quantity is None or self.min_quantity < other.max_quantity
                )
                other_starts_before_self_ends = (
                    self.max_quantity is None or other.min_quantity < self.max_quantity
                )

                if self_starts_before_other_ends and other_starts_before_self_ends:
                    self_bracket = f"[{self.min_quantity}, {self.max_quantity or 'inf'})"
                    other_bracket = f"[{other.min_quantity}, {other.max_quantity or 'inf'})"
                    raise ValidationError(
                        f"Rate tier {self_bracket} overlaps with existing tier {other_bracket} "
                        f"for rate line {self.rate_line_id}."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        max_str = self.max_quantity if self.max_quantity is not None else "inf"
        return f"RateTier([{self.min_quantity}, {max_str}) @ {self.unit_rate})"
