"""Pilot Gate B3B: Rate Matrix contract schema (spec v2.1 section 3.5.1).

Schema and model validation only. No resolver, loader, or pricing calculation.
"""

import datetime
import importlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import ProtectedError
from django.test import TransactionTestCase

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import ProductCode
from pricing_v4.rate_matrix_models import RateApplicability, RateLine, RateSheet

MIGRATION_MODULE = importlib.import_module(
    "pricing_v4.migrations.0044_pilot_rate_matrix_contract_schema"
)
MIGRATE_FROM = ("pricing_v4", "0043_commercial_terms_margin_semantics")
MIGRATE_TO = ("pricing_v4", "0044_pilot_rate_matrix_contract_schema")


@pytest.fixture
def loader_user(db):
    return get_user_model().objects.create_user(username="tariff-loader", password="x")


def _commercial_code(code="AF-FREIGHT", **overrides):
    values = {
        "code": code,
        "name": f"Test {code}",
        "category": CommercialProductCode.Category.FREIGHT,
        "gst_treatment": CommercialProductCode.GstTreatment.ZERO_RATED,
        "charge_basis_default": CommercialProductCode.ChargeBasis.PER_KG,
    }
    values.update(overrides)
    return CommercialProductCode.objects.create(**values)


def _legacy_code(pk=1001, code="EXP-FRT-AIR"):
    return ProductCode.objects.create(
        id=pk,
        code=code,
        description="Export Air Freight",
        domain=ProductCode.DOMAIN_EXPORT,
        category=ProductCode.CATEGORY_FREIGHT,
        is_gst_applicable=False,
        gst_rate="0.00",
        gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
        gl_revenue_code="4101",
        gl_cost_code="5101",
        default_unit=ProductCode.UNIT_KG,
    )


def _sheet_values(user, **overrides):
    values = {
        "name": "Pilot Tariff",
        "rate_type": RateSheet.RateType.SELL,
        "transport_mode": RateSheet.TransportMode.AIR,
        "currency_code": "PGK",
        "valid_from": datetime.date(2026, 1, 1),
        "version": 1,
        "source_reference": "TARIFF-REF-001",
        "created_by": user,
    }
    values.update(overrides)
    return values


def _line(sheet, **overrides):
    values = {
        "sheet": sheet,
        "product_code": _commercial_code(code=f"PC-{RateLine.objects.count()}"),
        "rate_basis": RateLine.RateBasis.PER_KG,
        "unit_rate": Decimal("0.2000"),
    }
    values.update(overrides)
    return RateLine(**values)


@pytest.mark.django_db
class TestGstClassification:
    def test_only_three_approved_classes_exist(self):
        assert list(CommercialProductCode.GstTreatment.values) == [
            "STANDARD",
            "ZERO_RATED",
            "EXEMPT",
        ]

    @pytest.mark.parametrize("value", ["STANDARD", "ZERO_RATED", "EXEMPT"])
    def test_approved_class_accepted(self, value):
        code = _commercial_code(code=f"GST-{value}", gst_treatment=value)
        code.full_clean()
        assert code.gst_treatment == value

    @pytest.mark.parametrize(
        "value", ["FREIGHT_EXPORT", "FREIGHT_IMPORT", "DOMESTIC_STANDARD", "OUT_OF_SCOPE", ""]
    )
    def test_other_class_rejected_by_model_and_database(self, value):
        candidate = CommercialProductCode(
            code=f"GST-BAD-{value or 'BLANK'}",
            name="Rejected",
            category=CommercialProductCode.Category.FREIGHT,
            gst_treatment=value,
            charge_basis_default=CommercialProductCode.ChargeBasis.FLAT,
        )
        with pytest.raises(ValidationError):
            candidate.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            candidate.save()


