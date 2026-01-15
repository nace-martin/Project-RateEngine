# backend/parties/admin.py

from django.contrib import admin
# Add CustomerCommercialProfile to imports
from .models import Company, Address, Contact, CustomerCommercialProfile 

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

# --- ADD INLINE FOR COMMERCIAL PROFILE ---
class CustomerCommercialProfileInline(admin.StackedInline):
    model = CustomerCommercialProfile
    can_delete = False # Usually want one profile per company
    verbose_name_plural = 'Commercial Profile'
    fields = (
        'preferred_quote_currency', 
        'default_margin_percent', 
        'min_margin_percent',
        'payment_term_default',
        # Add other fields as needed
    )
# ---

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin configuration for the Company model."""
    list_display = ('name', 'tax_id', 'created_at')
    search_fields = ('name', 'tax_id')
    exclude = ('company_type',)
    # Add the new inline
    inlines = [CustomerCommercialProfileInline, AddressInline, ContactInline] 

# We can also register Address and Contact separately if needed for direct access
# admin.site.register(Address)
# admin.site.register(Contact)

# Register separately if direct access is needed (optional)
# admin.site.register(CustomerCommercialProfile)