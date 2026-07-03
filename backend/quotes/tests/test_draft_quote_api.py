import pytest
import uuid
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB, SPESourceBatchDB
from pricing_v4.models import ProductCode
from quotes.contracts.draft_quote_contract import DraftQuoteSchema, DraftQuoteResolveResponseSchema

pytestmark = pytest.mark.django_db

def _mk_user(username: str, role: str):
    return get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass",
        role=role,
    )

def test_draft_quote_comprehensive_read_cases(transactional_db):
    user = _mk_user("test_sales", "sales")
    
    # 1. Create the envelope
    envelope = SpotPricingEnvelopeDB.objects.create(
        status=SpotPricingEnvelopeDB.Status.DRAFT,
        shipment_context_json={
            "origin_code": "SIN",
            "destination_code": "POM",
            "mode": "AIR",
            "pieces": 3,
            "actual_weight_kg": 150.0,
            "chargeable_weight_kg": 200.0,
            "commodity": "GCR",
            "origin_country": "SG",
            "destination_country": "PG",
            "supplier_name": "Qantas Air Cargo"
        },
        shipment_context_hash="mock_hash_value",
        expires_at=timezone.now() + timezone.timedelta(days=7),
        created_by=user
    )

    # 2. Create source batch with analysis summary
    batch = SPESourceBatchDB.objects.create(
        envelope=envelope,
        source_kind=SPESourceBatchDB.SourceKind.AGENT,
        source_type=SPESourceBatchDB.SourceType.PDF,
        label="Test Batch",
        file_name="QAN-QUOTE-9912.pdf",
        analysis_summary_json={
            "extracted_total": 1100.00,
            "warnings": ["Test warning in batch"],
            "unclassified_items": [
                {
                    "id": "unclass-001",
                    "raw_text": "Possible cartage / transfer charge: SGD 120.00",
                    "review_reason": "Unclassified text block"
                }
            ],
            "ignored_items": [
                {
                    "id": "ign-001",
                    "raw_text": "boilerplate disclaimer",
                    "ignored_reason": "Standard boilerplate content ignored"
                }
            ]
        }
    )

    # 3. Create matching product codes
    pc_freight = ProductCode.objects.create(
        id=2001,
        code="AF-FREIGHT",
        description="Air Freight",
        domain=ProductCode.DOMAIN_IMPORT,
        category=ProductCode.CATEGORY_FREIGHT,
        is_gst_applicable=False,
        gl_revenue_code="4000",
        gl_cost_code="5000",
        default_unit=ProductCode.UNIT_KG
    )

    # Clean mapped freight line
    line_freight = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="AF-FREIGHT",
        description="Air Freight weight charge",
        amount=900.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.PER_KG,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        resolved_product_code=pc_freight,
        source_label="Air Freight SIN-POM @ USD 4.50/kg",
        source_excerpt="Air Freight rate to POM is USD 4.50 per kg",
        rate=4.50,
        min_charge=150.00,
        entered_at=timezone.now(),
        source_reference="QAN-QUOTE-9912.pdf"
    )

    # Low-confidence/ambiguous charge line that requires review
    line_fuel = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="FUEL_SUR",
        description="Fuel Surcharge",
        amount=200.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.PER_KG,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        normalization_status=SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        source_label="FSC USD 1.00/kg",
        source_excerpt="FSC rate: USD 1.00 per kg",
        rate=1.00,
        entered_at=timezone.now(),
        source_reference="QAN-QUOTE-9912.pdf"
    )

    # Excluded/ignored charge line
    line_ignored = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="OTHER_TAX",
        description="Tax line excluded",
        amount=50.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.FLAT,
        bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        exclude_from_totals=True,
        entered_at=timezone.now(),
        source_reference="QAN-QUOTE-9912.pdf"
    )

    # Mixed currency charge line
    line_mixed_curr = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="ORIGIN_HAND",
        description="Origin handling in SGD",
        amount=100.00,
        currency="SGD",
        unit=SPEChargeLineDB.Unit.FLAT,
        bucket=SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        entered_at=timezone.now(),
        source_reference="QAN-QUOTE-9912.pdf"
    )

    client = APIClient()
    
    # Check 1. Unauthenticated client returns 401
    url = f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/"
    response_unauth = client.get(url)
    assert response_unauth.status_code == 401

    # Authenticate user
    client.force_authenticate(user=user)
    response = client.get(url)

    # Check 2. Endpoint returns 200 and validates against DraftQuoteSchema
    assert response.status_code == 200
    data = response.data
    schema = DraftQuoteSchema(**data)
    
    # Check 3. contract_version is as expected
    assert schema.contract_version == "1.0.0"

    # Check 4. Multiple charge lines are mapped correctly (we created 4 charge lines)
    assert len(schema.suggested_charges) == 4
    
    # Check 5. Ambiguous/Missing ProductCode maps to needs_review status
    fuel_charge = next(c for c in schema.suggested_charges if c.id == str(line_fuel.id))
    assert fuel_charge.status == "needs_review"
    assert fuel_charge.product_code_conflict is True
    
    # Check 6. Exclude_from_totals charge maps to ignored status
    ignored_charge = next(c for c in schema.suggested_charges if c.id == str(line_ignored.id))
    assert ignored_charge.status == "ignored"
    assert ignored_charge.include_in_totals is False

    # Check 7. Mixed currency charge generates correct warning and totals status
    assert schema.totals_validation.currency_consistent is False
    assert any("Mixed currency" in w for w in schema.warnings)

    # Check 8. Non-existent envelope returns 404
    url_404 = f"/api/v3/spot/envelopes/{uuid.uuid4()}/draft-quote/"
    response_404 = client.get(url_404)
    assert response_404.status_code == 404

    # Check 9. User without access gets 404 (existing SPOT IDOR behavior)
    other_user = _mk_user("other_sales", "sales")
    client_other = APIClient()
    client_other.force_authenticate(user=other_user)
    response_other = client_other.get(url)
    assert response_other.status_code == 404


