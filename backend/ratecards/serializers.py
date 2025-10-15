from rest_framework import serializers
from .models import RatecardFile

class RatecardFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RatecardFile
        fields = '__all__'
