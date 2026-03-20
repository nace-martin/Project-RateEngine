# backend/core/views.py

from typing import List, Dict

from django.db import connection
from django.db.models import Q  # Import Q for complex lookups
from django.db.utils import OperationalError
from rest_framework import generics, filters
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Airport, City, Country, Location
from .serializers import (
    LocationSearchSerializer,
    AirportSearchSerializer,
    CountryOptionSerializer,
    CityOptionSerializer,
)

def _format_location_display(location: Location, code: str) -> str:
    """
    Build a human-readable label for a Location object.
    """
    city_name = location.city.name if location.city else location.name
    country_code = None
    if location.country and location.country.code:
        country_code = location.country.code
    elif location.city and location.city.country:
        country_code = location.city.country.code

    if code and country_code:
        return f"{city_name} ({code}), {country_code}"
    if code:
        return f"{city_name} ({code})"
    if country_code:
        return f"{city_name}, {country_code}"
    return city_name


def _serialize_location(location: Location) -> Dict[str, str]:
    """
    Convert a Location object into the payload expected by the frontend combobox.
    """
    code = location.code
    if not code and location.airport:
        code = location.airport.iata_code
    if not code and location.port:
        code = location.port.unlocode
    if not code and location.city:
        code = location.city.name[:3].upper()

    display_name = _format_location_display(location, code or '')

    country_code = None
    if location.country and location.country.code:
        country_code = location.country.code
    elif location.city and location.city.country:
        country_code = location.city.country.code

    return {
        "id": str(location.id),
        "code": code or location.name[:3].upper(),
        "display_name": display_name,
        "country_code": country_code,
    }


def _build_location_results(query: str) -> List[Dict[str, str]]:
    """
    Shared helper that performs the location lookup using the canonical Location model.
    """
    results: List[Dict[str, str]] = []

    if len(query) >= 2:  # Start searching after 2 characters
        locations = (
            Location.objects.filter(is_active=True)
            .filter(
                Q(name__icontains=query)
                | Q(code__icontains=query)
                | Q(city__name__icontains=query)
                | Q(airport__iata_code__icontains=query)
                | Q(port__unlocode__icontains=query)
            )
            .select_related(
                'country',
                'city__country',
                'airport__city__country',
                'port__city__country',
            )
            .order_by('name')[:10]
        )

        results = [_serialize_location(location) for location in locations]
        results.sort(key=lambda x: x['display_name'])

    return results

class LocationV3SearchView(APIView):
    """
    V3 endpoint for locations, currently sharing logic with the legacy view.
    """

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '')
        results = _build_location_results(query)
        serializer = LocationSearchSerializer(results, many=True)
        return Response(serializer.data)


class HealthCheckAPIView(APIView):
    """
    Lightweight unauthenticated health endpoint for load balancers and Render.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        database_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError:
            database_ok = False

        status_code = 200 if database_ok else 503
        return Response(
            {
                "status": "ok" if database_ok else "degraded",
                "database": "ok" if database_ok else "unavailable",
            },
            status=status_code,
        )


class AirportSearchAPIView(generics.ListAPIView):
    """
    Provides a searchable list of airports.
    Usage: /api/v3/core/airports/search/?search=BNE
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AirportSearchSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['iata_code', 'name', 'city__name']

    def get_queryset(self):
        """
        Optimize the query by pre-fetching the related city and country.
        """
        return Airport.objects.select_related('city__country').all()


class CountryListAPIView(generics.ListAPIView):
    """
    Provides a searchable country reference list.
    Usage: /api/v3/core/countries/?q=au
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CountryOptionSerializer

    def get_queryset(self):
        query = (self.request.query_params.get('q') or '').strip()
        queryset = Country.objects.all().order_by('name')
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(code__icontains=query))
        return queryset[:250]


class CityListAPIView(generics.ListAPIView):
    """
    Provides a searchable city reference list, optionally scoped by country.
    Usage: /api/v3/core/cities/?country=PG&q=port
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CityOptionSerializer

    def get_queryset(self):
        query = (self.request.query_params.get('q') or '').strip()
        country_code = (self.request.query_params.get('country') or '').strip().upper()
        queryset = City.objects.select_related('country').all()
        if country_code:
            queryset = queryset.filter(country__code=country_code)
        if query:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by('name')[:250]
