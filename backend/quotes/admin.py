from django.contrib import admin
from .models import Client, Quote, RateCard

admin.site.register(Client)
admin.site.register(Quote)
admin.site.register(RateCard)