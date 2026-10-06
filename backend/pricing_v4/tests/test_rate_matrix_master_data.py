"""Pilot Gate B3F: controlled Rate Matrix master-data loader.

Every value here is synthetic test data. No real party, ProductCode, or tariff appears.
"""

import copy
import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from parties.party_models import PartyMaster, PartyRole, PartyRoleIdentifier

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import ProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.rate_matrix_master_data import (
    MasterDataApplyError,
    apply_master_data_text,
    plan_master_data_text,
)

PARTY = "Synthetic Agent Pty Ltd"
EXISTING = "IMP-SYNTH-EXISTING"
ZERO = "IMP-SYNTH-ZERO"
RETIRED = "IMP-SYNTH-RETIRED"
NEW = "IMP-SYNTH-NEW"


def _legacy_row(pk, code, gst="STANDARD", **extra):
    return ProductCode.objects.create(
        id=pk, code=code, description=f"Synthetic {code}", domain=ProductCode.DOMAIN_IMPORT,
        category=ProductCode.CATEGORY_HANDLING, is_gst_applicable=(gst == "STANDARD"), gst_rate="0.1000",
        gst_treatment=gst, gl_revenue_code="4000", gl_cost_code="5000",
        default_unit=ProductCode.UNIT_SHIPMENT, **extra,
    )


@pytest.fixture
def world(db):
    return {
        "existing": _legacy_row(2981, EXISTING),
        "zero": _legacy_row(2982, ZERO, gst="ZERO_RATED"),
        "retired": _legacy_row(2983, RETIRED, is_active=False, retired_at=timezone.now()),
        "operator": get_user_model().objects.create_user(username="synthetic-operator", password="x"),
    }


def _mirror(code, legacy_id, gst="STANDARD", approved=True, **overrides):
    values = {
        "code": code, "name": f"Synthetic {code}", "category": "DESTINATION", "sub_category": "",
        "gst_treatment": gst, "charge_basis_default": "FLAT", "is_active": True,
        "legacy_product_code": {"id": legacy_id, "code": code},
        "gst_approval": {"approved": approved, "reference": "SYNTHETIC-APPROVAL-1" if approved else ""},
        "evidence": "Synthetic evidence for the mirror",
    }
    values.update(overrides)
    return values


def valid_manifest():
    return {
        "manifest_version": 1,
        "parties": [{
            "legal_name": PARTY, "trade_name": "", "entity_type": "COMPANY", "country_code": "ZZ",
            "roles": ["AGENT"],
            "identifiers": [{"role": "AGENT", "scheme": "TAX_ID", "value": "SYNTH-000111"}],
            "evidence": "Synthetic register entry",
        }],
        "legacy_product_codes": [{
            "id": 2990, "code": NEW, "description": "Synthetic new destination fee", "domain": "IMPORT",
            "category": "HANDLING", "default_unit": "SHIPMENT", "is_gst_applicable": True, "gst_rate": "0.1000",
            "gst_treatment": "STANDARD", "gl_revenue_code": "4000", "gl_cost_code": "5000",
            "percent_of_product_code": None, "evidence": "Synthetic rate card line",
        }],
        "commercial_product_codes": [_mirror(EXISTING, 2981), _mirror(NEW, 2990)],
    }


def text_of(manifest):
    return json.dumps(manifest, indent=1)


def plan_of(manifest):
    return plan_master_data_text(text_of(manifest))


def apply_of(manifest, world, **kwargs):
    text = text_of(manifest)
    sha = kwargs.pop("reviewed_sha256", plan_master_data_text(text).manifest_sha256)
    return apply_master_data_text(text, operator=world["operator"], reviewed_sha256=sha, **kwargs)


TABLES = (PartyMaster, PartyRole, PartyRoleIdentifier, ProductCode, CommercialProductCode,
          RateSheet, RateLine, RateApplicability, RateTier)


