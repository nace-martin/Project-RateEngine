from rest_framework import serializers
from .models import ServiceComponent

class ServiceComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceComponent
        fields = ['id', 'code', 'description', 'mode', 'leg', 'category', 'cost_type', 'cost_source']
