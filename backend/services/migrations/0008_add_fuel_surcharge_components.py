# Data migration to create separate fuel surcharge components
# PICKUP_FUEL_ORG - linked to origin pickup
# PICKUP_FUEL_DST - linked to destination pickup (if destination pickup exists)

from django.db import migrations


def create_fuel_surcharge_components(apps, schema_editor):
    """
    Creates PICKUP_FUEL_ORG and PICKUP_FUEL_DST service components.
    
    Each fuel surcharge is linked to its respective base pickup component
    via percent_of_component FK.
    
    The actual percentage value comes from agent rate cards at runtime,
    not the static percent_value on the component.
    """
    ServiceComponent = apps.get_model('services', 'ServiceComponent')
    ServiceCode = apps.get_model('services', 'ServiceCode')
    
    # Find base components
    # For origin: use PICKUP or PKUP_ORG
    origin_pickup = ServiceComponent.objects.filter(
        code__in=['PICKUP', 'PKUP_ORG', 'PICKUP_ORG'],
        leg='ORIGIN'
    ).first()
    
    if not origin_pickup:
        # Try finding by code only
        origin_pickup = ServiceComponent.objects.filter(code='PICKUP').first()
    
    # For destination: use CARTAGE, DLVY_DST, PICKUP_DST, or similar
    dest_pickup = ServiceComponent.objects.filter(
        code__in=['CARTAGE', 'DLVY_DST', 'PICKUP_DST', 'DELIVERY'],
        leg='DESTINATION'
    ).first()
    
    # Get or create fuel surcharge service code
    fuel_service_code = ServiceCode.objects.filter(
        service_category='FUEL_SURCHARGE'
    ).first()
    
    # Create PICKUP_FUEL_ORG
    pickup_fuel_org, created = ServiceComponent.objects.get_or_create(
        code='PICKUP_FUEL_ORG',
        defaults={
            'description': 'Origin Pickup Fuel Surcharge',
            'mode': 'AIR',
            'leg': 'ORIGIN',
            'cost_type': 'COGS',
            'cost_source': 'PARTNER_RATECARD',
            'unit': 'SHIPMENT',
            'audience': 'BOTH',
            'percent_of_component': origin_pickup,
            'percent_value': None,  # Will be sourced from agent rate card
            'is_active': True,
            'service_code': fuel_service_code,
        }
    )
    
    if created:
        print(f"Created PICKUP_FUEL_ORG linked to {origin_pickup.code if origin_pickup else 'None'}")
    else:
        # Update existing
        pickup_fuel_org.percent_of_component = origin_pickup
        pickup_fuel_org.description = 'Origin Pickup Fuel Surcharge'
        pickup_fuel_org.save()
        print(f"Updated PICKUP_FUEL_ORG linked to {origin_pickup.code if origin_pickup else 'None'}")
    
    # Create PICKUP_FUEL_DST (only if destination pickup exists)
    if dest_pickup:
        pickup_fuel_dst, created = ServiceComponent.objects.get_or_create(
            code='PICKUP_FUEL_DST',
            defaults={
                'description': 'Destination Pickup Fuel Surcharge',
                'mode': 'AIR',
                'leg': 'DESTINATION',
                'cost_type': 'COGS',
                'cost_source': 'PARTNER_RATECARD',
                'unit': 'SHIPMENT',
                'audience': 'BOTH',
                'percent_of_component': dest_pickup,
                'percent_value': None,  # Will be sourced from agent rate card
                'is_active': True,
                'service_code': fuel_service_code,
            }
        )
        
        if created:
            print(f"Created PICKUP_FUEL_DST linked to {dest_pickup.code}")
        else:
            pickup_fuel_dst.percent_of_component = dest_pickup
            pickup_fuel_dst.description = 'Destination Pickup Fuel Surcharge'
            pickup_fuel_dst.save()
            print(f"Updated PICKUP_FUEL_DST linked to {dest_pickup.code}")
    else:
        print("No destination pickup component found - skipping PICKUP_FUEL_DST")
    
    # Optionally: Deactivate the old PICKUP_FUEL component
    old_fuel = ServiceComponent.objects.filter(code='PICKUP_FUEL').first()
    if old_fuel:
        old_fuel.is_active = False
        old_fuel.save()
        print("Deactivated old PICKUP_FUEL component")


def reverse_fuel_surcharge_components(apps, schema_editor):
    """Reverse: reactivate old PICKUP_FUEL and deactivate new ones."""
    ServiceComponent = apps.get_model('services', 'ServiceComponent')
    
    # Reactivate old
    old_fuel = ServiceComponent.objects.filter(code='PICKUP_FUEL').first()
    if old_fuel:
        old_fuel.is_active = True
        old_fuel.save()
    
    # Deactivate new
    ServiceComponent.objects.filter(
        code__in=['PICKUP_FUEL_ORG', 'PICKUP_FUEL_DST']
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0007_a2d_dap_rate'),
    ]

    operations = [
        migrations.RunPython(
            create_fuel_surcharge_components,
            reverse_code=reverse_fuel_surcharge_components,
        ),
    ]