def snapshot():
    return {
        "counts": {m._meta.db_table: m.objects.count() for m in TABLES},
        "legacy": list(ProductCode.objects.order_by("id").values()),
        "parties": list(PartyMaster.objects.order_by("legal_name").values("legal_name", "trade_name", "entity_type", "is_active")),
        "mirrors": list(CommercialProductCode.objects.order_by("code").values("code", "category", "legacy_product_code_id")),
    }


def actions(plan):
    return {(r.kind, r.identity): r.action for r in plan.records}


def record(plan, kind, index=0):
    return [r for r in plan.records if r.kind == kind][index]


# --------------------------------------------------------------------------- dry run


@pytest.mark.django_db
class TestDryRun:
    def test_plans_creates_and_is_ready(self, world):
        plan = plan_of(valid_manifest())
        assert plan.manifest_errors == []
        assert plan.ready
        assert plan.counts() == {"CREATE": 4, "REUSE": 0, "CONFLICT": 0, "BLOCKED": 0}
        assert actions(plan) == {
            ("PartyMaster", f'"{PARTY}" (ZZ)'): "CREATE",
            ("ProductCode", f"2990 {NEW}"): "CREATE",
            ("CommercialProductCode", f"{EXISTING} -> legacy 2981"): "CREATE",
            ("CommercialProductCode", f"{NEW} -> legacy 2990"): "CREATE",
        }
        party = record(plan, "PartyMaster")
        assert party.details == [
            "PartyMaster CREATE", "PartyRole AGENT CREATE", "PartyRoleIdentifier TAX_ID SYNTH-000111 CREATE",
        ]
        assert party.evidence == "Synthetic register entry"

    def test_performs_zero_writes(self, world):
        before = snapshot()
        with CaptureQueriesContext(connection) as queries:
            assert plan_of(valid_manifest()).ready
        writes = [
            q["sql"] for q in queries
            if q["sql"].lstrip().upper().split(None, 1)[0] in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"}
        ]
        assert writes == []
        assert snapshot() == before

    def test_not_ready_plan_performs_zero_writes(self, world):
        manifest = valid_manifest()
        manifest["commercial_product_codes"][0]["gst_treatment"] = "EXEMPT"
        before = snapshot()
        assert not plan_of(manifest).ready
        assert snapshot() == before

    def test_repeated_dry_runs_are_identical(self, world):
        first, second = plan_of(valid_manifest()), plan_of(valid_manifest())
        assert first.render_text() == second.render_text()
        assert first.render_json() == second.render_json()

    def test_text_report(self, world):
        text = plan_of(valid_manifest()).render_text()
        assert "Mode: DRY RUN" in text
        assert "CREATE 4   REUSE 0   CONFLICT 0   BLOCKED 0" in text
        assert f'[CREATE] "{PARTY}" (ZZ)' in text
        assert "evidence: Synthetic register entry" in text
        assert text.rstrip().endswith("Writes performed: 0")
        assert "Result: READY" in text

    def test_connection_writable_after_dry_run(self, world):
        plan_of(valid_manifest())
        PartyMaster(legal_name="Written After", entity_type="X", country_code="ZZ").save()
        assert PartyMaster.objects.filter(legal_name="Written After").exists()


# --------------------------------------------------------------------------- strict manifest


