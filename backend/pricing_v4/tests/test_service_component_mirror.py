"""Pilot Gate B3H: controlled creation of one same-code ServiceComponent.

Every value here is synthetic test data. No real ProductCode, charge, or rate appears.
"""

import copy
import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.management.commands.sync_v4_components import infer_component_leg
from pricing_v4.models import ProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.service_component_mirror import (
    ComponentApplyError,
    apply_component_text,
    plan_component_text,
)
from services.models import ServiceComponent

CODE = "IMP-SYNTH-TERM"
OTHER = "IMP-SYNTH-OTHER"


def _legacy(pk, code, **extra):
    values = {
        "description": f"Synthetic {code}", "domain": ProductCode.DOMAIN_IMPORT,
        "category": ProductCode.CATEGORY_HANDLING, "is_gst_applicable": True, "gst_rate": "0.1000",
        "gst_treatment": "STANDARD", "gl_revenue_code": "4000", "gl_cost_code": "5000",
        "default_unit": ProductCode.UNIT_SHIPMENT,
    }
    values.update(extra)
    return ProductCode.objects.create(id=pk, code=code, **values)


def _mirror(legacy, **extra):
    values = {
        "code": legacy.code, "name": legacy.description, "category": "DESTINATION", "sub_category": "",
        "gst_treatment": "STANDARD", "charge_basis_default": "FLAT", "is_active": True, "legacy_product_code": legacy,
    }
    values.update(extra)
    return CommercialProductCode.objects.create(**values)


@pytest.fixture
def world(db):
    legacy = _legacy(2991, CODE)
    return {
        "legacy": legacy,
        "mirror": _mirror(legacy),
        "operator": get_user_model().objects.create_user(username="synthetic-operator", password="x"),
    }


def valid_manifest():
    return {
        "manifest_version": 1,
        "service_components": [
            {
                "code": CODE, "description": f"Synthetic {CODE}", "mode": "AIR",
                "leg": infer_component_leg(ProductCode.objects.get(code=CODE)), "category": "ACCESSORIAL",
                "cost_type": "COGS", "cost_source": "BASE_COST", "unit": "SHIPMENT", "audience": "BOTH",
                "is_active": True, "evidence": "Synthetic approval record 2030-01-01.",
            }
        ],
    }


def text_of(manifest):
    return json.dumps(manifest, indent=1)


def plan_of(manifest):
    return plan_component_text(text_of(manifest))


def apply_of(manifest, world, **kwargs):
    text = text_of(manifest)
    sha = kwargs.pop("reviewed_sha256", plan_component_text(text).manifest_sha256)
    return apply_component_text(text, operator=world["operator"], reviewed_sha256=sha, **kwargs)


GUARDED = (ProductCode, CommercialProductCode, RateSheet, RateLine, RateApplicability, RateTier)


def snapshot():
    return {
        "components": list(ServiceComponent.objects.order_by("code").values()),
        "counts": {m._meta.db_table: m.objects.count() for m in GUARDED},
        "legacy": list(ProductCode.objects.order_by("id").values()),
        "mirrors": list(CommercialProductCode.objects.order_by("code").values()),
    }


def _stored(**overrides):
    values = {
        "code": CODE, "description": f"Synthetic {CODE}", "mode": "AIR",
        "leg": infer_component_leg(ProductCode.objects.get(code=CODE)), "category": "ACCESSORIAL",
        "cost_type": "COGS", "cost_source": "BASE_COST", "unit": "SHIPMENT", "audience": "BOTH", "is_active": True,
    }
    values.update(overrides)
    return ServiceComponent.objects.create(**values)


# --------------------------------------------------------------------------- dry run


