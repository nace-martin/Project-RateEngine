import pytest

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import City, Country
from core.models import Currency
from parties.models import Address, Company, Contact


pytestmark = pytest.mark.django_db


def _mk_user(username: str, role: str):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass",
        role=role,
    )


def test_customer_detail_get_allowed_for_authenticated_user():
    user = _mk_user("sales_get", "sales")
    company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(f"/api/v3/customer-details/{company.id}/")
    assert response.status_code == 200
    assert response.data["company_name"] == "Seed Customer"
    assert "commercial_profile" in response.data


def test_customer_detail_put_forbidden_for_non_admin():
    user = _mk_user("sales_put", "sales")
    company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.put(
        f"/api/v3/customer-details/{company.id}/",
        {"company_name": "Renamed Customer"},
        format="json",
    )
    assert response.status_code == 403
    company.refresh_from_db()
    assert company.name == "Seed Customer"


def test_customer_detail_put_allowed_for_admin():
    admin = _mk_user("admin_put", "admin")
    company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.put(
        f"/api/v3/customer-details/{company.id}/",
        {"company_name": "Renamed Customer"},
        format="json",
    )
    assert response.status_code == 200
    company.refresh_from_db()
    assert company.name == "Renamed Customer"


def test_customer_detail_put_updates_commercial_profile():
    admin = _mk_user("admin_put_commercial", "admin")
    company = Company.objects.create(name="Commercial Customer", is_customer=True, company_type="CUSTOMER")
    Currency.objects.create(code="AUD", name="Australian Dollar")
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.put(
        f"/api/v3/customer-details/{company.id}/",
        {
            "company_name": "Commercial Customer",
            "commercial_profile": {
                "preferred_quote_currency": "AUD",
                "default_margin_percent": "12.50",
                "min_margin_percent": "8.00",
                "payment_term_default": "PREPAID",
            },
        },
        format="json",
    )

    assert response.status_code == 200
    company.refresh_from_db()
    profile = company.commercial_profile
    assert profile.preferred_quote_currency.code == "AUD"
    assert str(profile.default_margin_percent) == "12.50"
    assert str(profile.min_margin_percent) == "8.00"
    assert profile.payment_term_default == "PREPAID"


def test_customer_detail_put_updates_extended_customer_fields():
    admin = _mk_user("admin_put_full", "admin")
    company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
    Contact.objects.create(
        company=company,
        first_name="Old",
        last_name="Name",
        email="old@example.com",
        phone="+675111",
        is_primary=True,
        is_active=True,
    )
    country = Country.objects.create(code="PG", name="Papua New Guinea")
    city = City.objects.create(name="Port Moresby", country=country)
    au_country = Country.objects.create(code="AU", name="Australia")
    au_city = City.objects.create(name="Brisbane", country=au_country)
    Address.objects.create(
        company=company,
        address_line_1="Old Street",
        city=city,
        country=country,
        postal_code="111",
        is_primary=True,
    )
    client = APIClient()
    client.force_authenticate(user=admin)

    payload = {
        "company_name": "Updated Customer Name",
        "audience_type": "OVERSEAS_PARTNER_AU",
        "address_description": "Level 2, Unit 7",
        "contact_person_name": "Jane Doe",
        "contact_person_email": "jane@example.com",
        "contact_person_phone": "+675999",
        "primary_address": {
            "address_line_1": "123 Queen Street",
            "address_line_2": "Suite 9",
            "city_id": str(au_city.id),
            "city": "Brisbane",
            "postcode": "4000",
            "country": "AU",
        },
    }
    response = client.put(
        f"/api/v3/customer-details/{company.id}/",
        payload,
        format="json",
    )
    assert response.status_code == 200

    company.refresh_from_db()
    assert company.name == "Updated Customer Name"
    assert company.audience_type == "OVERSEAS_PARTNER_AU"
    assert company.address_description == "Level 2, Unit 7"

    contact = company.contacts.get(is_primary=True)
    assert contact.first_name == "Jane"
    assert contact.last_name == "Doe"
    assert contact.email == "jane@example.com"
    assert contact.phone == "+675999"

    address = company.addresses.get(is_primary=True)
    assert address.address_line_1 == "123 Queen Street"
    assert address.address_line_2 == "Suite 9"
    assert address.city.name == "Brisbane"
    assert address.country.code == "AU"
    assert address.postal_code == "4000"


def test_customer_detail_put_rejects_invalid_audience_type():
    admin = _mk_user("admin_put_bad_audience", "admin")
    company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.put(
        f"/api/v3/customer-details/{company.id}/",
        {"audience_type": "INVALID_TYPE"},
        format="json",
    )
    assert response.status_code == 400


def test_customer_detail_delete_forbidden_for_non_admin():
    user = _mk_user("sales_delete", "sales")
    company = Company.objects.create(name="Seed Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.delete(f"/api/v3/customer-details/{company.id}/")
    assert response.status_code == 403
    assert Company.objects.filter(id=company.id).exists()


def test_customer_detail_delete_allowed_for_admin():
    admin = _mk_user("admin_delete", "admin")
    company = Company.objects.create(name="Delete Me Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.delete(f"/api/v3/customer-details/{company.id}/")
    assert response.status_code == 204
    assert not Company.objects.filter(id=company.id).exists()


def test_customer_detail_patch_archive_allowed_for_admin():
    admin = _mk_user("admin_archive", "admin")
    company = Company.objects.create(name="Archive Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.patch(
        f"/api/v3/customer-details/{company.id}/",
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200
    company.refresh_from_db()
    assert company.is_active is False


def test_customer_detail_patch_archive_forbidden_for_non_admin():
    user = _mk_user("sales_archive", "sales")
    company = Company.objects.create(name="Archive Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.patch(
        f"/api/v3/customer-details/{company.id}/",
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 403