@pytest.mark.django_db
class TestStrictManifest:
    def test_invalid_json(self, world):
        plan = plan_master_data_text("{nope")
        assert not plan.ready
        assert plan.manifest_errors[0]["code"] == "MANIFEST_NOT_STRICT_JSON"

    def test_unknown_and_missing_fields(self, world):
        manifest = valid_manifest()
        manifest["parties"][0]["notes"] = "extra"
        del manifest["legacy_product_codes"][0]["gl_cost_code"]
        plan = plan_of(manifest)
        found = {(e["code"], e["path"]) for e in plan.manifest_errors}
        assert ("MANIFEST_UNKNOWN_FIELD", "$.parties[0].notes") in found
        assert ("MANIFEST_MISSING_FIELD", "$.legacy_product_codes[0].gl_cost_code") in found
        assert not plan.ready

    def test_unsupported_version(self, world):
        manifest = valid_manifest()
        manifest["manifest_version"] = 2
        assert plan_of(manifest).manifest_errors[0]["code"] == "MANIFEST_VERSION"

    @pytest.mark.parametrize(
        "section, key, value",
        [
            ("parties", "country_code", "zz"),
            ("parties", "roles", []),
            ("parties", "roles", ["BROKER"]),
            ("parties", "legal_name", " padded "),
            ("legacy_product_codes", "gst_rate", 0.1),
            ("legacy_product_codes", "gst_rate", "10"),
            ("legacy_product_codes", "id", "2990"),
            ("commercial_product_codes", "category", "LOCAL"),
            ("commercial_product_codes", "gst_treatment", "OUT_OF_SCOPE"),
            ("commercial_product_codes", "charge_basis_default", "AWB"),
        ],
    )
    def test_invalid_values_are_manifest_errors(self, world, section, key, value):
        manifest = valid_manifest()
        manifest[section][0][key] = value
        plan = plan_of(manifest)
        assert plan.manifest_errors, plan.render_text()
        assert not plan.ready

    def test_approved_gst_requires_a_reference(self, world):
        manifest = valid_manifest()
        manifest["commercial_product_codes"][0]["gst_approval"] = {"approved": True, "reference": ""}
        plan = plan_of(manifest)
        assert plan.manifest_errors[0]["path"] == "$.commercial_product_codes[0].gst_approval.reference"


# --------------------------------------------------------------------------- apply


@pytest.mark.django_db
class TestApply:
    def test_creates_every_planned_row(self, world):
        legacy_before = list(ProductCode.objects.filter(pk__in=[2981, 2982, 2983]).order_by("id").values())
        plan = apply_of(valid_manifest(), world)
        assert plan.ready
        assert plan.applied == {"operator": "synthetic-operator", "rows_created": 6}

        party = PartyMaster.objects.get(legal_name=PARTY, country_code="ZZ")
        assert (party.entity_type, party.trade_name, party.is_active) == ("COMPANY", "", True)
        role = PartyRole.objects.get(party=party)
        assert (role.role_type, role.is_active) == ("AGENT", True)
        assert list(PartyRoleIdentifier.objects.filter(role=role).values_list("scheme", "value")) == [("TAX_ID", "SYNTH-000111")]

        new = ProductCode.objects.get(pk=2990)
        assert (new.code, new.domain, new.category, new.default_unit, new.gst_treatment) == (
            NEW, "IMPORT", "HANDLING", "SHIPMENT", "STANDARD")
        assert (new.is_active, new.retired_at) == (True, None)

        mirrors = {m.code: m for m in CommercialProductCode.objects.all()}
        assert set(mirrors) == {EXISTING, NEW}
        assert mirrors[EXISTING].legacy_product_code_id == 2981
        assert mirrors[NEW].legacy_product_code_id == 2990
        assert mirrors[NEW].category == "DESTINATION"

        assert list(ProductCode.objects.filter(pk__in=[2981, 2982, 2983]).order_by("id").values()) == legacy_before
        assert RateSheet.objects.count() == 0

    def test_rerun_is_idempotent(self, world):
        apply_of(valid_manifest(), world)
        after_first = snapshot()
        second = apply_of(valid_manifest(), world)
        assert second.ready
        assert second.counts() == {"CREATE": 0, "REUSE": 4, "CONFLICT": 0, "BLOCKED": 0}
        assert second.applied["rows_created"] == 0
        assert snapshot() == after_first

    def test_dry_run_after_apply_reports_reuse(self, world):
        apply_of(valid_manifest(), world)
        plan = plan_of(valid_manifest())
        assert set(actions(plan).values()) == {"REUSE"}

    def test_refuses_when_manifest_differs_from_reviewed_dry_run(self, world):
        before = snapshot()
        with pytest.raises(MasterDataApplyError, match="does not match the reviewed dry run"):
            apply_of(valid_manifest(), world, reviewed_sha256="0" * 64)
        assert snapshot() == before

    def test_refuses_inactive_operator(self, world):
        world["operator"].is_active = False
        before = snapshot()
        with pytest.raises(MasterDataApplyError, match="active operator"):
            apply_of(valid_manifest(), world)
        assert snapshot() == before

    def test_any_conflict_refuses_the_whole_manifest(self, world):
        manifest = valid_manifest()
        manifest["commercial_product_codes"][0]["gst_treatment"] = "EXEMPT"
        before = snapshot()
        plan = apply_of(manifest, world)
        assert not plan.ready
        assert plan.applied is None
        assert "Apply refused. Nothing was written." in plan.render_text()
        assert snapshot() == before

    def test_blocked_gst_refuses_the_whole_manifest(self, world):
        manifest = valid_manifest()
        manifest["commercial_product_codes"].append(_mirror(ZERO, 2982, gst="ZERO_RATED", approved=False))
        before = snapshot()
        plan = apply_of(manifest, world)
        assert plan.counts() == {"CREATE": 4, "REUSE": 0, "CONFLICT": 0, "BLOCKED": 1}
        assert plan.applied is None
        assert snapshot() == before

    def test_failure_part_way_rolls_everything_back(self, world, monkeypatch):
        def explode(self, *args, **kwargs):
            raise ValidationError("synthetic failure while saving the mirror")

        monkeypatch.setattr(CommercialProductCode, "full_clean", explode)
        before = snapshot()
        with pytest.raises(ValidationError):
            apply_of(valid_manifest(), world)
        assert snapshot() == before
        assert not PartyMaster.objects.filter(legal_name=PARTY).exists()
        assert not ProductCode.objects.filter(pk=2990).exists()

    def test_failed_post_apply_verification_rolls_back(self, world, monkeypatch):
        import pricing_v4.services.rate_matrix_master_data as module

        real_execute = module._execute

        def execute_then_drop_a_row(plan, using):
            created = real_execute(plan, using)
            CommercialProductCode.objects.filter(code=NEW).delete()
            return created

        monkeypatch.setattr(module, "_execute", execute_then_drop_a_row)
        before = snapshot()
        with pytest.raises(MasterDataApplyError, match="Post-apply verification failed"):
            apply_of(valid_manifest(), world)
        assert snapshot() == before


