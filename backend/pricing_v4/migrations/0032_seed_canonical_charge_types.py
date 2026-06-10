from django.db import migrations


def seed_canonical_charge_types(apps, schema_editor):
    CanonicalChargeType = apps.get_model('pricing_v4', 'CanonicalChargeType')

    initial_types = [
        # category, code, name, description, mode_scope, direction_scope, sort_order
        ('FREIGHT', 'AIR_FREIGHT', 'Air Freight Surcharge', 'Base airport-to-airport freight carriage cost.', 'ANY', 'MAIN', 10),
        
        ('HANDLING', 'ORIGIN_HANDLING', 'Origin Handling Fee', 'Cargo handling, terminal fees at origin airport.', 'ANY', 'ORIGIN', 20),
        ('CARTAGE', 'ORIGIN_CARTAGE', 'Origin Cartage / Pickup', 'Land transport cargo pickup fee at origin.', 'ANY', 'ORIGIN', 30),
        
        ('HANDLING', 'DEST_HANDLING', 'Destination Handling Fee', 'Cargo handling, terminal fees at destination.', 'ANY', 'DESTINATION', 40),
        ('CARTAGE', 'DEST_DELIVERY', 'Destination Delivery', 'Land transport cargo delivery fee at destination.', 'ANY', 'DESTINATION', 50),
        
        ('CUSTOMS', 'CUSTOMS_CLEARANCE', 'Customs Clearance Fee', 'Filing customs entry with regulatory authorities.', 'ANY', 'ANY', 60),
        ('CUSTOMS', 'QUARANTINE_INSP', 'Quarantine Inspection', 'Bio-security processing and physical inspection fees.', 'ANY', 'ANY', 70),
        
        ('DOCUMENTATION', 'AWB_DOCUMENTATION', 'Air Waybill Fee', 'Fee for issuing/processing the primary AWB.', 'ANY', 'ANY', 80),
        ('DOCUMENTATION', 'ORIGIN_DOCS', 'Origin Documentation', 'Local origin certificates, permits, or documentation.', 'ANY', 'ORIGIN', 90),
        ('DOCUMENTATION', 'DEST_DOCS', 'Destination Documentation', 'Delivery orders, local terminal documentation fees.', 'ANY', 'DESTINATION', 100),
        
        ('SECURITY', 'SECURITY_SCREENING', 'Security Screening Fee', 'X-Ray, physical screening, or security surcharges.', 'ANY', 'ANY', 110),
        
        ('FUEL', 'AIRLINE_FUEL', 'Airline Fuel Surcharge', 'Fuel surcharge applied by air carrier (per kg).', 'ANY', 'MAIN', 120),
        ('FUEL', 'CARTAGE_FUEL', 'Cartage Fuel Surcharge', 'Fuel surcharge applied on cartage legs (flat/percent).', 'ANY', 'ANY', 130),
        ('FUEL', 'WAR_RISK', 'War Risk Surcharge', 'Emergency risk or carrier safety surcharges.', 'ANY', 'ANY', 140),
        
        ('ADMIN', 'ADMIN_COMMUNICATION', 'Agency & Admin Fee', 'General communication, file fees, or agency commissions.', 'ANY', 'ANY', 150),
        
        ('MISC', 'UNKNOWN_CHARGE', 'Unknown Charge Line', 'Unrecognized charge requiring classification.', 'ANY', 'ANY', 160),
        ('MISC', 'CONDITIONAL_STORAGE', 'Conditional Storage', 'Warehouse storage fees (conditional/accrual basis).', 'ANY', 'ANY', 170),
        ('MISC', 'CONDITIONAL_DEMURRAGE', 'Conditional Demurrage', 'Container/terminal detention fees (conditional).', 'ANY', 'ANY', 180),
    ]

    for category, code, name, description, mode_scope, direction_scope, sort_order in initial_types:
        CanonicalChargeType.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'category': category,
                'description': description,
                'mode_scope': mode_scope,
                'direction_scope': direction_scope,
                'is_system': True,
                'is_active': True,
                'sort_order': sort_order,
            }
        )


def reverse_seed_canonical_charge_types(apps, schema_editor):
    CanonicalChargeType = apps.get_model('pricing_v4', 'CanonicalChargeType')
    codes_to_remove = [
        'AIR_FREIGHT', 'ORIGIN_HANDLING', 'ORIGIN_CARTAGE', 'DEST_HANDLING', 'DEST_DELIVERY',
        'CUSTOMS_CLEARANCE', 'QUARANTINE_INSP', 'AWB_DOCUMENTATION', 'ORIGIN_DOCS', 'DEST_DOCS',
        'SECURITY_SCREENING', 'AIRLINE_FUEL', 'CARTAGE_FUEL', 'WAR_RISK', 'ADMIN_COMMUNICATION',
        'UNKNOWN_CHARGE', 'CONDITIONAL_STORAGE', 'CONDITIONAL_DEMURRAGE'
    ]
    CanonicalChargeType.objects.filter(code__in=codes_to_remove).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0031_canonicalchargetype_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_canonical_charge_types, reverse_seed_canonical_charge_types),
    ]