@pytest.mark.django_db
class TestLegacyProductCodeLink:
    def test_link_is_optional(self):
        first = _commercial_code(code="NO-LINK-1")
        second = _commercial_code(code="NO-LINK-2")
        assert first.legacy_product_code is None
        assert second.legacy_product_code is None

    def test_link_is_one_to_one(self):
        legacy = _legacy_code()
        mirror = _commercial_code(code="EXP-FRT-AIR", legacy_product_code=legacy)
        assert legacy.commercial_product_code == mirror

        with pytest.raises(IntegrityError), transaction.atomic():
            _commercial_code(code="EXP-FRT-AIR-DUP", legacy_product_code=legacy)

    def test_linked_legacy_code_is_protected(self):
        legacy = _legacy_code()
        _commercial_code(code="EXP-FRT-AIR", legacy_product_code=legacy)
        with pytest.raises(ProtectedError):
            legacy.delete()
        assert ProductCode.objects.filter(pk=legacy.pk).exists()


@pytest.mark.django_db
class TestRateSheetProvenance:
    def test_source_reference_is_trimmed(self, loader_user):
        sheet = RateSheet.objects.create(
            **_sheet_values(loader_user, source_reference="  PX tariff 2026/07  ")
        )
        sheet.refresh_from_db()
        assert sheet.source_reference == "PX tariff 2026/07"
        assert sheet.created_at is not None

    @pytest.mark.parametrize("value", ["", "   "])
    def test_source_reference_required(self, loader_user, value):
        candidate = RateSheet(**_sheet_values(loader_user, source_reference=value))
        with pytest.raises(ValidationError) as excinfo:
            candidate.full_clean()
        assert "source_reference" in excinfo.value.message_dict
        with pytest.raises(IntegrityError), transaction.atomic():
            candidate.save()

    def test_untrimmed_source_reference_rejected_by_database(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.filter(pk=sheet.pk).update(source_reference=" padded ")

    def test_created_by_required(self, loader_user):
        values = _sheet_values(loader_user)
        values.pop("created_by")
        candidate = RateSheet(**values)
        with pytest.raises(ValidationError) as excinfo:
            candidate.full_clean()
        assert "created_by" in excinfo.value.message_dict
        with pytest.raises(IntegrityError), transaction.atomic():
            candidate.save()

    def test_created_by_user_is_protected(self, loader_user):
        RateSheet.objects.create(**_sheet_values(loader_user))
        with pytest.raises(ProtectedError):
            loader_user.delete()

    def test_duplicate_name_and_version_rejected(self, loader_user):
        RateSheet.objects.create(**_sheet_values(loader_user))
        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.create(**_sheet_values(loader_user, currency_code="AUD"))

    def test_same_name_with_new_version_allowed(self, loader_user):
        RateSheet.objects.create(**_sheet_values(loader_user))
        second = RateSheet.objects.create(**_sheet_values(loader_user, version=2))
        assert second.version == 2


@pytest.mark.django_db
class TestAdditiveFlatAmount:
    def test_allowed_for_per_kg(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet, additive_flat_amount=Decimal("45.0000"))
        line.full_clean()
        line.save()
        line.refresh_from_db()
        assert line.additive_flat_amount == Decimal("45.0000")
        assert line.unit_rate == Decimal("0.2000")

    def test_optional_for_per_kg(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet)
        line.full_clean()
        line.save()
        assert line.additive_flat_amount is None

    @pytest.mark.parametrize(
        "basis",
        [RateLine.RateBasis.FLAT, RateLine.RateBasis.PER_CBM, RateLine.RateBasis.PER_UNIT],
    )
    def test_rejected_for_other_scalar_bases(self, loader_user, basis):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet, rate_basis=basis, additive_flat_amount=Decimal("45.0000"))
        with pytest.raises(ValidationError) as excinfo:
            line.full_clean()
        assert "additive_flat_amount" in excinfo.value.message_dict
        with pytest.raises(IntegrityError), transaction.atomic():
            line.save()

    def test_rejected_for_tiered_weight(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(
            sheet,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
            unit_rate=None,
            additive_flat_amount=Decimal("45.0000"),
        )
        with pytest.raises(ValidationError):
            line.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            line.save()

    def test_rejected_for_percentage(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        base = _commercial_code(code="PCT-BASE")
        line = _line(
            sheet,
            rate_basis=RateLine.RateBasis.PERCENTAGE,
            unit_rate=None,
            percentage_rate=Decimal("10.00"),
            percentage_basis_product_code=base,
            additive_flat_amount=Decimal("45.0000"),
        )
        with pytest.raises(ValidationError):
            line.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            line.save()

    def test_negative_rejected(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet, additive_flat_amount=Decimal("-1.0000"))
        with pytest.raises(ValidationError):
            line.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            line.save()


@pytest.mark.django_db
class TestPaymentTerm:
    @pytest.mark.parametrize("value", ["", "PREPAID", "COLLECT"])
    def test_valid_values_accepted_on_sell(self, loader_user, value):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet)
        line.save()
        applicability = RateApplicability(
            rate_line=line,
            direction=RateApplicability.Direction.IMPORT,
            payment_term=value,
        )
        applicability.full_clean()
        applicability.save()
        applicability.refresh_from_db()
        assert applicability.payment_term == value

    def test_defaults_to_blank(self, loader_user):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet)
        line.save()
        applicability = RateApplicability.objects.create(
            rate_line=line, direction=RateApplicability.Direction.EXPORT
        )
        assert applicability.payment_term == ""

    @pytest.mark.parametrize("value", ["ANY", "prepaid", "THIRD_PARTY"])
    def test_other_values_rejected(self, loader_user, value):
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))
        line = _line(sheet)
        line.save()
        applicability = RateApplicability(
            rate_line=line,
            direction=RateApplicability.Direction.IMPORT,
            payment_term=value,
        )
        with pytest.raises(ValidationError) as excinfo:
            applicability.full_clean()
        assert "payment_term" in excinfo.value.message_dict
        with pytest.raises(IntegrityError), transaction.atomic():
            applicability.save()

    @pytest.mark.parametrize("value", ["PREPAID", "COLLECT"])
    def test_buy_sheet_must_use_blank(self, loader_user, value):
        sheet = RateSheet.objects.create(
            **_sheet_values(loader_user, rate_type=RateSheet.RateType.BUY)
        )
        line = _line(sheet)
        line.save()
        applicability = RateApplicability(
            rate_line=line,
            direction=RateApplicability.Direction.IMPORT,
            payment_term=value,
        )
        with pytest.raises(ValidationError) as excinfo:
            applicability.full_clean()
        assert "payment_term" in excinfo.value.message_dict

    def test_buy_sheet_with_blank_accepted(self, loader_user):
        sheet = RateSheet.objects.create(
            **_sheet_values(loader_user, rate_type=RateSheet.RateType.BUY)
        )
        line = _line(sheet)
        line.save()
        applicability = RateApplicability(
            rate_line=line, direction=RateApplicability.Direction.IMPORT
        )
        applicability.full_clean()


