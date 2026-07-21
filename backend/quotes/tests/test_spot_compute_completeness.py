import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.dataclasses import CalculatedChargeLine, CalculatedTotals, QuoteCharges
from core.models import Currency, Country, Location
from core.tests.helpers import create_location
from crm.models import Interaction, Opportunity
from parties.models import Company, Contact
from pricing_v4.adapter import PricingServiceV4Adapter, PricingMode
from pricing_v4.models import ProductCode
from quotes.models import Quote, QuoteLine, QuoteTotal, QuoteVersion
from quotes.spot_models import SpotPricingEnvelopeDB, SPEAcknowledgementDB, SPEChargeLineDB, SPESourceBatchDB
from quotes.spot_services import SpotTriggerReason


pytestmark = pytest.mark.django_db


def _create_location(code: str, country: Country) -> Location:
    return create_location(
        code=code,
        name=f"{code} Airport",
        country=country,
    )


def _create_ready_spe(
    user,
    origin_code: str,
    dest_code: str,
    origin_country: str,
    dest_country: str,
    service_scope: str,
    finalized_review: bool = True,
    context_overrides: dict | None = None,
):
    ctx = {
        "origin_country": origin_country,
        "destination_country": dest_country,
        "origin_code": origin_code,
        "destination_code": dest_code,
        "commodity": "GCR",
        "total_weight_kg": 100.0,
        "pieces": 1,
        "service_scope": service_scope.lower(),
    }
    if context_overrides:
        ctx.update(context_overrides)

    conditions = {
        "draft_quote_review": {
            "status": "finalized",
            "finalized_by": user.id,
            "finalized_at": timezone.now().isoformat(),
            "idempotency_key": str(uuid.uuid4()),
        }
    } if finalized_review else {}

    spe = SpotPricingEnvelopeDB.objects.create(
        status=SpotPricingEnvelopeDB.Status.READY,
        shipment_context_json=ctx,
        conditions_json=conditions,
        spot_trigger_reason_code=SpotTriggerReason.MISSING_SCOPE_RATES,
        spot_trigger_reason_text="Missing required rate components",
        created_by=user,
        expires_at=timezone.now() + timedelta(hours=72),
    )

    SPEAcknowledgementDB.objects.create(
        envelope=spe,
        acknowledged_by=user,
        acknowledged_at=timezone.now(),
        statement=SPEAcknowledgementDB.ACKNOWLEDGEMENT_STATEMENT,
    )

    return spe


def _quote_charges_with_bucket(bucket: str) -> QuoteCharges:
    line = CalculatedChargeLine(
        service_component_id=uuid.uuid4(),
        service_component_code="TEST_COMPONENT",
        service_component_desc="Test Component",
        leg="MAIN",
        cost_pgk=Decimal("0.0"),
        sell_pgk=Decimal("0.0"),
        sell_pgk_incl_gst=Decimal("0.0"),
        sell_fcy=Decimal("0.0"),
        sell_fcy_incl_gst=Decimal("0.0"),
        cost_source="SPOT",
        bucket=bucket,
    )

    totals = CalculatedTotals(
        total_cost_pgk=Decimal("0.0"),
        total_sell_pgk=Decimal("0.0"),
        total_sell_pgk_incl_gst=Decimal("0.0"),
        total_sell_fcy=Decimal("0.0"),
        total_sell_fcy_incl_gst=Decimal("0.0"),
        total_sell_fcy_currency="PGK",
        has_missing_rates=False,
        notes=None,
    )

    return QuoteCharges(lines=[line], totals=totals)


def _patch_calculate_charges(monkeypatch, bucket: str):
    def fake_calculate(self):
        self.pricing_mode = PricingMode.SPOT
        return _quote_charges_with_bucket(bucket)

    monkeypatch.setattr(PricingServiceV4Adapter, "calculate_charges", fake_calculate)


def _quote_charges_for_buckets(buckets: list[str]) -> QuoteCharges:
    lines: list[CalculatedChargeLine] = []
    for idx, bucket in enumerate(buckets, start=1):
        lines.append(
            CalculatedChargeLine(
                service_component_id=uuid.uuid4(),
                service_component_code=f"TEST_COMPONENT_{idx}",
                service_component_desc=f"Test Component {idx}",
                leg="MAIN",
                cost_pgk=Decimal("0.0"),
                sell_pgk=Decimal("10.0"),
                sell_pgk_incl_gst=Decimal("10.0"),
                sell_fcy=Decimal("10.0"),
                sell_fcy_incl_gst=Decimal("10.0"),
                cost_source="SPOT",
                bucket=bucket,
            )
        )

    totals = CalculatedTotals(
        total_cost_pgk=Decimal("0.0"),
        total_sell_pgk=Decimal("30.0"),
        total_sell_pgk_incl_gst=Decimal("30.0"),
        total_sell_fcy=Decimal("30.0"),
        total_sell_fcy_incl_gst=Decimal("30.0"),
        total_sell_fcy_currency="PGK",
        has_missing_rates=False,
        notes=None,
    )
    return QuoteCharges(lines=lines, totals=totals)


