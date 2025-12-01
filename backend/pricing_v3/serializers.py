from rest_framework import serializers
from .models import (
    Zone, ZoneMember, RateCard, RateLine, RateBreak,
    QuoteSpotRate, QuoteSpotCharge, LocalFeeRule
)
from core.models import Location
from services.models import ServiceComponent

class ZoneMemberSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)
    location_code = serializers.CharField(source='location.code', read_only=True)

    class Meta:
        model = ZoneMember
        fields = ['id', 'zone', 'location', 'location_name', 'location_code']

class ZoneSerializer(serializers.ModelSerializer):
    members = ZoneMemberSerializer(many=True, read_only=True)
    member_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Location.objects.all(), source='members'
    )

    class Meta:
        model = Zone
        fields = ['id', 'code', 'name', 'mode', 'partner', 'members', 'member_ids']
    
    def create(self, validated_data):
        members_data = validated_data.pop('members', [])
        zone = Zone.objects.create(**validated_data)
        for location in members_data:
            ZoneMember.objects.create(zone=zone, location=location)
        return zone

    def update(self, instance, validated_data):
        members_data = validated_data.pop('members', None)
        instance = super().update(instance, validated_data)
        
        if members_data is not None:
            instance.members.all().delete()
            for location in members_data:
                ZoneMember.objects.create(zone=instance, location=location)
        return instance

class RateBreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateBreak
        fields = ['id', 'line', 'from_value', 'to_value', 'rate']

class RateLineSerializer(serializers.ModelSerializer):
    breaks = RateBreakSerializer(many=True, required=False)
    component_code = serializers.CharField(source='component.code', read_only=True)

    class Meta:
        model = RateLine
        fields = [
            'id', 'card', 'component', 'component_code', 'method', 'unit', 
            'min_charge', 'percent_value', 'percent_of_component', 
            'description', 'breaks'
        ]

    def create(self, validated_data):
        breaks_data = validated_data.pop('breaks', [])
        rate_line = RateLine.objects.create(**validated_data)
        for break_data in breaks_data:
            RateBreak.objects.create(line=rate_line, **break_data)
        return rate_line

    def update(self, instance, validated_data):
        breaks_data = validated_data.pop('breaks', None)
        instance = super().update(instance, validated_data)
        
        if breaks_data is not None:
            instance.breaks.all().delete()
            for break_data in breaks_data:
                RateBreak.objects.create(line=instance, **break_data)
        return instance

class RateCardSerializer(serializers.ModelSerializer):
    lines = RateLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    origin_zone_name = serializers.CharField(source='origin_zone.name', read_only=True)
    destination_zone_name = serializers.CharField(source='destination_zone.name', read_only=True)

    # Virtual fields for simplified UI
    origin_location_id = serializers.UUIDField(write_only=True, required=False)
    destination_location_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = RateCard
        fields = [
            'id', 'supplier', 'supplier_name', 'mode', 
            'origin_zone', 'origin_zone_name', 
            'destination_zone', 'destination_zone_name',
            'origin_location_id', 'destination_location_id',
            'currency', 'scope', 'valid_from', 'valid_until', 
            'priority', 'name', 'created_at', 'updated_at', 'lines'
        ]
        extra_kwargs = {
            'origin_zone': {'required': False},
            'destination_zone': {'required': False},
        }

    def validate(self, data):
        # Ensure either Zone OR Location is provided for Origin
        if not data.get('origin_zone') and not data.get('origin_location_id'):
            raise serializers.ValidationError("Either origin_zone or origin_location_id must be provided.")
        
        # Ensure either Zone OR Location is provided for Destination
        if not data.get('destination_zone') and not data.get('destination_location_id'):
            raise serializers.ValidationError("Either destination_zone or destination_location_id must be provided.")
            
        return data

    def _get_or_create_auto_zone(self, location_id, mode):
        """
        Finds a zone that contains ONLY this location, or creates one.
        """
        location = Location.objects.get(id=location_id)
        
        # Try to find existing single-member zone for this location
        # We filter by zones that have this member, and then check count
        candidates = Zone.objects.filter(members__location_id=location_id)
        
        for zone in candidates:
            if zone.members.count() == 1:
                return zone
        
        # Create new auto-zone
        zone_name = f"Auto-Zone: {location.code}"
        zone_code = f"AUTO-{location.code}-{mode}"
        
        # Ensure code uniqueness
        counter = 1
        original_code = zone_code
        while Zone.objects.filter(code=zone_code).exists():
            zone_code = f"{original_code}-{counter}"
            counter += 1
            
        zone = Zone.objects.create(
            code=zone_code,
            name=zone_name,
            mode=mode
        )
        ZoneMember.objects.create(zone=zone, location=location)
        return zone

    def create(self, validated_data):
        origin_loc_id = validated_data.pop('origin_location_id', None)
        dest_loc_id = validated_data.pop('destination_location_id', None)
        mode = validated_data.get('mode')

        if origin_loc_id:
            validated_data['origin_zone'] = self._get_or_create_auto_zone(origin_loc_id, mode)
            
        if dest_loc_id:
            validated_data['destination_zone'] = self._get_or_create_auto_zone(dest_loc_id, mode)

        return super().create(validated_data)

class QuoteSpotChargeSerializer(serializers.ModelSerializer):
    component_code = serializers.CharField(source='component.code', read_only=True)
    component_description = serializers.CharField(source='component.description', read_only=True)

    class Meta:
        model = QuoteSpotCharge
        fields = [
            'id', 'spot_rate', 'component', 'component_code', 'component_description',
            'method', 'unit', 'rate', 'min_charge', 
            'percent_value', 'percent_of_component', 'description'
        ]

class QuoteSpotRateSerializer(serializers.ModelSerializer):
    charges = QuoteSpotChargeSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    origin_location_name = serializers.CharField(source='origin_location.name', read_only=True)
    destination_location_name = serializers.CharField(source='destination_location.name', read_only=True)

    class Meta:
        model = QuoteSpotRate
        fields = [
            'id', 'quote', 'supplier', 'supplier_name',
            'origin_location', 'origin_location_name',
            'destination_location', 'destination_location_name',
            'mode', 'currency', 'valid_until', 'notes', 
            'created_at', 'charges'
        ]
