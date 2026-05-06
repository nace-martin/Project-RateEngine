import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from services.models import SERVICE_SCOPE_CHOICES, SHIPMENT_DIRECTION_CHOICES


SERVICE_TYPE_CHOICES = [
    ("AIR", "Air"),
    ("SEA", "Sea"),
    ("CUSTOMS", "Customs"),
    ("TRANSPORT", "Transport"),
    ("DOMESTIC", "Domestic"),
    ("MULTIMODAL", "Multimodal"),
]


class Opportunity(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        QUALIFIED = "QUALIFIED", "Qualified"
        QUOTED = "QUOTED", "Quoted"
        WON = "WON", "Won"
        LOST = "LOST", "Lost"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("parties.Company", on_delete=models.CASCADE, related_name="opportunities")
    title = models.CharField(max_length=255)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES, db_index=True)
    direction = models.CharField(max_length=16, choices=SHIPMENT_DIRECTION_CHOICES, blank=True, default="", db_index=True)
    scope = models.CharField(max_length=3, choices=SERVICE_SCOPE_CHOICES, blank=True, default="")
    origin = models.CharField(max_length=255, blank=True, default="")
    destination = models.CharField(max_length=255, blank=True, default="")
    estimated_weight_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estimated_volume_cbm = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    estimated_fcl_count = models.PositiveIntegerField(null=True, blank=True)
    estimated_frequency = models.CharField(max_length=120, blank=True, default="")
    estimated_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estimated_currency = models.CharField(max_length=3, blank=True, default="PGK")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_opportunities",
    )
    next_action = models.CharField(max_length=255, blank=True, default="")
    next_action_date = models.DateField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)
    won_at = models.DateTimeField(null=True, blank=True)
    won_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_opportunities",
    )
    won_reason = models.TextField(blank=True, default="")
    lost_reason = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["service_type", "priority"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.company.name})"


class Interaction(models.Model):
    class InteractionType(models.TextChoices):
        CALL = "CALL", "Call"
        MEETING = "MEETING", "Meeting"
        EMAIL = "EMAIL", "Email"
        SITE_VISIT = "SITE_VISIT", "Site Visit"
        SYSTEM = "SYSTEM", "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey("parties.Company", on_delete=models.CASCADE, related_name="interactions")
    contact = models.ForeignKey(
        "parties.Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="crm_interactions")
    interaction_type = models.CharField(max_length=20, choices=InteractionType.choices)
    summary = models.TextField()
    outcomes = models.TextField(blank=True, default="")
    next_action = models.CharField(max_length=255, blank=True, default="")
    next_action_date = models.DateField(null=True, blank=True)
    is_system_generated = models.BooleanField(default=False, db_index=True)
    system_event_type = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["opportunity", "-created_at"]),
            models.Index(fields=["interaction_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.interaction_type} with {self.company.name}"

    def clean(self):
        if self.contact_id and self.company_id and self.contact.company_id != self.company_id:
            raise ValidationError({"contact": "Selected contact does not belong to the selected company."})
        if self.opportunity_id and self.company_id and self.opportunity.company_id != self.company_id:
            raise ValidationError({"opportunity": "Selected opportunity does not belong to the selected company."})

    def save(self, *args, **kwargs):
        is_create = self._state.adding
        super().save(*args, **kwargs)
        if is_create:
            interaction_time = self.created_at
            update_fields = ["last_interaction_at", "updated_at"]
            self.company.last_interaction_at = interaction_time
            self.company.save(update_fields=update_fields)
            if self.opportunity_id:
                self.opportunity.last_activity_at = interaction_time
                self.opportunity.save(update_fields=["last_activity_at", "updated_at"])


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        "parties.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="crm_tasks",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasks",
    )
    description = models.TextField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="crm_tasks")
    due_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_crm_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "status", "due_date"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["opportunity", "status"]),
        ]

    def clean(self):
        if not self.company_id and not self.opportunity_id:
            raise ValidationError("Task must link to at least a company or opportunity.")
        if self.company_id and self.opportunity_id and self.opportunity.company_id != self.company_id:
            raise ValidationError({"opportunity": "Selected opportunity does not belong to the selected company."})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.opportunity and not self.company:
            self.company = self.opportunity.company
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.description[:80]
