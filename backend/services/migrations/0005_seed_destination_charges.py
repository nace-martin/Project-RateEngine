from decimal import Decimal

from django.db import migrations


DESTINATION_COMPONENTS = [
    (
        "DEST_CUSTOMS_CLEARANCE",
        {
            "description": "Customs Clearance (Import)",
            "mode": "AIR",
            "leg": "DESTINATION",
            "category": "CUSTOMS",
            "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "base_pgk_cost": Decimal("300.00"),
            "unit": "SHIPMENT",
            "tax_rate": Decimal("0.00"),
        },
    ),
    (
        "DEST_AGENCY_FEE",
        {
            "description": "Destination Agency Fee",
            "mode": "AIR",
            "leg": "DESTINATION",
            "category": "ACCESSORIAL",
            "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "base_pgk_cost": Decimal("250.00"),
            "unit": "SHIPMENT",
            "tax_rate": Decimal("0.00"),
        },
    ),
    (
        "DEST_DOCUMENTATION",
        {
            "description": "Documentation Fee (Destination)",
            "mode": "AIR",
            "leg": "DESTINATION",
            "category": "DOCUMENTATION",
            "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "base_pgk_cost": Decimal("50.00"),
            "unit": "SHIPMENT",
            "tax_rate": Decimal("0.00"),
        },
    ),
    (
        "DEST_HANDLING_GENERAL",
        {
            "description": "Handling Fee - General Cargo",
            "mode": "AIR",
            "leg": "DESTINATION",
            "category": "HANDLING",
            "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "base_pgk_cost": Decimal("50.00"),
            "unit": "SHIPMENT",
            "tax_rate": Decimal("0.00"),
        },
    ),
    (
        "DEST_TERMINAL_ITF",
        {
            "description": "International Terminal Fee (ITF)",
            "mode": "AIR",
            "leg": "DESTINATION",
            "category": "HANDLING",
            "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "base_pgk_cost": Decimal("75.00"),
            "unit": "SHIPMENT",
            "tax_rate": Decimal("0.00"),
        },
    ),
    (
        "DEST_CARTAGE",
        {
            "description": "Cartage & Delivery",
            "mode": "AIR",
            "leg": "DESTINATION",
            "category": "LOCAL",
            "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "base_pgk_cost": Decimal("1.50"),
            "unit": "KG",
            "min_charge_pgk": Decimal("95.00"),
            "tax_rate": Decimal("0.00"),
        },
    ),
]


def seed_destination_charges(apps, schema_editor):
    ServiceComponent = apps.get_model("services", "ServiceComponent")
    IncotermRule = apps.get_model("services", "IncotermRule")

    component_instances = []
    for code, defaults in DESTINATION_COMPONENTS:
        component, _ = ServiceComponent.objects.update_or_create(
            code=code,
            defaults=defaults,
        )
        component_instances.append(component)

    rule, _ = IncotermRule.objects.get_or_create(
        mode="AIR",
        shipment_type="IMPORT",
        incoterm="DAP",
        defaults={
            "description": "Air import DAP destination services",
        },
    )

    existing_components = list(rule.service_components.all())
    for component in component_instances:
        if component not in existing_components:
            rule.service_components.add(component)


def reverse_destination_charges(apps, schema_editor):
    ServiceComponent = apps.get_model("services", "ServiceComponent")
    IncotermRule = apps.get_model("services", "IncotermRule")

    codes = [code for code, _ in DESTINATION_COMPONENTS]
    ServiceComponent.objects.filter(code__in=codes).delete()

    try:
        rule = IncotermRule.objects.get(
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="DAP",
        )
    except IncotermRule.DoesNotExist:
        return

    rule.service_components.remove(*rule.service_components.filter(code__in=codes))


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0004_alter_servicecomponent_description"),
    ]

    operations = [
        migrations.RunPython(
            seed_destination_charges,
            reverse_destination_charges,
        ),
    ]