@pytest.mark.django_db
class TestDryRun:
    def test_plans_create_and_is_ready(self, world):
        plan = plan_of(valid_manifest())
        assert plan.ready
        assert plan.action == "CREATE"
        assert plan.counts() == {"CREATE": 1, "REUSE": 0, "CONFLICT": 0}
        assert plan.mode == "DRY_RUN"
        assert plan.evidence == "Synthetic approval record 2030-01-01."

    def test_performs_zero_writes(self, world):
        before = snapshot()
        plan_of(valid_manifest())
        assert snapshot() == before

    def test_repeated_dry_runs_are_identical(self, world):
        assert plan_of(valid_manifest()).render_json() == plan_of(valid_manifest()).render_json()

    def test_text_report_shows_evidence_and_zero_writes(self, world):
        text = plan_of(valid_manifest()).render_text()
        assert "Mode: DRY RUN" in text
        assert "ServiceComponent [CREATE] " + CODE in text
        assert "evidence: Synthetic approval record" in text
        assert "Writes performed: 0" in text


# --------------------------------------------------------------------------- strict manifest


@pytest.mark.django_db
class TestStrictManifest:
    def test_invalid_json(self, world):
        plan = plan_component_text("{not json")
        assert not plan.ready
        assert plan.manifest_errors[0]["code"] == "MANIFEST_NOT_STRICT_JSON"

    def test_duplicate_keys_rejected(self, world):
        plan = plan_component_text('{"manifest_version": 1, "manifest_version": 1, "service_components": []}')
        assert plan.manifest_errors[0]["code"] == "MANIFEST_NOT_STRICT_JSON"

    def test_unknown_and_missing_fields(self, world):
        manifest = valid_manifest()
        manifest["extra"] = 1
        del manifest["service_components"][0]["leg"]
        manifest["service_components"][0]["surprise"] = "x"
        plan = plan_of(manifest)
        codes = {(e["code"], e["path"]) for e in plan.manifest_errors}
        assert ("MANIFEST_UNKNOWN_FIELD", "$.extra") in codes
        assert plan.action is None
        assert not plan.ready

    @pytest.mark.parametrize("count", [0, 2])
    def test_exactly_one_component(self, world, count):
        manifest = valid_manifest()
        manifest["service_components"] = [copy.deepcopy(valid_manifest()["service_components"][0]) for _ in range(count)]
        plan = plan_of(manifest)
        assert [e["code"] for e in plan.manifest_errors] == ["SERVICE_COMPONENT_COUNT"]
        assert not plan.ready

    def test_unsupported_version(self, world):
        manifest = valid_manifest()
        manifest["manifest_version"] = 2
        assert plan_of(manifest).manifest_errors[0]["code"] == "MANIFEST_VERSION"

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("code", "imp-synth-term"), ("code", "X" * 21), ("code", " " + CODE), ("description", ""),
            ("mode", "WARP"), ("leg", "SIDEWAYS"), ("category", "MISC"), ("cost_type", "FREE"),
            ("cost_source", "GUESS"), ("unit", "FURLONG"), ("audience", "NOBODY"), ("is_active", "true"),
            ("evidence", ""),
        ],
    )
    def test_invalid_values_are_manifest_errors(self, world, key, value):
        manifest = valid_manifest()
        manifest["service_components"][0][key] = value
        plan = plan_of(manifest)
        assert plan.manifest_errors
        assert plan.action is None
        assert not plan.ready


# --------------------------------------------------------------------------- prerequisites


