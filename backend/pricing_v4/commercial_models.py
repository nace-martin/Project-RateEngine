"""Permanent commercial product codes, charge aliases, and commercial terms policy.

Existing pricing runtime continues to use pricing_v4.ProductCode, pricing_v4.ChargeAlias,
and core.models.Policy until the cutover phase.
"""

import re
import uuid
from decimal import Decimal

from core.corridor_models import TransportMode
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Trim, Upper

CURRENCY_CODE_REGEX = re.compile(r"^[A-Z]{3}$")


class CommercialProductCode(models.Model):
    class Category(models.TextChoices):
        FREIGHT = "FREIGHT", "Freight"
        ORIGIN = "ORIGIN", "Origin"
        DESTINATION = "DESTINATION", "Destination"
        CLEARANCE = "CLEARANCE", "Clearance"
        SERVICE = "SERVICE", "Service"

    class GstTreatment(models.TextChoices):
        FREIGHT_EXPORT = "FREIGHT_EXPORT", "Freight Export"
        FREIGHT_IMPORT = "FREIGHT_IMPORT", "Freight Import"
        DOMESTIC_STANDARD = "DOMESTIC_STANDARD", "Domestic Standard"
        EXEMPT = "EXEMPT", "Exempt"
        ZERO_RATED = "ZERO_RATED", "Zero Rated"

    class ChargeBasis(models.TextChoices):
        FLAT = "FLAT", "Flat"
        PER_KG = "PER_KG", "Per kg"
        PER_CBM = "PER_CBM", "Per cbm"
        PER_UNIT = "PER_UNIT", "Per unit"
        TIERED_WEIGHT = "TIERED_WEIGHT", "Tiered weight"
        PERCENTAGE = "PERCENTAGE", "Percentage"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=32, choices=Category.choices)
    sub_category = models.CharField(max_length=64, blank=True)
    gst_treatment = models.CharField(max_length=32, choices=GstTreatment.choices)
    charge_basis_default = models.CharField(max_length=32, choices=ChargeBasis.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "commercial_product_code"
        constraints = (
            models.CheckConstraint(
                condition=~models.Q(code="") & models.Q(code=Upper(Trim("code"))),
                name="comm_product_code_normalized",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    category__in=["FREIGHT", "ORIGIN", "DESTINATION", "CLEARANCE", "SERVICE"]
                ),
                name="comm_product_code_category_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    gst_treatment__in=[
                        "FREIGHT_EXPORT",
                        "FREIGHT_IMPORT",
                        "DOMESTIC_STANDARD",
                        "EXEMPT",
                        "ZERO_RATED",
                    ]
                ),
                name="comm_product_code_gst_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    charge_basis_default__in=[
                        "FLAT",
                        "PER_KG",
                        "PER_CBM",
                        "PER_UNIT",
                        "TIERED_WEIGHT",
                        "PERCENTAGE",
                    ]
                ),
                name="comm_product_code_basis_valid",
            ),
        )

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()
            if not self.code:
                raise ValidationError({"code": "Product code cannot be blank."})
        if self.sub_category:
            self.sub_category = self.sub_category.strip()

    def __str__(self):
        return f"{self.code} - {self.name}"


def normalize_alias_text(text: str) -> str:
    """Deterministic alias text normalization: strip, uppercase, collapse internal whitespace."""
    if not text:
        return ""
    return " ".join(text.strip().upper().split())


