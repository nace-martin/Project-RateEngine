"""Backfill only airports supported by agreeing legacy structured records."""

import re

from django.db import migrations


def backfill_geo_airports(apps, schema_editor):
    Location = apps.get_model("core", "Location")
    GeoLocation = apps.get_model("core", "GeoLocation")
    GeoLocationIdentifier = apps.get_model("core", "GeoLocationIdentifier")

    evidence = {}
    for legacy in Location.objects.select_related("airport__city", "city", "country").order_by("pk"):
        if legacy.kind != "AIRPORT" or not legacy.airport_id:
            continue
        airport = legacy.airport
        code = airport.iata_code
        if not re.fullmatch(r"[A-Z]{3}", code or "") or legacy.code != code:
            continue
        if not airport.city_id or not legacy.city_id or not legacy.country_id:
            continue
        country_code = airport.city.country_id
        if legacy.city_id != airport.city_id or legacy.country_id != country_code:
            continue
        if not airport.name.strip():
            continue
        fact = (country_code, bool(legacy.is_active), airport.name)
        if code in evidence and evidence[code] != fact:
            raise ValueError(f"Conflicting structured legacy airport evidence for IATA {code}")
        evidence[code] = fact

    for code, (country_code, is_active, name) in sorted(evidence.items()):
        matches = list(GeoLocationIdentifier.objects.filter(scheme="IATA", code=code).select_related("location"))
        if len(matches) > 1:
            raise ValueError(f"Duplicate clean IATA identifier for {code}")
        if matches:
            geo = matches[0].location
            if (geo.location_type, geo.country_code, geo.is_active) != ("AIRPORT", country_code, is_active):
                raise ValueError(f"Conflicting clean geography for IATA {code}")
            continue
        geo = GeoLocation.objects.create(
            canonical_name=name,
            country_code=country_code,
            location_type="AIRPORT",
            is_active=is_active,
        )
        GeoLocationIdentifier.objects.create(location=geo, scheme="IATA", code=code)


class Migration(migrations.Migration):
    dependencies = [("core", "0015_delete_fxrate")]  # noqa: RUF012 - Django migration convention
    operations = [migrations.RunPython(backfill_geo_airports, migrations.RunPython.noop)]  # noqa: RUF012
