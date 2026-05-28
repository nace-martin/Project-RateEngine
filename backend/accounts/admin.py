from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser
from core.models import Location

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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "primary_location":
            kwargs["queryset"] = Location.objects.filter(is_branch=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "authorised_locations":
            kwargs["queryset"] = Location.objects.filter(is_branch=True)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

admin.site.register(CustomUser, CustomUserAdmin)