# --------------------------------------------------------------------------- parties


@pytest.mark.django_db
class TestParties:
    def _party_only(self, **changes):
        manifest = valid_manifest()
        manifest["legacy_product_codes"] = []
        manifest["commercial_product_codes"] = []
        manifest["parties"][0].update(changes)
        return manifest

    def test_existing_party_with_role_and_identifier_is_reused(self, world):
        party = PartyMaster(legal_name=PARTY, entity_type="COMPANY", country_code="ZZ")
        party.save()
        role = PartyRole.objects.create(party=party, role_type="AGENT")
        PartyRoleIdentifier.objects.create(role=role, scheme="TAX_ID", value="SYNTH-000111")
        plan = plan_of(self._party_only())
        assert record(plan, "PartyMaster").action == "REUSE"
        assert PartyMaster.objects.filter(legal_name=PARTY).count() == 1

    def test_missing_role_is_added_to_existing_party_without_duplicating_it(self, world):
        party = PartyMaster(legal_name=PARTY, entity_type="COMPANY", country_code="ZZ")
        party.save()
        manifest = self._party_only()
        plan = plan_of(manifest)
        assert record(plan, "PartyMaster").action == "CREATE"
        assert record(plan, "PartyMaster").details[:2] == [f"PartyMaster REUSE {party.id}", "PartyRole AGENT CREATE"]
        applied = apply_of(manifest, world)
        assert applied.applied["rows_created"] == 2
        assert PartyMaster.objects.filter(legal_name=PARTY).count() == 1
        assert PartyRole.objects.get(party=party).role_type == "AGENT"

    def test_same_name_in_another_country_is_a_different_party(self, world):
        other = PartyMaster(legal_name=PARTY, entity_type="COMPANY", country_code="YY")
        other.save()
        assert record(plan_of(self._party_only()), "PartyMaster").action == "CREATE"

    @pytest.mark.parametrize(
        "existing_fields, reason",
        [
            ({"trade_name": "Other Trading Name"}, "differs in trade_name"),
            ({"entity_type": "AIRLINE"}, "differs in entity_type"),
            ({"is_active": False}, "is inactive"),
        ],
    )
    def test_incompatible_existing_party_conflicts(self, world, existing_fields, reason):
        fields = {"legal_name": PARTY, "entity_type": "COMPANY", "country_code": "ZZ", **existing_fields}
        PartyMaster(**fields).save()
        before = snapshot()
        plan = plan_of(self._party_only())
        target = record(plan, "PartyMaster")
        assert target.action == "CONFLICT"
        assert reason in " ".join(target.reasons)
        assert snapshot() == before

    def test_inactive_existing_role_conflicts(self, world):
        party = PartyMaster(legal_name=PARTY, entity_type="COMPANY", country_code="ZZ")
        party.save()
        PartyRole.objects.create(party=party, role_type="AGENT", is_active=False)
        target = record(plan_of(self._party_only()), "PartyMaster")
        assert target.action == "CONFLICT"
        assert "Existing AGENT role is inactive." in target.reasons

    def test_identifier_held_by_another_party_conflicts(self, world):
        other = PartyMaster(legal_name="Someone Else Ltd", entity_type="COMPANY", country_code="ZZ")
        other.save()
        role = PartyRole.objects.create(party=other, role_type="AGENT")
        PartyRoleIdentifier.objects.create(role=role, scheme="TAX_ID", value="SYNTH-000111")
        target = record(plan_of(self._party_only()), "PartyMaster")
        assert target.action == "CONFLICT"
        assert "already belongs to another party or role" in target.reasons[0]

    def test_duplicate_party_in_manifest_conflicts(self, world):
        manifest = self._party_only()
        manifest["parties"].append(copy.deepcopy(manifest["parties"][0]))
        plan = plan_of(manifest)
        assert [r.action for r in plan.records] == ["CREATE", "CONFLICT"]
        assert not plan.ready


