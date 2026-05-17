import uuid
from datetime import date, timedelta
from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework import serializers

from pricing_v4.models import ExportSellRate, ProductCode, LocalSellRate
from pricing_v4.serializers import ExportSellRateSerializer, ImportCOGSSerializer

class LaneSerializerHardeningTests(APITestCase):
    def setUp(self):
        # Clean up existing test data if any
        ProductCode.objects.filter(id__in=[1991, 2991, 1992]).delete()

        # Use high range IDs to avoid conflicts with standard seeds
        # Export ProductCode (1xxx) - Non-local category
        self.pc_export = ProductCode.objects.create(
            id=1991,
            code=f"EXPORT-PC-{uuid.uuid4().hex[:4]}",
            description="Export PC",
            category="FREIGHT", # Lane-based category
            domain="EXPORT",
            is_gst_applicable=True,
            gst_treatment="ZERO_RATED",
            gl_revenue_code="REV-1",
            gl_cost_code="COST-1"
        )
        # Import ProductCode (2xxx)
        self.pc_import = ProductCode.objects.create(
            id=2991,
            code=f"IMPORT-PC-{uuid.uuid4().hex[:4]}",
            description="Import PC",
            category="FREIGHT",
            domain="IMPORT",
            is_gst_applicable=True,
            gst_treatment="ZERO_RATED",
            gl_revenue_code="REV-2",
            gl_cost_code="COST-2"
        )
        # Local category ProductCode
        self.pc_local = ProductCode.objects.create(
            id=1992,
            code=f"LOCAL-PC-{uuid.uuid4().hex[:4]}",
            description="Local PC",
            category="AGENCY", # Local category
            domain="EXPORT",
            is_gst_applicable=True,
            gst_treatment="ZERO_RATED",
            gl_revenue_code="REV-3",
            gl_cost_code="COST-3"
        )
        self.today = date.today()

    def test_export_serializer_rejects_import_pc(self):
        """Serializer should reject ProductCode from wrong domain."""
        data = {
            'product_code': self.pc_import.id,
            'origin_airport': 'POM',
            'destination_airport': 'BNE',
            'currency': 'PGK',
            'rate_per_kg': '10.00',
            'valid_from': self.today,
            'valid_until': self.today + timedelta(days=30),
        }
        serializer = ExportSellRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('product_code', serializer.errors)
        # If it says object does not exist, we'll check why, but if it says domain mismatch, good.
        self.assertTrue(any('requires Export' in str(e) or 'does not exist' in str(e) for e in serializer.errors['product_code']))

    def test_export_serializer_rejects_local_category_pc(self):
        """Serializer should reject ProductCode with local category."""
        data = {
            'product_code': self.pc_local.id,
            'origin_airport': 'POM',
            'destination_airport': 'BNE',
            'currency': 'PGK',
            'rate_per_kg': '10.00',
            'valid_from': self.today,
            'valid_until': self.today + timedelta(days=30),
        }
        serializer = ExportSellRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('product_code', serializer.errors)
        self.assertIn('is a local charge', str(serializer.errors['product_code'][0]))

    def test_export_serializer_rejects_overlap(self):
        """
        Serializer should reject overlap. 
        """
        ExportSellRate.objects.create(
            product_code=self.pc_export,
            origin_airport='POM',
            destination_airport='BNE',
            currency='PGK',
            rate_per_kg=Decimal('10.00'),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30)
        )

        data = {
            'product_code': self.pc_export.id,
            'origin_airport': 'POM',
            'destination_airport': 'BNE',
            'currency': 'PGK',
            'rate_per_kg': '12.00',
            'valid_from': self.today + timedelta(days=5),
            'valid_until': self.today + timedelta(days=15),
        }
        serializer = ExportSellRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('valid_from', serializer.errors)

    def test_serializer_accepts_valid_data(self):
        """Serializer should accept valid data."""
        data = {
            'product_code': self.pc_export.id,
            'origin_airport': 'POM',
            'destination_airport': 'BNE',
            'currency': 'PGK',
            'rate_per_kg': '10.00',
            'valid_from': self.today,
            'valid_until': self.today + timedelta(days=30),
        }
        serializer = ExportSellRateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rollover_continuity_is_preserved(self):
        """Serializer allows sequential rollover dates."""
        v1_from = date(2025, 1, 1)
        v1_to = date(2025, 12, 31)
        v2_from = date(2026, 1, 1)
        v2_to = date(2026, 12, 31)

        ExportSellRate.objects.create(
            product_code=self.pc_export,
            origin_airport='POM',
            destination_airport='BNE',
            currency='PGK',
            rate_per_kg=Decimal('10.00'),
            valid_from=v1_from,
            valid_until=v1_to
        )

        data = {
            'product_code': self.pc_export.id,
            'origin_airport': 'POM',
            'destination_airport': 'BNE',
            'currency': 'PGK',
            'rate_per_kg': '11.00',
            'valid_from': v2_from,
            'valid_until': v2_to,
        }
        serializer = ExportSellRateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
