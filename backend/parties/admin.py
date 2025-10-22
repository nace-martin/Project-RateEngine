# backend/parties/admin.py

from django.contrib import admin
from .models import Company, Address, Contact

class AddressInline(admin.StackedInline):
    """Allows editing Addresses directly within the Company admin page."""
    model = Address
    extra = 1 # Show one blank address form by default
    fields = ('address_line_1', 'address_line_2', 'city', 'country', 'postal_code', 'is_primary')

class ContactInline(admin.TabularInline):
    """Allows editing Contacts directly within the Company admin page."""
    model = Contact
    extra = 1 # Show one blank contact form by default
    fields = ('first_name', 'last_name', 'email', 'phone', 'is_primary')

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin configuration for the Company model."""
    list_display = ('name', 'tax_id', 'created_at')
    search_fields = ('name', 'tax_id')
    inlines = [AddressInline, ContactInline] # Add the inline editors

# We can also register Address and Contact separately if needed for direct access
# admin.site.register(Address)
# admin.site.register(Contact)