@pytest.mark.django_db
class TestMigrationPreconditionFunction:
    """The guard, called directly against the current schema."""

    @staticmethod
    def _run():
        from django.apps import apps

        MIGRATION_MODULE.assert_rate_matrix_tables_empty(
            apps, SimpleNamespace(connection=connection)
        )

    def test_guards_all_six_tables(self):
        assert MIGRATION_MODULE.GUARDED_MODELS == (
            "CommercialProductCode",
            "CommercialChargeAlias",
            "RateSheet",
            "RateLine",
            "RateApplicability",
            "RateTier",
        )

    def test_passes_on_empty_tables(self):
        self._run()

    def test_refuses_and_leaves_rows_untouched(self, loader_user):
        code = _commercial_code(code="EXISTING")
        sheet = RateSheet.objects.create(**_sheet_values(loader_user))

        with pytest.raises(MIGRATION_MODULE.RateMatrixTablesNotEmpty) as excinfo:
            self._run()

        message = str(excinfo.value)
        assert "commercial_product_code=1" in message
        assert "rate_sheet=1" in message
        assert "No rows were changed" in message
        assert CommercialProductCode.objects.get(pk=code.pk).code == "EXISTING"
        assert RateSheet.objects.get(pk=sheet.pk).source_reference == "TARIFF-REF-001"


