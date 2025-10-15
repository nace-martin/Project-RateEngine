# backend/quotes/admin.py

from django.contrib import admin
from .models import Quote, QuoteLine, QuoteTotal

class QuoteLineInline(admin.TabularInline):
    model = QuoteLine
    extra = 0
    readonly_fields = ('id',)

class QuoteTotalInline(admin.StackedInline):
    model = QuoteTotal

@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    inlines = [QuoteTotalInline, QuoteLineInline]
    list_display = ('quote_number', 'bill_to', 'scenario', 'status', 'created_at')
    readonly_fields = ('id', 'created_at', 'updated_at')