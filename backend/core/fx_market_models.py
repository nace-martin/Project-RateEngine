"""Permanent objective FX market rate facts; legacy pricing still uses core.models.FxRate/FxSnapshot."""

import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models

CURRENCY_CODE_REGEX = re.compile(r"^[A-Z]{3}$")


class FxMarketRate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_currency = models.CharField(max_length=3)
    quote_currency = models.CharField(max_length=3)
    effective_date = models.DateField()
    tt_buy_rate = models.DecimalField(max_digits=18, decimal_places=8)
    tt_sell_rate = models.DecimalField(max_digits=18, decimal_places=8)
    mid_rate = models.DecimalField(max_digits=18, decimal_places=8)
    source = models.CharField(max_length=64)

    class Meta:
        db_table = "fx_market_rate"
        constraints = (
            models.UniqueConstraint(
                fields=["base_currency", "quote_currency", "effective_date", "source"],
                name="fx_market_rate_unique_entry",
            ),
            models.CheckConstraint(
                condition=models.Q(tt_buy_rate__gt=0),
                name="fx_market_tt_buy_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(tt_sell_rate__gt=0),
                name="fx_market_tt_sell_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(mid_rate__gt=0),
                name="fx_market_mid_rate_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(base_currency__regex=r"^[A-Z]{3}$"),
                name="fx_market_base_currency_format",
            ),
            models.CheckConstraint(
                condition=models.Q(quote_currency__regex=r"^[A-Z]{3}$"),
                name="fx_market_quote_currency_format",
            ),
            models.CheckConstraint(
                condition=~models.Q(base_currency=models.F("quote_currency")),
                name="fx_market_currencies_distinct",
            ),
        )

    def clean(self):
        super().clean()
        if self.base_currency:
            self.base_currency = self.base_currency.strip().upper()
        if not self.base_currency or not CURRENCY_CODE_REGEX.match(self.base_currency):
            raise ValidationError(
                {"base_currency": f"Currency code must be exactly 3 uppercase letters [A-Z]{{3}}, got '{self.base_currency}'."}
            )
        if self.quote_currency:
            self.quote_currency = self.quote_currency.strip().upper()
        if not self.quote_currency or not CURRENCY_CODE_REGEX.match(self.quote_currency):
            raise ValidationError(
                {"quote_currency": f"Currency code must be exactly 3 uppercase letters [A-Z]{{3}}, got '{self.quote_currency}'."}
            )
        if (
            self.base_currency
            and self.quote_currency
            and self.base_currency == self.quote_currency
        ):
            raise ValidationError(
                {"quote_currency": "Base currency and quote currency must be distinct."}
            )
        if self.tt_buy_rate is not None and self.tt_buy_rate <= 0:
            raise ValidationError({"tt_buy_rate": "TT BUY rate must be strictly positive."})
        if self.tt_sell_rate is not None and self.tt_sell_rate <= 0:
            raise ValidationError({"tt_sell_rate": "TT SELL rate must be strictly positive."})
        if self.mid_rate is not None and self.mid_rate <= 0:
            raise ValidationError({"mid_rate": "Mid rate must be strictly positive."})

    def save(self, *args, **kwargs):
        if self.base_currency:
            self.base_currency = self.base_currency.strip().upper()
        if self.quote_currency:
            self.quote_currency = self.quote_currency.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.base_currency}/{self.quote_currency} @ {self.effective_date} "
            f"(B:{self.tt_buy_rate} S:{self.tt_sell_rate} M:{self.mid_rate}) [{self.source}]"
        )
