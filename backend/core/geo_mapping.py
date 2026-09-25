"""Fail-closed bridge from legacy quote locations to clean geography."""

import re

from core.geo_models import GeoLocationIdentifier


class GeoMappingError(ValueError):
    def __init__(self, category: str, reason: str):
        self.category = category
        self.reason = reason
        super().__init__(reason)


def airport_evidence(location):
    """Return the IATA code and country only when legacy structured links agree."""
    if location.kind != "AIRPORT":
        raise GeoMappingError("unresolved", "unsupported_location_kind")
    if not location.airport_id:
        raise GeoMappingError("unresolved", "missing_airport")
    airport = location.airport
    if not airport or not re.fullmatch(r"[A-Z]{3}", airport.iata_code or ""):
        raise GeoMappingError("unresolved", "invalid_airport_iata")
    if location.code != airport.iata_code:
        raise GeoMappingError("conflict", "location_airport_code_mismatch")
    if not airport.city_id or not location.city_id or not location.country_id:
        raise GeoMappingError("unresolved", "missing_city_or_country")
    if location.city_id != airport.city_id or location.country_id != airport.city.country_id:
        raise GeoMappingError("conflict", "location_airport_geography_mismatch")
    if not airport.name.strip():
        raise GeoMappingError("unresolved", "missing_airport_name")
    return airport.iata_code, airport.city.country_id


def resolve_geo_location(legacy_location):
    """Resolve only an active, structurally verified AIRPORT through its IATA ID."""
    code, country_code = airport_evidence(legacy_location)
    if not legacy_location.is_active:
        raise GeoMappingError("unresolved", "inactive_legacy_location")
    try:
        identifier = GeoLocationIdentifier.objects.select_related("location").get(
            scheme=GeoLocationIdentifier.Scheme.IATA, code=code
        )
    except GeoLocationIdentifier.DoesNotExist as exc:
        raise GeoMappingError("unresolved", "missing_iata_identifier") from exc
    except GeoLocationIdentifier.MultipleObjectsReturned as exc:
        raise GeoMappingError("conflict", "duplicate_iata_identifier") from exc
    geo = identifier.location
    if geo.location_type != "AIRPORT" or geo.country_code != country_code:
        raise GeoMappingError("conflict", "identifier_geography_mismatch")
    if not geo.is_active:
        raise GeoMappingError("unresolved", "inactive_geography")
    return geo
