from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from core.models import Country, City, Airport, Location


class LocationSearchViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='locationsearchtester',
            password='pass123',
            email='locationsearchtester@example.com',
        )
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(code='AU', name='Australia')
        self.city = City.objects.create(name='Brisbane', country=self.country)
        self.airport = Airport.objects.create(
            iata_code='BNE',
            name='Brisbane International',
            city=self.city,
        )
        self.airport_location = Location.objects.create(
            kind=Location.Kind.AIRPORT,
            name='Brisbane International Airport',
            code='BNE',
            country=self.country,
            city=self.city,
            airport=self.airport,
        )
        self.city_location = Location.objects.create(
            kind=Location.Kind.CITY,
            name=self.city.name,
            code='BRI',
            country=self.country,
            city=self.city,
        )

    def test_airport_search_returns_location_uuid(self):
        url = reverse('core:location-search-v3')
        response = self.client.get(url, {'q': 'BNE'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item['id'] for item in payload}

        self.assertIn(str(self.airport_location.id), ids)
        self.assertTrue(all(len(item['id']) == 36 for item in payload))

    def test_city_search_returns_city_location_uuid(self):
        url = reverse('core:location-search-v3')
        response = self.client.get(url, {'q': 'Bris'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ids = {item['id'] for item in payload}

        self.assertIn(str(self.city_location.id), ids)

    def test_location_string_prefers_city_name_for_airport_backed_locations(self):
        self.assertEqual(str(self.airport_location), "BNE - Brisbane")