def _setup_user_and_locations():
    currency = Currency.objects.create(code="PGK", name="Papua New Guinea Kina")
    pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=currency)
    au = Country.objects.create(code="AU", name="Australia", currency=currency)

    origin = _create_location("BNE", au)
    destination = _create_location("POM", pg)

    user = get_user_model().objects.create_user(username="spotuser", password="testpass")
    return user, origin, destination


def test_spot_compute_returns_completeness_state(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )

    _patch_calculate_charges(monkeypatch, bucket="airfreight")

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/compute/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "output_currency": "PGK"}},
        format="json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_complete"] is False
    assert data["has_missing_rates"] is True
    assert "DESTINATION_LOCAL" in data["missing_components"]
    assert "Missing required components" in (data.get("completeness_notes") or "")


def test_spot_create_quote_blocks_on_missing_components(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )

    _patch_calculate_charges(monkeypatch, bucket="airfreight")

    customer = Company.objects.create(
        name="Spot Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    initial_count = Quote.objects.count()

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "output_currency": "PGK", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["has_missing_rates"] is True
    assert "DESTINATION_LOCAL" in data["missing_components"]
    assert Quote.objects.count() == initial_count


def test_spot_create_quote_requires_finalized_exception_workspace_review(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
        finalized_review=False,
    )
    _patch_calculate_charges(monkeypatch, bucket="airfreight")
    customer = Company.objects.create(
        name="Unfinished Review Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "output_currency": "PGK", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    assert "review must be finalized" in response.json()["error"]


def test_spot_create_quote_preserves_persisted_spe_context(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    customer = Company.objects.create(
        name="Persisted Context Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )
    contact = Contact.objects.create(
        company=customer,
        first_name="Persisted",
        last_name="Contact",
        email="persisted@example.com",
        is_active=True,
    )
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
        context_overrides={
            "customer_id": str(customer.id),
            "contact_id": str(contact.id),
            "incoterm": "FOB",
            "service_scope": "P2P",
            "payment_term": "COLLECT",
            "output_currency": "USD",
        },
    )

    captured: dict[str, str] = {}

    def fake_calculate(self):
        self.pricing_mode = PricingMode.SPOT
        captured["payment_term"] = self.quote_input.shipment.payment_term
        captured["service_scope"] = self.quote_input.shipment.service_scope
        captured["output_currency"] = self.quote_input.output_currency
        return _quote_charges_with_bucket("airfreight")

    monkeypatch.setattr(PricingServiceV4Adapter, "calculate_charges", fake_calculate)

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {}},
        format="json",
    )

    assert response.status_code == 200
    quote = Quote.objects.get(id=response.json()["quote_id"])
    assert quote.customer_id == customer.id
    assert quote.contact_id == contact.id
    assert quote.incoterm == "FOB"
    assert quote.service_scope == "P2P"
    assert quote.payment_term == "COLLECT"
    assert quote.output_currency == "USD"
    assert captured == {
        "payment_term": "COLLECT",
        "service_scope": "P2P",
        "output_currency": "USD",
    }


def test_spot_create_quote_is_idempotent_after_quote_version_created(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
    )
    _patch_calculate_charges(monkeypatch, bucket="airfreight")
    customer = Company.objects.create(
        name="Idempotent Spot Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )

    client = APIClient()
    client.force_authenticate(user=user)
    payload = {"quote_request": {"service_scope": "P2P", "payment_term": "PREPAID", "output_currency": "PGK", "customer_id": str(customer.id)}}

    first = client.post(f"/api/v3/spot/envelopes/{spe.id}/create-quote/", payload, format="json")
    second = client.post(f"/api/v3/spot/envelopes/{spe.id}/create-quote/", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["quote_id"] == first.json()["quote_id"]
    spe.refresh_from_db()
    assert spe.quote.versions.filter(reason="Created from SPOT Envelope").count() == 1


def test_finalized_review_editing_charges_reopens_and_blocks_quote_until_refinalized(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    customer = Company.objects.create(
        name="Invalidated Review Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
        context_overrides={"customer_id": str(customer.id)},
    )
    spe.status = SpotPricingEnvelopeDB.Status.DRAFT
    spe.save(update_fields=["status"])

    client = APIClient()
    client.force_authenticate(user=user)

    patch_response = client.patch(
        f"/api/v3/spot/envelopes/{spe.id}/",
        {
            "charges": [
                {
                    "code": "SPOT-FRT",
                    "description": "Updated spot freight",
                    "amount": "100.00",
                    "currency": "USD",
                    "unit": "flat",
                    "bucket": "airfreight",
                    "is_primary_cost": True,
                    "source_reference": "edited intake",
                }
            ]
        },
        format="json",
    )

    assert patch_response.status_code == 200, patch_response.json()
    spe.refresh_from_db()
    assert spe.conditions_json["draft_quote_review"]["status"] == "in_review"
    assert spe.conditions_json["draft_quote_review"]["invalidated_reason"] == "charge_patch"

    _patch_calculate_charges(monkeypatch, bucket="airfreight")
    create_response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "P2P", "payment_term": "PREPAID", "output_currency": "PGK"}},
        format="json",
    )

    assert create_response.status_code == 400
    assert "review must be finalized" in create_response.json()["error"]

    product_code, _ = ProductCode.objects.get_or_create(
        id=2901,
        defaults={
            "code": "IMP-SPOT-FRT",
            "description": "Import Spot Freight",
            "domain": ProductCode.DOMAIN_IMPORT,
            "category": ProductCode.CATEGORY_FREIGHT,
            "is_gst_applicable": True,
            "gst_rate": "0.10",
            "gst_treatment": ProductCode.GST_TREATMENT_STANDARD,
            "gl_revenue_code": "4201",
            "gl_cost_code": "5201",
            "default_unit": ProductCode.UNIT_SHIPMENT,
        },
    )
    line = spe.charge_lines.get()
    line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
    line.manual_resolved_product_code = product_code
    line.save(update_fields=["manual_resolution_status", "manual_resolved_product_code"])

    spe.conditions_json["draft_quote_review"].update({
        "status": "finalized",
        "finalized_by": user.id,
        "finalized_at": timezone.now().isoformat(),
        "idempotency_key": str(uuid.uuid4()),
    })
    spe.status = SpotPricingEnvelopeDB.Status.READY
    spe.save(update_fields=["conditions_json", "status"])

    refinalized_response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "P2P", "payment_term": "PREPAID", "output_currency": "PGK"}},
        format="json",
    )
    assert refinalized_response.status_code == 200


