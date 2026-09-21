"""Internal EFM hierarchy, separate from counterparties and legacy RBAC models."""

import uuid

from django.db import models


class OrgCompany(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=24, unique=True)
    country_code = models.CharField(max_length=2)
    currency_code = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "org_company"

    def __str__(self):
        return self.name


class OrgOperatingEntity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        OrgCompany, on_delete=models.PROTECT, related_name="operating_entities"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=24)
    tax_id = models.CharField(max_length=50, blank=True)
    functional_currency = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "org_operating_entity"
        constraints = (
            models.UniqueConstraint(
                fields=["company", "code"], name="org_entity_company_code_uniq"
            ),
        )

    def __str__(self):
        return self.name


class OrgBranch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operating_entity = models.ForeignKey(
        OrgOperatingEntity, on_delete=models.PROTECT, related_name="branches"
    )
    location = models.ForeignKey(
        "core.GeoLocation", on_delete=models.PROTECT, related_name="branches"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=24)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "org_branch"
        constraints = (
            models.UniqueConstraint(
                fields=["operating_entity", "code"], name="org_branch_entity_code_uniq"
            ),
        )

    def __str__(self):
        return self.name


class OrgDepartment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        OrgBranch, on_delete=models.PROTECT, related_name="departments"
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=24)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "org_department"
        constraints = (
            models.UniqueConstraint(
                fields=["branch", "code"], name="org_department_branch_code_uniq"
            ),
        )

    def __str__(self):
        return self.name
