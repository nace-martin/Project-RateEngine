"""Phase 1 integrity checks run unchanged on SQLite and PostgreSQL."""

import uuid

import pytest
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from core.models import GeoLocation, GeoLocationIdentifier, Location
from parties.models import (
    Company,
    OrgBranch,
    OrgCompany,
    OrgDepartment,
    OrgOperatingEntity,
    PartyAddress,
    PartyContact,
    PartyMaster,
    PartyRole,
    PartyRoleIdentifier,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def location():
    return GeoLocation.objects.create(
        canonical_name="Jacksons International Airport",
        country_code="PG",
        location_type="AIRPORT",
    )


@pytest.fixture
def branch(location):
    company = OrgCompany.objects.create(
        name="EFM Group", code="EFM", country_code="PG", currency_code="PGK"
    )
    entity = OrgOperatingEntity.objects.create(
        company=company, name="EFM PNG", code="PNG", functional_currency="PGK"
    )
    return OrgBranch.objects.create(
        operating_entity=entity, location=location, name="Port Moresby", code="POM"
    )


@pytest.fixture
def party():
    return PartyMaster.objects.create(
        legal_name="Air Niugini", entity_type="COMPANY", country_code="PG"
    )


def assert_rejected(instance):
    """Both Django validation and writes bypassing validation must reject the row."""
    with pytest.raises(ValidationError):
        instance.full_clean()
    with pytest.raises(IntegrityError), transaction.atomic():
        instance.save(force_insert=True)
        connection.check_constraints()


def test_org_hierarchy_has_required_parents_and_no_shadow_parties(branch):
    department = OrgDepartment.objects.create(
        branch=branch, name="Air Freight", code="AIR"
    )
    department.full_clean()
    assert department.branch.operating_entity.company.code == "EFM"
    assert branch.location.country_code == "PG"
    assert not PartyMaster.objects.exists()
    assert not Company.objects.exists()
    assert not Location.objects.exists()
    with pytest.raises(ValueError):
        OrgDepartment(branch=branch.operating_entity)
    with pytest.raises(ValueError):
        OrgBranch(operating_entity=branch.operating_entity.company)


@pytest.mark.parametrize(
    "model,field",
    [
        (OrgOperatingEntity, "company"),
        (OrgBranch, "operating_entity"),
        (OrgDepartment, "branch"),
    ],
)
@pytest.mark.parametrize("parent_id", [None, uuid.UUID(int=1)])
def test_org_orphans_rejected(branch, model, field, parent_id):
    kwargs = {"name": "Invalid", "code": "INVALID", f"{field}_id": parent_id}
    if model is OrgOperatingEntity:
        kwargs["functional_currency"] = "PGK"
    if model is OrgBranch:
        kwargs["location"] = branch.location
    assert_rejected(model(**kwargs))


def test_org_unique_codes_are_scoped_to_parent(branch):
    entity = branch.operating_entity
    assert_rejected(
        OrgCompany(name="Duplicate", code="EFM", country_code="AU", currency_code="AUD")
    )
    assert_rejected(
        OrgOperatingEntity(
            company=entity.company,
            name="Duplicate",
            code="PNG",
            functional_currency="PGK",
        )
    )
    assert_rejected(
        OrgBranch(
            operating_entity=entity,
            location=branch.location,
            name="Duplicate",
            code="POM",
        )
    )
    OrgDepartment.objects.create(branch=branch, name="Air Freight", code="AIR")
    assert_rejected(OrgDepartment(branch=branch, name="Duplicate", code="AIR"))
    other_company = OrgCompany.objects.create(
        name="Other", code="OTHER", country_code="PG", currency_code="PGK"
    )
    other_entity = OrgOperatingEntity.objects.create(
        company=other_company, name="Other PNG", code="PNG", functional_currency="PGK"
    )
    other_branch = OrgBranch.objects.create(
        operating_entity=other_entity,
        location=branch.location,
        name="Other station",
        code="POM",
    )
    OrgDepartment.objects.create(
        branch=other_branch, name="Air Freight", code="AIR"
    ).full_clean()


def test_org_parent_deletion_is_protected(branch):
    OrgDepartment.objects.create(branch=branch, name="Air Freight", code="AIR")
    for parent in [
        branch,
        branch.operating_entity,
        branch.operating_entity.company,
        branch.location,
    ]:
        with pytest.raises(ProtectedError):
            parent.delete()


def test_single_customer_and_simultaneous_roles(party):
    PartyRole.objects.create(party=party, role_type="CUSTOMER").full_clean()
    assert list(party.roles.values_list("role_type", flat=True)) == ["CUSTOMER"]
    for role_type in ["CARRIER", "SUPPLIER", "AGENT", "VENDOR"]:
        PartyRole.objects.create(party=party, role_type=role_type).full_clean()
    assert PartyMaster.objects.count() == 1
    assert party.roles.count() == 5
    assert not Company.objects.exists()


def test_duplicate_role_and_invalid_role_rejected(party):
    PartyRole.objects.create(party=party, role_type="CARRIER")
    assert_rejected(PartyRole(party=party, role_type="CARRIER"))
    assert_rejected(PartyRole(party=party, role_type="BRANCH"))


def test_role_identifier_conflict_and_inactive_identity_retained(party):
    role = PartyRole.objects.create(party=party, role_type="CARRIER")
    identifier = PartyRoleIdentifier.objects.create(
        role=role, scheme="IATA_CARRIER", value="PX"
    )
    other = PartyMaster.objects.create(
        legal_name="Other airline", country_code="PG", entity_type="COMPANY"
    )
    other_role = PartyRole.objects.create(party=other, role_type="CARRIER")
    assert_rejected(
        PartyRoleIdentifier(role=other_role, scheme="IATA_CARRIER", value="PX")
    )
    role.is_active = False
    role.save(update_fields=["is_active"])
    assert not party.roles.filter(is_active=True).exists()
    assert party.roles.get(pk=role.pk).is_active is False
    assert PartyRoleIdentifier.objects.get(pk=identifier.pk).role_id == role.pk
    assert_rejected(PartyRole(party=party, role_type="CARRIER"))
    assert_rejected(
        PartyRoleIdentifier(role=other_role, scheme="IATA_CARRIER", value="PX")
    )
    with pytest.raises(ProtectedError):
        role.delete()
    with pytest.raises(ProtectedError):
        party.delete()
    role.is_active = True
    role.save(update_fields=["is_active"])
    assert party.roles.filter(is_active=True).count() == 1


def test_party_identity_contact_and_address_constraints(party, location):
    assert_rejected(
        PartyMaster(
            legal_name=party.legal_name, country_code="PG", entity_type="COMPANY"
        )
    )
    contact = {
        "party": party,
        "first_name": "Test",
        "last_name": "Contact",
        "email": "contact@example.test",
    }
    PartyContact.objects.create(**contact).full_clean()
    assert_rejected(PartyContact(**contact))
    other = PartyMaster.objects.create(
        legal_name="Other", country_code="PG", entity_type="COMPANY"
    )
    PartyContact.objects.create(**{**contact, "party": other}).full_clean()
    address = PartyAddress.objects.create(
        party=party,
        location=location,
        address_type="BILLING",
        line1="Test street",
        city="Port Moresby",
        postal_code="121",
    )
    address.full_clean()
    assert address.location_id == location.id
    assert_rejected(
        PartyAddress(
            party=party,
            location=location,
            address_type="UNKNOWN",
            line1="Test",
            city="POM",
        )
    )


@pytest.mark.parametrize(
    "scheme", ["IATA_CARRIER", "ICAO", "SCAC", "CUSTOMS_BROKER", "TAX_ID"]
)
def test_role_identifier_schemes(party, scheme):
    role = PartyRole.objects.create(party=party, role_type="SUPPLIER")
    PartyRoleIdentifier.objects.create(
        role=role, scheme=scheme, value="TEST"
    ).full_clean()


@pytest.mark.parametrize(
    "scheme,value", [("UNKNOWN", "PX"), ("IATA_CARRIER", ""), ("IATA_CARRIER", " PX ")]
)
def test_invalid_role_identifiers_rejected(party, scheme, value):
    role = PartyRole.objects.create(party=party, role_type="CARRIER")
    assert_rejected(PartyRoleIdentifier(role=role, scheme=scheme, value=value))


def test_multiple_geo_identifiers_and_stable_relational_identity(branch):
    location = branch.location
    for scheme, code in [
        ("IATA", "POM"),
        ("ICAO", "AYPY"),
        ("INTERNAL_STATION", "EFM-POM-AIR"),
    ]:
        GeoLocationIdentifier.objects.create(
            location=location, scheme=scheme, code=code
        ).full_clean()
    assert location.identifiers.count() == 3
    assert isinstance(location.pk, uuid.UUID)
    with pytest.raises(FieldDoesNotExist):
        GeoLocation._meta.get_field("code")
    GeoLocationIdentifier.objects.filter(scheme="INTERNAL_STATION").update(
        code="EFM-POM-AIR-NEW"
    )
    branch.refresh_from_db()
    assert branch.location_id == location.pk
    assert not Location.objects.exists()


def test_seaport_unlocode_and_scheme_uniqueness(location):
    port = GeoLocation.objects.create(
        canonical_name="Port Moresby Port", country_code="PG", location_type="SEAPORT"
    )
    GeoLocationIdentifier.objects.create(
        location=port, scheme="UNLOCODE", code="PGPOM"
    ).full_clean()
    assert_rejected(
        GeoLocationIdentifier(location=location, scheme="UNLOCODE", code="PGPOM")
    )
    GeoLocationIdentifier.objects.create(
        location=location, scheme="INTERNAL_STATION", code="PGPOM"
    ).full_clean()


@pytest.mark.parametrize("scheme", ["POSTAL", "CUSTOM", "GPS", "UNKNOWN", "iata"])
def test_forbidden_geo_schemes_rejected(location, scheme):
    assert set(GeoLocationIdentifier.Scheme.values) == {
        "IATA",
        "ICAO",
        "UNLOCODE",
        "INTERNAL_STATION",
    }
    assert_rejected(GeoLocationIdentifier(location=location, scheme=scheme, code="POM"))


@pytest.mark.parametrize("code", ["", "pom", " POM "])
def test_geo_identifier_must_be_normalized(location, code):
    assert_rejected(GeoLocationIdentifier(location=location, scheme="IATA", code=code))


def test_invalid_location_type_rejected():
    assert_rejected(
        GeoLocation(
            canonical_name="Invalid", country_code="PG", location_type="UNKNOWN"
        )
    )


@pytest.mark.parametrize(
    "model,table",
    [
        (OrgCompany, "org_company"),
        (OrgOperatingEntity, "org_operating_entity"),
        (OrgBranch, "org_branch"),
        (OrgDepartment, "org_department"),
        (GeoLocation, "geo_location"),
        (GeoLocationIdentifier, "geo_location_identifier"),
        (PartyMaster, "party_master"),
        (PartyRole, "party_role"),
        (PartyRoleIdentifier, "party_role_identifier"),
        (PartyContact, "party_contact"),
        (PartyAddress, "party_address"),
    ],
)
def test_foundation_models_registered_and_tables_created(model, table):
    assert apps.get_model(model._meta.app_label, model.__name__) is model
    assert model._meta.db_table == table
    assert table in connection.introspection.table_names()


def test_no_unexpected_migration_state():
    call_command("makemigrations", "core", "parties", check=True, dry_run=True)
