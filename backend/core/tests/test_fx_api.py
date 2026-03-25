from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

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
        self.assertIn('PGK:SGD', mock_call_command.call_args.kwargs['pairs'])
        self.assertIn('PGK:CNY', mock_call_command.call_args.kwargs['pairs'])

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
