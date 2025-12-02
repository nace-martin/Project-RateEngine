# backend/core/serializers.py
from rest_framework import serializers
from .models import Currency, Country, City, Airport

class LocationSearchSerializer(serializers.Serializer):
    """
    Serializer for location search results (airports only).
    """
    id = serializers.CharField()
    code = serializers.CharField()
    display_name = serializers.CharField()


class AirportSearchSerializer(serializers.ModelSerializer):
    """
    Serializer for the Airport search, providing a useful label.
    """
    city_country = serializers.StringRelatedField(source='city')

    class Meta:
        model = Airport
        fields = ['iata_code', 'name', 'city_country']
