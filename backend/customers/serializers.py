from rest_framework import serializers
from .models import Customer, Address

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ['id', 'address_line_1', 'address_line_2', 'city', 'state_province', 'postcode', 'country']
        validators = []

class CustomerListSerializer(serializers.ModelSerializer):
    """Serializer for listing customers, with a simple string for the address."""
    primary_address = serializers.StringRelatedField(allow_null=True)

    class Meta:
        model = Customer
        fields = ['id', 'company_name', 'primary_address', 'contact_person_name', 'audience_type']

class CustomerDetailSerializer(serializers.ModelSerializer):
    """Serializer for a single customer, with a full nested address object."""
    primary_address = AddressSerializer(allow_null=True, required=False)

    class Meta:
        model = Customer
        fields = ['id', 'company_name', 'primary_address', 'address_description', 'contact_person_name', 'contact_person_email', 'contact_person_phone', 'audience_type', 'created_at', 'updated_at']

    def create(self, validated_data):
        address_data = validated_data.pop('primary_address', None)
        address = None
        if address_data:
            address_data.pop('id', None)
            address, _ = Address.objects.get_or_create(**address_data)
        customer = Customer.objects.create(primary_address=address, **validated_data)
        return customer

    def update(self, instance, validated_data):
        if 'primary_address' in validated_data:
            address_data = validated_data.pop('primary_address')
            if address_data:
                address_data.pop('id', None)
                address, _ = Address.objects.get_or_create(**address_data)
                instance.primary_address = address
            else:
                instance.primary_address = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance