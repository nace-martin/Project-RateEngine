import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Role, UserMembership
from parties.models import Branch, Department, OperatingEntity, Organization
from pricing_v4.models import ProductCode, ProductCodeCreationRequest
from quotes.contracts.draft_quote_contract import DraftQuoteSchema
from quotes.spot_models import (
    DraftQuoteDecisionDB,
    SPEChargeLineDB,
    SPESourceBatchDB,
    SpotPricingEnvelopeDB,
)


class SpotExceptionWorkspaceE2ETests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Express Freight Management", slug="efm")
        self.other_org = Organization.objects.create(name="Other Tenant", slug="other-tenant")
        self.entity = OperatingEntity.objects.create(organization=self.org, code="EFM_PNG", name="EFM PNG")
        self.branch = Branch.objects.create(organization=self.org, operating_entity=self.entity, code="POM", name="Port Moresby")
        self.department = Department.objects.create(organization=self.org, branch=self.branch, code="AIR", name="Air Freight")
        other_branch = Branch.objects.create(organization=self.other_org, code="BNE", name="Brisbane")
        other_department = Department.objects.create(
            organization=self.other_org,
            branch=other_branch,
            code="AIR",
            name="Air Freight",
        )

        User = get_user_model()
        self.sales = User.objects.create_user(username="spot_e2e_sales", password="x", role=User.ROLE_SALES)
        self.manager = User.objects.create_user(username="spot_e2e_manager", password="x", role=User.ROLE_MANAGER)
        self.admin = User.objects.create_user(username="spot_e2e_admin", password="x", role=User.ROLE_ADMIN)
        self.finance = User.objects.create_user(username="spot_e2e_finance", password="x", role=User.ROLE_FINANCE)
        self.cross_scope = User.objects.create_user(username="spot_e2e_cross", password="x", role=User.ROLE_SALES)
        for user, role_code in ((self.sales, "sales"), (self.manager, "manager"), (self.admin, "admin"), (self.finance, "finance")):
            self._membership(user, self.org, self.branch, self.department, role_code)
        self._membership(self.cross_scope, self.other_org, other_branch, other_department, "sales")

        self.freight_pc = self._product_code(9101, "AIR-FREIGHT-E2E", "Air freight", ProductCode.CATEGORY_FREIGHT)
        self.fuel_pc = self._product_code(9102, "AIR-FUEL-E2E", "Air fuel surcharge", ProductCode.CATEGORY_SURCHARGE)
        self.docs_pc = self._product_code(9103, "IMP-DOC-E2E", "Import documentation", ProductCode.CATEGORY_DOCUMENTATION)
        self.handling_pc = self._product_code(9104, "IMP-HANDLING-E2E", "Import handling", ProductCode.CATEGORY_HANDLING)

        self.envelope = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={
                "origin_code": "SIN",
                "destination_code": "POM",
                "origin_country": "SG",
                "destination_country": "PG",
                "mode": "AIR",
                "service_scope": "A2D",
                "pieces": 4,
                "actual_weight_kg": 180,
                "chargeable_weight_kg": 220,
                "commodity": "GCR",
                "supplier_name": "Pilot Air Cargo",
            },
            conditions_json={"validity": {"text": "Valid for 7 days", "normalized_value": "P7D"}},
            spot_trigger_reason_code="AIR_IMPORT_PILOT_EXCEPTION",
            spot_trigger_reason_text="Air import pilot requires SPOT exception workspace review.",
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
            source_type=SPESourceBatchDB.SourceType.EMAIL,
            target_bucket=SPESourceBatchDB.TargetBucket.MIXED,
            label="Pilot Air Cargo reply",
            file_name="pilot-air-cargo-email.txt",
            raw_text="Air freight USD 880; FSC USD 120; Terminal fee USD 45; Documentation fee USD 25.",
            analysis_summary_json={
                "extracted_total": "1070.00",
                "warnings": ["Supplier total includes mixed USD/PGK rows."],
                "unclassified_items": [
                    {"id": "unclass-ignore", "raw_text": "Rates subject to space availability.", "review_reason": "Commercial-looking boilerplate"},
                    {"id": "unclass-docs", "raw_text": "Documentation fee USD 25", "review_reason": "Potential charge"},
                ],
                "ignored_items": [
                    {"id": "boilerplate-1", "raw_text": "Thank you for your business.", "ignored_reason": "Standard boilerplate content ignored"}
                ],
            },
            created_by=self.sales,
        )
        self.mapped_charge = self._charge(
            "AIR-FREIGHT-E2E",
            "Air freight SIN-POM",
            "880.00",
            "USD",
            SPEChargeLineDB.Unit.PER_KG,
            SPEChargeLineDB.Bucket.AIRFREIGHT,
            SPEChargeLineDB.NormalizationStatus.MATCHED,
            resolved_product_code=self.freight_pc,
            rate="4.0000",
            is_primary_cost=True,
        )
        self.ambiguous_charge = self._charge(
            "FSC",
            "Fuel surcharge",
            "120.00",
            "USD",
            SPEChargeLineDB.Unit.PER_KG,
            SPEChargeLineDB.Bucket.AIRFREIGHT,
            SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        )
        self.unmapped_charge = self._charge(
            "TERM-FEE",
            "Terminal handling fee",
            "45.00",
            "PGK",
            SPEChargeLineDB.Unit.FLAT,
            SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )

    def _membership(self, user, organization, branch, department, role_code):
        role, _ = Role.objects.get_or_create(code=role_code, defaults={"name": role_code.title()})
        UserMembership.objects.create(
            user=user,
            organization=organization,
            branch=branch,
            department=department,
            role=role,
            is_active=True,
            is_primary=True,
        )

    def _product_code(self, pk, code, description, category):
        return ProductCode.objects.create(
            id=pk,
            code=code,
            description=description,
            domain=ProductCode.DOMAIN_IMPORT,
            category=category,
            is_gst_applicable=False,
            gl_revenue_code="4000",
            gl_cost_code="5000",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def _charge(self, code, description, amount, currency, unit, bucket, normalization_status, **extra):
        return SPEChargeLineDB.objects.create(
            envelope=self.envelope,
            source_batch=self.batch,
            code=code,
            description=description,
            amount=Decimal(amount),
            currency=currency,
            unit=unit,
            bucket=bucket,
            normalization_status=normalization_status,
            source_label=description,
            source_excerpt=f"{description} {currency} {amount}",
            source_reference=self.batch.file_name,
            entered_by=self.sales,
            entered_at=timezone.now(),
            **extra,
        )

    def _read(self, user=None):
        self.client.force_authenticate(user=user or self.sales)
        return self.client.get(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/")

    def _resolve(self, decisions, key=None, user=None):
        self.client.force_authenticate(user=user or self.sales)
        return self.client.post(
            f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/resolve/",
            {"idempotency_key": str(key or uuid.uuid4()), "decisions": decisions},
            format="json",
        )

    def _finalize(self, key=None, user=None):
        self.client.force_authenticate(user=user or self.sales)
        actor = user or self.sales
        return self.client.post(
            f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/finalize/",
            {"idempotency_key": str(key or uuid.uuid4()), "audit_metadata": {"user_id": actor.id}},
            format="json",
        )

    def _reopen(self, user=None):
        self.client.force_authenticate(user=user or self.manager)
        return self.client.post(f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/reopen/", {}, format="json")

    def _decision(self, decision_type, target_id, details=None, decision_id=None):
        return {
            "decision_id": decision_id or f"{decision_type}-{target_id}",
            "type": decision_type,
            "target_id": str(target_id),
            "details": details or {},
            "audit_metadata": {"user_id": self.sales.id, "timestamp": "2026-07-07T00:00:00Z"},
        }

    def _read_charge(self, charge_id):
        res = self._read()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return next(c for c in res.data["suggested_charges"] if c["id"] == str(charge_id))

    def test_air_freight_pilot_workspace_full_workflow(self):
        read_url = f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/"
        resolve_url = f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/resolve/"
        finalize_url = f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/finalize/"
        reopen_url = f"/api/v3/spot/envelopes/{self.envelope.id}/draft-quote/reopen/"

        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(read_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(resolve_url, {}, format="json").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(finalize_url, {}, format="json").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(reopen_url, {}, format="json").status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.finance)
        self.assertEqual(self.client.get(read_url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(resolve_url, {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(finalize_url, {}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(reopen_url, {}, format="json").status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.cross_scope)
        self.assertEqual(self.client.get(read_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(resolve_url, {}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(finalize_url, {}, format="json").status_code, status.HTTP_404_NOT_FOUND)

        read = self._read()
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        draft = DraftQuoteSchema(**read.data)
        self.assertEqual(draft.review_session.status, "draft")
        self.assertEqual(draft.review_session.remaining_blockers, 4)
        self.assertEqual(
            {item["id"] for item in read.data["review_queue"]},
            {str(self.ambiguous_charge.id), str(self.unmapped_charge.id), "unclass-ignore", "unclass-docs"},
        )
        self.assertFalse(read.data["totals_validation"]["currency_consistent"])
        self.assertIn("Mixed currency warning: Multiple currencies found in charge items.", read.data["warnings"])
        self.assertEqual(self._finalize().status_code, status.HTTP_400_BAD_REQUEST)

        accept_key = uuid.uuid4()
        accept_decision = self._decision("accept_suggestion", self.ambiguous_charge.id, decision_id="accept-fuel")
        accept = self._resolve([accept_decision], key=accept_key)
        self.assertEqual(accept.status_code, status.HTTP_200_OK)
        self.assertEqual(accept.data["applied_decisions"][0]["status"], "applied")
        self.assertEqual(self._resolve([accept_decision], key=accept_key).status_code, status.HTTP_200_OK)
        self.assertEqual(DraftQuoteDecisionDB.objects.filter(envelope=self.envelope, idempotency_key=accept_key).count(), 1)
        self.assertEqual(self._read_charge(self.ambiguous_charge.id)["status"], "accepted_by_user")

        edit = self._resolve([
            self._decision(
                "edit_charge",
                self.unmapped_charge.id,
                {"original_values": {}, "updated_values": {"amount": "50.00", "currency": "USD"}},
                "edit-terminal",
            )
        ])
        self.assertEqual(edit.status_code, status.HTTP_200_OK)
        self.assertEqual(edit.data["applied_decisions"][0]["status"], "applied")
        self.unmapped_charge.refresh_from_db()
        self.assertEqual(self.unmapped_charge.amount, Decimal("50.00"))
        self.assertEqual(self.unmapped_charge.currency, "USD")

        pending_key = uuid.uuid4()
        pending_decision = self._decision(
            "request_product_code",
            self.unmapped_charge.id,
            {
                "proposed_code": "IMP-TERMINAL-E2E",
                "description": "Import terminal handling fee",
                "category": "destination_charges",
                "domain": "IMPORT",
                "reason": "Pilot agent quoted a terminal fee not yet in catalog.",
            },
            "request-terminal",
        )
        pending = self._resolve([
            pending_decision
        ], key=pending_key)
        self.assertEqual(pending.status_code, status.HTTP_200_OK)
        self.assertEqual(pending.data["applied_decisions"][0]["status"], "skipped")
        self.assertEqual(self._resolve([pending_decision], key=pending_key).status_code, status.HTTP_200_OK)
        self.assertEqual(ProductCodeCreationRequest.objects.filter(source_envelope=self.envelope, suggested_name="IMP-TERMINAL-E2E").count(), 1)
        pending_charge = self._read_charge(self.unmapped_charge.id)
        self.assertEqual(pending_charge["correction_actions"], ["PENDING_ADMIN_REVIEW"])
        self.assertEqual(pending_charge["product_code_request_id"], ProductCodeCreationRequest.objects.get(suggested_name="IMP-TERMINAL-E2E").id)

        ignore_unclassified = self._resolve([
            self._decision(
                "classify_unclassified",
                "unclass-ignore",
                {"classification": "ignored", "reason": "Supplier boilerplate"},
                "ignore-boilerplate",
            )
        ])
        self.assertEqual(ignore_unclassified.status_code, status.HTTP_200_OK)
        self.assertEqual(ignore_unclassified.data["applied_decisions"][0]["status"], "applied")

        classify_charge = self._resolve([
            self._decision(
                "classify_unclassified",
                "unclass-docs",
                {
                    "classification": "charge",
                    "bucket": SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
                    "display_label": "Documentation fee",
                    "product_code": self.docs_pc.code,
                    "amount": "25.00",
                    "currency": "USD",
                    "unit": SPEChargeLineDB.Unit.FLAT,
                },
                "classify-docs",
            )
        ])
        self.assertEqual(classify_charge.status_code, status.HTTP_200_OK)
        self.assertEqual(classify_charge.data["applied_decisions"][0]["status"], "applied")
        self.assertTrue(SPEChargeLineDB.objects.filter(envelope=self.envelope, description="Documentation fee").exists())

        req = ProductCodeCreationRequest.objects.get(suggested_name="IMP-TERMINAL-E2E")
        approved_pc = self._product_code(9199, "IMP-TERMINAL-APPROVED", "Approved terminal handling", ProductCode.CATEGORY_HANDLING)
        req.status = ProductCodeCreationRequest.STATUS_APPROVED
        req.approved_product_code = approved_pc
        req.save(update_fields=["status", "approved_product_code"])
        approved_charge = self._read_charge(self.unmapped_charge.id)
        self.assertEqual(approved_charge["correction_actions"], ["APPROVED_PRODUCTCODE_AVAILABLE"])
        self.assertEqual(approved_charge["approved_product_code"], approved_pc.code)

        consume = self._resolve([
            self._decision(
                "use_approved_product_code",
                self.unmapped_charge.id,
                {"product_code_request_id": req.id, "product_code_id": approved_pc.id},
                "use-approved-terminal",
            )
        ])
        self.assertEqual(consume.status_code, status.HTTP_200_OK)
        self.assertEqual(consume.data["applied_decisions"][0]["status"], "applied")
        self.assertEqual(self._read_charge(self.unmapped_charge.id)["status"], "accepted_by_user")

        rejected_charge = self._charge(
            "SECURITY",
            "Security screening fee",
            "30.00",
            "USD",
            SPEChargeLineDB.Unit.FLAT,
            SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )
        rejected_req = ProductCodeCreationRequest.objects.create(
            source_label="Security screening fee",
            suggested_name="IMP-SECURITY-E2E",
            suggested_bucket="origin_charges",
            suggested_basis="FLAT",
            suggested_reason="Pilot security fee",
            source_envelope=self.envelope,
            source_charge_line=rejected_charge,
            status=ProductCodeCreationRequest.STATUS_REJECTED,
            rejected_at=timezone.now(),
            rejection_reason="Use existing import handling code.",
            created_by=self.sales,
        )
        DraftQuoteDecisionDB.objects.create(
            envelope=self.envelope,
            idempotency_key=uuid.uuid4(),
            decision_id="request-security-rejected",
            decision_type="request_product_code",
            target_id=str(rejected_charge.id),
            details_json={"product_code_request_id": rejected_req.id},
            client_audit_metadata_json={"user_id": self.sales.id},
            server_user=self.sales,
            status="skipped",
            message="ProductCode request created and pending admin review.",
        )
        rejected_payload = self._read_charge(rejected_charge.id)
        self.assertEqual(
            rejected_payload["correction_actions"],
            [
                "PRODUCTCODE_REJECTED",
                "MAP_TO_EXISTING_PRODUCTCODE",
                "EDIT_AND_RESUBMIT_PRODUCTCODE_REQUEST",
                "IGNORE_REJECTED_PRODUCTCODE_REQUEST",
            ],
        )
        self.assertEqual(rejected_payload["product_code_rejection_reason"], "Use existing import handling code.")
        recovered = self._resolve([
            self._decision("map_to_product_code", rejected_charge.id, {"product_code": self.handling_pc.code}, "map-security-existing")
        ])
        self.assertEqual(recovered.status_code, status.HTTP_200_OK)
        self.assertEqual(recovered.data["applied_decisions"][0]["status"], "applied")

        another_rejected = self._charge(
            "QUARANTINE",
            "Quarantine admin fee",
            "15.00",
            "USD",
            SPEChargeLineDB.Unit.FLAT,
            SPEChargeLineDB.Bucket.DESTINATION_CHARGES,
            SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )
        another_req = ProductCodeCreationRequest.objects.create(
            source_label="Quarantine admin fee",
            suggested_name="IMP-QUARANTINE-E2E",
            suggested_bucket="destination_charges",
            suggested_basis="FLAT",
            source_envelope=self.envelope,
            source_charge_line=another_rejected,
            status=ProductCodeCreationRequest.STATUS_REJECTED,
            rejected_at=timezone.now(),
            rejection_reason="Not billable on this pilot lane.",
            created_by=self.sales,
        )
        DraftQuoteDecisionDB.objects.create(
            envelope=self.envelope,
            idempotency_key=uuid.uuid4(),
            decision_id="request-quarantine-rejected",
            decision_type="request_product_code",
            target_id=str(another_rejected.id),
            details_json={"product_code_request_id": another_req.id},
            client_audit_metadata_json={"user_id": self.sales.id},
            server_user=self.sales,
            status="skipped",
            message="ProductCode request created and pending admin review.",
        )
        ignored_rejected = self._resolve([
            self._decision("ignore", another_rejected.id, {"reason": "Not billable on this lane"}, "ignore-quarantine")
        ])
        self.assertEqual(ignored_rejected.status_code, status.HTTP_200_OK)
        self.assertEqual(ignored_rejected.data["applied_decisions"][0]["status"], "applied")

        third_rejected = self._charge(
            "XRAY",
            "X-ray surcharge",
            "18.00",
            "USD",
            SPEChargeLineDB.Unit.FLAT,
            SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            SPEChargeLineDB.NormalizationStatus.UNMAPPED,
        )
        third_req = ProductCodeCreationRequest.objects.create(
            source_label="X-ray surcharge",
            suggested_name="IMP-XRAY-OLD",
            suggested_bucket="origin_charges",
            suggested_basis="FLAT",
            source_envelope=self.envelope,
            source_charge_line=third_rejected,
            status=ProductCodeCreationRequest.STATUS_REJECTED,
            rejected_at=timezone.now(),
            rejection_reason="Code name too broad.",
            created_by=self.sales,
        )
        DraftQuoteDecisionDB.objects.create(
            envelope=self.envelope,
            idempotency_key=uuid.uuid4(),
            decision_id="request-xray-rejected",
            decision_type="request_product_code",
            target_id=str(third_rejected.id),
            details_json={"product_code_request_id": third_req.id},
            client_audit_metadata_json={"user_id": self.sales.id},
            server_user=self.sales,
            status="skipped",
            message="ProductCode request created and pending admin review.",
        )
        resubmit = self._resolve([
            self._decision(
                "request_product_code",
                third_rejected.id,
                {
                    "proposed_code": "IMP-XRAY-CORRECTED",
                    "description": "Corrected x-ray surcharge",
                    "category": "origin_charges",
                    "domain": "IMPORT",
                    "reason": "Corrected after admin rejection.",
                },
                "resubmit-xray",
            )
        ])
        self.assertEqual(resubmit.status_code, status.HTTP_200_OK)
        self.assertEqual(resubmit.data["applied_decisions"][0]["status"], "skipped")
        self.assertEqual(ProductCodeCreationRequest.objects.filter(source_envelope=self.envelope, suggested_name="IMP-XRAY-CORRECTED").count(), 1)

        final_read = self._read()
        self.assertEqual(final_read.status_code, status.HTTP_200_OK)
        self.assertEqual(final_read.data["review_session"]["remaining_blockers"], 0)
        self.assertEqual(final_read.data["review_session"]["available_actions"], ["finalize"])

        finalize_key = uuid.uuid4()
        finalized = self._finalize(key=finalize_key)
        replay_finalized = self._finalize(key=finalize_key)
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        self.assertEqual(replay_finalized.status_code, status.HTTP_200_OK)
        self.assertEqual(finalized.data["review_status"], "finalized")
        self.assertEqual(replay_finalized.data["finalized_at"], finalized.data["finalized_at"])
        self.assertEqual(self._read().data["review_session"]["status"], "finalized")

        blocked = self._resolve([
            self._decision("edit_charge", self.mapped_charge.id, {"original_values": {}, "updated_values": {"amount": "881.00"}}, "edit-after-final")
        ])
        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(blocked.data["error_code"], "DRAFT_QUOTE_FINALIZED")

        self.assertEqual(self._reopen(user=self.sales).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._reopen(user=self.finance).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._reopen(user=self.cross_scope).status_code, status.HTTP_403_FORBIDDEN)
        reopened = self._reopen(user=self.admin)
        self.assertEqual(reopened.status_code, status.HTTP_200_OK)
        self.assertEqual(reopened.data["review_status"], "in_review")
        after_reopen = self._resolve([
            self._decision("edit_charge", self.mapped_charge.id, {"original_values": {}, "updated_values": {"amount": "881.00"}}, "edit-after-reopen")
        ])
        self.assertEqual(after_reopen.status_code, status.HTTP_200_OK)
        self.assertEqual(after_reopen.data["applied_decisions"][0]["status"], "applied")

        other_envelope = SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            shipment_context_json={"origin_country": "SG", "destination_country": "PG", "mode": "AIR"},
            spot_trigger_reason_code="OTHER",
            spot_trigger_reason_text="Other envelope",
            expires_at=timezone.now() + timezone.timedelta(days=7),
            organization=self.org,
            branch=self.branch,
            department=self.department,
            owner=self.sales,
            created_by=self.sales,
        )
        other_batch = SPESourceBatchDB.objects.create(envelope=other_envelope, source_kind=SPESourceBatchDB.SourceKind.AGENT)
        other_charge = SPEChargeLineDB.objects.create(
            envelope=other_envelope,
            source_batch=other_batch,
            code="OTHER",
            description="Other fee",
            amount=Decimal("1.00"),
            currency="USD",
            unit=SPEChargeLineDB.Unit.FLAT,
            bucket=SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            source_reference="other.txt",
            entered_by=self.sales,
            entered_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.sales)
        other_res = self.client.post(
            f"/api/v3/spot/envelopes/{other_envelope.id}/draft-quote/resolve/",
            {
                "idempotency_key": str(accept_key),
                "decisions": [self._decision("ignore", other_charge.id, {"reason": "Other envelope"}, "accept-fuel")],
            },
            format="json",
        )
        self.assertEqual(other_res.status_code, status.HTTP_200_OK)
        self.assertEqual(other_res.data["envelope_id"], str(other_envelope.id))
        self.assertEqual(DraftQuoteDecisionDB.objects.filter(idempotency_key=accept_key).count(), 2)
