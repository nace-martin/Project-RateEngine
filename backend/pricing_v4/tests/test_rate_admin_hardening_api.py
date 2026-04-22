from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Currency
from core.tests.helpers import create_location
from pricing_v4.models import ExportSellRate, ProductCode, RateChangeLog


class RateAdminHardeningAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username='phase3-manager',
            password='testpass123',
            role='manager',
        )
        self.sales = User.objects.create_user(
            username='phase3-sales',
            password='testpass123',
            role='sales',
        )

        self.today = timezone.localdate()

        Currency.objects.create(code='AUD', name='Australian Dollar', minor_units=2)
        Currency.objects.create(code='PGK', name='Papua New Guinean Kina', minor_units=2)
        create_location(code='POM', name='Port Moresby')
        create_location(code='SYD', name='Sydney')

        self.export_freight = ProductCode.objects.create(
            id=1901,
            code='EXP-FRT-PH3',
            description='Export Freight Phase 3',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate=Decimal('0.1000'),
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit=ProductCode.UNIT_KG,
        )

    def _export_sell_payload(self, **overrides):
        payload = {
            'product_code': self.export_freight.id,
            'origin_airport': 'POM',
            'destination_airport': 'SYD',
            'currency': 'AUD',
            'rate_per_kg': '5.2500',
            'rate_per_shipment': None,
            'min_charge': '100.00',
            'max_charge': None,
            'percent_rate': None,
            'weight_breaks': None,
            'is_additive': False,
            'valid_from': str(self.today),
            'valid_until': str(self.today + timedelta(days=30)),
        }
        payload.update(overrides)
        return payload

    def test_create_writes_rate_change_log(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post('/api/v4/rates/export/', self._export_sell_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RateChangeLog.objects.count(), 1)
        log = RateChangeLog.objects.get()
        self.assertEqual(log.action, RateChangeLog.Action.CREATE)
        self.assertEqual(log.actor, self.manager)
        self.assertIsNotNone(log.lineage_id)
        self.assertIsNone(log.before_snapshot)
        self.assertEqual(log.after_snapshot['product_code'], self.export_freight.id)

    def test_update_writes_rate_change_log(self):
        row = ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport='POM',
            destination_airport='SYD',
            currency='AUD',
            rate_per_kg=Decimal('5.25'),
            min_charge=Decimal('100.00'),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.patch(
            f'/api/v4/rates/export/{row.id}/',
            {'min_charge': '125.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = RateChangeLog.objects.get()
        self.assertEqual(log.action, RateChangeLog.Action.UPDATE)
        self.assertIsNotNone(log.lineage_id)
        self.assertEqual(log.before_snapshot['min_charge'], '100.00')
        self.assertEqual(log.after_snapshot['min_charge'], '125.00')

    def test_revise_creates_new_row_shortens_prior_row_and_records_history(self):
        row = ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport='POM',
            destination_airport='SYD',
            currency='AUD',
            rate_per_kg=Decimal('5.25'),
            min_charge=Decimal('100.00'),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f'/api/v4/rates/export/{row.id}/revise/',
            self._export_sell_payload(
                rate_per_kg='5.9500',
                valid_from=str(self.today + timedelta(days=10)),
                valid_until=str(self.today + timedelta(days=45)),
                retire_previous=True,
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        row.refresh_from_db()
        revised = ExportSellRate.objects.exclude(pk=row.pk).get()
        self.assertIsNotNone(row.lineage_id)
        self.assertEqual(revised.lineage_id, row.lineage_id)
        self.assertEqual(revised.supersedes_rate_id, row.id)
        self.assertEqual(row.valid_until, self.today + timedelta(days=9))
        self.assertEqual(revised.valid_from, self.today + timedelta(days=10))
        self.assertEqual(RateChangeLog.objects.filter(action=RateChangeLog.Action.REVISE).count(), 2)
        self.assertEqual(
            set(RateChangeLog.objects.values_list('object_pk', flat=True)),
            {str(row.id), str(revised.id)},
        )

        history_response = self.client.get(f'/api/v4/rates/export/{row.id}/history/')
        self.assertEqual(history_response.status_code, status.HTTP_200_OK)
        self.assertEqual(history_response.data[0]['action'], RateChangeLog.Action.REVISE)
        self.assertEqual({entry['object_pk'] for entry in history_response.data}, {str(row.id), str(revised.id)})

    def test_history_endpoint_requires_manager_or_admin(self):
        row = ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport='POM',
            destination_airport='SYD',
            currency='AUD',
            rate_per_kg=Decimal('5.25'),
            min_charge=Decimal('100.00'),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30),
        )
        self.client.force_authenticate(self.sales)

        response = self.client.get(f'/api/v4/rates/export/{row.id}/history/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_dry_run_returns_preview_without_writing_rows(self):
        self.client.force_authenticate(self.manager)
        upload = SimpleUploadedFile(
            'rates.csv',
            (
                'rate_type,origin_code,destination_code,product_code,currency,amount,amount_basis,valid_from,valid_until\n'
                f'EXPORT,POM,SYD,{self.export_freight.id},AUD,5.25,PER_KG,{self.today},{self.today + timedelta(days=30)}\n'
            ).encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            '/api/v4/rates/upload/',
            {'file': upload, 'dry_run': 'true'},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['dry_run'])
        self.assertEqual(response.data['created_rows'], 1)
        self.assertEqual(len(response.data['preview_rows']), 1)
        self.assertEqual(ExportSellRate.objects.count(), 0)