# --------------------------------------------------------------------------- legacy ProductCodes


def _mutate_legacy(**changes):
    def apply(manifest):
        manifest["legacy_product_codes"][0].update(changes)
    return apply


LEGACY_CONFLICTS = [
    (_mutate_legacy(id=2981), "already belongs to"),
    (_mutate_legacy(id=1910), "Import ProductCode ID must be 2xxx"),
    (_mutate_legacy(default_unit="AWB"), "default_unit"),
    (_mutate_legacy(category="DESTINATION"), "category"),
    (_mutate_legacy(domain="INTERNATIONAL"), "domain"),
    (_mutate_legacy(is_gst_applicable=False), "STANDARD requires is_gst_applicable true"),
    (_mutate_legacy(gst_treatment="ZERO_RATED"), "is_gst_applicable true requires gst_treatment STANDARD"),
    (_mutate_legacy(percent_of_product_code="IMP-NOT-A-CODE"), "does not exist"),
]


@pytest.mark.django_db
class TestLegacyProductCodes:
    @pytest.mark.parametrize("mutate, reason", LEGACY_CONFLICTS, ids=[c[1][:28] for c in LEGACY_CONFLICTS])
    def test_invalid_new_product_code_conflicts(self, world, mutate, reason):
        manifest = valid_manifest()
        mutate(manifest)
        before = snapshot()
        plan = plan_of(manifest)
        target = record(plan, "ProductCode")
        assert target.action == "CONFLICT", plan.render_text()
        assert reason in " ".join(target.reasons)
        assert not plan.ready
        assert snapshot() == before

    def test_mirror_of_conflicting_new_code_is_blocked(self, world):
        manifest = valid_manifest()
        manifest["legacy_product_codes"][0]["default_unit"] = "AWB"
        plan = plan_of(manifest)
        mirror = record(plan, "CommercialProductCode", 1)
        assert mirror.action == "BLOCKED"
        assert "which is CONFLICT in this manifest" in mirror.reasons[0]

    def test_identical_existing_code_is_reused(self, world):
        apply_of(valid_manifest(), world)
        plan = plan_of(valid_manifest())
        assert record(plan, "ProductCode").action == "REUSE"
        assert ProductCode.objects.filter(code=NEW).count() == 1

    def test_existing_code_with_different_fields_is_never_altered(self, world):
        manifest = valid_manifest()
        manifest["legacy_product_codes"][0].update(id=2981, code=EXISTING, description="A changed description")
        manifest["commercial_product_codes"] = [_mirror(EXISTING, 2981)]
        before = snapshot()
        plan = plan_of(manifest)
        target = record(plan, "ProductCode")
        assert target.action == "CONFLICT"
        assert "differs in: description" in target.reasons[0]
        assert "never altered" in target.reasons[0]
        assert not apply_of(manifest, world).ready
        assert snapshot() == before
        assert ProductCode.objects.get(pk=2981).description == f"Synthetic {EXISTING}"

    def test_duplicate_new_code_in_manifest_conflicts(self, world):
        manifest = valid_manifest()
        manifest["legacy_product_codes"].append({**manifest["legacy_product_codes"][0], "id": 2991})
        plan = plan_of(manifest)
        assert record(plan, "ProductCode", 1).action == "CONFLICT"

    def test_percentage_code_may_depend_on_a_code_in_the_same_manifest(self, world):
        manifest = valid_manifest()
        manifest["commercial_product_codes"] = []
        manifest["legacy_product_codes"].append({
            **manifest["legacy_product_codes"][0], "id": 2991, "code": "IMP-SYNTH-PCT",
            "category": "SURCHARGE", "default_unit": "PERCENT", "percent_of_product_code": NEW,
        })
        plan = apply_of(manifest, world)
        assert plan.ready
        assert ProductCode.objects.get(pk=2991).percent_of_product_code_id == 2990