@pytest.mark.django_db
class TestPrerequisites:
    def test_unknown_product_code_conflicts(self, world):
        manifest = valid_manifest()
        manifest["service_components"][0]["code"] = "IMP-SYNTH-NOPE"
        plan = plan_of(manifest)
        assert plan.action == "CONFLICT"
        assert "No legacy ProductCode" in plan.reasons[0]

    def test_inactive_legacy_product_code_conflicts(self, world):
        ProductCode.objects.filter(pk=2991).update(is_active=False)
        plan = plan_of(valid_manifest())
        assert plan.action == "CONFLICT"
        assert any("inactive or retired" in r for r in plan.reasons)

    def test_missing_commercial_mirror_conflicts(self, world):
        world["mirror"].delete()
        plan = plan_of(valid_manifest())
        assert plan.action == "CONFLICT"
        assert any("No CommercialProductCode" in r for r in plan.reasons)

    def test_inactive_commercial_mirror_conflicts(self, world):
        CommercialProductCode.objects.filter(code=CODE).update(is_active=False)
        assert plan_of(valid_manifest()).action == "CONFLICT"

    def test_mirror_of_another_legacy_code_conflicts(self, world):
        other = _legacy(2992, OTHER)
        CommercialProductCode.objects.filter(code=CODE).update(legacy_product_code=other)
        assert plan_of(valid_manifest()).action == "CONFLICT"

    @pytest.mark.parametrize(
        ("key", "value"),
        [("mode", "SEA"), ("category", "CUSTOMS"), ("cost_type", "RATE_OFFER"), ("cost_source", "SURCHARGE"),
         ("unit", "KG"), ("is_active", False), ("leg", "ORIGIN"), ("description", "Something else")],
    )
    def test_fields_must_equal_the_sync_derivation(self, world, key, value):
        manifest = valid_manifest()
        manifest["service_components"][0][key] = value
        plan = plan_of(manifest)
        assert plan.action == "CONFLICT"
        assert any("sync_v4_components" in r and r.startswith(key) for r in plan.reasons)

    def test_description_used_by_another_component_conflicts(self, world):
        ServiceComponent.objects.create(
            code="OTHER-COMP", description=f"Synthetic {CODE} (V4)", mode="AIR", leg="DESTINATION",
        )
        manifest = valid_manifest()
        # Sync would add the suffix because the plain description is taken by another code.
        ServiceComponent.objects.create(
            code="TAKER", description=f"Synthetic {CODE}", mode="AIR", leg="DESTINATION",
        )
        manifest["service_components"][0]["description"] = f"Synthetic {CODE} (V4)"
        plan = plan_of(manifest)
        assert plan.action == "CONFLICT"
        assert any("already used by ServiceComponent 'OTHER-COMP'" in r for r in plan.reasons)


# --------------------------------------------------------------------------- audience


@pytest.mark.django_db
class TestAudience:
    """sync_v4_components never sets audience, so the canonical mirror state is the model default BOTH."""

    def test_both_is_ready(self, world):
        plan = plan_of(valid_manifest())
        assert valid_manifest()["service_components"][0]["audience"] == "BOTH"
        assert plan.ready
        assert plan.action == "CREATE"
        assert plan.fields["audience"] == "BOTH"

    @pytest.mark.parametrize("audience", ["BUY", "SELL"])
    def test_buy_and_sell_conflict(self, world, audience):
        manifest = valid_manifest()
        manifest["service_components"][0]["audience"] = audience
        before = snapshot()
        plan = plan_of(manifest)
        assert plan.action == "CONFLICT"
        assert not plan.ready
        assert any(r.startswith(f"audience '{audience}' must be 'BOTH'") for r in plan.reasons)
        assert snapshot() == before

    @pytest.mark.parametrize("audience", ["BUY", "SELL"])
    def test_apply_refuses_a_non_default_audience(self, world, audience):
        manifest = valid_manifest()
        manifest["service_components"][0]["audience"] = audience
        before = snapshot()
        plan = apply_of(manifest, world)
        assert not plan.ready
        assert plan.applied is None
        assert snapshot() == before

    def test_created_row_has_the_model_default_audience(self, world):
        apply_of(valid_manifest(), world)
        assert ServiceComponent.objects.get(code=CODE).audience == ServiceComponent._meta.get_field("audience").default == "BOTH"

    def test_later_sync_is_a_no_op_including_audience(self, world):
        apply_of(valid_manifest(), world)
        before = list(ServiceComponent.objects.filter(code=CODE).values())
        call_command("sync_v4_components", stdout=StringIO())
        after = list(ServiceComponent.objects.filter(code=CODE).values())
        assert after == before
        assert after[0]["audience"] == "BOTH"

    def test_sync_created_component_has_both(self, db):
        legacy = _legacy(2996, "IMP-SYNTH-AUD")
        _mirror(legacy)
        call_command("sync_v4_components", stdout=StringIO())
        assert ServiceComponent.objects.get(code="IMP-SYNTH-AUD").audience == "BOTH"


