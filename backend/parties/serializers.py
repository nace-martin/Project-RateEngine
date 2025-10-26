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

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'


# --- ADD THIS SERIALIZER ---
class ContactSerializer(serializers.ModelSerializer):
    """
    Serializer for the Contact model.
    """
    # Optionally display the company name instead of just the ID
    # company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = Contact
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'company', # Keep the company ID for reference
            # 'company_name', # Uncomment if you want the name displayed
        ]
        read_only_fields = ['id', 'company'] # Company is set via URL/view logic

# --- END ADD ---