from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from core.models import City, Country


class ReferenceDataAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='refdatatester',
            password='pass123',
            email='refdatatester@example.com',
        )
        self.client.force_authenticate(user=self.user)

        self.pg = Country.objects.create(code='PG', name='Papua New Guinea')
        self.au = Country.objects.create(code='AU', name='Australia')
        self.city_pom = City.objects.create(name='Port Moresby', country=self.pg)
        self.city_bne = City.objects.create(name='Brisbane', country=self.au)

    def test_country_list_returns_reference_options(self):
        url = reverse('core:country-list')
        response = self.client.get(url, {'q': 'au'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item['code'] == 'AU' for item in payload))
        self.assertFalse(any(item['code'] == 'PG' for item in payload))

    def test_city_list_can_be_scoped_by_country(self):
        url = reverse('core:city-list')
        response = self.client.get(url, {'country': 'PG'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        city_ids = {item['id'] for item in payload}
        self.assertIn(str(self.city_pom.id), city_ids)
        self.assertNotIn(str(self.city_bne.id), city_ids)

    def test_city_list_supports_partial_match(self):
        url = reverse('core:city-list')
        response = self.client.get(url, {'q': 'bris'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]['name'], 'Brisbane')