# --------------------------------------------------------------------------- existing rows


@pytest.mark.django_db
class TestExisting:
    def test_identical_stored_row_is_reused(self, world):
        _stored()
        plan = plan_of(valid_manifest())
        assert plan.action == "REUSE"
        assert plan.ready

    @pytest.mark.parametrize(
        "change",
        [
            {"leg": "ORIGIN"}, {"unit": "KG"}, {"is_active": False}, {"audience": "SELL"},
            {"base_pgk_cost": "12.50"}, {"cost_currency_type": "FCY"}, {"tax_rate": "0.1000"},
            {"tax_code": "GST"}, {"min_charge_pgk": "1.00"}, {"tiering_json": {"x": 1}},
        ],
    )
    def test_any_difference_conflicts_and_is_never_updated(self, world, change):
        _stored(**change)
        before = snapshot()
        plan = plan_of(valid_manifest())
        assert plan.action == "CONFLICT"
        assert "never updated" in plan.reasons[-1]
        assert snapshot() == before

    def test_apply_does_not_touch_a_differing_stored_row(self, world):
        _stored(base_pgk_cost="12.50")
        before = snapshot()
        plan = apply_of(valid_manifest(), world)
        assert not plan.ready
        assert plan.applied is None
        assert "Apply refused. Nothing was written." in plan.render_text()
        assert snapshot() == before


# --------------------------------------------------------------------------- apply


