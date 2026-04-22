from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from parties.models import Company
from pricing_v4.models import (
    Agent,
    Carrier,
    DomesticCOGS,
    ExportSellRate,
    LocalCOGSRate,
    LocalSellRate,
    ProductCode,
)
from ratecards.models import PartnerRateCard


class UnifiedRateAdminAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(
            username='phase2-manager',
            password='testpass123',
            role='manager',
        )
        self.admin = User.objects.create_user(
            username='phase2-admin',
            password='testpass123',
            role='admin',
        )
        self.sales = User.objects.create_user(
            username='phase2-sales',
            password='testpass123',
            role='sales',
        )
        self.finance = User.objects.create_user(
            username='phase2-finance',
            password='testpass123',
            role='finance',
        )

        self.today = timezone.localdate()
        self.agent = Agent.objects.create(
            code='PH2-AG',
            name='Phase 2 Agent',
            country_code='AU',
            agent_type='ORIGIN',
        )
        self.carrier = Carrier.objects.create(
            code='PH2-CAR',
            name='Phase 2 Carrier',
            carrier_type='AIRLINE',
        )
        self.export_freight = ProductCode.objects.create(
            id=1107,
            code='EXP-FRT-PH2',
            description='Export Freight Phase 2',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate=Decimal('0.1000'),
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit=ProductCode.UNIT_KG,
        )
        self.export_cartage = ProductCode.objects.create(
            id=1160,
            code='EXP-CART-PH2',
            description='Export Cartage Phase 2',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_CARTAGE,
            is_gst_applicable=True,
            gst_rate=Decimal('0.1000'),
            gl_revenue_code='4101',
            gl_cost_code='5101',
            default_unit=ProductCode.UNIT_KG,
        )
        self.export_pickup = ProductCode.objects.create(
            id=1161,
            code='EXP-PICK-PH2',
            description='Export Pickup Phase 2',
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_CARTAGE,
            is_gst_applicable=True,
            gst_rate=Decimal('0.1000'),
            gl_revenue_code='4102',
            gl_cost_code='5102',
            default_unit=ProductCode.UNIT_KG,
        )
        self.domestic_freight = ProductCode.objects.create(
            id=3101,
            code='DOM-FRT-PH2',
            description='Domestic Freight Phase 2',
            domain=ProductCode.DOMAIN_DOMESTIC,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=True,
            gst_rate=Decimal('0.1000'),
            gl_revenue_code='4200',
            gl_cost_code='5200',
            default_unit=ProductCode.UNIT_KG,
        )

    def _export_sell_payload(self, **overrides):
        payload = {
            'product_code': self.export_freight.id,
            'origin_airport': 'POM',
            'destination_airport': 'SYD',
            'currency': 'AUD',
            'rate_per_kg': '4.2500',
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

    def _local_sell_payload(self, **overrides):
        payload = {
            'product_code': self.export_cartage.id,
            'location': 'POM',
            'direction': 'EXPORT',
            'payment_term': 'ANY',
            'currency': 'PGK',
            'rate_type': 'PER_KG',
            'amount': '5.0000',
            'is_additive': False,
            'additive_flat_amount': None,
            'min_charge': '15.00',
            'max_charge': None,
            'weight_breaks': None,
            'percent_of_product_code': None,
            'valid_from': str(self.today),
            'valid_until': str(self.today + timedelta(days=30)),
        }
        payload.update(overrides)
        return payload

    def _local_cogs_payload(self, **overrides):
        payload = {
            'product_code': self.export_cartage.id,
            'location': 'POM',
            'direction': 'EXPORT',
            'agent': self.agent.id,
            'carrier': None,
            'currency': 'PGK',
            'rate_type': 'PER_KG',
            'amount': '4.1000',
            'is_additive': False,
            'additive_flat_amount': None,
            'min_charge': '10.00',
            'max_charge': None,
            'weight_breaks': None,
            'percent_of_product_code': None,
            'valid_from': str(self.today),
            'valid_until': str(self.today + timedelta(days=30)),
        }
        payload.update(overrides)
        return payload

    def _domestic_cogs_payload(self, **overrides):
        payload = {
            'product_code': self.domestic_freight.id,
            'origin_zone': 'POM',
            'destination_zone': 'LAE',
            'agent': None,
            'carrier': self.carrier.id,
            'currency': 'PGK',
            'rate_per_kg': '2.5000',
            'rate_per_shipment': None,
            'min_charge': '35.00',
            'max_charge': None,
            'weight_breaks': None,
            'is_additive': False,
            'valid_from': str(self.today),
            'valid_until': str(self.today + timedelta(days=30)),
        }
        payload.update(overrides)
        return payload

    def test_finance_cannot_create_export_sell_rate(self):
        self.client.force_authenticate(self.finance)

        response = self.client.post('/api/v4/rates/export/', self._export_sell_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_export_sell_rejects_overlapping_effective_dates(self):
        ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport='POM',
            destination_airport='SYD',
            currency='AUD',
            rate_per_kg=Decimal('4.25'),
            min_charge=Decimal('100.00'),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=10),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            '/api/v4/rates/export/',
            self._export_sell_payload(
                valid_from=str(self.today + timedelta(days=5)),
                valid_until=str(self.today + timedelta(days=20)),
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('valid_from', response.data)

    def test_export_sell_retire_shortens_active_row(self):
        row = ExportSellRate.objects.create(
            product_code=self.export_freight,
            origin_airport='POM',
            destination_airport='SYD',
            currency='AUD',
            rate_per_kg=Decimal('4.25'),
            valid_from=self.today - timedelta(days=3),
            valid_until=self.today + timedelta(days=10),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(f'/api/v4/rates/export/{row.id}/retire/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row.refresh_from_db()
        self.assertEqual(row.valid_until, self.today - timedelta(days=1))

    def test_local_sell_any_payment_term_blocks_overlapping_specific_term(self):
        LocalSellRate.objects.create(
            product_code=self.export_cartage,
            location='POM',
            direction='EXPORT',
            payment_term='ANY',
            currency='PGK',
            rate_type='PER_KG',
            amount=Decimal('5.00'),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30),
        )
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            '/api/v4/rates/local-sell/',
            self._local_sell_payload(payment_term='PREPAID'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('valid_from', response.data)

    def test_local_sell_percent_requires_reference_product_code(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            '/api/v4/rates/local-sell/',
            self._local_sell_payload(
                product_code=self.export_pickup.id,
                rate_type='PERCENT',
                amount='12.5000',
                min_charge=None,
                percent_of_product_code=None,
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('percent_of_product_code', response.data)

    def test_local_cogs_requires_exactly_one_counterparty(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            '/api/v4/rates/local-cogs/',
            self._local_cogs_payload(carrier=self.carrier.id),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agent', response.data)

    def test_domestic_cogs_requires_pgk_currency(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            '/api/v4/rates/domestic-cogs/',
            self._domestic_cogs_payload(currency='AUD'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('currency', response.data)

    def test_legacy_v3_ratecard_endpoints_are_manager_admin_only(self):
        supplier = Company.objects.create(name='Legacy Supplier Phase 2', company_type='SUPPLIER')
        PartnerRateCard.objects.create(
            supplier=supplier,
            name='Legacy Phase 2 Card',
            currency_code='AUD',
            valid_from=self.today,
        )

        self.client.force_authenticate(self.sales)
        list_response = self.client.get('/api/v3/ratecards/')
        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)

        upload = SimpleUploadedFile('legacy.csv', b'header\nvalue\n', content_type='text/csv')
        upload_response = self.client.post(
            '/api/v3/ratecards/upload/',
            {'file': upload, 'supplier_id': str(supplier.id)},
            format='multipart',
        )
        self.assertEqual(upload_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.manager)
        manager_response = self.client.get('/api/v3/ratecards/')
        self.assertEqual(manager_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(manager_response.data), 1)
