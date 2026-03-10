from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import Currency, Location
from pricing_v4.models import ExportSellRate, LocalSellRate, ProductCode
from pricing_v4.serializers import ExportSellRateSerializer, LocalSellRateSerializer
from pricing_v4.services.csv_importer import import_v4_rate_cards_csv


class RateTableSeparationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.create(code='PGK', name='Papua New Guinean Kina', minor_units=2)
        Currency.objects.create(code='AUD', name='Australian Dollar', minor_units=2)

        Location.objects.create(code='POM', name='Port Moresby')
        Location.objects.create(code='BNE', name='Brisbane')

        cls.export_freight = ProductCode.objects.create(
            id=1001,
            code='EXP-FRT-AIR',
            description='Export Air Freight',
            domain='EXPORT',
            category='FREIGHT',
            is_gst_applicable=False,
            gst_rate='0.00',
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit='KG',
        )
        cls.export_doc = ProductCode.objects.create(
            id=1010,
            code='EXP-DOC',
            description='Export Documentation Fee',
            domain='EXPORT',
            category='DOCUMENTATION',
            is_gst_applicable=False,
            gst_rate='0.00',
            gl_revenue_code='4200',
            gl_cost_code='5200',
            default_unit='SHIPMENT',
        )

    def test_csv_routes_export_local_charge_to_local_sell_rate(self):
        csv_content = (
            'rate_type,origin_code,destination_code,product_code,currency,amount,amount_basis,payment_term,valid_from,valid_until\n'
            'EXPORT,POM,BNE,1010,PGK,50,PER_SHIPMENT,ANY,2026-01-01,2026-12-31\n'
        )
        upload = SimpleUploadedFile('rates.csv', csv_content.encode('utf-8'), content_type='text/csv')

        result = import_v4_rate_cards_csv(upload)

        self.assertEqual(result.created_rows, 1)
        self.assertEqual(ExportSellRate.objects.count(), 0)
        self.assertEqual(LocalSellRate.objects.count(), 1)

        local = LocalSellRate.objects.get()
        self.assertEqual(local.product_code_id, self.export_doc.id)
        self.assertEqual(local.location, 'POM')
        self.assertEqual(local.direction, 'EXPORT')
        self.assertEqual(local.payment_term, 'ANY')

    def test_csv_keeps_export_freight_in_lane_table(self):
        csv_content = (
            'rate_type,origin_code,destination_code,product_code,currency,amount,amount_basis,valid_from,valid_until\n'
            'EXPORT,POM,BNE,1001,PGK,7.9,PER_KG,2026-01-01,2026-12-31\n'
        )
        upload = SimpleUploadedFile('rates.csv', csv_content.encode('utf-8'), content_type='text/csv')

        result = import_v4_rate_cards_csv(upload)

        self.assertEqual(result.created_rows, 1)
        self.assertEqual(ExportSellRate.objects.count(), 1)
        self.assertEqual(LocalSellRate.objects.count(), 0)

    def test_export_lane_serializer_rejects_local_product(self):
        serializer = ExportSellRateSerializer(
            data={
                'product_code': self.export_doc.id,
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': '50.00',
                'valid_from': date(2026, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('product_code', serializer.errors)

    def test_local_sell_serializer_rejects_freight_product(self):
        serializer = LocalSellRateSerializer(
            data={
                'product_code': self.export_freight.id,
                'location': 'POM',
                'direction': 'EXPORT',
                'payment_term': 'ANY',
                'currency': 'PGK',
                'rate_type': 'FIXED',
                'amount': '50.00',
                'valid_from': date(2026, 1, 1),
                'valid_until': date(2026, 12, 31),
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn('product_code', serializer.errors)