class CommercialChargeAlias(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_code = models.ForeignKey(
        CommercialProductCode,
        on_delete=models.PROTECT,
        related_name="aliases",
    )
    raw_text = models.CharField(max_length=255)
    transport_mode = models.CharField(max_length=16, choices=TransportMode.choices)
    carrier_party = models.ForeignKey(
        "parties.PartyMaster",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commercial_charge_aliases",
    )
    source_currency = models.CharField(max_length=3, blank=True)
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("1.0000"),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "commercial_charge_alias"
        constraints = (
            models.UniqueConstraint(
                fields=["raw_text", "transport_mode"],
                condition=models.Q(carrier_party__isnull=True),
                name="charge_alias_global_uniq",
            ),
            models.UniqueConstraint(
                fields=["raw_text", "transport_mode", "carrier_party"],
                condition=models.Q(carrier_party__isnull=False),
                name="charge_alias_carrier_uniq",
            ),
            models.CheckConstraint(
                condition=~models.Q(raw_text="") & models.Q(raw_text=Upper(Trim("raw_text"))),
                name="charge_alias_raw_text_normalized",
            ),
            models.CheckConstraint(
                condition=models.Q(transport_mode__in=["AIR", "SEA", "ROAD"]),
                name="charge_alias_transport_mode_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence_score__gte=0) & models.Q(confidence_score__lte=1),
                name="charge_alias_confidence_range",
            ),
            models.CheckConstraint(
                condition=models.Q(source_currency="")
                | models.Q(source_currency__regex=r"^[A-Z]{3}$"),
                name="charge_alias_source_currency_format",
            ),
        )

    def clean(self):
        super().clean()
        if self.raw_text:
            self.raw_text = normalize_alias_text(self.raw_text)
            if not self.raw_text:
                raise ValidationError({"raw_text": "Raw text cannot be empty."})
        if self.source_currency:
            self.source_currency = self.source_currency.strip().upper()
            if not CURRENCY_CODE_REGEX.match(self.source_currency):
                raise ValidationError(
                    {
                        "source_currency": (
                            f"Currency code must be exactly 3 uppercase letters [A-Z]{{3}}, "
                            f"got '{self.source_currency}'."
                        )
                    }
                )
        if (
            self.confidence_score is not None
            and (self.confidence_score < Decimal("0.0") or self.confidence_score > Decimal("1.0"))
        ):
            raise ValidationError(
                {"confidence_score": "Confidence score must be between 0.0 and 1.0."}
            )

        # Python-level deterministic uniqueness validation across SQLite and PostgreSQL
        if self.raw_text and self.transport_mode:
            qs = CommercialChargeAlias.objects.filter(
                raw_text=self.raw_text,
                transport_mode=self.transport_mode,
                carrier_party=self.carrier_party,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                scope = (
                    "global" if self.carrier_party is None else f"carrier {self.carrier_party_id}"
                )
                raise ValidationError(
                    f"A charge alias for '{self.raw_text}' in mode {self.transport_mode} already exists for {scope}."
                )

    def save(self, *args, **kwargs):
        if self.raw_text:
            self.raw_text = normalize_alias_text(self.raw_text)
        if self.source_currency:
            self.source_currency = self.source_currency.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        carrier = f" [{self.carrier_party}]" if self.carrier_party else " [GLOBAL]"
        return f"'{self.raw_text}' ({self.transport_mode}{carrier}) -> {self.product_code.code}"


class CommercialTermsPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    policy_code = models.CharField(max_length=64, unique=True)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    target_gross_margin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    import_caf_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    export_caf_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    gst_standard_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "policy_commercial_terms"
        constraints = (
            models.CheckConstraint(
                condition=~models.Q(policy_code="")
                & models.Q(policy_code=Upper(Trim("policy_code"))),
                name="comm_policy_code_normalized",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="comm_policy_valid_window",
            ),
            models.CheckConstraint(
                condition=models.Q(target_gross_margin_percent__isnull=True)
                | (
                    models.Q(target_gross_margin_percent__gte=0)
                    & models.Q(target_gross_margin_percent__lt=100)
                ),
                name="comm_policy_margin_valid_range",
            ),
            models.CheckConstraint(
                condition=models.Q(import_caf_percent__isnull=True)
                | (
                    models.Q(import_caf_percent__gte=0)
                    & models.Q(import_caf_percent__lte=100)
                ),
                name="comm_policy_import_caf_range",
            ),
            models.CheckConstraint(
                condition=models.Q(export_caf_percent__isnull=True)
                | (
                    models.Q(export_caf_percent__gte=0)
                    & models.Q(export_caf_percent__lte=100)
                ),
                name="comm_policy_export_caf_range",
            ),
            models.CheckConstraint(
                condition=models.Q(gst_standard_percent__gte=0)
                & models.Q(gst_standard_percent__lte=100),
                name="comm_policy_gst_standard_range",
            ),
        )

    def clean(self):
        super().clean()
        if self.policy_code:
            self.policy_code = self.policy_code.strip().upper()
            if not self.policy_code:
                raise ValidationError({"policy_code": "Policy code cannot be empty."})
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError(
                {"valid_until": "valid_until must be strictly greater than valid_from."}
            )
        if (
            self.target_gross_margin_percent is not None
            and (self.target_gross_margin_percent < 0 or self.target_gross_margin_percent >= 100)
        ):
            raise ValidationError(
                {
                    "target_gross_margin_percent": "Target gross margin percent must be >= 0% and < 100%."
                }
            )
        if self.import_caf_percent is not None and (
            self.import_caf_percent < 0 or self.import_caf_percent > 100
        ):
            raise ValidationError(
                {"import_caf_percent": "Import CAF percent must be between 0% and 100%."}
            )
        if self.export_caf_percent is not None and (
            self.export_caf_percent < 0 or self.export_caf_percent > 100
        ):
            raise ValidationError(
                {"export_caf_percent": "Export CAF percent must be between 0% and 100%."}
            )
        if self.gst_standard_percent is not None and (
            self.gst_standard_percent < 0 or self.gst_standard_percent > 100
        ):
            raise ValidationError(
                {"gst_standard_percent": "GST standard percent must be between 0% and 100%."}
            )

    def __str__(self):
        return f"{self.policy_code} (Valid: {self.valid_from} - {self.valid_until or 'Present'})"
