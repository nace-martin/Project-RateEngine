from django.contrib import admin
from .models import OrganizationMembership

@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "can_quote", "can_view_costs", "is_primary_contact")
    list_filter = ("role", "can_quote", "can_view_costs")
    search_fields = ("user__username", "user__email", "organization__name")
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    # You can add fields here to display in the admin list
    list_display = ['email', 'username', 'is_staff']

admin.site.register(CustomUser, CustomUserAdmin)
