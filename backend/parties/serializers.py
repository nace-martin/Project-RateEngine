# backend/parties/serializers.py

from rest_framework import serializers
from .models import Company, Contact # Add Contact

class CompanySearchSerializer(serializers.ModelSerializer):
    """
    A lightweight serializer for company search results.
    """
    class Meta:
        model = Company
        fields = ['id', 'name']

# --- ADD THIS NEW SERIALIZER ---
class ContactSerializer(serializers.ModelSerializer):
    """Serializer for listing contacts."""
    class Meta:
        model = Contact
        fields = ['id', 'first_name', 'last_name', 'email'] # Adjust fields as needed