class RateMatrixContractMigrationTests(TransactionTestCase):
    """Migration 0044 applied and reversed through the real executor."""

    def tearDown(self):
        from django.apps import apps

        for model_name in reversed(MIGRATION_MODULE.GUARDED_MODELS):
            with connection.cursor() as cursor:
                cursor.execute(
                    f'DELETE FROM "{apps.get_model("pricing_v4", model_name)._meta.db_table}"'
                )
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()
        connection.close()

    @staticmethod
    def _columns(table):
        with connection.cursor() as cursor:
            return {
                column.name
                for column in connection.introspection.get_table_description(cursor, table)
            }

    @staticmethod
    def _is_applied():
        return MigrationRecorder.Migration.objects.filter(
            app=MIGRATE_TO[0], name=MIGRATE_TO[1]
        ).exists()

    @staticmethod
    def _migrate(target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def test_forward_and_reverse_on_empty_tables(self):
        self._migrate(MIGRATE_FROM)
        assert not self._is_applied()
        assert "source_reference" not in self._columns("rate_sheet")
        assert "additive_flat_amount" not in self._columns("rate_line")
        assert "payment_term" not in self._columns("rate_applicability")
        assert "legacy_product_code_id" not in self._columns("commercial_product_code")

        new_apps = self._migrate(MIGRATE_TO)
        assert self._is_applied()
        assert {"source_reference", "created_by_id", "created_at"} <= self._columns("rate_sheet")
        assert "additive_flat_amount" in self._columns("rate_line")
        assert "payment_term" in self._columns("rate_applicability")
        assert "legacy_product_code_id" in self._columns("commercial_product_code")
        for model_name in MIGRATION_MODULE.GUARDED_MODELS:
            assert new_apps.get_model("pricing_v4", model_name).objects.count() == 0

    def test_forward_refuses_non_empty_table_and_changes_nothing(self):
        old_apps = self._migrate(MIGRATE_FROM)
        OldCode = old_apps.get_model("pricing_v4", "CommercialProductCode")
        row = OldCode.objects.create(
            code="PRE-EXISTING",
            name="Pre-existing row",
            category="FREIGHT",
            gst_treatment="FREIGHT_EXPORT",
            charge_basis_default="PER_KG",
        )

        with self.assertRaises(MIGRATION_MODULE.RateMatrixTablesNotEmpty):
            self._migrate(MIGRATE_TO)

        assert not self._is_applied()
        assert "legacy_product_code_id" not in self._columns("commercial_product_code")
        assert "source_reference" not in self._columns("rate_sheet")
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT code, name, gst_treatment FROM "commercial_product_code" WHERE id = %s',
                [row.pk.hex if connection.vendor == "sqlite" else str(row.pk)],
            )
            assert cursor.fetchone() == ("PRE-EXISTING", "Pre-existing row", "FREIGHT_EXPORT")
            cursor.execute('SELECT COUNT(*) FROM "commercial_product_code"')
            assert cursor.fetchone()[0] == 1

    def test_reverse_refuses_non_empty_table_and_changes_nothing(self):
        new_apps = self._migrate(MIGRATE_TO)
        NewCode = new_apps.get_model("pricing_v4", "CommercialProductCode")
        row = NewCode.objects.create(
            code="LOADED-AFTER",
            name="Loaded after 0044",
            category="FREIGHT",
            gst_treatment="STANDARD",
            charge_basis_default="PER_KG",
        )

        with self.assertRaises(MIGRATION_MODULE.RateMatrixTablesNotEmpty):
            self._migrate(MIGRATE_FROM)

        assert self._is_applied()
        assert "legacy_product_code_id" in self._columns("commercial_product_code")
        assert "source_reference" in self._columns("rate_sheet")
        assert NewCode.objects.get(pk=row.pk).gst_treatment == "STANDARD"
