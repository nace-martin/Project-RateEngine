import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from django.urls import reverse

from core.models import Currency, Country
from core.tests.helpers import create_location
from pricing_v4.models import ProductCode
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB, SPESourceBatchDB
from quotes.spot_services import SpotTriggerReason
from quotes.spot_schemas import SpotPricingEnvelope, SPEShipmentContext, SPEStatus


pytestmark = pytest.mark.django_db


def _setup_test_data():
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")

    currency = Currency.objects.create(code="PGK", name="Papua New Guinea Kina")
    pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=currency)
    au = Country.objects.create(code="AU", name="Australia", currency=currency)

    origin = create_location(code="POM", name="Port Moresby", country=pg)
    dest = create_location(code="SYD", name="Sydney", country=au)

    product_code = ProductCode.objects.create(
        id=5001,
        code="EXP-FRT-TEST",
        description="Export Freight Test",
        domain="EXPORT",
        category="FREIGHT",
        default_unit="KG",
        is_gst_applicable=False,
        gst_rate=Decimal("0.00"),
        gl_revenue_code="4100",
        gl_cost_code="5100",
    )

    return user, origin, dest, product_code


def test_manual_resolution_syncs_batch_analysis_summary():
    user, origin, dest, pc = _setup_test_data()
    client = APIClient()
    client.force_authenticate(user=user)

    # 1. Create SPE with an unsafe batch (unmapped line)
    spe = SpotPricingEnvelopeDB.objects.create(
        created_by=user,
        status="draft",
        expires_at=timezone.now() + timedelta(days=7),
        shipment_context_json={
            'origin_country': 'PG',
            'destination_country': 'AU',
            'origin_code': 'POM',
            'destination_code': 'SYD',
            'total_weight_kg': 100,
            'pieces': 1,
            'commodity': 'GCR',
            'service_scope': 'D2D'
        },
        spot_trigger_reason_code=SpotTriggerReason.MISSING_SCOPE_RATES,
        spot_trigger_reason_text="Missing required rate components",
    )

    batch = SPESourceBatchDB.objects.create(
        envelope=spe,
        source_kind='AGENT',
        source_type='TEXT',
        label='Test Batch',
        analysis_summary_json={
            'can_proceed': True,
            'unmapped_line_count': 1,
            'risk_flags': ['unmapped_lines'],
            'risk_level': 'MEDIUM',
            'is_safe_to_quote': False
        }
    )

    cl = SPEChargeLineDB.objects.create(
        envelope=spe,
        source_batch=batch,
        code='UNMAPPED',
        description='Test Unmapped Charge',
        amount=100,
        currency='USD',
        unit='flat',
        bucket='airfreight',
        normalization_status='UNMAPPED',
        entered_at=timezone.now(),
        entered_by=user,
        source_reference='Test'
    )

    # Verify initial state is unsafe
    detail_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": spe.id})
    resp = client.get(detail_url)
    assert resp.json()["intake_safety"]["is_safe_to_quote"] is False

    # 2. Resolve the line via API
    resolution_url = reverse(
        "quotes:spot-charge-line-manual-resolution",
        kwargs={"envelope_id": spe.id, "charge_line_id": cl.id}
    )
    resp = client.patch(resolution_url, {"manual_resolved_product_code_id": pc.id}, format="json")
    assert resp.status_code == 200

    # 3. Verify batch summary is synced and SPE is now safe
    batch.refresh_from_db()
    assert batch.analysis_summary_json["unmapped_line_count"] == 0
    assert batch.analysis_summary_json["risk_level"] == "LOW"

    resp = client.get(detail_url)
    assert resp.json()["intake_safety"]["is_safe_to_quote"] is True


def test_patch_preserves_imported_charge_audit_when_round_tripped_by_id():
    user, origin, dest, pc = _setup_test_data()
    client = APIClient()
    client.force_authenticate(user=user)

    spe = SpotPricingEnvelopeDB.objects.create(
        created_by=user,
        status="draft",
        expires_at=timezone.now() + timedelta(days=7),
        shipment_context_json={
            "origin_country": "PG",
            "destination_country": "AU",
            "origin_code": origin.code,
            "destination_code": dest.code,
            "total_weight_kg": 100,
            "pieces": 1,
            "commodity": "GCR",
            "service_scope": "D2D",
        },
        spot_trigger_reason_code=SpotTriggerReason.MISSING_SCOPE_RATES,
        spot_trigger_reason_text="Missing required rate components",
    )
    batch = SPESourceBatchDB.objects.create(
        envelope=spe,
        source_kind="AGENT",
        source_type="TEXT",
        label="Agent reply",
        analysis_summary_json={"can_proceed": True, "unmapped_line_count": 0, "risk_level": "LOW"},
    )
    line = SPEChargeLineDB.objects.create(
        envelope=spe,
        source_batch=batch,
        code="FRT_SPOT",
        description="Import Air Freight",
        amount=Decimal("100.00"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        source_label="A/F",
        normalized_label="a f",
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        normalization_method=SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
        resolved_product_code=pc,
        source_reference="Agent email",
        source_line_identity="agent:1",
        entered_at=timezone.now(),
        entered_by=user,
    )

    detail_url = reverse("quotes:spot-envelope-detail", kwargs={"envelope_id": spe.id})
    response = client.patch(
        detail_url,
        {
            "charges": [
                {
                    "charge_line_id": str(line.id),
                    "code": line.code,
                    "description": line.description,
                    "amount": "125.00",
                    "currency": line.currency,
                    "unit": line.unit,
                    "bucket": line.bucket,
                    "is_primary_cost": line.is_primary_cost,
                    "conditional": line.conditional,
                    "source_reference": line.source_reference,
                    "source_line_identity": line.source_line_identity,
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    payload_line = response.json()["charges"][0]
    assert payload_line["id"] == str(line.id)
    assert payload_line["source_label"] == "A/F"
    assert payload_line["normalization_status"] == "MATCHED"
    assert payload_line["effective_resolved_product_code"]["id"] == pc.id

    line.refresh_from_db()
    assert line.amount == Decimal("125.00")
    assert line.source_batch_id == batch.id
    assert line.source_label == "A/F"
    assert line.normalization_status == SPEChargeLineDB.NormalizationStatus.MATCHED
    assert line.resolved_product_code_id == pc.id


def test_a2a_service_scope_schema_support():
    """Verify that 'a2a' service scope is supported in the Pydantic schema."""
    context = SPEShipmentContext(
        origin_country="PG",
        destination_country="AU",
        origin_code="POM",
        destination_code="SYD",
        commodity="GCR",
        total_weight_kg=100,
        pieces=1,
        service_scope="a2a", # This should not raise ValidationError now
    )
    assert context.service_scope == "a2a"

    spe = SpotPricingEnvelope(
        id=str(uuid.uuid4()),
        status=SPEStatus.DRAFT,
        shipment=context,
        charges=[],
        conditions={},
        spot_trigger_reason_code="TEST",
        spot_trigger_reason_text="Test",
        created_by_user_id="1",
        created_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    assert spe.shipment.service_scope == "a2a"
