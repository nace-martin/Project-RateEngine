from rest_framework import serializers
from .models import Customer

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'company_name', 'address_line_1', 'address_line_2', 'city', 'state_province', 'postcode', 'country', 'address_description', 'contact_person_name', 'contact_person_email', 'contact_person_phone', 'audience_type', 'created_at', 'updated_at']