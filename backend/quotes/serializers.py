from rest_framework import serializers
from .models import Client, RateCard, Quote

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__' # This will include all fields from the Client model

class RateCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateCard
        fields = '__all__'

class QuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = '__all__'