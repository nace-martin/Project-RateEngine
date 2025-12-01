from django.test import TestCase
from core.models import Location
from pricing_v3.models import RateCard, Zone, ZoneMember
from pricing_v3.serializers import RateCardSerializer
from parties.models import Company

class AutoZoneTestCase(TestCase):
    def setUp(self):
        self.supplier = Company.objects.create(name="Test Supplier", company_type="SUPPLIER")
        self.loc_origin = Location.objects.create(code="BNE", name="Brisbane", kind="PORT")
        self.loc_dest = Location.objects.create(code="POM", name="Port Moresby", kind="PORT")

    def test_create_rate_card_with_locations(self):
        data = {
            "supplier": self.supplier.id,
            "mode": "AIR",
            "origin_location_id": self.loc_origin.id,
            "destination_location_id": self.loc_dest.id,
            "currency": "AUD",
            "scope": "CONTRACT",
            "priority": 100,
            "name": "Test Auto Zone Card",
            "valid_from": "2025-01-01"
        }

        serializer = RateCardSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        rate_card = serializer.save()

        # Verify Rate Card created
        self.assertIsNotNone(rate_card)
        self.assertEqual(rate_card.name, "Test Auto Zone Card")

        # Verify Zones created/linked
        self.assertIsNotNone(rate_card.origin_zone)
        self.assertIsNotNone(rate_card.destination_zone)

        # Verify Zone content
        origin_zone = rate_card.origin_zone
        self.assertTrue(origin_zone.name.startswith("Auto-Zone: BNE"))
        self.assertEqual(origin_zone.members.count(), 1)
        self.assertEqual(origin_zone.members.first().location, self.loc_origin)

        dest_zone = rate_card.destination_zone
        self.assertTrue(dest_zone.name.startswith("Auto-Zone: POM"))
        self.assertEqual(dest_zone.members.count(), 1)
        self.assertEqual(dest_zone.members.first().location, self.loc_dest)

    def test_reuse_existing_auto_zone(self):
        # Create a zone manually first
        zone = Zone.objects.create(code="AUTO-BNE-AIR", name="Auto-Zone: BNE", mode="AIR")
        ZoneMember.objects.create(zone=zone, location=self.loc_origin)

        data = {
            "supplier": self.supplier.id,
            "mode": "AIR",
            "origin_location_id": self.loc_origin.id,
            "destination_location_id": self.loc_dest.id,
            "currency": "AUD",
            "scope": "CONTRACT",
            "priority": 100,
            "name": "Test Reuse Zone",
            "valid_from": "2025-01-01"
        }

        serializer = RateCardSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        rate_card = serializer.save()

        # Should reuse the existing origin zone
        self.assertEqual(rate_card.origin_zone, zone)
        # Should create a new destination zone
        self.assertNotEqual(rate_card.destination_zone, zone)