# --------------------------------------------------------------------------- commercial mirrors


def _mirror_only(*mirrors):
    manifest = valid_manifest()
    manifest["parties"] = []
    manifest["legacy_product_codes"] = []
    manifest["commercial_product_codes"] = list(mirrors)
    return manifest


@pytest.mark.django_db
class TestCommercialMirrors:
    @pytest.mark.parametrize(
        "mirror, reason",
        [
            (_mirror(EXISTING, 2981, gst="ZERO_RATED"), "does not match legacy ProductCode 2981"),
            (_mirror(RETIRED, 2983), "inactive or retired"),
            (_mirror("IMP-SYNTH-GHOST", 2997), "No legacy ProductCode has id 2997"),
            (_mirror("IMP-SYNTH-RENAMED", 2981, legacy_product_code={"id": 2981, "code": EXISTING}),
             "does not exactly mirror legacy code"),
            (_mirror(EXISTING, 2981, legacy_product_code={"id": 2981, "code": "IMP-WRONG"}), "has code"),
        ],
        ids=["gst-mismatch", "retired-legacy", "missing-legacy", "not-exact-mirror", "wrong-legacy-code"],
    )
    def test_invalid_mirror_conflicts(self, world, mirror, reason):
        before = snapshot()
        plan = plan_of(_mirror_only(mirror))
        target = record(plan, "CommercialProductCode")
        assert target.action == "CONFLICT", plan.render_text()
        assert reason in " ".join(target.reasons)
        assert snapshot() == before

    def test_unapproved_gst_is_blocked_not_created(self, world):
        manifest = _mirror_only(_mirror(ZERO, 2982, gst="ZERO_RATED", approved=False))
        plan = plan_of(manifest)
        target = record(plan, "CommercialProductCode")
        assert target.action == "BLOCKED"
        assert "ZERO_RATED is not commercially approved for loading" in target.reasons[0]
        before = snapshot()
        assert apply_of(manifest, world).applied is None
        assert snapshot() == before

    def test_approved_gst_creates(self, world):
        manifest = _mirror_only(_mirror(ZERO, 2982, gst="ZERO_RATED"))
        assert apply_of(manifest, world).applied["rows_created"] == 1
        assert CommercialProductCode.objects.get(code=ZERO).gst_treatment == "ZERO_RATED"

    def test_identical_existing_mirror_is_reused(self, world):
        apply_of(_mirror_only(_mirror(EXISTING, 2981)), world)
        plan = plan_of(_mirror_only(_mirror(EXISTING, 2981)))
        target = record(plan, "CommercialProductCode")
        assert target.action == "REUSE"
        assert "GST approval: SYNTHETIC-APPROVAL-1" in target.details

    def test_identical_existing_mirror_without_gst_approval_is_blocked_not_reused(self, world):
        apply_of(_mirror_only(_mirror(EXISTING, 2981)), world)
        manifest = _mirror_only(_mirror(EXISTING, 2981, approved=False))
        plan = plan_of(manifest)
        target = record(plan, "CommercialProductCode")
        assert target.action == "BLOCKED"
        assert "STANDARD is not commercially approved for loading" in target.reasons[0]
        assert not plan.ready

    def test_existing_zero_rated_mirror_without_gst_approval_is_blocked(self, world):
        apply_of(_mirror_only(_mirror(ZERO, 2982, gst="ZERO_RATED")), world)
        plan = plan_of(_mirror_only(_mirror(ZERO, 2982, gst="ZERO_RATED", approved=False)))
        assert record(plan, "CommercialProductCode").action == "BLOCKED"

    def test_unapproved_reuse_refuses_the_whole_apply(self, world):
        apply_of(_mirror_only(_mirror(EXISTING, 2981)), world)
        manifest = _mirror_only(_mirror(EXISTING, 2981, approved=False), _mirror(ZERO, 2982, gst="ZERO_RATED"))
        before = snapshot()
        plan = apply_of(manifest, world)
        assert plan.counts() == {"CREATE": 1, "REUSE": 0, "CONFLICT": 0, "BLOCKED": 1}
        assert plan.applied is None
        assert snapshot() == before
        assert not CommercialProductCode.objects.filter(code=ZERO).exists()

    def test_conflicting_existing_mirror_stays_conflict_when_unapproved(self, world):
        apply_of(_mirror_only(_mirror(EXISTING, 2981)), world)
        plan = plan_of(_mirror_only(_mirror(EXISTING, 2981, approved=False, category="CLEARANCE")))
        assert record(plan, "CommercialProductCode").action == "CONFLICT"

    @pytest.mark.parametrize("field, value", [("category", "CLEARANCE"), ("charge_basis_default", "PER_KG"), ("name", "Other")])
    def test_existing_mirror_with_different_fields_conflicts(self, world, field, value):
        apply_of(_mirror_only(_mirror(EXISTING, 2981)), world)
        before = snapshot()
        plan = plan_of(_mirror_only(_mirror(EXISTING, 2981, **{field: value})))
        target = record(plan, "CommercialProductCode")
        assert target.action == "CONFLICT"
        assert f"differs in: {field}" in target.reasons[0]
        assert snapshot() == before

    def test_legacy_code_already_mapped_under_another_commercial_code_conflicts(self, world):
        CommercialProductCode.objects.create(
            code="OTHER-CODE", name="Other", category="DESTINATION", gst_treatment="STANDARD",
            charge_basis_default="FLAT", legacy_product_code=world["existing"],
        )
        target = record(plan_of(_mirror_only(_mirror(EXISTING, 2981))), "CommercialProductCode")
        assert target.action == "CONFLICT"
        assert "already mapped to CommercialProductCode 'OTHER-CODE'" in target.reasons[0]

    def test_existing_mirror_mapped_to_another_legacy_code_conflicts(self, world):
        CommercialProductCode.objects.create(
            code=EXISTING, name=f"Synthetic {EXISTING}", category="DESTINATION", gst_treatment="STANDARD",
            charge_basis_default="FLAT", legacy_product_code=world["zero"],
        )
        target = record(plan_of(_mirror_only(_mirror(EXISTING, 2981))), "CommercialProductCode")
        assert target.action == "CONFLICT"

    def test_one_legacy_code_cannot_be_mirrored_twice_in_a_manifest(self, world):
        plan = plan_of(_mirror_only(_mirror(EXISTING, 2981), _mirror(EXISTING, 2981)))
        assert [r.action for r in plan.records] == ["CREATE", "CONFLICT"]
        assert not plan.ready


