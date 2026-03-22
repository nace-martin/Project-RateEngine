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
    country_code = serializers.CharField(required=False, allow_null=True)


class AirportSearchSerializer(serializers.ModelSerializer):
    """
    Serializer for the Airport search, providing a useful label.
    """
    city_country = serializers.StringRelatedField(source='city')

    class Meta:
        model = Airport
        fields = ['iata_code', 'name', 'city_country']


class CountryOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ['code', 'name']


class CityOptionSerializer(serializers.ModelSerializer):
    country_code = serializers.CharField(source='country.code', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = City
        fields = ['id', 'name', 'country_code', 'country_name', 'display_name']

    def get_display_name(self, obj: City) -> str:
        return f"{obj.name}, {obj.country.code}"
