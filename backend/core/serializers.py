# backend/core/serializers.py
from rest_framework import serializers
from .models import Currency, Country, City, Airport

class LocationSearchSerializer(serializers.Serializer):
    """
    Serializer for location search results (Cities/Airports).
    """
    id = serializers.CharField() # Could be City ID (UUID) or Airport IATA code (str)
    code = serializers.CharField() # City name or Airport IATA code
    display_name = serializers.CharField() # e.g., "Port Moresby (POM), PG" or "Brisbane (BNE), AU"
    type = serializers.CharField() # 'city' or 'airport'


class AirportSearchSerializer(serializers.ModelSerializer):
    """
    Serializer for the Airport search, providing a useful label.
    """
    city_country = serializers.StringRelatedField(source='city')

    class Meta:
        model = Airport
        fields = ['iata_code', 'name', 'city_country']