def test_draft_quote_resolve_endpoint(transactional_db):
    user = _mk_user("test_sales_resolve", "sales")
    envelope = SpotPricingEnvelopeDB.objects.create(
        status=SpotPricingEnvelopeDB.Status.DRAFT,
        shipment_context_json={},
        shipment_context_hash="mock_hash_value",
        expires_at=timezone.now() + timezone.timedelta(days=7),
        created_by=user
    )

    client = APIClient()
    url = f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/resolve/"

    # 1. Auth required
    res_unauth = client.post(url, {}, format="json")
    assert res_unauth.status_code == 401

    client.force_authenticate(user=user)

    # 2. Invalid payload (missing idempotency_key) returns 400
    res_bad = client.post(url, {"decisions": []}, format="json")
    assert res_bad.status_code == 400
    assert any("idempotency_key" in str(detail) for detail in res_bad.data["details"])

    # 3. Invalid idempotency UUID returns 400
    res_bad_uuid = client.post(url, {
        "idempotency_key": "not-a-uuid",
        "decisions": []
    }, format="json")
    assert res_bad_uuid.status_code == 400

    # 4. Valid resolve payload returns 200 and persists decision
    valid_payload = {
        "idempotency_key": "8e9b2520-22c5-4309-88cc-51e6b3648612",
        "decisions": [
            {
                "decision_id": "dec-001",
                "type": "accept_suggestion",
                "target_id": "chg-001",
                "details": {},
                "audit_metadata": {
                    "user_id": 999,  # Client-side user ID to verify server ignores it
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            }
        ]
    }
    res_valid = client.post(url, valid_payload, format="json")
    assert res_valid.status_code == 200
    
    resp_schema = DraftQuoteResolveResponseSchema(**res_valid.data)
    assert resp_schema.status == "accepted"
    assert str(resp_schema.idempotency_key) == "8e9b2520-22c5-4309-88cc-51e6b3648612"
    assert str(resp_schema.envelope_id) == str(envelope.id)
    assert len(resp_schema.applied_decisions) == 1
    assert resp_schema.applied_decisions[0].decision_id == "dec-001"

    # Verify decision is persisted in DB
    from quotes.spot_models import DraftQuoteDecisionDB
    db_record = DraftQuoteDecisionDB.objects.get(envelope=envelope, decision_id="dec-001")
    assert db_record.decision_type == "accept_suggestion"
    assert db_record.target_id == "chg-001"
    assert db_record.server_user == user  # Verify backend derived user
    assert db_record.client_audit_metadata_json["user_id"] == 999  # Verify original telemetry stored

    # Verify idempotency: resubmitting exact same request returns same response
    res_retry = client.post(url, valid_payload, format="json")
    assert res_retry.status_code == 200
    resp_retry_schema = DraftQuoteResolveResponseSchema(**res_retry.data)
    assert resp_retry_schema.status == "accepted"
    assert "Idempotent resolution" in resp_retry_schema.message

    # Ensure no duplicate records created in DB
    assert DraftQuoteDecisionDB.objects.filter(envelope=envelope).count() == 1

    # 5. Non-existent envelope returns 404
    url_404 = f"/api/v3/spot/envelopes/{uuid.uuid4()}/draft-quote/resolve/"
    res_404 = client.post(url_404, valid_payload, format="json")
    assert res_404.status_code == 404

    # 6. User without access returns 404
    other_user = _mk_user("other_sales_resolve", "sales")
    client_other = APIClient()
    client_other.force_authenticate(user=other_user)
    res_other = client_other.post(url, valid_payload, format="json")
    assert res_other.status_code == 404

    # 7. Verify no side-effects (no charge lines mutated, no catalog changes)
    assert SPEChargeLineDB.objects.filter(envelope=envelope).count() == 0
    assert ProductCode.objects.filter(code="AF-FUEL").count() == 0