def test_spot_create_quote_failure_rolls_back_partial_objects(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    customer = Company.objects.create(
        name="Rollback Spot Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
        context_overrides={"customer_id": str(customer.id)},
    )
    _patch_calculate_charges(monkeypatch, bucket="airfreight")

    def fail_total_create(*args, **kwargs):
        raise RuntimeError("forced total failure")

    monkeypatch.setattr(QuoteTotal.objects, "create", fail_total_create)

    client = APIClient()
    client.force_authenticate(user=user)
    initial_quote_count = Quote.objects.count()
    initial_version_count = QuoteVersion.objects.count()
    initial_line_count = QuoteLine.objects.count()
    initial_total_count = QuoteTotal.objects.count()

    with pytest.raises(RuntimeError, match="forced total failure"):
        client.post(
            f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
            {"quote_request": {"service_scope": "P2P", "payment_term": "PREPAID", "output_currency": "PGK"}},
            format="json",
        )

    spe.refresh_from_db()
    assert spe.quote_id is None
    assert Quote.objects.count() == initial_quote_count
    assert QuoteVersion.objects.count() == initial_version_count
    assert QuoteLine.objects.count() == initial_line_count
    assert QuoteTotal.objects.count() == initial_total_count


def test_spot_compute_uses_import_prepaid_fcy_output_currency(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )

    captured: dict[str, str] = {}

    def fake_calculate(self):
        self.pricing_mode = PricingMode.SPOT
        captured["output_currency"] = self.quote_input.output_currency
        return _quote_charges_with_bucket("airfreight")

    monkeypatch.setattr(PricingServiceV4Adapter, "calculate_charges", fake_calculate)

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/compute/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "output_currency": "PGK"}},
        format="json",
    )

    assert response.status_code == 200
    assert captured.get("output_currency") == "AUD"