@pytest.mark.django_db
class TestApply:
    def test_creates_exactly_one_component_and_nothing_else(self, world):
        before = snapshot()
        plan = apply_of(valid_manifest(), world)
        assert plan.ready
        assert plan.mode == "APPLY"
        assert plan.applied == {"operator": "synthetic-operator", "rows_created": 1}
        after = snapshot()
        assert [c for c in after["components"] if c["code"] == CODE]
        assert len(after["components"]) == len(before["components"]) + 1
        # Everything outside ServiceComponent is byte-identical.
        assert {k: after[k] for k in ("counts", "legacy", "mirrors")} == {k: before[k] for k in ("counts", "legacy", "mirrors")}

    def test_stored_row_matches_the_manifest_and_model_defaults(self, world):
        apply_of(valid_manifest(), world)
        row = ServiceComponent.objects.get(code=CODE)
        assert (row.description, row.mode, row.category, row.cost_type, row.cost_source, row.unit, row.audience) == (
            f"Synthetic {CODE}", "AIR", "ACCESSORIAL", "COGS", "BASE_COST", "SHIPMENT", "BOTH",
        )
        assert row.is_active is True
        assert (row.base_pgk_cost, row.cost_currency_type, row.tax_rate) == (0, "PGK", 0)
        assert row.percent_of_component_id is None and row.service_code_id is None

    def test_second_apply_creates_zero_rows(self, world):
        apply_of(valid_manifest(), world)
        before = snapshot()
        plan = apply_of(valid_manifest(), world)
        assert plan.action == "REUSE"
        assert plan.applied == {"operator": "synthetic-operator", "rows_created": 0}
        assert snapshot() == before

    def test_dry_run_after_apply_reports_reuse(self, world):
        apply_of(valid_manifest(), world)
        assert plan_of(valid_manifest()).counts() == {"CREATE": 0, "REUSE": 1, "CONFLICT": 0}

    def test_other_existing_components_are_untouched(self, world):
        ServiceComponent.objects.create(code="UNRELATED", description="Unrelated", mode="AIR", leg="MAIN")
        before = list(ServiceComponent.objects.filter(code="UNRELATED").values())
        apply_of(valid_manifest(), world)
        assert list(ServiceComponent.objects.filter(code="UNRELATED").values()) == before

    def test_refuses_when_manifest_differs_from_reviewed_dry_run(self, world):
        before = snapshot()
        with pytest.raises(ComponentApplyError, match="does not match the reviewed dry run"):
            apply_of(valid_manifest(), world, reviewed_sha256="0" * 64)
        assert snapshot() == before

    def test_refuses_inactive_operator(self, world):
        world["operator"].is_active = False
        before = snapshot()
        with pytest.raises(ComponentApplyError, match="active operator"):
            apply_of(valid_manifest(), world)
        assert snapshot() == before

    def test_refuses_missing_operator(self, world):
        with pytest.raises(ComponentApplyError, match="active operator"):
            apply_component_text(text_of(valid_manifest()), operator=None, reviewed_sha256="0" * 64)

    def test_failure_while_saving_rolls_back(self, world, monkeypatch):
        def explode(self, *args, **kwargs):
            raise ValidationError("synthetic failure while saving the component")

        monkeypatch.setattr(ServiceComponent, "full_clean", explode)
        before = snapshot()
        with pytest.raises(ValidationError):
            apply_of(valid_manifest(), world)
        assert snapshot() == before
        assert not ServiceComponent.objects.filter(code=CODE).exists()

    def test_failed_post_apply_verification_rolls_back(self, world, monkeypatch):
        import pricing_v4.services.service_component_mirror as module

        real_plan = module._plan
        calls = {"n": 0}

        def plan_then_lie(text, plan, using):
            real_plan(text, plan, using)
            calls["n"] += 1
            if calls["n"] == 2:  # the verification pass
                ServiceComponent.objects.filter(code=CODE).delete()
                plan.manifest_errors.clear()
                plan.action = "CREATE"

        sha = plan_of(valid_manifest()).manifest_sha256
        monkeypatch.setattr(module, "_plan", plan_then_lie)
        before = snapshot()
        with pytest.raises(ComponentApplyError, match="Post-apply verification failed"):
            apply_component_text(text_of(valid_manifest()), operator=world["operator"], reviewed_sha256=sha)
        assert snapshot() == before


# --------------------------------------------------------------------------- sync compatibility


@pytest.mark.django_db
class TestSyncCompatibility:
    """The loader's row must be exactly what the broad sync would write, so a later sync is a no-op."""

    def test_later_sync_does_not_change_the_row(self, world):
        apply_of(valid_manifest(), world)
        before = list(ServiceComponent.objects.filter(code=CODE).values())
        call_command("sync_v4_components", stdout=StringIO())
        assert list(ServiceComponent.objects.filter(code=CODE).values()) == before

    @pytest.mark.parametrize(
        ("category", "domain", "unit"),
        [
            (ProductCode.CATEGORY_HANDLING, ProductCode.DOMAIN_IMPORT, ProductCode.UNIT_SHIPMENT),
            (ProductCode.CATEGORY_FREIGHT, ProductCode.DOMAIN_IMPORT, ProductCode.UNIT_SHIPMENT),
            (ProductCode.CATEGORY_DOCUMENTATION, ProductCode.DOMAIN_EXPORT, ProductCode.UNIT_SHIPMENT),
        ],
    )
    def test_derivation_equals_what_sync_writes(self, db, category, domain, unit):
        legacy = _legacy(2995, "IMP-SYNTH-SYNC", category=category, domain=domain, default_unit=unit)
        _mirror(legacy)
        call_command("sync_v4_components", stdout=StringIO())
        synced = ServiceComponent.objects.get(code="IMP-SYNTH-SYNC")
        ServiceComponent.objects.filter(code="IMP-SYNTH-SYNC").delete()
        manifest = {
            "manifest_version": 1,
            "service_components": [{
                "code": "IMP-SYNTH-SYNC", "description": synced.description, "mode": synced.mode,
                "leg": synced.leg, "category": synced.category, "cost_type": synced.cost_type,
                "cost_source": synced.cost_source, "unit": synced.unit, "audience": synced.audience,
                "is_active": synced.is_active, "evidence": "Synthetic.",
            }],
        }
        plan = plan_of(manifest)
        assert plan.action == "CREATE", plan.reasons
        user = get_user_model().objects.create_user(username="synthetic-sync-operator", password="x")
        apply_component_text(text_of(manifest), operator=user, reviewed_sha256=plan.manifest_sha256)
        created = ServiceComponent.objects.get(code="IMP-SYNTH-SYNC")
        for name in ("description", "mode", "leg", "category", "cost_type", "cost_source", "unit", "audience",
                     "is_active", "base_pgk_cost", "cost_currency_type", "tax_rate"):
            assert getattr(created, name) == getattr(synced, name), name


