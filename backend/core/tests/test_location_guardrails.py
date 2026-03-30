from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from core.models import Country, Location
from core.tests.helpers import create_location


class LocationCodeValidationTests(TestCase):
    def test_location_code_rejects_non_iata_values(self):
        country = Country.objects.create(code="AU", name="Australia")
        location = Location(code="BNE2", name="Brisbane", country=country)

        with self.assertRaises(ValidationError):
            location.full_clean()

    def test_create_location_helper_validates_before_save(self):
        country = Country.objects.create(code="AU", name="Australia")

        with self.assertRaises(ValidationError):
            create_location(code="BNE2", name="Brisbane", country=country)


class LocationTestUsageGuardrails(SimpleTestCase):
    def test_tests_use_create_location_helper(self):
        backend_root = Path(__file__).resolve().parents[2]
        offenders = []

        for path in sorted(backend_root.rglob("tests/test*.py")):
            if path.name == "test_location_guardrails.py":
                continue
            if "Location.objects.create(" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(backend_root).as_posix())

        self.assertEqual(
            offenders,
            [],
            f"Use core.tests.helpers.create_location() instead of Location.objects.create() in tests: {', '.join(offenders)}",
        )