def test_spot_create_quote_uses_export_collect_non_au_fcy_output_currency(monkeypatch):
    pgk = Currency.objects.create(code="PGK", name="Papua New Guinea Kina")
    usd = Currency.objects.create(code="USD", name="US Dollar")
    pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)
    hk = Country.objects.create(code="HK", name="Hong Kong", currency=usd)

    origin = _create_location("POM", pg)
    destination = _create_location("HKG", hk)
    user = get_user_model().objects.create_user(username="spotcurrency", password="testpass")
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="PG",
        dest_country="HK",
        service_scope="D2D",
    )

    captured: dict[str, str] = {}

    def fake_calculate(self):
        self.pricing_mode = PricingMode.SPOT
        captured["output_currency"] = self.quote_input.output_currency
        return _quote_charges_for_buckets(["origin_charges", "airfreight", "destination_charges"])

    monkeypatch.setattr(PricingServiceV4Adapter, "calculate_charges", fake_calculate)

    customer = Company.objects.create(
        name="Spot Currency Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "D2D", "payment_term": "COLLECT", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    quote = Quote.objects.get(id=payload["quote_id"])
    assert captured.get("output_currency") == "USD"
    assert quote.output_currency == "USD"


def test_spot_create_quote_persists_selected_contact_and_incoterm(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
    )

    def fake_calculate(self):
        self.pricing_mode = PricingMode.SPOT
        return _quote_charges_for_buckets(["origin_charges", "airfreight", "destination_charges"])

    monkeypatch.setattr(PricingServiceV4Adapter, "calculate_charges", fake_calculate)

    customer = Company.objects.create(
        name="Spot Detail Customer",
        is_customer=True,
        company_type="CUSTOMER",
    )
    contact = Contact.objects.create(
        company=customer,
        first_name="Chris",
        last_name="Im",
        email="chris@example.com",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {
            "quote_request": {
                "service_scope": "D2D",
                "payment_term": "COLLECT",
                "output_currency": "PGK",
                "customer_id": str(customer.id),
                "contact_id": str(contact.id),
                "incoterm": "EXW",
            }
        },
        format="json",
    )

    assert response.status_code == 200
    quote = Quote.objects.get(id=response.json()["quote_id"])
    version = quote.versions.get(version_number=1)

    assert quote.customer_id == customer.id
    assert quote.contact_id == contact.id
    assert quote.incoterm == "EXW"
    assert quote.payment_term == "COLLECT"
    assert quote.service_scope == "D2D"
    assert quote.request_details_json["contact_id"] == str(contact.id)
    assert quote.request_details_json["incoterm"] == "EXW"
    assert version.payload_json["contact_id"] == str(contact.id)
    assert version.payload_json["incoterm"] == "EXW"


def test_spot_create_quote_rejects_contact_from_another_customer(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["origin_charges", "airfreight", "destination_charges"]),
    )

    customer = Company.objects.create(name="Spot Customer", is_customer=True, company_type="CUSTOMER")
    other_customer = Company.objects.create(name="Other Customer", is_customer=True, company_type="CUSTOMER")
    other_contact = Contact.objects.create(company=other_customer, first_name="Wrong", last_name="Contact")

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {
            "quote_request": {
                "service_scope": "D2D",
                "payment_term": "COLLECT",
                "customer_id": str(customer.id),
                "contact_id": str(other_contact.id),
                "incoterm": "EXW",
            }
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.json()["error"] == "Selected contact is not available for this customer/user."


def test_spot_create_quote_auto_creates_and_links_opportunity(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["origin_charges", "airfreight", "destination_charges"]),
    )
    customer = Company.objects.create(name="Spot Opportunity Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "D2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 200
    quote = Quote.objects.get(id=response.json()["quote_id"])
    opportunity = quote.opportunity
    assert opportunity is not None
    assert opportunity.company == customer
    assert opportunity.service_type == "AIR"
    assert opportunity.direction == Quote.ShipmentType.IMPORT
    assert opportunity.scope == "D2D"
    assert opportunity.interactions.filter(
        interaction_type=Interaction.InteractionType.SYSTEM,
        system_event_type="QUOTE_OPPORTUNITY_CREATED",
        outcomes__contains=f"quote_id={quote.id}",
    ).exists()
    assert not Opportunity.objects.filter(service_type="DOMESTIC").exists()


def test_spot_create_quote_allows_matched_exact_alias_line(monkeypatch):
    pgk = Currency.objects.create(code="PGK", name="Papua New Guinea Kina")
    usd = Currency.objects.create(code="USD", name="US Dollar")
    pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)
    hk = Country.objects.create(code="HK", name="Hong Kong", currency=usd)

    origin = _create_location("POM", pg)
    destination = _create_location("HKG", hk)
    user = get_user_model().objects.create_user(username="spotmatched", password="testpass")
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="PG",
        dest_country="HK",
        service_scope="D2D",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="FREIGHT",
        description="Airfreight",
        amount=Decimal("5.00"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        source_reference="Agent reply",
        source_excerpt="Airfreight USD 5/kg",
        source_line_number=1,
        source_line_identity="assertion-line:1",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        entered_at=timezone.now(),
    )

    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["origin_charges", "airfreight", "destination_charges"]),
    )
    customer = Company.objects.create(name="Matched Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "D2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_spot_create_quote_blocks_unmapped_line(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        source_reference="Agent reply",
        normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.NONE,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["destination_charges"]),
    )
    customer = Company.objects.create(name="Blocked Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    assert "Destination fee: Unmapped" in response.json()["blocking_issues"]


def test_spot_create_quote_blocks_pattern_alias_matched_line(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        source_reference="Agent reply",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.PATTERN_ALIAS,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["destination_charges"]),
    )
    customer = Company.objects.create(name="Pattern Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    assert "Destination fee: Review non-exact match" in response.json()["blocking_issues"]


def test_spot_create_quote_blocks_ambiguous_line(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        source_reference="Agent reply",
        normalization_status=SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["destination_charges"]),
    )
    customer = Company.objects.create(name="Ambiguous Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    assert "Destination fee: Ambiguous" in response.json()["blocking_issues"]


def test_spot_create_quote_blocks_risky_source_batch_until_reviewed(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPESourceBatchDB.objects.create(
        envelope=spe,
        source_kind=SPESourceBatchDB.SourceKind.AGENT,
        source_type=SPESourceBatchDB.SourceType.TEXT,
        target_bucket=SPESourceBatchDB.TargetBucket.DESTINATION_CHARGES,
        label="Agent reply",
        source_reference="Agent reply",
        raw_text="Destination fee USD 75",
        analysis_summary_json={
            "can_proceed": True,
            "ai_used": True,
            "imported_charge_count": 1,
            "critic_missed_charges": ["Destination delivery"],
        },
        created_by=user,
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        source_reference="Agent reply",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["destination_charges"]),
    )
    customer = Company.objects.create(name="Risk Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["intake_safety"]["is_safe_to_quote"] is False


def test_spot_create_quote_allows_low_confidence_source_warning(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPESourceBatchDB.objects.create(
        envelope=spe,
        source_kind=SPESourceBatchDB.SourceKind.AGENT,
        source_type=SPESourceBatchDB.SourceType.TEXT,
        target_bucket=SPESourceBatchDB.TargetBucket.DESTINATION_CHARGES,
        label="Uploaded rates",
        source_reference="Uploaded rates",
        raw_text="Destination fee USD 75",
        analysis_summary_json={
            "can_proceed": True,
            "ai_used": True,
            "imported_charge_count": 1,
            "low_confidence_line_count": 1,
        },
        created_by=user,
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        source_reference="Uploaded rates",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["destination_charges"]),
    )
    customer = Company.objects.create(name="Low Confidence Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    detail_response = client.get(f"/api/v3/spot/envelopes/{spe.id}/")
    assert detail_response.status_code == 200
    assert detail_response.json()["intake_safety"]["is_safe_to_quote"] is True
    assert detail_response.json()["sources"][0]["review_status"] == "NOT_REQUIRED"

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_spot_create_quote_blocks_unacknowledged_conditional_matched_line(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Conditional destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        conditional=True,
        conditional_acknowledged=False,
        source_reference="Agent reply",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["destination_charges"]),
    )
    customer = Company.objects.create(name="Conditional Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Resolve SPOT charge exceptions before creating quote."
    assert "Conditional destination fee: Conditional" in response.json()["blocking_issues"]


def test_spot_create_quote_allows_acknowledged_conditional_matched_line(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_ready_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DESTINATION_LOCAL",
        description="Conditional destination fee",
        amount=Decimal("75.00"),
        currency="USD",
        unit="flat",
        bucket="destination_charges",
        conditional=True,
        conditional_acknowledged=True,
        conditional_acknowledged_by=user,
        conditional_acknowledged_at=timezone.now(),
        source_reference="Agent reply",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        entered_at=timezone.now(),
    )
    monkeypatch.setattr(
        PricingServiceV4Adapter,
        "calculate_charges",
        lambda self: _quote_charges_for_buckets(["airfreight", "destination_charges"]),
    )
    customer = Company.objects.create(name="Acknowledged Conditional Customer", is_customer=True, company_type="CUSTOMER")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/create-quote/",
        {"quote_request": {"service_scope": "A2D", "payment_term": "PREPAID", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
