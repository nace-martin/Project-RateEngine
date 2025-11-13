# backend/core/views.py

from typing import List, Dict

from django.db.models import Q  # Import Q for complex lookups
from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import City, Airport
from .serializers import LocationSearchSerializer, AirportSearchSerializer

def _build_location_results(query: str) -> List[Dict[str, str]]:
    """
    Shared helper that performs the legacy location lookup logic.
    """
    results: List[Dict[str, str]] = []

    if len(query) >= 2:  # Start searching after 2 characters
        airports = Airport.objects.filter(
            Q(iata_code__icontains=query) | Q(name__icontains=query) | Q(city__name__icontains=query)
        ).select_related('city', 'city__country')[:5]  # Limit results

        cities = City.objects.filter(name__icontains=query).select_related('country')[:5]  # Limit results

        for airport in airports:
            city = airport.city
            country_code = city.country.code if city else 'N/A'
            city_name = city.name if city else airport.name
            display = f"{city_name} ({airport.iata_code}), {country_code}"
            results.append(
                {
                    "id": airport.iata_code,
                    "code": airport.iata_code,
                    "display_name": display,
                    "type": "airport",
                }
            )

        airport_cities = {a.city.id for a in airports if a.city}
        for city in cities:
            if city.id in airport_cities:
                continue

            display = f"{city.name}, {city.country.code}"
            main_airport = Airport.objects.filter(city=city).first()
            if main_airport:
                display = f"{city.name} ({main_airport.iata_code}), {city.country.code}"
                code = main_airport.iata_code
            else:
                code = city.name[:3].upper()

            results.append(
                {
                    "id": str(city.id),
                    "code": code,
                    "display_name": display,
                    "type": "city",
                }
            )

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
