from rest_framework import serializers
from .models import RatecardFile, Rate

class RatecardFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RatecardFile
        fields = '__all__'

class RateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rate
        fields = '__all__'
