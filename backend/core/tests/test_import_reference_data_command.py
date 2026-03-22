import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Airport, City, Country, Currency, Location


class ImportReferenceDataCommandTests(TestCase):
    def _write_csv(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_dry_run_does_not_write(self):
        currencies_csv = self._write_csv(
            "code,name,minor_units\n"
            "PGK,Papua New Guinean Kina,2\n"
            "AUD,Australian Dollar,2\n"
        )
        countries_csv = self._write_csv(
            "code,name,currency_code\n"
            "PG,Papua New Guinea,PGK\n"
            "AU,Australia,AUD\n"
        )
        cities_csv = self._write_csv(
            "country_code,name\n"
            "PG,Port Moresby\n"
            "AU,Brisbane\n"
        )
        airports_csv = self._write_csv(
            "iata_code,name,city_name,country_code\n"
            "POM,Port Moresby Jacksons Intl,Port Moresby,PG\n"
            "BNE,Brisbane Intl,Brisbane,AU\n"
        )

        call_command(
            "import_reference_data",
            currencies=currencies_csv,
            countries=countries_csv,
            cities=cities_csv,
            airports=airports_csv,
            dry_run=True,
            stdout=StringIO(),
        )

        self.assertEqual(Currency.objects.count(), 0)
        self.assertEqual(Country.objects.count(), 0)
        self.assertEqual(City.objects.count(), 0)
        self.assertEqual(Airport.objects.count(), 0)
        self.assertEqual(Location.objects.count(), 0)

    def test_import_creates_core_rows_and_location_overrides(self):
        currencies_csv = self._write_csv(
            "code,name,minor_units\n"
            "PGK,Papua New Guinean Kina,2\n"
            "AUD,Australian Dollar,2\n"
        )
        countries_csv = self._write_csv(
            "code,name,currency_code\n"
            "PG,Papua New Guinea,PGK\n"
            "AU,Australia,AUD\n"
        )
        cities_csv = self._write_csv(
            "country_code,name\n"
            "PG,Port Moresby\n"
            "AU,Brisbane\n"
        )
        airports_csv = self._write_csv(
            "iata_code,name,city_name,country_code\n"
            "POM,Port Moresby Jacksons Intl,Port Moresby,PG\n"
            "BNE,Brisbane Intl,Brisbane,AU\n"
        )
        locations_csv = self._write_csv(
            "kind,code,name,country_code,city_name,airport_iata,is_active,metadata_json\n"
            "AIRPORT,POM,Port Moresby Airport Override,PG,Port Moresby,POM,false,\"{\"\"source\"\":\"\"seed\"\"}\"\n"
            "CITY,POR,Port Moresby City,PG,Port Moresby,,true,\n"
        )

        call_command(
            "import_reference_data",
            currencies=currencies_csv,
            countries=countries_csv,
            cities=cities_csv,
            airports=airports_csv,
            locations=locations_csv,
            stdout=StringIO(),
        )

        self.assertEqual(Currency.objects.count(), 2)
        self.assertEqual(Country.objects.count(), 2)
        self.assertEqual(City.objects.count(), 2)
        self.assertEqual(Airport.objects.count(), 2)

        pg = Country.objects.get(code="PG")
        self.assertEqual(pg.currency.code, "PGK")

        airport_location = Location.objects.get(kind=Location.Kind.AIRPORT, code="POM")
        self.assertEqual(airport_location.name, "Port Moresby Airport Override")
        self.assertFalse(airport_location.is_active)
        self.assertEqual(airport_location.metadata, {"source": "seed"})
        self.assertEqual(airport_location.airport_id, "POM")

        city_location = Location.objects.get(kind=Location.Kind.CITY, code="POR")
        self.assertEqual(city_location.name, "Port Moresby City")
        self.assertEqual(city_location.city.name, "Port Moresby")
        self.assertEqual(city_location.country.code, "PG")
