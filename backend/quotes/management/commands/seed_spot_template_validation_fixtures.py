import uuid
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SPEChargeLineDB,
    ExpectedChargeTemplate,
    ExpectedTemplateLine
)
from pricing_v4.models import CanonicalChargeType


class Command(BaseCommand):
    help = "Seed stable QA/test fixtures for SPOT template validation states."

    def handle(self, *args, **options):
        self.stdout.write("Seeding SPOT template validation fixtures...")

        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.filter(username="qa_analyst").first()
        if not user:
            user = User.objects.create_user(
                username="qa_analyst",
                email="qa@rateengine.com",
                password="ChangeMe123!",
                role="sales"
            )

        with transaction.atomic():
            # 1. Ensure CanonicalChargeTypes exist
            ct_air_freight, _ = CanonicalChargeType.objects.get_or_create(
                code="AIR_FREIGHT",
                defaults={"name": "Air Freight", "category": "TRANSPORT", "is_system": True}
            )
            ct_awb, _ = CanonicalChargeType.objects.get_or_create(
                code="AWB_DOCUMENTATION",
                defaults={"name": "AWB Documentation", "category": "DOCUMENTATION", "is_system": True}
            )
            ct_quarantine, _ = CanonicalChargeType.objects.get_or_create(
                code="QUARANTINE_INSP",
                defaults={"name": "Quarantine Inspection", "category": "STATUTORY", "is_system": True}
            )
            ct_storage, _ = CanonicalChargeType.objects.get_or_create(
                code="CONDITIONAL_STORAGE",
                defaults={"name": "Conditional Storage", "category": "STORAGE", "is_system": True}
            )

            # --- Scenario 1: PASSED ---
            t_passed, _ = ExpectedChargeTemplate.objects.update_or_create(
                name="QA Passed Template",
                defaults={
                    "is_active": True,
                    "mode": "EXPORT",
                    "transport_mode": "AIR",
                    "service_scope": "D2D",
                    "origin_country": "PG",
                    "destination_country": "SG",
                    "origin_code": "POM",
                    "destination_code": "SIN",
                }
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_passed,
                canonical_charge_type=ct_air_freight,
                defaults={"requirement_level": "REQUIRED", "expected_basis": "per_kg"}
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_passed,
                canonical_charge_type=ct_awb,
                defaults={"requirement_level": "REQUIRED", "expected_basis": "flat"}
            )

            # Find or create envelope for PASSED
            spe_passed = SpotPricingEnvelopeDB.objects.filter(spot_trigger_reason_code="QA_SEED_PASSED").first()
            if spe_passed:
                spe_passed.charge_lines.all().delete()
            else:
                spe_passed = SpotPricingEnvelopeDB.objects.create(
                    status="draft",
                    shipment_context_json={
                        "origin_code": "POM",
                        "destination_code": "SIN",
                        "origin_country": "PG",
                        "destination_country": "SG",
                        "service_scope": "D2D",
                        "transport_mode": "AIR"
                    },
                    spot_trigger_reason_code="QA_SEED_PASSED",
                    spot_trigger_reason_text="QA template validation passed",
                    expires_at=timezone.now() + timezone.timedelta(hours=72)
                )

            SPEChargeLineDB.objects.create(
                envelope=spe_passed,
                code="FRT_SPOT",
                description="Air Freight",
                amount=5.00,
                currency="USD",
                unit="per_kg",
                calculation_basis="per_kg",
                bucket="airfreight",
                canonical_charge_type=ct_air_freight,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )
            SPEChargeLineDB.objects.create(
                envelope=spe_passed,
                code="AWB_FEE",
                description="AWB Fee",
                amount=50.00,
                currency="USD",
                unit="flat",
                calculation_basis="flat",
                bucket="airfreight",
                canonical_charge_type=ct_awb,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )

            # --- Scenario 2: WARNINGS ---
            t_warnings, _ = ExpectedChargeTemplate.objects.update_or_create(
                name="QA Warnings Template",
                defaults={
                    "is_active": True,
                    "mode": "EXPORT",
                    "transport_mode": "AIR",
                    "service_scope": "D2D",
                    "origin_country": "PG",
                    "destination_country": "AU",
                    "origin_code": "POM",
                    "destination_code": "SYD",
                }
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_warnings,
                canonical_charge_type=ct_air_freight,
                defaults={"requirement_level": "REQUIRED", "expected_basis": "per_kg"}
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_warnings,
                canonical_charge_type=ct_awb,
                defaults={"requirement_level": "REQUIRED", "expected_basis": "flat"}
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_warnings,
                canonical_charge_type=ct_quarantine,
                defaults={"requirement_level": "EXCLUDED"}
            )

            spe_warnings = SpotPricingEnvelopeDB.objects.filter(spot_trigger_reason_code="QA_SEED_WARNINGS").first()
            if spe_warnings:
                spe_warnings.charge_lines.all().delete()
            else:
                spe_warnings = SpotPricingEnvelopeDB.objects.create(
                    status="draft",
                    shipment_context_json={
                        "origin_code": "POM",
                        "destination_code": "SYD",
                        "origin_country": "PG",
                        "destination_country": "AU",
                        "service_scope": "D2D",
                        "transport_mode": "AIR"
                    },
                    spot_trigger_reason_code="QA_SEED_WARNINGS",
                    spot_trigger_reason_text="QA template validation warnings",
                    expires_at=timezone.now() + timezone.timedelta(hours=72)
                )

            # AWB present, but AIR_FREIGHT is missing. Excluded QUARANTINE is present.
            SPEChargeLineDB.objects.create(
                envelope=spe_warnings,
                code="AWB_FEE",
                description="AWB Fee",
                amount=50.00,
                currency="USD",
                unit="flat",
                calculation_basis="flat",
                bucket="airfreight",
                canonical_charge_type=ct_awb,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )
            SPEChargeLineDB.objects.create(
                envelope=spe_warnings,
                code="QUARANTINE_FEE",
                description="Quarantine Fee",
                amount=120.00,
                currency="AUD",
                unit="flat",
                calculation_basis="flat",
                bucket="destination_charges",
                canonical_charge_type=ct_quarantine,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )

            # --- Scenario 3: REVIEW ---
            t_review, _ = ExpectedChargeTemplate.objects.update_or_create(
                name="QA Review Template",
                defaults={
                    "is_active": True,
                    "mode": "EXPORT",
                    "transport_mode": "AIR",
                    "service_scope": "D2D",
                    "origin_country": "PG",
                    "destination_country": "AU",
                    "origin_code": "POM",
                    "destination_code": "MEL",
                }
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_review,
                canonical_charge_type=ct_air_freight,
                defaults={"requirement_level": "REQUIRED", "expected_basis": "per_kg"}
            )
            ExpectedTemplateLine.objects.update_or_create(
                template=t_review,
                canonical_charge_type=ct_storage,
                defaults={"requirement_level": "CONDITIONAL", "expected_basis": "flat"}
            )

            spe_review = SpotPricingEnvelopeDB.objects.filter(spot_trigger_reason_code="QA_SEED_REVIEW").first()
            if spe_review:
                spe_review.charge_lines.all().delete()
            else:
                spe_review = SpotPricingEnvelopeDB.objects.create(
                    status="draft",
                    shipment_context_json={
                        "origin_code": "POM",
                        "destination_code": "MEL",
                        "origin_country": "PG",
                        "destination_country": "AU",
                        "service_scope": "D2D",
                        "transport_mode": "AIR"
                    },
                    spot_trigger_reason_code="QA_SEED_REVIEW",
                    spot_trigger_reason_text="QA template validation review",
                    expires_at=timezone.now() + timezone.timedelta(hours=72)
                )

            # Air freight present but flat (mismatch) + duplicate + conditional storage present
            SPEChargeLineDB.objects.create(
                envelope=spe_review,
                code="FRT_SPOT",
                description="Air Freight",
                amount=500.00,
                currency="USD",
                unit="flat",
                calculation_basis="flat",
                bucket="airfreight",
                canonical_charge_type=ct_air_freight,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )
            SPEChargeLineDB.objects.create(
                envelope=spe_review,
                code="FRT_SPOT_DUP",
                description="Air Freight Duplicated",
                amount=600.00,
                currency="USD",
                unit="flat",
                calculation_basis="flat",
                bucket="airfreight",
                canonical_charge_type=ct_air_freight,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )
            SPEChargeLineDB.objects.create(
                envelope=spe_review,
                code="STORAGE_FEE",
                description="Storage Fee",
                amount=150.00,
                currency="AUD",
                unit="flat",
                calculation_basis="flat",
                bucket="destination_charges",
                canonical_charge_type=ct_storage,
                source_reference="QA Reference",
                entered_by=user,
                entered_at=timezone.now()
            )

            # --- Scenario 4: TEMPLATE NOT FOUND ---
            spe_not_found = SpotPricingEnvelopeDB.objects.filter(spot_trigger_reason_code="QA_SEED_NO_TEMPLATE").first()
            if spe_not_found:
                spe_not_found.charge_lines.all().delete()
            else:
                spe_not_found = SpotPricingEnvelopeDB.objects.create(
                    status="draft",
                    shipment_context_json={
                        "origin_code": "LAE",
                        "destination_code": "HGU",
                        "origin_country": "PG",
                        "destination_country": "PG",
                        "service_scope": "D2D",
                        "transport_mode": "AIR"
                    },
                    spot_trigger_reason_code="QA_SEED_NO_TEMPLATE",
                    spot_trigger_reason_text="QA template not found",
                    expires_at=timezone.now() + timezone.timedelta(hours=72)
                )

        self.stdout.write(self.style.SUCCESS("SPOT template validation fixtures seeded successfully."))
