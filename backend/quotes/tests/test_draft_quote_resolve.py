import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Role, UserMembership
from parties.models import Branch, Department, Organization
from pricing_v4.models import ProductCode, ProductCodeCreationRequest
from quotes.spot_models import DraftQuoteDecisionDB, SPEChargeLineDB, SPESourceBatchDB, SpotPricingEnvelopeDB


class DraftQuoteResolveHighValueTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Test Org", slug="test-org")
        self.other_org = Organization.objects.create(name="Other Org", slug="other-org")
        self.branch = Branch.objects.create(organization=self.org, code="POM", name="Port Moresby")
        self.other_branch = Branch.objects.create(organization=self.other_org, code="BNE", name="Brisbane")
        self.department = Department.objects.create(organization=self.org, branch=self.branch, code="AIR", name="Air Freight")
        self.other_department = Department.objects.create(organization=self.other_org, branch=self.other_branch, code="SEA", name="Sea Freight")
        User = get_user_model()
        self.sales = User.objects.create_user(username="sales_resolve", password="x", role=User.ROLE_SALES)
        self.manager = User.objects.create_user(username="manager_resolve", password="x", role=User.ROLE_MANAGER)
        self.finance = User.objects.create_user(username="finance_resolve", password="x", role=User.ROLE_FINANCE)
        self.other_sales = User.objects.create_user(username="other_sales_resolve", password="x", role=User.ROLE_SALES)
        self._membership(self.sales, self.org, self.branch, self.department, "sales")
        self._membership(self.manager, self.org, self.branch, self.department, "manager")
        self._membership(self.finance, self.org, self.branch, self.department, "finance")
        self._membership(self.other_sales, self.other_org, self.other_branch, self.other_department, "sales")
        self.envelope = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={"origin_country": "SG", "destination_country": "PG", "mode": "AIR"},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test",
            expires_at=timezone.now() + timezone.timedelta(days=7),
            organization=self.org,
            branch=self.branch,
            department=self.department,
            owner=self.sales,
            created_by=self.sales,
        )
        self.batch = SPESourceBatchDB.objects.create(
            envelope=self.envelope,
            source_kind=SPESourceBatchDB.SourceKind.AGENT,
            source_type=SPESourceBatchDB.SourceType.TEXT,
            label="Agent reply",
            file_name="agent.txt",
            analysis_summary_json={
                "unclassified_items": [
                    {"id": "unclass-1", "raw_text": "Documentation fee USD 25", "evidence": {"source_text": "Documentation fee USD 25"}},
                    {"id": "unclass-2", "raw_text": "Have a nice day"},
                ]
            },
        )
        self.product_code = ProductCode.objects.create(
            id=2001,
            code="IMP-DOC-FEE",
            description="Import documentation fee",
            domain=ProductCode.DOMAIN_IMPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=False,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        self.charge = SPEChargeLineDB.objects.create(
            envelope=self.envelope,
            source_batch=self.batch,
            code="RAW-DOC",
            description="Raw documentation fee",
            amount=Decimal("10.00"),
            currency="USD",
            unit=SPEChargeLineDB.Unit.FLAT,
            bucket=SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            source_label="DOC FEE",
            source_excerpt="DOC FEE USD 10",
            source_reference="agent.txt",
            entered_by=self.sales,
            entered_at=timezone.now(),
        )

    def _membership(self, user, organization, branch, department, role_code):
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code.title()})
        UserMembership.objects.create(user=user, organization=organization, branch=branch, department=department, role=role, is_active=True, is_primary=True)

    def _post(self, decisions, key=None, user=None):
        self.client.force_authenticate(user=user or self.sales)
        return self.client.post(
            f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/resolve/",
            {"idempotency_key": str(key or uuid.uuid4()), "decisions": decisions},
            format="json",
        )

    def _decision(self, decision_type, target_id=None, details=None, decision_id="dec-1"):
        return {
            "decision_id": decision_id,
            "type": decision_type,
            "target_id": str(target_id or self.charge.id),
            "details": details or {},
            "audit_metadata": {"user_id": self.sales.id, "timestamp": "2026-07-06T00:00:00Z"},
        }

    def _rejected_product_code_request(self):
        return ProductCodeCreationRequest.objects.create(
            source_label="DOC FEE",
            suggested_name="IMP-DOC-NEW",
            suggested_bucket="destination_charges",
            suggested_basis="FLAT",
            suggested_reason="Supplier added documentation fee",
            source_envelope=self.envelope,
            source_charge_line=self.charge,
            status=ProductCodeCreationRequest.STATUS_REJECTED,
            rejected_at=timezone.now(),
            rejection_reason="Duplicate of existing import documentation fee.",
            created_by=self.sales,
        )

    def _persist_request_decision(self, request):
        DraftQuoteDecisionDB.objects.create(
            envelope=self.envelope,
            idempotency_key=uuid.uuid4(),
            decision_id=f"request-{request.id}",
            decision_type="request_product_code",
            target_id=str(self.charge.id),
            details_json={"product_code_request_id": request.id},
            client_audit_metadata_json={"user_id": self.sales.id, "timestamp": "2026-07-06T00:00:00Z"},
            server_user=self.sales,
            status="skipped",
            message="ProductCode request created and pending admin review.",
        )

    def _read_charge(self):
        self.client.force_authenticate(user=self.sales)
        res = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return next(c for c in res.data["suggested_charges"] if c["id"] == str(self.charge.id))

    def _finalize(self, key=None, user=None):
        self.client.force_authenticate(user=user or self.sales)
        return self.client.post(
            f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/finalize/",
            {"idempotency_key": str(key or uuid.uuid4()), "audit_metadata": {"user_id": (user or self.sales).id}},
            format="json",
        )

    def _reopen(self, user=None):
        self.client.force_authenticate(user=user or self.manager)
        return self.client.post(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/reopen/", {}, format="json")

    def _resolve_all_blockers(self):
        res = self._post([
            self._decision("map_to_product_code", details={"product_code": self.product_code.code}, decision_id="map-finalize"),
            self._decision("classify_unclassified", target_id="unclass-1", details={"classification": "ignored", "reason": "Not billable"}, decision_id="ignore-u1"),
            self._decision("classify_unclassified", target_id="unclass-2", details={"classification": "ignored", "reason": "Greeting"}, decision_id="ignore-u2"),
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"], [])

    def test_map_to_product_code_applies_to_charge_line_and_read_queue(self):
        res = self._post([self._decision("map_to_product_code", details={"product_code": self.product_code.code})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.manual_resolved_product_code_id, self.product_code.id)
        self.assertEqual(self.charge.manual_resolution_status, SPEChargeLineDB.ManualResolutionStatus.RESOLVED)
        self.assertEqual(self.charge.source_excerpt, "DOC FEE USD 10")
        self.assertEqual(res.data["unresolved_items_remaining"], 2)

    def test_map_to_product_code_rejects_invalid_product_code(self):
        res = self._post([self._decision("map_to_product_code", details={"product_code": "NOPE"})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_NOT_FOUND")
        self.charge.refresh_from_db()
        self.assertIsNone(self.charge.manual_resolved_product_code_id)

    def test_map_to_product_code_rejects_product_code_from_wrong_domain(self):
        export_product_code = ProductCode.objects.create(
            id=1001,
            code="EXP-DOC-FEE",
            description="Export documentation fee",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=False,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        res = self._post([self._decision("map_to_product_code", details={"product_code": export_product_code.code})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_DOMAIN_MISMATCH")
        self.charge.refresh_from_db()
        self.assertIsNone(self.charge.manual_resolved_product_code_id)

    def test_map_to_product_code_route_countries_override_explicit_json_direction(self):
        self.envelope.shipment_context_json = {"direction": "EXPORT", "origin_country": "SG", "destination_country": "PG", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        export_product_code = ProductCode.objects.create(
            id=1001,
            code="EXP-DOC-FEE",
            description="Export documentation fee",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=False,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        res = self._post([self._decision("map_to_product_code", details={"product_code": export_product_code.code})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_DOMAIN_MISMATCH")
        self.charge.refresh_from_db()
        self.assertIsNone(self.charge.manual_resolved_product_code_id)

    def test_map_to_product_code_rejects_when_direction_unavailable(self):
        self.envelope.shipment_context_json = {"origin_country": "SG", "destination_country": "AU", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        res = self._post([self._decision("map_to_product_code", details={"product_code": self.product_code.code})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_DIRECTION_UNAVAILABLE")
        self.charge.refresh_from_db()
        self.assertIsNone(self.charge.manual_resolved_product_code_id)

    def test_draft_quote_payload_direction_uses_route_countries_over_json_direction(self):
        from quotes.services.draft_quote_adapter import build_draft_quote_payload

        self.envelope.shipment_context_json = {
            "direction": "EXPORT",
            "origin_country": "SG",
            "destination_country": "PG",
            "origin_code": "SIN",
            "destination_code": "POM",
            "mode": "AIR",
        }
        self.envelope.save(update_fields=["shipment_context_json"])
        payload = build_draft_quote_payload(self.envelope)
        self.assertEqual(payload["shipment_context"]["direction"], "IMPORT")
        self.assertEqual(payload["shipment_context"]["origin"], "SIN")
        self.assertEqual(payload["shipment_context"]["destination"], "POM")
        self.assertEqual(payload["shipment_context"]["origin_country"], "SG")
        self.assertEqual(payload["shipment_context"]["destination_country"], "PG")
        self.assertEqual(payload["shipment_context"]["origin_code"], "SIN")
        self.assertEqual(payload["shipment_context"]["destination_code"], "POM")

    def test_draft_quote_payload_derives_export_and_domestic_from_trusted_countries(self):
        from quotes.services.draft_quote_adapter import build_draft_quote_payload

        self.envelope.shipment_context_json = {"origin_country": "PG", "destination_country": "AU", "origin_code": "POM", "destination_code": "BNE", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        export_payload = build_draft_quote_payload(self.envelope)
        self.assertEqual(export_payload["shipment_context"]["direction"], "EXPORT")
        self.assertEqual(export_payload["shipment_context"]["origin_country"], "PG")
        self.assertEqual(export_payload["shipment_context"]["destination_country"], "AU")

        self.envelope.shipment_context_json = {"origin_country": "PG", "destination_country": "PG", "origin_code": "POM", "destination_code": "LAE", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        domestic_payload = build_draft_quote_payload(self.envelope)
        self.assertEqual(domestic_payload["shipment_context"]["direction"], "DOMESTIC")
        self.assertEqual(domestic_payload["shipment_context"]["origin_code"], "POM")
        self.assertEqual(domestic_payload["shipment_context"]["destination_code"], "LAE")

    def test_draft_quote_payload_preserves_stale_origin_destination_compatibility(self):
        from quotes.services.draft_quote_adapter import build_draft_quote_payload

        self.envelope.shipment_context_json = {"origin": "Singapore", "destination": "Port Moresby", "origin_country": "SG", "destination_country": "PG", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        payload = build_draft_quote_payload(self.envelope)
        self.assertEqual(payload["shipment_context"]["origin"], "Singapore")
        self.assertEqual(payload["shipment_context"]["destination"], "Port Moresby")
        self.assertEqual(payload["shipment_context"]["origin_code"], "")
        self.assertEqual(payload["shipment_context"]["destination_code"], "")
        self.assertEqual(payload["shipment_context"]["direction"], "IMPORT")

    def test_draft_quote_payload_omits_direction_when_route_countries_are_unsupported(self):
        from quotes.services.draft_quote_adapter import build_draft_quote_payload

        self.envelope.shipment_context_json = {"direction": "IMPORT", "origin_country": "SG", "destination_country": "AU", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        payload = build_draft_quote_payload(self.envelope)
        self.assertNotIn("direction", payload["shipment_context"])

    def test_draft_quote_payload_omits_raw_json_direction_without_route_countries(self):
        from quotes.services.draft_quote_adapter import build_draft_quote_payload

        self.envelope.shipment_context_json = {"direction": "IMPORT", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        payload = build_draft_quote_payload(self.envelope)
        self.assertNotIn("direction", payload["shipment_context"])

    def test_map_to_product_code_rejects_raw_json_direction_without_route_countries(self):
        self.envelope.shipment_context_json = {"direction": "IMPORT", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        res = self._post([self._decision("map_to_product_code", details={"product_code": self.product_code.code})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_DIRECTION_UNAVAILABLE")
        self.charge.refresh_from_db()
        self.assertIsNone(self.charge.manual_resolved_product_code_id)

    def test_source_finding_appears_blocks_finalize_and_resolves_with_note(self):
        self.batch.analysis_summary_json = {
            **self.batch.analysis_summary_json,
            "ai_used": True,
            "can_proceed": True,
            "imported_charge_count": 1,
            "critic_missed_charges": ["Destination delivery fee"],
        }
        self.batch.save(update_fields=["analysis_summary_json"])

        self.client.force_authenticate(user=self.sales)
        read = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        source_items = [item for item in read.data["review_queue"] if item["type"] == "source_finding"]
        self.assertEqual(len(source_items), 1)
        self.assertIn("Destination delivery fee", source_items[0]["message"])
        self.assertEqual(source_items[0]["available_actions"], ["resolved_in_workspace", "not_commercially_applicable"])
        self.assertEqual(self._finalize().status_code, status.HTTP_400_BAD_REQUEST)

        missing_note = self._post([
            self._decision(
                "resolve_source_finding",
                target_id=source_items[0]["id"],
                details={
                    "source_batch_id": source_items[0]["source_batch_id"],
                    "source_finding_id": source_items[0]["source_finding_id"],
                    "action": "not_commercially_applicable",
                    "review_note": "",
                },
                decision_id="source-missing-note",
            )
        ])
        self.assertEqual(missing_note.status_code, status.HTTP_400_BAD_REQUEST)

        resolved = self._post([
            self._decision(
                "resolve_source_finding",
                target_id=source_items[0]["id"],
                details={
                    "source_batch_id": source_items[0]["source_batch_id"],
                    "source_finding_id": source_items[0]["source_finding_id"],
                    "action": "not_commercially_applicable",
                    "review_note": "Reviewed supplier evidence; destination delivery not applicable to A2A quote.",
                },
                decision_id="source-resolve",
            )
        ])
        self.assertEqual(resolved.status_code, status.HTTP_200_OK)
        self.assertEqual(resolved.data["rejected_decisions"], [])
        self.batch.refresh_from_db()
        findings = self.batch.analysis_summary_json["source_findings"]
        self.assertEqual(findings[0]["status"], "resolved")
        self.assertIn("Destination delivery fee", findings[0]["evidence"]["source_text"])

        reread = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        self.assertFalse([item for item in reread.data["review_queue"] if item["type"] == "source_finding"])

    def test_source_finding_resolution_clears_only_target_finding_and_is_idempotent(self):
        self.batch.analysis_summary_json = {
            **self.batch.analysis_summary_json,
            "ai_used": True,
            "can_proceed": True,
            "imported_charge_count": 1,
            "critic_missed_charges": ["Destination delivery fee", "Terminal handling"],
        }
        self.batch.save(update_fields=["analysis_summary_json"])
        self.client.force_authenticate(user=self.sales)
        read = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        source_items = [item for item in read.data["review_queue"] if item["type"] == "source_finding"]
        self.assertEqual(len(source_items), 2)
        key = uuid.uuid4()
        decision = self._decision(
            "resolve_source_finding",
            target_id=source_items[0]["id"],
            details={
                "source_batch_id": source_items[0]["source_batch_id"],
                "source_finding_id": source_items[0]["source_finding_id"],
                "action": "resolved_in_workspace",
                "review_note": "Addressed against existing destination charge in the workspace.",
                "charge_line_id": str(self.charge.id),
            },
            decision_id="source-one",
        )
        self._post([decision], key=key)
        self._post([decision], key=key)
        reread = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        remaining = [item for item in reread.data["review_queue"] if item["type"] == "source_finding"]
        self.assertEqual(len(remaining), 1)
        self.assertIn("Terminal handling", remaining[0]["message"])

    def test_source_finding_ids_are_content_stable_not_index_based(self):
        self.batch.analysis_summary_json = {
            **self.batch.analysis_summary_json,
            "ai_used": True,
            "can_proceed": True,
            "imported_charge_count": 1,
            "critic_missed_charges": ["Destination delivery fee", "Terminal handling"],
        }
        self.batch.save(update_fields=["analysis_summary_json"])
        self.client.force_authenticate(user=self.sales)
        first = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        first_ids_by_message = {
            item["message"]: item["source_finding_id"]
            for item in first.data["review_queue"]
            if item["type"] == "source_finding"
        }

        self.batch.analysis_summary_json = {
            **self.batch.analysis_summary_json,
            "critic_missed_charges": ["Terminal handling", "Destination delivery fee", "Terminal handling"],
        }
        self.batch.save(update_fields=["analysis_summary_json"])
        second = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        second_ids_by_message = {
            item["message"]: item["source_finding_id"]
            for item in second.data["review_queue"]
            if item["type"] == "source_finding"
        }
        self.assertEqual(first_ids_by_message, second_ids_by_message)
        self.assertNotIn("critic-missed-charges-0", " ".join(second_ids_by_message.values()))
        self.assertEqual(len(second_ids_by_message), 2)

    def test_source_batch_review_rejects_blanket_approval_when_findings_are_open(self):
        self.batch.analysis_summary_json = {
            **self.batch.analysis_summary_json,
            "ai_used": True,
            "can_proceed": True,
            "imported_charge_count": 1,
            "critic_missed_charges": ["Destination delivery fee"],
        }
        self.batch.save(update_fields=["analysis_summary_json"])
        self.client.force_authenticate(user=self.sales)
        response = self.client.post(
            f"/api/v3/spot/envelopes/{self.envelope.id}/sources/{self.batch.id}/review/",
            {"reviewed_safe_to_quote": True, "review_note": "Looks okay."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("blanket source approval", response.data["error"])

    def test_low_confidence_source_finding_does_not_block_finalize(self):
        self.batch.analysis_summary_json = {
            **self.batch.analysis_summary_json,
            "ai_used": True,
            "can_proceed": True,
            "imported_charge_count": 1,
            "low_confidence_line_count": 1,
        }
        self.batch.save(update_fields=["analysis_summary_json"])
        self._resolve_all_blockers()
        self.client.force_authenticate(user=self.sales)
        read = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        self.assertFalse([item for item in read.data["review_queue"] if item["type"] == "source_finding"])
        finalize = self._finalize()
        self.assertEqual(finalize.status_code, status.HTTP_200_OK)

    def test_map_to_product_code_replay_is_idempotent(self):
        key = uuid.uuid4()
        decision = self._decision("map_to_product_code", details={"product_code": self.product_code.code})
        self._post([decision], key=key)
        self._post([decision], key=key)
        self.assertEqual(DraftQuoteDecisionDB.objects.filter(idempotency_key=key).count(), 1)

    def test_classify_unclassified_charge_persists_line_and_preserves_evidence(self):
        res = self._post([
            self._decision(
                "classify_unclassified",
                target_id="unclass-1",
                details={
                    "classification": "charge",
                    "display_label": "Documentation fee",
                    "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
                    "currency": "USD",
                    "amount": "25.00",
                    "unit": SPEChargeLineDB.Unit.FLAT,
                    "product_code": self.product_code.code,
                },
                decision_id="classify-charge",
            )
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"], [])
        created = SPEChargeLineDB.objects.get(description="Documentation fee")
        self.assertEqual(created.manual_resolved_product_code_id, self.product_code.id)
        self.assertEqual(created.source_excerpt, "Documentation fee USD 25")
        self.assertEqual(created.rule_meta["unclassified_item_evidence"]["source_text"], "Documentation fee USD 25")
        self.batch.refresh_from_db()
        summary = self.batch.analysis_summary_json
        self.assertFalse(any(item.get("id") == "unclass-1" for item in summary["unclassified_items"]))
        self.assertFalse(any(item.get("id") == "unclass-1" for item in summary.get("ignored_items", [])))

    def test_classify_unclassified_charge_rejects_wrong_domain_and_invalid_fields(self):
        export_product_code = ProductCode.objects.create(
            id=1001,
            code="EXP-DOC-FEE",
            description="Export documentation fee",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_DOCUMENTATION,
            is_gst_applicable=False,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        base_details = {
            "classification": "charge",
            "display_label": "Documentation fee",
            "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            "currency": "USD",
            "amount": "25.00",
            "unit": SPEChargeLineDB.Unit.FLAT,
            "product_code": export_product_code.code,
        }
        res = self._post([self._decision("classify_unclassified", target_id="unclass-1", details=base_details, decision_id="wrong-domain")])
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_DOMAIN_MISMATCH")
        self.assertFalse(SPEChargeLineDB.objects.filter(description="Documentation fee").exists())

        invalid_cases = [
            ({"bucket": "bad"}, "INVALID_BUCKET"),
            ({"currency": "USDX"}, "INVALID_CURRENCY"),
            ({"amount": "-1"}, "NEGATIVE_NUMERIC_VALUE"),
            ({"unit": "bad"}, "INVALID_UNIT"),
        ]
        for idx, (override, error_code) in enumerate(invalid_cases):
            details = {**base_details, "product_code": self.product_code.code, **override}
            res = self._post([self._decision("classify_unclassified", target_id="unclass-1", details=details, decision_id=f"invalid-{idx}")])
            self.assertEqual(res.data["rejected_decisions"][0]["error_code"], error_code)

    def test_classify_unclassified_rejects_missing_direction(self):
        self.envelope.shipment_context_json = {"origin_country": "SG", "destination_country": "AU", "mode": "AIR"}
        self.envelope.save(update_fields=["shipment_context_json"])
        res = self._post([
            self._decision(
                "classify_unclassified",
                target_id="unclass-1",
                details={"classification": "charge", "display_label": "Doc", "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES, "currency": "USD", "amount": "25", "unit": SPEChargeLineDB.Unit.FLAT, "product_code": self.product_code.code},
                decision_id="missing-direction",
            )
        ])
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_DIRECTION_UNAVAILABLE")

    def test_classify_unclassified_ignored_and_note_persist_after_reload(self):
        res = self._post([
            self._decision("classify_unclassified", target_id="unclass-1", details={"classification": "ignored", "reason": "Not billable"}, decision_id="ignore-unknown"),
            self._decision("classify_unclassified", target_id="unclass-2", details={"classification": "note", "reason": "Commercial note"}, decision_id="note-unknown"),
        ])
        self.assertEqual(res.data["rejected_decisions"], [])
        payload = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/").data
        self.assertFalse(any(item["id"] in {"unclass-1", "unclass-2"} for item in payload["unclassified_items"]))
        self.assertTrue(any(item["id"] == "unclass-1" for item in payload["ignored_items"]))
        self.assertTrue(any(term["type"] == "note" and "Have a nice day" in term["text"] for term in payload["commercial_terms"]))

    def test_unknown_product_code_request_creates_provisional_charge_and_can_apply_approved_code(self):
        res = self._post([
            self._decision(
                "request_product_code",
                target_id="unclass-1",
                details={"proposed_code": "IMP-DOC-NEW", "description": "Documentation fee", "display_label": "Documentation fee", "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES, "currency": "USD", "amount": "25", "unit": SPEChargeLineDB.Unit.FLAT, "reason": "Missing code"},
                decision_id="request-unknown",
            )
        ])
        self.assertEqual(res.data["rejected_decisions"], [])
        request = ProductCodeCreationRequest.objects.get(suggested_name="IMP-DOC-NEW")
        self.assertIsNotNone(request.source_charge_line_id)
        charge = request.source_charge_line
        self.assertEqual(charge.source_excerpt, "Documentation fee USD 25")
        self.assertEqual(charge.normalization_status, SPEChargeLineDB.NormalizationStatus.UNMAPPED)
        request.status = ProductCodeCreationRequest.STATUS_APPROVED
        request.approved_product_code = self.product_code
        request.approved_at = timezone.now()
        request.approved_by = self.manager
        request.save(update_fields=["status", "approved_product_code", "approved_at", "approved_by"])
        res = self._post([
            self._decision("use_approved_product_code", target_id=str(charge.id), details={"product_code_request_id": request.id, "product_code_id": self.product_code.id}, decision_id="use-approved-unknown")
        ])
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        charge.refresh_from_db()
        self.assertEqual(charge.manual_resolved_product_code_id, self.product_code.id)

    def test_unknown_charge_creation_replay_creates_one_charge(self):
        key = uuid.uuid4()
        decision = self._decision(
            "classify_unclassified",
            target_id="unclass-1",
            details={
                "classification": "charge",
                "display_label": "Documentation fee",
                "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
                "currency": "USD",
                "amount": "25.00",
                "unit": SPEChargeLineDB.Unit.FLAT,
                "product_code": self.product_code.code,
            },
            decision_id="classify-replay",
        )

        first = self._post([decision], key=key)
        second = self._post([decision], key=key)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(SPEChargeLineDB.objects.filter(description="Documentation fee").count(), 1)
        self.assertEqual(DraftQuoteDecisionDB.objects.filter(idempotency_key=key, decision_id="classify-replay").count(), 1)

    def test_unknown_charge_reload_then_finalize(self):
        res = self._post([
            self._decision(
                "classify_unclassified",
                target_id="unclass-1",
                details={
                    "classification": "charge",
                    "display_label": "Documentation fee",
                    "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
                    "currency": "USD",
                    "amount": "25.00",
                    "unit": SPEChargeLineDB.Unit.FLAT,
                    "product_code": self.product_code.code,
                },
                decision_id="classify-reload-finalize",
            ),
            self._decision("classify_unclassified", target_id="unclass-2", details={"classification": "ignored", "reason": "Greeting"}, decision_id="ignore-note-finalize"),
            self._decision("map_to_product_code", details={"product_code": self.product_code.code}, decision_id="map-existing-finalize"),
        ])
        self.assertEqual(res.data["rejected_decisions"], [])

        self.client.force_authenticate(user=self.sales)
        read_res = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        self.assertEqual(read_res.status_code, status.HTTP_200_OK)
        self.assertEqual(read_res.data["review_session"]["remaining_blockers"], 0)
        finalize = self._finalize()
        self.assertEqual(finalize.status_code, status.HTTP_200_OK)
        self.assertEqual(finalize.data["review_status"], "finalized")

    def test_edit_charge_updates_allowed_fields_and_preserves_evidence(self):
        res = self._post([
            self._decision(
                "edit_charge",
                details={"original_values": {}, "updated_values": {"description": "Edited fee", "amount": "12.50", "include_in_totals": False}},
            )
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.description, "Edited fee")
        self.assertEqual(self.charge.amount, Decimal("12.50"))
        self.assertTrue(self.charge.exclude_from_totals)
        self.assertEqual(self.charge.source_label, "DOC FEE")
        decision = DraftQuoteDecisionDB.objects.get(decision_type="edit_charge")
        self.assertEqual(decision.details_json["before"]["description"], "Raw documentation fee")
        self.assertEqual(decision.details_json["after"]["amount"], "12.50")

    def test_edit_charge_rejects_unknown_field(self):
        res = self._post([self._decision("edit_charge", details={"original_values": {}, "updated_values": {"source_excerpt": "rewrite raw"}})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "INVALID_FIELD")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.source_excerpt, "DOC FEE USD 10")

    def test_edit_charge_maps_calculation_basis_to_unit_type(self):
        res = self._post([
            self._decision(
                "edit_charge",
                details={"original_values": {}, "updated_values": {"calculation_basis": SPEChargeLineDB.UnitType.KG}},
            )
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.unit_type, SPEChargeLineDB.UnitType.KG)
        self.assertIsNone(self.charge.calculation_basis)

    def test_edit_charge_rejects_invalid_currency(self):
        res = self._post([
            self._decision("edit_charge", details={"original_values": {}, "updated_values": {"currency": "USDX"}})
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "INVALID_CURRENCY")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.currency, "USD")

    def test_edit_charge_rejects_invalid_unit(self):
        res = self._post([
            self._decision("edit_charge", details={"original_values": {}, "updated_values": {"unit": "per_container"}})
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "INVALID_UNIT")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.unit, SPEChargeLineDB.Unit.FLAT)

    def test_edit_charge_rejects_negative_numeric_value(self):
        res = self._post([
            self._decision("edit_charge", details={"original_values": {}, "updated_values": {"amount": "-0.01"}})
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "NEGATIVE_NUMERIC_VALUE")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.amount, Decimal("10.00"))

    def test_classify_unclassified_as_charge_creates_charge_line(self):
        res = self._post([
            self._decision(
                "classify_unclassified",
                target_id="unclass-1",
                details={
                    "classification": "charge",
                    "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
                    "display_label": "Documentation fee",
                    "product_code": self.product_code.code,
                    "amount": "25.00",
                    "currency": "USD",
                    "unit": SPEChargeLineDB.Unit.FLAT,
                },
            )
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        created = SPEChargeLineDB.objects.get(description="Documentation fee")
        self.assertEqual(created.manual_resolved_product_code_id, self.product_code.id)
        self.assertEqual(created.source_excerpt, "Documentation fee USD 25")
        self.batch.refresh_from_db()
        self.assertEqual([i["id"] for i in self.batch.analysis_summary_json["unclassified_items"]], ["unclass-2"])
        self.assertFalse(any(i.get("id") == "unclass-1" for i in self.batch.analysis_summary_json.get("ignored_items", [])))

    def test_classify_unclassified_without_product_code_is_skipped(self):
        res = self._post([
            self._decision(
                "classify_unclassified",
                target_id="unclass-1",
                details={
                    "classification": "charge",
                    "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
                    "display_label": "Documentation fee",
                    "product_code": "MISSING",
                    "amount": "25.00",
                    "currency": "USD",
                    "unit": SPEChargeLineDB.Unit.FLAT,
                },
            )
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rejected_decisions"][0]["status"], "rejected")
        self.assertEqual(res.data["rejected_decisions"][0]["error_code"], "PRODUCT_CODE_REQUIRED")

    def test_classify_unclassified_as_ignored_preserves_text(self):
        res = self._post([self._decision("classify_unclassified", target_id="unclass-2", details={"classification": "ignored", "reason": "Greeting"})])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.analysis_summary_json["ignored_items"][0]["raw_text"], "Have a nice day")

    def test_rejected_product_code_request_metadata_appears_in_read_payload(self):
        rejected_request = self._rejected_product_code_request()
        self._persist_request_decision(rejected_request)

        charge = self._read_charge()

        self.assertEqual(charge["product_code_request_id"], rejected_request.id)
        self.assertEqual(charge["rejected_product_code"], "IMP-DOC-NEW")
        self.assertEqual(charge["rejected_product_code_name"], "DOC FEE")
        self.assertEqual(charge["product_code_rejection_reason"], "Duplicate of existing import documentation fee.")
        self.assertEqual(charge["product_code_rejected_at"], rejected_request.rejected_at.isoformat())
        self.assertEqual(
            charge["correction_actions"],
            [
                "PRODUCTCODE_REJECTED",
                "MAP_TO_EXISTING_PRODUCTCODE",
                "EDIT_AND_RESUBMIT_PRODUCTCODE_REQUEST",
                "IGNORE_REJECTED_PRODUCTCODE_REQUEST",
            ],
        )

    def test_map_existing_product_code_after_rejection_resolves_charge(self):
        rejected_request = self._rejected_product_code_request()
        self._persist_request_decision(rejected_request)

        res = self._post([
            self._decision("map_to_product_code", details={"product_code": self.product_code.code}, decision_id="map-after-reject")
        ])

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.manual_resolved_product_code_id, self.product_code.id)
        charge = self._read_charge()
        self.assertEqual(charge["status"], "accepted_by_user")
        self.assertEqual(charge["correction_actions"], [])
        self.assertIsNone(charge["product_code_request_id"])

    def test_ordinary_charge_request_retains_server_charge_bucket_unit_metadata(self):
        res = self._post([
            self._decision(
                "request_product_code",
                details={
                    "proposed_code": "IMP-DOC-ORDINARY",
                    "description": "Client-side edited description",
                    "bucket": "",
                    "category": "",
                    "unit": "",
                    "reason": "Supplier added new fee",
                },
                decision_id="request-ordinary-metadata",
            )
        ])

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "skipped")
        request = ProductCodeCreationRequest.objects.get(suggested_name="IMP-DOC-ORDINARY")
        self.assertEqual(request.source_label, "DOC FEE")
        self.assertEqual(request.suggested_bucket, SPEChargeLineDB.Bucket.DESTINATION_CHARGES)
        self.assertEqual(request.suggested_basis, SPEChargeLineDB.Unit.FLAT)
        self.assertEqual(request.source_context_json["domain"], "IMPORT")
        self.assertEqual(request.source_context_json["source_label"], "DOC FEE")
        self.assertEqual(request.source_context_json["source_charge_line_id"], str(self.charge.id))
        self.assertEqual(request.source_context_json["charge_bucket"], SPEChargeLineDB.Bucket.DESTINATION_CHARGES)
        self.assertEqual(request.source_context_json["charge_unit"], SPEChargeLineDB.Unit.FLAT)

    def test_resubmitting_rejected_product_code_creates_new_pending_request(self):
        rejected_request = self._rejected_product_code_request()
        self._persist_request_decision(rejected_request)
        rejected_snapshot = {
            "status": rejected_request.status,
            "rejection_reason": rejected_request.rejection_reason,
            "rejected_at": rejected_request.rejected_at,
        }

        res = self._post([
            self._decision(
                "request_product_code",
                details={
                    "proposed_code": "IMP-DOC-CORRECTED",
                    "description": "Corrected import documentation fee",
                    "category": "destination_charges",
                    "domain": "IMPORT",
                    "reason": "Corrected after admin rejection",
                },
                decision_id="resubmit-rejected",
            )
        ])

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "skipped")
        rejected_request.refresh_from_db()
        self.assertEqual(rejected_request.status, rejected_snapshot["status"])
        self.assertEqual(rejected_request.rejection_reason, rejected_snapshot["rejection_reason"])
        self.assertEqual(rejected_request.rejected_at, rejected_snapshot["rejected_at"])
        pending = ProductCodeCreationRequest.objects.get(
            source_envelope=self.envelope,
            suggested_name="IMP-DOC-CORRECTED",
        )
        self.assertEqual(pending.status, ProductCodeCreationRequest.STATUS_PENDING)
        self.assertEqual(pending.source_charge_line_id, self.charge.id)
        charge = self._read_charge()
        self.assertEqual(charge["correction_actions"], ["PENDING_ADMIN_REVIEW"])
        self.assertEqual(charge["product_code_request_id"], pending.id)

    def test_ignored_rejected_product_code_blocker_is_auditable(self):
        rejected_request = self._rejected_product_code_request()
        self._persist_request_decision(rejected_request)

        res = self._post([
            self._decision("ignore", details={"reason": "Not billable after admin rejection"}, decision_id="ignore-rejected")
        ])

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.charge.refresh_from_db()
        self.assertTrue(self.charge.exclude_from_totals)
        decision = DraftQuoteDecisionDB.objects.get(decision_id="ignore-rejected")
        self.assertEqual(decision.decision_type, "ignore")
        self.assertEqual(decision.details_json["reason"], "Not billable after admin rejection")
        charge = self._read_charge()
        self.assertEqual(charge["status"], "ignored")
        self.assertEqual(charge["correction_actions"], [])

    def test_finance_and_cross_scope_users_cannot_resolve_high_value_decisions(self):
        decision = self._decision("map_to_product_code", details={"product_code": self.product_code.code})
        self.assertEqual(self._post([decision], user=self.finance).status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(self._post([decision], user=self.other_sales).status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_low_risk_and_product_code_request_flows_still_pass(self):
        res = self._post([
            self._decision("accept_suggestion", decision_id="accept"),
            self._decision("ignore", decision_id="ignore", details={"reason": "Not commercial"}),
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual([d["status"] for d in res.data["applied_decisions"]], ["applied", "applied"])

        request_res = self._post([
            self._decision(
                "request_product_code",
                decision_id="request",
                details={
                    "proposed_code": "IMP-NEW",
                    "description": "New import fee",
                    "category": "destination_charges",
                    "domain": "IMPORT",
                    "reason": "Supplier added new fee",
                },
            )
        ])
        self.assertEqual(request_res.status_code, status.HTTP_200_OK)
        self.assertEqual(request_res.data["applied_decisions"][0]["status"], "skipped")
        self.assertEqual(ProductCodeCreationRequest.objects.filter(source_envelope=self.envelope).count(), 1)

    def test_approved_product_code_consumption_still_passes(self):
        req = ProductCodeCreationRequest.objects.create(
            source_label="DOC FEE",
            suggested_name="IMP-DOC-FEE",
            suggested_bucket="destination_charges",
            suggested_basis="FLAT",
            source_envelope=self.envelope,
            source_charge_line=self.charge,
            status=ProductCodeCreationRequest.STATUS_APPROVED,
            approved_product_code=self.product_code,
            created_by=self.sales,
        )
        res = self._post([
            self._decision(
                "use_approved_product_code",
                details={"product_code_request_id": req.id, "product_code_id": self.product_code.id},
            )
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.manual_resolved_product_code_id, self.product_code.id)

    def test_pending_product_code_request_blocks_finalization(self):
        res = self._post([
            self._decision(
                "request_product_code",
                details={
                    "proposed_code": "IMP-PENDING",
                    "description": "Pending request",
                    "category": "destination_charges",
                    "reason": "Needs admin review",
                },
                decision_id="request-pending-finalize",
            ),
            self._decision("classify_unclassified", target_id="unclass-1", details={"classification": "ignored", "reason": "Not billable"}, decision_id="ignore-pending-u1"),
            self._decision("classify_unclassified", target_id="unclass-2", details={"classification": "ignored", "reason": "Greeting"}, decision_id="ignore-pending-u2"),
        ])
        self.assertEqual(res.data["rejected_decisions"], [])

        finalize = self._finalize()

        self.assertEqual(finalize.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(finalize.data["status"], "rejected")
        self.assertGreaterEqual(finalize.data["remaining_blockers"], 1)

    def test_request_approve_apply_then_finalize(self):
        res = self._post([
            self._decision(
                "request_product_code",
                details={
                    "proposed_code": "IMP-APPROVED-FLOW",
                    "description": "Approved flow",
                    "category": "destination_charges",
                    "reason": "Needs admin review",
                },
                decision_id="request-approved-flow",
            ),
            self._decision("classify_unclassified", target_id="unclass-1", details={"classification": "ignored", "reason": "Not billable"}, decision_id="ignore-approved-u1"),
            self._decision("classify_unclassified", target_id="unclass-2", details={"classification": "ignored", "reason": "Greeting"}, decision_id="ignore-approved-u2"),
        ])
        self.assertEqual(res.data["rejected_decisions"], [])
        request = ProductCodeCreationRequest.objects.get(suggested_name="IMP-APPROVED-FLOW")
        request.status = ProductCodeCreationRequest.STATUS_APPROVED
        request.approved_product_code = self.product_code
        request.approved_at = timezone.now()
        request.approved_by = self.manager
        request.save(update_fields=["status", "approved_product_code", "approved_at", "approved_by"])

        apply_res = self._post([
            self._decision(
                "use_approved_product_code",
                details={"product_code_request_id": request.id, "product_code_id": self.product_code.id},
                decision_id="apply-approved-flow",
            )
        ])
        self.assertEqual(apply_res.data["rejected_decisions"], [])

        finalize = self._finalize()
        self.assertEqual(finalize.status_code, status.HTTP_200_OK)
        self.assertEqual(finalize.data["review_status"], "finalized")

    def test_finalize_succeeds_when_blockers_resolved_and_read_reflects_state(self):
        self._resolve_all_blockers()
        key = uuid.uuid4()

        res = self._finalize(key=key)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "accepted")
        self.assertEqual(res.data["review_status"], "finalized")
        self.assertEqual(res.data["remaining_blockers"], 0)
        self.assertEqual(res.data["finalized_by"], self.sales.id)
        self.assertIsNotNone(res.data["finalized_at"])

        self.client.force_authenticate(user=self.sales)
        read_res = self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")
        self.assertEqual(read_res.status_code, status.HTTP_200_OK)
        self.assertEqual(read_res.data["review_session"]["status"], "finalized")
        self.assertEqual(read_res.data["review_session"]["remaining_blockers"], 0)
        self.assertEqual(read_res.data["review_session"]["available_actions"], ["reopen"])

    def test_finalize_fails_when_critical_blockers_remain(self):
        res = self._finalize()

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["status"], "rejected")
        self.assertGreaterEqual(res.data["remaining_blockers"], 1)
        self.assertEqual(res.data["review_status"], "draft")

    def test_finalize_replay_is_idempotent(self):
        self._resolve_all_blockers()
        key = uuid.uuid4()

        first = self._finalize(key=key)
        second = self._finalize(key=key)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["review_status"], "finalized")
        self.assertEqual(second.data["finalized_at"], first.data["finalized_at"])

    def test_finalized_workspace_blocks_further_resolve_decisions(self):
        self._resolve_all_blockers()
        self.assertEqual(self._finalize().status_code, status.HTTP_200_OK)

        res = self._post([
            self._decision("edit_charge", details={"original_values": {}, "updated_values": {"amount": "11.00"}}, decision_id="edit-after-final")
        ])

        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["error_code"], "DRAFT_QUOTE_FINALIZED")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.amount, Decimal("10.00"))

    def test_manager_can_reopen_finalized_review_and_resolve_can_continue(self):
        self._resolve_all_blockers()
        self.assertEqual(self._finalize().status_code, status.HTTP_200_OK)

        reopen = self._reopen(user=self.manager)
        self.assertEqual(reopen.status_code, status.HTTP_200_OK)
        self.assertEqual(reopen.data["review_status"], "in_review")

        res = self._post([
            self._decision("edit_charge", details={"original_values": {}, "updated_values": {"amount": "11.00"}}, decision_id="edit-after-reopen")
        ])
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["applied_decisions"][0]["status"], "applied")

    def test_finance_and_cross_scope_users_cannot_finalize_or_reopen(self):
        self._resolve_all_blockers()

        self.assertEqual(self._finalize(user=self.finance).status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(self._finalize(user=self.other_sales).status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

        self.assertEqual(self._finalize(user=self.sales).status_code, status.HTTP_200_OK)
        self.assertEqual(self._reopen(user=self.sales).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._reopen(user=self.finance).status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(self._reopen(user=self.other_sales).status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