# --------------------------------------------------------------------------- command


@pytest.mark.django_db
class TestCommand:
    @staticmethod
    def _write(tmp_path, manifest):
        path = tmp_path / "master.json"
        path.write_text(text_of(manifest), encoding="utf-8")
        return str(path)

    def test_dry_run_is_the_default(self, world, tmp_path):
        before = snapshot()
        out = StringIO()
        call_command("load_rate_matrix_master_data", self._write(tmp_path, valid_manifest()), stdout=out)
        assert "Mode: DRY RUN" in out.getvalue()
        assert "Writes performed: 0" in out.getvalue()
        assert snapshot() == before

    def test_not_ready_exits_non_zero_after_printing(self, world, tmp_path):
        manifest = valid_manifest()
        manifest["commercial_product_codes"].append(_mirror(ZERO, 2982, gst="ZERO_RATED", approved=False))
        out = StringIO()
        with pytest.raises(CommandError, match="NOT READY"):
            call_command("load_rate_matrix_master_data", self._write(tmp_path, manifest), stdout=out)
        assert "[BLOCKED]" in out.getvalue()

    def test_apply_requires_operator_and_reviewed_hash(self, world, tmp_path):
        path = self._write(tmp_path, valid_manifest())
        before = snapshot()
        with pytest.raises(CommandError, match="requires --operator and --reviewed-sha256"):
            call_command("load_rate_matrix_master_data", path, apply=True)
        with pytest.raises(CommandError, match="requires --operator and --reviewed-sha256"):
            call_command("load_rate_matrix_master_data", path, apply=True, operator="synthetic-operator")
        with pytest.raises(CommandError, match="No active user"):
            call_command("load_rate_matrix_master_data", path, apply=True, operator="nobody", reviewed_sha256="0" * 64)
        with pytest.raises(CommandError, match="does not match the reviewed dry run"):
            call_command("load_rate_matrix_master_data", path, apply=True, operator="synthetic-operator", reviewed_sha256="0" * 64)
        assert snapshot() == before

    def test_operator_flags_rejected_without_apply(self, world, tmp_path):
        with pytest.raises(CommandError, match="only valid with --apply"):
            call_command("load_rate_matrix_master_data", self._write(tmp_path, valid_manifest()), operator="synthetic-operator")

    def test_apply_with_reviewed_hash(self, world, tmp_path):
        path = self._write(tmp_path, valid_manifest())
        dry = StringIO()
        call_command("load_rate_matrix_master_data", path, format="json", stdout=dry)
        sha = json.loads(dry.getvalue())["manifest_sha256"]
        out = StringIO()
        call_command(
            "load_rate_matrix_master_data", path, apply=True, operator="synthetic-operator",
            reviewed_sha256=sha, stdout=out,
        )
        assert "Mode: APPLY" in out.getvalue()
        assert "Applied by synthetic-operator: 6 row(s) created." in out.getvalue()
        assert PartyMaster.objects.filter(legal_name=PARTY).count() == 1

    def test_missing_file(self, world, tmp_path):
        with pytest.raises(CommandError, match="not found"):
            call_command("load_rate_matrix_master_data", str(tmp_path / "absent.json"))
