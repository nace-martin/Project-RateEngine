from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Permission, Role, RolePermission, UserMembership

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'role', 'organization', 'is_staff']
    list_filter = ['role', 'organization', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('RateEngine Access', {'fields': ('role', 'department', 'organization')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ("permission",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    search_fields = ("code", "name", "description")
    list_filter = ("is_active",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "organization", "is_system", "is_active", "updated_at")
    search_fields = ("code", "name", "organization__name", "organization__slug")
    list_filter = ("organization", "is_system", "is_active")
    inlines = [RolePermissionInline]


@admin.register(UserMembership)
class UserMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "branch", "department", "role", "is_primary", "is_active")
    search_fields = ("user__username", "organization__name", "organization__slug", "role__code")
    list_filter = ("organization", "branch", "department", "role", "is_primary", "is_active")
    autocomplete_fields = ("user", "organization", "branch", "department", "role")
