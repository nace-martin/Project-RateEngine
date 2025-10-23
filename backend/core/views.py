# backend/core/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q # Import Q for complex lookups
from .models import City, Airport
from .serializers import LocationSearchSerializer

# --- ADD THIS VIEW ---
class LocationSearchAPIView(APIView):
    """
    Provides a search endpoint for locations (Cities and Airports).
    Accepts a query parameter `q`.
    e.g., /api/v2/locations/search/?q=POM
    """
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '')
        results = []

        if len(query) >= 2: # Start searching after 2 characters
            # Search Airports by IATA code or name
            airports = Airport.objects.filter(
                Q(iata_code__icontains=query) | Q(name__icontains=query) | Q(city__name__icontains=query)
            ).select_related('city', 'city__country')[:5] # Limit results

            # Search Cities by name
            cities = City.objects.filter(name__icontains=query).select_related('country')[:5] # Limit results

            # Format results
            for airport in airports:
                display = f"{airport.city.name if airport.city else airport.name} ({airport.iata_code}), {airport.city.country.code if airport.city else 'N/A'}"
                results.append({
                    "id": airport.iata_code,
                    "code": airport.iata_code,
                    "display_name": display,
                    "type": "airport"
                })

            # Avoid adding city if we already have its airport listed prominently
            airport_cities = {a.city.id for a in airports if a.city}
            for city in cities:
                if city.id not in airport_cities:
                    display = f"{city.name}, {city.country.code}"
                    # Try find associated airport code for display
                    main_airport = Airport.objects.filter(city=city).first()
                    if main_airport:
                       display = f"{city.name} ({main_airport.iata_code}), {city.country.code}"
                       code = main_airport.iata_code
                    else:
                        # Fallback if no specific airport linked - maybe less useful?
                        # Consider if we should only return airports/cities *with* IATA codes
                        code = city.name[:3].upper() # Less ideal fallback

                    results.append({
                        "id": str(city.id), # Use city ID here
                        "code": code, # Use airport code if possible, otherwise fallback
                        "display_name": display,
                        "type": "city"
                    })

            # Simple sort (could be refined)
            results.sort(key=lambda x: x['display_name'])

        serializer = LocationSearchSerializer(results, many=True)
        return Response(serializer.data)
