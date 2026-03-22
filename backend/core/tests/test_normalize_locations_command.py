from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Airport, City, Country, Currency, Location
from parties.models import Company, Contact
from quotes.models import Quote


class NormalizeLocationsCommandTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(code="PGK", name="Papua New Guinean Kina")
        self.country = Country.objects.create(code="PG", name="Papua New Guinea", currency=self.currency)
        self.city = City.objects.create(name="Lae", country=self.country)
        self.airport = Airport.objects.create(
            iata_code="LAE",
            name="Nadzab Tomodachi International Airport",
            city=self.city,
        )
        self.legacy_location = Location.objects.create(
            kind=Location.Kind.AIRPORT,
            code="LAE",
            name="Lae",
            country=self.country,
            city=self.city,
            airport=None,
            is_active=True,
        )
        self.canonical_location = Location.objects.get(airport=self.airport)
        self.customer = Company.objects.create(name="Normalize Test Customer")
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Lara",
            last_name="Loader",
            email="lara.loader@example.com",
        )
        self.quote = Quote.objects.create(
            customer=self.customer,
            contact=self.contact,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            incoterm="EXW",
            payment_term="COLLECT",
            service_scope="A2D",
            origin_location=self.legacy_location,
            destination_location=self.canonical_location,
            output_currency="PGK",
            status=Quote.Status.DRAFT,
        )

    def test_command_merges_orphan_airport_duplicate_and_repoints_quotes(self):
        stdout = StringIO()

        call_command("normalize_locations", stdout=stdout)

        self.quote.refresh_from_db()

        self.assertFalse(Location.objects.filter(id=self.legacy_location.id).exists())
        self.assertEqual(self.quote.origin_location_id, self.canonical_location.id)
        self.assertEqual(Location.objects.filter(code="LAE").count(), 1)
        self.assertIn("Merged and deleted orphan LAE", stdout.getvalue())
