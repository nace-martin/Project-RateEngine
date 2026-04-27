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
from parties.models import Company
from pricing_v4.adapter import PricingServiceV4Adapter, PricingMode
from quotes.models import Quote
from quotes.spot_models import SpotPricingEnvelopeDB, SPEAcknowledgementDB, SPEChargeLineDB, SPESourceBatchDB
from quotes.spot_services import SpotTriggerReason


pytestmark = pytest.mark.django_db


def _create_location(code: str, country: Country) -> Location:
    return create_location(
        code=code,
        name=f"{code} Airport",
        country=country,
    )


def _create_ready_spe(user, origin_code: str, dest_code: str, origin_country: str, dest_country: str, service_scope: str):
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

    spe = SpotPricingEnvelopeDB.objects.create(
        status=SpotPricingEnvelopeDB.Status.READY,
        shipment_context_json=ctx,
        conditions_json={},
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


def test_spot_create_quote_uses_export_prepaid_pgk_output_currency(monkeypatch):
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
        {"quote_request": {"service_scope": "D2D", "payment_term": "PREPAID", "output_currency": "PGK", "customer_id": str(customer.id)}},
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    quote = Quote.objects.get(id=payload["quote_id"])
    assert captured.get("output_currency") == "PGK"
    assert quote.output_currency == "PGK"


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
    assert "Conditional destination fee: Conditional" in response.json()["blocking_issues"]
