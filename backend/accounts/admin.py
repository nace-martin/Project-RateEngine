from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'role', 'organization', 'is_staff']
    list_filter = ['role', 'organization', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('RateEngine Access', {'fields': ('role', 'department', 'organization')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)
