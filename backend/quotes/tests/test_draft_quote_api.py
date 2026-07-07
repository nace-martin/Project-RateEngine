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
    
    # Create a batch
    batch = SPESourceBatchDB.objects.create(
        envelope=envelope,
        source_kind=SPESourceBatchDB.SourceKind.AGENT,
        source_type=SPESourceBatchDB.SourceType.PDF,
        label="Resolve Batch",
        file_name="resolve_test.pdf"
    )

    # Create real charge lines (with valid auto UUIDs)
    line_suggested = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="AF-FREIGHT",
        description="Suggested Freight Surcharge",
        amount=500.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.PER_KG,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        entered_at=timezone.now(),
        source_reference="resolve_test.pdf"
    )

    line_ignore = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="OTHER_TAX",
        description="Ignore tax line",
        amount=50.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.FLAT,
        bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        exclude_from_totals=False,
        entered_at=timezone.now(),
        source_reference="resolve_test.pdf"
    )

    line_edit = SPEChargeLineDB.objects.create(
        envelope=envelope,
        source_batch=batch,
        code="AF-FUEL",
        description="Fuel Surcharge to edit",
        amount=200.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.PER_KG,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        normalization_status=SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        entered_at=timezone.now(),
        source_reference="resolve_test.pdf"
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

    # 4. Valid resolve payload (low-risk and unimplemented ones)
    valid_payload = {
        "idempotency_key": "8e9b2520-22c5-4309-88cc-51e6b3648612",
        "decisions": [
            {
                "decision_id": "dec-001",
                "type": "accept_suggestion",
                "target_id": str(line_suggested.id),
                "details": {},
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            },
            {
                "decision_id": "dec-002",
                "type": "ignore",
                "target_id": str(line_ignore.id),
                "details": {"reason": "Non-commercial line item"},
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            },
            {
                "decision_id": "dec-003",
                "type": "edit_charge",
                "target_id": str(line_edit.id),
                "details": {
                    "original_values": {"amount": 200.00, "currency": "USD"},
                    "updated_values": {"amount": 250.00, "currency": "USD"}
                },
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            }
        ]
    }
    res_valid = client.post(url, valid_payload, format="json")
    assert res_valid.status_code == 200
    
    resp_schema = DraftQuoteResolveResponseSchema(**res_valid.data)
    assert resp_schema.status == "accepted"  # All decisions stored successfully
    assert str(resp_schema.idempotency_key) == "8e9b2520-22c5-4309-88cc-51e6b3648612"
    assert str(resp_schema.envelope_id) == str(envelope.id)
    
    # Check decision results
    applied_map = {d.decision_id: d for d in resp_schema.applied_decisions}
    assert applied_map["dec-001"].status == "applied"
    assert applied_map["dec-002"].status == "applied"
    assert applied_map["dec-003"].status == "applied"

    # Verify decision is persisted in DB with correct status
    from quotes.spot_models import DraftQuoteDecisionDB
    db_record_1 = DraftQuoteDecisionDB.objects.get(envelope=envelope, decision_id="dec-001")
    assert db_record_1.decision_type == "accept_suggestion"
    assert db_record_1.server_user == user
    assert db_record_1.status == "accepted"

    db_record_2 = DraftQuoteDecisionDB.objects.get(envelope=envelope, decision_id="dec-002")
    assert db_record_2.decision_type == "ignore"
    assert db_record_2.status == "accepted"

    db_record_3 = DraftQuoteDecisionDB.objects.get(envelope=envelope, decision_id="dec-003")
    assert db_record_3.decision_type == "edit_charge"
    assert db_record_3.status == "accepted"

    # Verify charge lines were actually updated for low-risk decisions
    line_suggested.refresh_from_db()
    assert line_suggested.manual_resolution_status == SPEChargeLineDB.ManualResolutionStatus.RESOLVED
    assert line_suggested.manual_resolution_by == user

    line_ignore.refresh_from_db()
    assert line_ignore.exclude_from_totals is True

    # Verify charge line for edit_charge was safely mutated.
    line_edit.refresh_from_db()
    assert float(line_edit.amount) == 250.00

    # Verify idempotency retry doesn't re-apply, duplicate records, or overwrite metadata
    original_at = line_suggested.manual_resolution_at
    original_user = line_suggested.manual_resolution_by

    res_retry = client.post(url, valid_payload, format="json")
    assert res_retry.status_code == 200
    resp_retry_schema = DraftQuoteResolveResponseSchema(**res_retry.data)
    assert resp_retry_schema.status == "accepted"
    assert "Idempotent resolution" in resp_retry_schema.message
    assert DraftQuoteDecisionDB.objects.filter(envelope=envelope).count() == 3

    # Assert applied status remains applied on retry
    retry_applied_map = {d.decision_id: d for d in resp_retry_schema.applied_decisions}
    assert retry_applied_map["dec-003"].status == "applied"

    # Assert charge line metadata remains untouched
    line_suggested.refresh_from_db()
    assert line_suggested.manual_resolution_at == original_at
    assert line_suggested.manual_resolution_by == original_user

    # Test that a new idempotency key with same target/type creates a new DraftQuoteDecisionDB record but does not overwrite metadata
    payload_new_key = {
        "idempotency_key": "9f9b2520-22c5-4309-88cc-51e6b3648613",
        "decisions": [
            {
                "decision_id": "dec-005",
                "type": "accept_suggestion",
                "target_id": str(line_suggested.id),
                "details": {},
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            }
        ]
    }
    res_new_key = client.post(url, payload_new_key, format="json")
    assert res_new_key.status_code == 200
    # Confirms it created a new DraftQuoteDecisionDB record (now 4 total for envelope)
    assert DraftQuoteDecisionDB.objects.filter(envelope=envelope).count() == 4
    # Confirms it did not overwrite resolution timestamp/operator
    line_suggested.refresh_from_db()
    assert line_suggested.manual_resolution_at == original_at
    assert line_suggested.manual_resolution_by == original_user



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

    # 7. Unknown target_id returns rejected/skipped status
    payload_bad_target = {
        "idempotency_key": "c33f27f0-0fa4-46b5-88f5-9610f607ad77",
        "decisions": [
            {
                "decision_id": "dec-004",
                "type": "accept_suggestion",
                "target_id": str(uuid.uuid4()),
                "details": {},
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            }
        ]
    }
    res_bad_target = client.post(url, payload_bad_target, format="json")
    assert res_bad_target.status_code == 200  # Stored successfully as rejected
    resp_bad_target_schema = DraftQuoteResolveResponseSchema(**res_bad_target.data)
    assert resp_bad_target_schema.status == "rejected"
    assert len(resp_bad_target_schema.rejected_decisions) == 1
    assert resp_bad_target_schema.rejected_decisions[0].error_code == "TARGET_NOT_FOUND"

    # 8. Verify read API reflects ignored line and resolved line correctly
    url_read = f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/"
    res_read = client.get(url_read)
    assert res_read.status_code == 200
    read_schema = DraftQuoteSchema(**res_read.data)
    
    freight_charge = next(c for c in read_schema.suggested_charges if c.id == str(line_suggested.id))
    assert freight_charge.status == "accepted_by_user"

    ignored_charge = next(c for c in read_schema.suggested_charges if c.id == str(line_ignore.id))
    assert ignored_charge.status == "ignored"

    # Test ProductCodeRequest creation (Phase 8D.12A)
    payload_pc_req = {
        "idempotency_key": "4c9b2520-22c5-4309-88cc-51e6b3648614",
        "decisions": [
            {
                "decision_id": "dec-006",
                "type": "request_product_code",
                "target_id": str(line_edit.id),
                "details": {
                    "proposed_code": "AF-FUEL-NEW",
                    "description": "Fuel Surcharge - special import surcharge",
                    "category": "airfreight",
                    "domain": "IMPORT",
                    "reason": "New airline carrier fee added for fuel"
                },
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            }
        ]
    }
    res_pc = client.post(url, payload_pc_req, format="json")
    assert res_pc.status_code == 200
    resp_pc = DraftQuoteResolveResponseSchema(**res_pc.data)
    assert resp_pc.status == "accepted"
    # Result must be skipped
    assert resp_pc.applied_decisions[0].status == "skipped"
    assert "pending admin review" in resp_pc.applied_decisions[0].message
    
    # Assert that one ProductCodeCreationRequest is created with PENDING status
    from pricing_v4.models import ProductCodeCreationRequest
    req_objs = ProductCodeCreationRequest.objects.filter(source_envelope=envelope)
    assert req_objs.count() == 1
    req_obj = req_objs.first()
    assert req_obj.suggested_name == "AF-FUEL-NEW"
    assert req_obj.status == ProductCodeCreationRequest.STATUS_PENDING
    assert req_obj.source_charge_line == line_edit
    assert req_obj.created_by == user

    # Assert that retry with same idempotency_key does not create a duplicate ProductCodeCreationRequest
    res_retry_pc = client.post(url, payload_pc_req, format="json")
    assert res_retry_pc.status_code == 200
    assert ProductCodeCreationRequest.objects.filter(source_envelope=envelope).count() == 1

    # Assert that high-risk skipped decisions remain skipped on retry
    resp_retry_pc = DraftQuoteResolveResponseSchema(**res_retry_pc.data)
    assert resp_retry_pc.applied_decisions[0].status == "skipped"

    # Assert that Read API reflects the pending state correctly
    res_read_pending = client.get(f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/")
    assert res_read_pending.status_code == 200
    read_data = DraftQuoteSchema(**res_read_pending.data)
    edit_charge = next(c for c in read_data.suggested_charges if c.id == str(line_edit.id))
    assert edit_charge.correction_actions == ["PENDING_ADMIN_REVIEW"]
    assert any("Pending ProductCode Creation Request" in w for w in edit_charge.warnings)

    # Set request to APPROVED and verify it surfaces correctly (Phase 8D.12B)
    from pricing_v4.models import ProductCode
    pc_approved = ProductCode.objects.create(
        id=9999,
        code="AF-APPROVED-NEW",
        description="Approved Surcharge",
        domain=ProductCode.DOMAIN_IMPORT,
        category=ProductCode.CATEGORY_SURCHARGE,
        is_gst_applicable=False,
        gl_revenue_code="4000",
        gl_cost_code="5000",
        default_unit=ProductCode.UNIT_SHIPMENT
    )
    req_obj.status = ProductCodeCreationRequest.STATUS_APPROVED
    req_obj.approved_product_code = pc_approved
    req_obj.save()

    res_read_approved = client.get(f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/")
    assert res_read_approved.status_code == 200
    read_data_approved = DraftQuoteSchema(**res_read_approved.data)
    approved_charge = next(c for c in read_data_approved.suggested_charges if c.id == str(line_edit.id))
    assert approved_charge.correction_actions == ["APPROVED_PRODUCTCODE_AVAILABLE"]
    assert any("ProductCode Creation Request Approved" in w for w in approved_charge.warnings)

    # Set request to REJECTED and verify it surfaces correctly (Phase 8D.12B)
    req_obj.status = ProductCodeCreationRequest.STATUS_REJECTED
    req_obj.rejection_reason = "Duplicate of existing code AF-FUEL."
    req_obj.save()

    res_read_rejected = client.get(f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/")
    assert res_read_rejected.status_code == 200
    read_data_rejected = DraftQuoteSchema(**res_read_rejected.data)
    rejected_charge = next(c for c in read_data_rejected.suggested_charges if c.id == str(line_edit.id))
    assert rejected_charge.correction_actions == ["PRODUCTCODE_REJECTED"]
    assert any("ProductCode Creation Request Rejected" in w for w in rejected_charge.warnings)
    assert "Duplicate of existing code AF-FUEL." in rejected_charge.review_reason


    # 9. Same idempotency_key on a different envelope must not return decisions from another envelope (isolated namespaces)
    envelope_2 = SpotPricingEnvelopeDB.objects.create(
        status=SpotPricingEnvelopeDB.Status.DRAFT,
        shipment_context_json={},
        shipment_context_hash="mock_hash_value_2",
        expires_at=timezone.now() + timezone.timedelta(days=7),
        created_by=user
    )
    batch_2 = SPESourceBatchDB.objects.create(
        envelope=envelope_2,
        source_kind=SPESourceBatchDB.SourceKind.AGENT,
        source_type=SPESourceBatchDB.SourceType.PDF,
        label="Resolve Batch 2",
        file_name="resolve_test_2.pdf"
    )
    line_suggested_2 = SPEChargeLineDB.objects.create(
        envelope=envelope_2,
        source_batch=batch_2,
        code="AF-FREIGHT",
        description="Suggested Freight Surcharge",
        amount=500.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.PER_KG,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        entered_at=timezone.now(),
        source_reference="resolve_test_2.pdf"
    )
    line_ignore_2 = SPEChargeLineDB.objects.create(
        envelope=envelope_2,
        source_batch=batch_2,
        code="OTHER_TAX",
        description="Ignore tax line",
        amount=50.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.FLAT,
        bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
        normalization_status=SPEChargeLineDB.NormalizationStatus.MATCHED,
        exclude_from_totals=False,
        entered_at=timezone.now(),
        source_reference="resolve_test_2.pdf"
    )
    line_edit_2 = SPEChargeLineDB.objects.create(
        envelope=envelope_2,
        source_batch=batch_2,
        code="AF-FUEL",
        description="Fuel Surcharge to edit",
        amount=200.00,
        currency="USD",
        unit=SPEChargeLineDB.Unit.PER_KG,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        normalization_status=SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        entered_at=timezone.now(),
        source_reference="resolve_test_2.pdf"
    )

    payload_env_2 = {
        "idempotency_key": "8e9b2520-22c5-4309-88cc-51e6b3648612",  # Same idempotency key!
        "decisions": [
            {
                "decision_id": "dec-001",
                "type": "accept_suggestion",
                "target_id": str(line_suggested_2.id),
                "details": {},
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            },
            {
                "decision_id": "dec-002",
                "type": "ignore",
                "target_id": str(line_ignore_2.id),
                "details": {"reason": "Non-commercial line item"},
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            },
            {
                "decision_id": "dec-003",
                "type": "edit_charge",
                "target_id": str(line_edit_2.id),
                "details": {
                    "original_values": {"amount": 200.00, "currency": "USD"},
                    "updated_values": {"amount": 250.00, "currency": "USD"}
                },
                "audit_metadata": {
                    "user_id": 999,
                    "timestamp": "2026-07-03T00:00:00Z"
                }
            }
        ]
    }

    url_2 = f"/api/v3/spot/envelopes/{envelope_2.id}/draft-quote/resolve/"
    res_diff_env = client.post(url_2, payload_env_2, format="json")
    assert res_diff_env.status_code == 200
    resp_diff_schema = DraftQuoteResolveResponseSchema(**res_diff_env.data)
    assert resp_diff_schema.status == "accepted"
    assert "Operator decisions" in resp_diff_schema.message
    assert str(resp_diff_schema.envelope_id) == str(envelope_2.id)
    assert DraftQuoteDecisionDB.objects.filter(envelope=envelope_2).count() == 3
    assert DraftQuoteDecisionDB.objects.filter(idempotency_key="8e9b2520-22c5-4309-88cc-51e6b3648612").count() == 6


@pytest.mark.django_db
def test_resolve_use_approved_product_code():
    from pricing_v4.models import ProductCodeCreationRequest, ProductCode
    from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB, DraftQuoteDecisionDB
    from quotes.contracts.draft_quote_contract import DraftQuoteResolveResponseSchema
    from rest_framework.test import APIClient
    from django.contrib.auth import get_user_model
    import uuid

    User = get_user_model()
    user = User.objects.create_user(username="test_operator", password="password")
    
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
        shipment_context_hash="mock_hash_value_approved",
        expires_at=timezone.now() + timezone.timedelta(days=7),
        created_by=user
    )
    
    charge_line = SPEChargeLineDB.objects.create(
        envelope=envelope,
        code="TEST-CHARGE",
        description="Test Charge Line",
        amount=100.00,
        currency="USD",
        unit="flat",
        bucket="origin_charges",
        entered_at=timezone.now()
    )

    product_code = ProductCode.objects.create(
        id=9999,
        code="APPROVED-PC-9999",
        description="Approved Product Code",
        domain=ProductCode.DOMAIN_IMPORT,
        category=ProductCode.CATEGORY_SURCHARGE,
        is_gst_applicable=False,
        gl_revenue_code="4000",
        gl_cost_code="5000",
        default_unit=ProductCode.UNIT_SHIPMENT
    )

    # 1. Approved request setup
    req_approved = ProductCodeCreationRequest.objects.create(
        source_label="Test Charge Line",
        suggested_name="TEST-CHARGE",
        suggested_bucket="origin_charges",
        suggested_basis="FLAT",
        source_envelope=envelope,
        source_charge_line=charge_line,
        status=ProductCodeCreationRequest.STATUS_APPROVED,
        approved_product_code=product_code,
        created_by=user
    )

    # 2. Pending request setup
    req_pending = ProductCodeCreationRequest.objects.create(
        source_label="Test Charge Line 2",
        suggested_name="TEST-CHARGE-2",
        suggested_bucket="origin_charges",
        suggested_basis="FLAT",
        source_envelope=envelope,
        source_charge_line=charge_line,
        status=ProductCodeCreationRequest.STATUS_PENDING,
        created_by=user
    )

    # 3. Rejected request setup
    req_rejected = ProductCodeCreationRequest.objects.create(
        source_label="Test Charge Line 3",
        suggested_name="TEST-CHARGE-3",
        suggested_bucket="origin_charges",
        suggested_basis="FLAT",
        source_envelope=envelope,
        source_charge_line=charge_line,
        status=ProductCodeCreationRequest.STATUS_REJECTED,
        created_by=user
    )

    client = APIClient()
    client.force_authenticate(user=user)
    url = f"/api/v3/spot/envelopes/{envelope.id}/draft-quote/resolve/"

    # Test pending request cannot be consumed
    payload_pending = {
        "idempotency_key": str(uuid.uuid4()),
        "decisions": [{
            "decision_id": "dec-pending",
            "type": "use_approved_product_code",
            "target_id": str(charge_line.id),
            "details": {
                "product_code_request_id": str(req_pending.id),
                "product_code_id": product_code.id
            },
            "audit_metadata": {"user_id": user.id, "timestamp": "2026-07-03T00:00:00Z"}
        }]
    }
    res = client.post(url, payload_pending, format="json")
    assert res.status_code == 200
    assert res.data["rejected_decisions"][0]["error_code"] == "REQUEST_NOT_APPROVED"

    # Test rejected request cannot be consumed
    payload_rejected = {
        "idempotency_key": str(uuid.uuid4()),
        "decisions": [{
            "decision_id": "dec-rejected",
            "type": "use_approved_product_code",
            "target_id": str(charge_line.id),
            "details": {
                "product_code_request_id": str(req_rejected.id),
                "product_code_id": product_code.id
            },
            "audit_metadata": {"user_id": user.id, "timestamp": "2026-07-03T00:00:00Z"}
        }]
    }
    res = client.post(url, payload_rejected, format="json")
    assert res.status_code == 200
    assert res.data["rejected_decisions"][0]["error_code"] == "REQUEST_NOT_APPROVED"

    # Test approved request can be consumed
    ik = str(uuid.uuid4())
    payload_approved = {
        "idempotency_key": ik,
        "decisions": [{
            "decision_id": "dec-approved",
            "type": "use_approved_product_code",
            "target_id": str(charge_line.id),
            "details": {
                "product_code_request_id": str(req_approved.id),
                "product_code_id": product_code.id
            },
            "audit_metadata": {"user_id": user.id, "timestamp": "2026-07-03T00:00:00Z"}
        }]
    }
    res = client.post(url, payload_approved, format="json")
    assert res.status_code == 200
    assert len(res.data["applied_decisions"]) == 1
    assert res.data["applied_decisions"][0]["status"] == "applied"

    # Verify database updates
    charge_line.refresh_from_db()
    assert charge_line.manual_resolved_product_code == product_code
    assert charge_line.manual_resolution_status == SPEChargeLineDB.ManualResolutionStatus.RESOLVED

    # Test idempotent replay returns cached decision and does not mutate twice
    res_replay = client.post(url, payload_approved, format="json")
    assert res_replay.status_code == 200
    assert "retrieved from database history" in res_replay.data["message"]






