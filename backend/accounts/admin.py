from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = [
        'username',
        'email',
        'role',
        'department',
        'primary_location',
        'organization',
        'is_active',
        'is_staff',
    ]
    list_filter = [
        'role',
        'department',
        'primary_location',
        'organization',
        'is_active',
        'is_staff',
    ]
    fieldsets = UserAdmin.fieldsets + (
        ('RateEngine Access', {
            'fields': (
                'role',
                'department',
                'allowed_departments',
                'primary_location',
                'authorised_locations',
                'organization',
            )
        }),
    )
    filter_horizontal = UserAdmin.filter_horizontal + ('authorised_locations',)

admin.site.register(CustomUser, CustomUserAdmin)
