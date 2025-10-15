# backend/core/admin.py

from django.contrib import admin
from .models import (
    Currency, Country, City, Airport, FxRate,
    FxSnapshot, Policy, Surcharge, LocalTariff
)

admin.site.register(Currency)
admin.site.register(Country)
admin.site.register(City)
admin.site.register(Airport)
admin.site.register(FxRate)
admin.site.register(FxSnapshot)
admin.site.register(Policy)
admin.site.register(Surcharge)
admin.site.register(LocalTariff)