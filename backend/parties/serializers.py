# backend/parties/serializers.py

from rest_framework import serializers
from .models import Company

class CompanySearchSerializer(serializers.ModelSerializer):
    """
    A lightweight serializer for company search results.
    """
    class Meta:
        model = Company
        fields = ['id', 'name']
