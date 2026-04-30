from django.contrib import admin

from .models import Interaction, Opportunity, Task


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "service_type", "direction", "status", "priority", "owner", "updated_at")
    list_filter = ("status", "priority", "service_type", "direction", "is_active")
    search_fields = ("title", "company__name", "origin", "destination")


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ("company", "opportunity", "interaction_type", "author", "is_system_generated", "created_at")
    list_filter = ("interaction_type", "is_system_generated", "system_event_type")
    search_fields = ("company__name", "summary", "outcomes")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("description", "company", "opportunity", "owner", "due_date", "status")
    list_filter = ("status", "due_date")
    search_fields = ("description", "company__name", "opportunity__title")
