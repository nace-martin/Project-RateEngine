from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.fx_market_models import FxMarketRate
from core.models import FxSnapshot


class FxRefreshAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.finance_user = user_model.objects.create_user(
            username='finance-user',
            password='pass123',
            email='finance@example.com',
            role=user_model.ROLE_FINANCE,
        )
        self.sales_user = user_model.objects.create_user(
            username='sales-user',
            password='pass123',
            email='sales@example.com',
            role=user_model.ROLE_SALES,
        )
        self.url = reverse('core:fx-refresh')

    @patch('core.fx_views.call_command')
    def test_finance_user_can_trigger_fx_refresh(self, mock_call_command):
        def fake_refresh(*args, **kwargs):
            FxSnapshot.objects.create(
                as_of_timestamp=timezone.now(),
                source='bsp_html',
                rates={
                    'AUD': {'tt_buy': '2.7700', 'tt_sell': '2.8500'},
                    'USD': {'tt_buy': '3.8500', 'tt_sell': '3.9500'},
                },
                caf_percent='0.0',
                fx_buffer_percent='0.0',
            )

        mock_call_command.side_effect = fake_refresh
        self.client.force_authenticate(user=self.finance_user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['source'], 'bsp_html')
        mock_call_command.assert_called_once()
        self.assertIn('SGD:PGK', mock_call_command.call_args.kwargs['pairs'])
        self.assertIn('CNY:PGK', mock_call_command.call_args.kwargs['pairs'])
        self.assertNotIn('PGK:SGD', mock_call_command.call_args.kwargs['pairs'])

    def test_sales_user_cannot_trigger_fx_refresh(self):
        self.client.force_authenticate(user=self.sales_user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('core.fx_views.call_command')
    def test_refresh_returns_gateway_error_when_fetch_fails(self, mock_call_command):
        mock_call_command.side_effect = RuntimeError('BSP unavailable')
        self.client.force_authenticate(user=self.finance_user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn('BSP unavailable', response.json()['detail'])


class ManualFxUpdateAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.finance_user = user_model.objects.create_user(
            username='fx-finance',
            password='pass123',
            email='fx-finance@example.com',
            role=user_model.ROLE_FINANCE,
        )
        self.url = reverse('core:fx-manual-update')

    def test_manual_update_writes_market_fact_and_snapshot(self):
        self.client.force_authenticate(user=self.finance_user)

        response = self.client.post(
            self.url,
            {
                'rates': {
                    'AUD': {'tt_buy': '2.45000000', 'tt_sell': '2.52000000'},
                },
                'note': 'Finance confirmed BSP TT board',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rate = FxMarketRate.objects.get(
            base_currency='AUD',
            quote_currency='PGK',
            source='MANUAL',
        )
        self.assertEqual(rate.tt_buy_rate, Decimal('2.45000000'))
        self.assertEqual(rate.tt_sell_rate, Decimal('2.52000000'))

        snapshot = FxSnapshot.objects.get(id=response.json()['snapshot_id'])
        self.assertEqual(snapshot.rates['AUD']['tt_buy'], '2.45000000')
        self.assertEqual(snapshot.rates['AUD']['tt_sell'], '2.52000000')
        self.assertEqual(snapshot.rates['AUD']['source'], 'MANUAL')

    def test_manual_update_rejects_inverted_or_heuristic_orientation(self):
        self.client.force_authenticate(user=self.finance_user)

        response = self.client.post(
            self.url,
            {
                'rates': {
                    'AUD': {'tt_buy': '2.52000000', 'tt_sell': '2.45000000'},
                }
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FxMarketRate.objects.count(), 0)