# --------------------------------------------------------------------------- command


@pytest.mark.django_db
class TestCommand:
    @staticmethod
    def _write(tmp_path, manifest):
        path = tmp_path / "component.json"
        path.write_text(text_of(manifest), encoding="utf-8")
        return str(path)

    def test_dry_run_is_the_default(self, world, tmp_path):
        before = snapshot()
        out = StringIO()
        call_command("load_service_component_mirror", self._write(tmp_path, valid_manifest()), stdout=out)
        assert "Mode: DRY RUN" in out.getvalue()
        assert "Writes performed: 0" in out.getvalue()
        assert snapshot() == before

    def test_not_ready_exits_non_zero_after_printing(self, world, tmp_path):
        manifest = valid_manifest()
        manifest["service_components"][0]["unit"] = "KG"
        out = StringIO()
        with pytest.raises(CommandError, match="NOT READY"):
            call_command("load_service_component_mirror", self._write(tmp_path, manifest), stdout=out)
        assert "[CONFLICT]" in out.getvalue()

    def test_apply_requires_operator_and_reviewed_hash(self, world, tmp_path):
        path = self._write(tmp_path, valid_manifest())
        before = snapshot()
        with pytest.raises(CommandError, match="requires --operator and --reviewed-sha256"):
            call_command("load_service_component_mirror", path, apply=True)
        with pytest.raises(CommandError, match="No active user"):
            call_command("load_service_component_mirror", path, apply=True, operator="nobody", reviewed_sha256="0" * 64)
        with pytest.raises(CommandError, match="does not match the reviewed dry run"):
            call_command(
                "load_service_component_mirror", path, apply=True, operator="synthetic-operator",
                reviewed_sha256="0" * 64,
            )
        assert snapshot() == before

    def test_operator_flags_rejected_without_apply(self, world, tmp_path):
        with pytest.raises(CommandError, match="only valid with --apply"):
            call_command(
                "load_service_component_mirror", self._write(tmp_path, valid_manifest()),
                operator="synthetic-operator",
            )

    def test_apply_with_reviewed_hash(self, world, tmp_path):
        path = self._write(tmp_path, valid_manifest())
        dry = StringIO()
        call_command("load_service_component_mirror", path, format="json", stdout=dry)
        report = json.loads(dry.getvalue())
        assert report["writes_performed"] == 0
        out = StringIO()
        call_command(
            "load_service_component_mirror", path, apply=True, operator="synthetic-operator",
            reviewed_sha256=report["manifest_sha256"], stdout=out,
        )
        assert "Applied by synthetic-operator: 1 row(s) created." in out.getvalue()
        assert ServiceComponent.objects.filter(code=CODE).count() == 1

    def test_missing_file(self, world, tmp_path):
        with pytest.raises(CommandError, match="not found"):
            call_command("load_service_component_mirror", str(tmp_path / "absent.json"))
