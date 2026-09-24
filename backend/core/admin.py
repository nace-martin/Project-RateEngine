# backend/core/admin.py

from django.contrib import admin

from .models import (
    Airport,
    City,
    Country,
    Currency,
    FxMarketRate,
    FxSnapshot,
    Policy,
)

admin.site.register(Currency)
admin.site.register(Country)
admin.site.register(City)
admin.site.register(Airport)
admin.site.register(FxMarketRate)
admin.site.register(FxSnapshot)
admin.site.register(Policy)
