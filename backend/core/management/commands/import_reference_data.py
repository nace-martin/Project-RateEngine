import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Airport, City, Country, Currency, Location


class _DryRunRollback(Exception):
    """Internal signal used to roll back a dry-run import transaction."""


class Command(BaseCommand):
    help = (
        "Import core reference data from CSV files. Supports currencies, countries, "
        "cities, airports, and optional location overrides/additions."
    )

    def add_arguments(self, parser):
        parser.add_argument("--currencies", help="Path to currencies CSV")
        parser.add_argument("--countries", help="Path to countries CSV")
        parser.add_argument("--cities", help="Path to cities CSV")
        parser.add_argument("--airports", help="Path to airports CSV")
        parser.add_argument("--locations", help="Path to locations CSV")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing to the database",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        paths = {
            "currencies": options.get("currencies"),
            "countries": options.get("countries"),
            "cities": options.get("cities"),
            "airports": options.get("airports"),
            "locations": options.get("locations"),
        }
        if not any(paths.values()):
            raise CommandError(
                "Provide at least one CSV file: --currencies, --countries, --cities, --airports, or --locations"
            )

        counts = {
            "currencies_created": 0,
            "currencies_updated": 0,
            "currencies_unchanged": 0,
            "countries_created": 0,
            "countries_updated": 0,
            "countries_unchanged": 0,
            "cities_created": 0,
            "cities_updated": 0,
            "cities_unchanged": 0,
            "airports_created": 0,
            "airports_updated": 0,
            "airports_unchanged": 0,
            "locations_created": 0,
            "locations_updated": 0,
            "locations_unchanged": 0,
        }
        row_counts = {
            "currencies": 0,
            "countries": 0,
            "cities": 0,
            "airports": 0,
            "locations": 0,
        }

        try:
            with transaction.atomic():
                if paths["currencies"]:
                    row_counts["currencies"] = self._import_currencies(paths["currencies"], dry_run, counts)
                if paths["countries"]:
                    row_counts["countries"] = self._import_countries(paths["countries"], dry_run, counts)
                if paths["cities"]:
                    row_counts["cities"] = self._import_cities(paths["cities"], dry_run, counts)
                if paths["airports"]:
                    row_counts["airports"] = self._import_airports(paths["airports"], dry_run, counts)
                if paths["locations"]:
                    row_counts["locations"] = self._import_locations(paths["locations"], dry_run, counts)
                if dry_run:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Reference data import summary"))
        for key, row_count in row_counts.items():
            if paths[key]:
                self.stdout.write(f"- {key} rows processed: {row_count}")
        self.stdout.write(f"- currencies created/updated/unchanged: {counts['currencies_created']}/{counts['currencies_updated']}/{counts['currencies_unchanged']}")
        self.stdout.write(f"- countries created/updated/unchanged: {counts['countries_created']}/{counts['countries_updated']}/{counts['countries_unchanged']}")
        self.stdout.write(f"- cities created/updated/unchanged: {counts['cities_created']}/{counts['cities_updated']}/{counts['cities_unchanged']}")
        self.stdout.write(f"- airports created/updated/unchanged: {counts['airports_created']}/{counts['airports_updated']}/{counts['airports_unchanged']}")
        self.stdout.write(f"- locations created/updated/unchanged: {counts['locations_created']}/{counts['locations_updated']}/{counts['locations_unchanged']}")

    def _import_currencies(self, csv_path: str, dry_run: bool, counts: dict) -> int:
        headers, rows = self._load_rows(csv_path)
        self._ensure_required_columns(headers, ["code", "name"], "Currencies CSV")
        for row_number, row in rows:
            code = self._required_upper(row, "code", row_number, expected_len=3)
            name = self._required_value(row, "name", row_number)
            minor_units = self._parse_int(row.get("minor_units"), "minor_units", row_number, default=2, minimum=0)

            obj = Currency.objects.filter(code=code).first()
            if not obj:
                counts["currencies_created"] += 1
                Currency.objects.create(code=code, name=name, minor_units=minor_units)
                continue

            changed = False
            if obj.name != name:
                obj.name = name
                changed = True
            if obj.minor_units != minor_units:
                obj.minor_units = minor_units
                changed = True

            if changed:
                counts["currencies_updated"] += 1
                obj.save(update_fields=["name", "minor_units"])
            else:
                counts["currencies_unchanged"] += 1
        return len(rows)

    def _import_countries(self, csv_path: str, dry_run: bool, counts: dict) -> int:
        headers, rows = self._load_rows(csv_path)
        self._ensure_required_columns(headers, ["code", "name"], "Countries CSV")
        for row_number, row in rows:
            code = self._required_upper(row, "code", row_number, expected_len=2)
            name = self._required_value(row, "name", row_number)
            currency = self._resolve_currency(row.get("currency_code"), row_number, required=False)

            obj = Country.objects.filter(code=code).first()
            if not obj:
                counts["countries_created"] += 1
                Country.objects.create(code=code, name=name, currency=currency)
                continue

            changed = False
            if obj.name != name:
                obj.name = name
                changed = True
            if obj.currency_id != (currency.code if currency else None):
                obj.currency = currency
                changed = True

            if changed:
                counts["countries_updated"] += 1
                obj.save(update_fields=["name", "currency"])
            else:
                counts["countries_unchanged"] += 1
        return len(rows)

    def _import_cities(self, csv_path: str, dry_run: bool, counts: dict) -> int:
        headers, rows = self._load_rows(csv_path)
        self._ensure_required_columns(headers, ["country_code", "name"], "Cities CSV")
        for row_number, row in rows:
            country = self._resolve_country(row.get("country_code"), row_number)
            name = self._required_value(row, "name", row_number)

            obj = City.objects.filter(country=country, name=name).first()
            if not obj:
                counts["cities_created"] += 1
                City.objects.create(country=country, name=name)
                continue

            counts["cities_unchanged"] += 1
        return len(rows)

    def _import_airports(self, csv_path: str, dry_run: bool, counts: dict) -> int:
        headers, rows = self._load_rows(csv_path)
        self._ensure_required_columns(headers, ["iata_code", "name", "city_name", "country_code"], "Airports CSV")
        for row_number, row in rows:
            iata_code = self._required_upper(row, "iata_code", row_number, expected_len=3)
            name = self._required_value(row, "name", row_number)
            city = self._resolve_city(
                city_name=row.get("city_name"),
                country_code=row.get("country_code"),
                row_number=row_number,
            )

            obj = Airport.objects.filter(iata_code=iata_code).first()
            if not obj:
                counts["airports_created"] += 1
                Airport.objects.create(iata_code=iata_code, name=name, city=city)
                continue

            changed = False
            if obj.name != name:
                obj.name = name
                changed = True
            if obj.city_id != city.id:
                obj.city = city
                changed = True

            if changed:
                counts["airports_updated"] += 1
                obj.save(update_fields=["name", "city"])
            else:
                counts["airports_unchanged"] += 1
        return len(rows)

    def _import_locations(self, csv_path: str, dry_run: bool, counts: dict) -> int:
        headers, rows = self._load_rows(csv_path)
        self._ensure_required_columns(headers, ["kind", "code", "name"], "Locations CSV")
        valid_kinds = {choice for choice, _ in Location.Kind.choices}
        for row_number, row in rows:
            kind = self._required_upper(row, "kind", row_number)
            if kind not in valid_kinds:
                valid_list = ", ".join(sorted(valid_kinds))
                raise CommandError(f"Row {row_number}: invalid kind '{kind}'. Expected one of: {valid_list}")

            code = self._required_upper(row, "code", row_number)
            name = self._required_value(row, "name", row_number)
            is_active = self._parse_bool(row.get("is_active"), "is_active", row_number, default=True)
            metadata = self._parse_json(row.get("metadata_json"), "metadata_json", row_number)

            country = None
            city = None
            airport = None

            city_name = self._norm_value(row.get("city_name"))
            country_code = self._norm_value(row.get("country_code"))
            airport_iata = self._norm_value(row.get("airport_iata"))

            if city_name:
                city = self._resolve_city(city_name=city_name, country_code=country_code, row_number=row_number)
                country = city.country
            elif country_code:
                country = self._resolve_country(country_code, row_number)

            if airport_iata:
                airport = Airport.objects.filter(iata_code=airport_iata.upper()).select_related("city__country").first()
                if not airport:
                    raise CommandError(f"Row {row_number}: airport_iata '{airport_iata}' does not exist")
            elif kind == Location.Kind.AIRPORT:
                airport = Airport.objects.filter(iata_code=code).select_related("city__country").first()
                if not airport:
                    raise CommandError(
                        f"Row {row_number}: AIRPORT location '{code}' must reference an existing airport via code or airport_iata"
                    )

            if airport:
                if not city and airport.city:
                    city = airport.city
                if not country and airport.city and airport.city.country:
                    country = airport.city.country

            address_line = self._norm_value(row.get("address_line")) or ""

            obj = Location.objects.filter(kind=kind, code=code).first()
            if not obj:
                counts["locations_created"] += 1
                Location.objects.create(
                    kind=kind,
                    code=code,
                    name=name,
                    country=country,
                    city=city,
                    airport=airport,
                    address_line=address_line,
                    metadata=metadata,
                    is_active=is_active,
                )
                continue

            changed = False
            field_values = {
                "name": name,
                "country": country,
                "city": city,
                "airport": airport,
                "address_line": address_line,
                "metadata": metadata,
                "is_active": is_active,
            }
            for field_name, value in field_values.items():
                current_value = getattr(obj, field_name)
                if hasattr(current_value, "pk"):
                    current_value = current_value.pk
                if hasattr(value, "pk"):
                    value = value.pk
                if current_value != value:
                    setattr(obj, field_name, field_values[field_name])
                    changed = True

            if changed:
                counts["locations_updated"] += 1
                obj.save(update_fields=["name", "country", "city", "airport", "address_line", "metadata", "is_active"])
            else:
                counts["locations_unchanged"] += 1
        return len(rows)

    def _load_rows(self, csv_path: str):
        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        decode_error = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames:
                        raise CommandError(f"CSV has no header row: {path}")
                    headers = [self._norm_key(header) for header in reader.fieldnames if header is not None]
                    rows = []
                    for row_number, row in enumerate(reader, start=2):
                        normalized = {
                            self._norm_key(key): self._norm_value(value)
                            for key, value in row.items()
                            if key is not None
                        }
                        rows.append((row_number, normalized))
                    return headers, rows
            except UnicodeDecodeError as exc:
                decode_error = exc
                continue
        raise CommandError(f"Unable to decode CSV using utf-8-sig/cp1252/latin-1: {decode_error}")

    @staticmethod
    def _norm_key(value):
        return str(value or "").strip().lower()

    @staticmethod
    def _norm_value(value):
        if value is None:
            return ""
        return str(value).strip()

    def _ensure_required_columns(self, headers, required, label):
        missing = [column for column in required if column not in set(headers)]
        if missing:
            raise CommandError(f"{label} missing required column(s): {', '.join(missing)}")

    def _required_value(self, row, key, row_number):
        value = self._norm_value(row.get(key))
        if not value:
            raise CommandError(f"Row {row_number}: {key} is required")
        return value

    def _required_upper(self, row, key, row_number, expected_len=None):
        value = self._required_value(row, key, row_number).upper()
        if expected_len is not None and len(value) != expected_len:
            raise CommandError(f"Row {row_number}: {key} must be {expected_len} characters")
        return value

    def _resolve_currency(self, value, row_number, required):
        currency_code = self._norm_value(value).upper()
        if not currency_code:
            if required:
                raise CommandError(f"Row {row_number}: currency_code is required")
            return None
        currency = Currency.objects.filter(code=currency_code).first()
        if not currency:
            raise CommandError(f"Row {row_number}: currency_code '{currency_code}' does not exist")
        return currency

    def _resolve_country(self, value, row_number):
        country_code = self._norm_value(value).upper()
        if not country_code:
            raise CommandError(f"Row {row_number}: country_code is required")
        country = Country.objects.filter(code=country_code).first()
        if not country:
            raise CommandError(f"Row {row_number}: country_code '{country_code}' does not exist")
        return country

    def _resolve_city(self, city_name, country_code, row_number):
        normalized_city = self._norm_value(city_name)
        if not normalized_city:
            raise CommandError(f"Row {row_number}: city_name is required")
        country = self._resolve_country(country_code, row_number)
        city = City.objects.filter(country=country, name=normalized_city).first()
        if not city:
            raise CommandError(
                f"Row {row_number}: city '{normalized_city}' does not exist for country '{country.code}'"
            )
        return city

    def _parse_int(self, value, field_name, row_number, default, minimum=None):
        normalized = self._norm_value(value)
        if not normalized:
            return default
        try:
            parsed = int(normalized)
        except ValueError as exc:
            raise CommandError(f"Row {row_number}: {field_name} must be an integer") from exc
        if minimum is not None and parsed < minimum:
            raise CommandError(f"Row {row_number}: {field_name} must be >= {minimum}")
        return parsed

    def _parse_bool(self, value, field_name, row_number, default):
        normalized = self._norm_value(value)
        if not normalized:
            return default
        truthy = {"1", "true", "yes", "y", "on"}
        falsey = {"0", "false", "no", "n", "off"}
        lowered = normalized.lower()
        if lowered in truthy:
            return True
        if lowered in falsey:
            return False
        raise CommandError(f"Row {row_number}: {field_name} must be a boolean-like value")

    def _parse_json(self, value, field_name, row_number):
        normalized = self._norm_value(value)
        if not normalized:
            return None
        try:
            return json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Row {row_number}: {field_name} must contain valid JSON") from exc
