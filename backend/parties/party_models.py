"""Counterparty identity and roles; no synchronization with legacy Company records."""

import uuid

from django.db import models
from django.db.models.functions import Trim


class PartyMaster(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    legal_name = models.CharField(max_length=255)
    trade_name = models.CharField(max_length=255, blank=True)
    entity_type = models.CharField(max_length=50)
    country_code = models.CharField(max_length=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "party_master"
        constraints = (
            models.UniqueConstraint(
                fields=["legal_name", "country_code"], name="party_name_country_uniq"
            ),
        )

    def __str__(self):
        return self.legal_name


class PartyRole(models.Model):
    class RoleType(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        CARRIER = "CARRIER", "Carrier"
        AGENT = "AGENT", "Agent"
        SUPPLIER = "SUPPLIER", "Supplier"
        VENDOR = "VENDOR", "Vendor"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(
        PartyMaster, on_delete=models.PROTECT, related_name="roles"
    )
    role_type = models.CharField(max_length=16, choices=RoleType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "party_role"
        constraints = (
            models.UniqueConstraint(
                fields=["party", "role_type"], name="party_role_type_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    role_type__in=["CUSTOMER", "CARRIER", "AGENT", "SUPPLIER", "VENDOR"]
                ),
                name="party_role_type_valid",
            ),
        )

    def __str__(self):
        return f"{self.party}: {self.role_type}"


class PartyRoleIdentifier(models.Model):
    class Scheme(models.TextChoices):
        IATA_CARRIER = "IATA_CARRIER", "IATA carrier"
        ICAO = "ICAO", "ICAO"
        SCAC = "SCAC", "SCAC"
        CUSTOMS_BROKER = "CUSTOMS_BROKER", "Customs broker"
        TAX_ID = "TAX_ID", "Tax ID"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(
        PartyRole, on_delete=models.PROTECT, related_name="identifiers"
    )
    scheme = models.CharField(max_length=16, choices=Scheme.choices)
    value = models.CharField(max_length=100)

    class Meta:
        db_table = "party_role_identifier"
        constraints = (
            models.UniqueConstraint(
                fields=["scheme", "value"], name="party_identifier_scheme_val_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    scheme__in=[
                        "IATA_CARRIER",
                        "ICAO",
                        "SCAC",
                        "CUSTOMS_BROKER",
                        "TAX_ID",
                    ]
                ),
                name="party_identifier_scheme_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(value="") & models.Q(value=Trim("value")),
                name="party_identifier_value_trimmed",
            ),
        )

    def __str__(self):
        return f"{self.scheme}/{self.value}"


class PartyContact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(
        PartyMaster, on_delete=models.PROTECT, related_name="contacts"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "party_contact"
        constraints = (
            models.UniqueConstraint(
                fields=["party", "email"], name="party_contact_email_uniq"
            ),
        )

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class PartyAddress(models.Model):
    class AddressType(models.TextChoices):
        BILLING = "BILLING", "Billing"
        PHYSICAL = "PHYSICAL", "Physical"
        DEPOT = "DEPOT", "Depot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    party = models.ForeignKey(
        PartyMaster, on_delete=models.PROTECT, related_name="addresses"
    )
    location = models.ForeignKey(
        "core.GeoLocation", on_delete=models.PROTECT, related_name="addresses"
    )
    address_type = models.CharField(max_length=16, choices=AddressType.choices)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "party_address"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(address_type__in=["BILLING", "PHYSICAL", "DEPOT"]),
                name="party_address_type_valid",
            ),
        )

    def __str__(self):
        return self.line1
