import argparse
import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


COUNTRIES_URL = "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
CURRENCY_CODES_URL = "https://raw.githubusercontent.com/datasets/currency-codes/master/data/codes-all.csv"
AIRPORTS_URL = "https://ourairports.com/data/airports.csv"
GEONAMES_CITIES500_URL = "https://download.geonames.org/export/dump/cities500.zip"

REGIONAL_COUNTRY_CODES = [
    "AU", "NZ", "PG",
    "FJ", "SB", "VU", "WS", "TO", "KI", "FM", "MH", "PW", "NR", "TV",
    "BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN",
    "CN", "KR", "JP",
    "IN",
    "GB", "NL", "DE",
]

HUB_CITY_DEFINITIONS = [
    {"country_code": "AU", "city_name": "Sydney", "airports": ["SYD"]},
    {"country_code": "AU", "city_name": "Melbourne", "airports": ["MEL"]},
    {"country_code": "AU", "city_name": "Brisbane", "airports": ["BNE"]},
    {"country_code": "AU", "city_name": "Perth", "airports": ["PER"]},
    {"country_code": "AU", "city_name": "Adelaide", "airports": ["ADL"]},
    {"country_code": "AU", "city_name": "Cairns", "airports": ["CNS"]},
    {"country_code": "NZ", "city_name": "Auckland", "airports": ["AKL"]},
    {"country_code": "NZ", "city_name": "Wellington", "airports": ["WLG"]},
    {"country_code": "NZ", "city_name": "Christchurch", "airports": ["CHC"]},
    {"country_code": "PG", "city_name": "Port Moresby", "airports": ["POM"]},
    {"country_code": "PG", "city_name": "Lae", "airports": ["LAE"]},
    {"country_code": "PG", "city_name": "Mount Hagen", "airports": ["HGU"]},
    {"country_code": "FJ", "city_name": "Nadi", "airports": ["NAN"]},
    {"country_code": "FJ", "city_name": "Suva", "airports": ["SUV"]},
    {"country_code": "SB", "city_name": "Honiara", "airports": ["HIR"]},
    {"country_code": "VU", "city_name": "Port Vila", "airports": ["VLI"]},
    {"country_code": "WS", "city_name": "Apia", "airports": ["APW"]},
    {"country_code": "TO", "city_name": "Nuku'alofa", "airports": ["TBU"]},
    {"country_code": "KI", "city_name": "Tarawa", "airports": ["TRW"]},
    {"country_code": "FM", "city_name": "Pohnpei", "airports": ["PNI"]},
    {"country_code": "FM", "city_name": "Chuuk", "airports": ["TKK"]},
    {"country_code": "MH", "city_name": "Majuro", "airports": ["MAJ"]},
    {"country_code": "MH", "city_name": "Kwajalein", "airports": ["KWA"]},
    {"country_code": "PW", "city_name": "Koror", "airports": ["ROR"]},
    {"country_code": "NR", "city_name": "Nauru", "airports": ["INU"]},
    {"country_code": "TV", "city_name": "Funafuti", "airports": ["FUN"]},
    {"country_code": "BN", "city_name": "Bandar Seri Begawan", "airports": ["BWN"]},
    {"country_code": "KH", "city_name": "Phnom Penh", "airports": ["PNH"]},
    {"country_code": "KH", "city_name": "Siem Reap", "airports": ["SAI"]},
    {"country_code": "ID", "city_name": "Jakarta", "airports": ["CGK", "HLP"]},
    {"country_code": "ID", "city_name": "Surabaya", "airports": ["SUB"]},
    {"country_code": "ID", "city_name": "Denpasar", "airports": ["DPS"]},
    {"country_code": "ID", "city_name": "Medan", "airports": ["KNO"]},
    {"country_code": "ID", "city_name": "Makassar", "airports": ["UPG"]},
    {"country_code": "LA", "city_name": "Vientiane", "airports": ["VTE"]},
    {"country_code": "LA", "city_name": "Luang Prabang", "airports": ["LPQ"]},
    {"country_code": "MY", "city_name": "Kuala Lumpur", "airports": ["KUL"]},
    {"country_code": "MY", "city_name": "Penang", "airports": ["PEN"]},
    {"country_code": "MY", "city_name": "Kuching", "airports": ["KCH"]},
    {"country_code": "MY", "city_name": "Kota Kinabalu", "airports": ["BKI"]},
    {"country_code": "MM", "city_name": "Yangon", "airports": ["RGN"]},
    {"country_code": "MM", "city_name": "Mandalay", "airports": ["MDL"]},
    {"country_code": "PH", "city_name": "Manila", "airports": ["MNL"]},
    {"country_code": "PH", "city_name": "Cebu", "airports": ["CEB"]},
    {"country_code": "PH", "city_name": "Davao", "airports": ["DVO"]},
    {"country_code": "PH", "city_name": "Clark", "airports": ["CRK"]},
    {"country_code": "SG", "city_name": "Singapore", "airports": ["SIN"]},
    {"country_code": "TH", "city_name": "Bangkok", "airports": ["BKK", "DMK"]},
    {"country_code": "TH", "city_name": "Phuket", "airports": ["HKT"]},
    {"country_code": "TH", "city_name": "Chiang Mai", "airports": ["CNX"]},
    {"country_code": "TL", "city_name": "Dili", "airports": ["DIL"]},
    {"country_code": "VN", "city_name": "Ho Chi Minh City", "airports": ["SGN"]},
    {"country_code": "VN", "city_name": "Hanoi", "airports": ["HAN"]},
    {"country_code": "VN", "city_name": "Da Nang", "airports": ["DAD"]},
    {"country_code": "CN", "city_name": "Beijing", "airports": ["PEK", "PKX"]},
    {"country_code": "CN", "city_name": "Shanghai", "airports": ["PVG", "SHA"]},
    {"country_code": "CN", "city_name": "Guangzhou", "airports": ["CAN"]},
    {"country_code": "CN", "city_name": "Shenzhen", "airports": ["SZX"]},
    {"country_code": "CN", "city_name": "Xiamen", "airports": ["XMN"]},
    {"country_code": "CN", "city_name": "Qingdao", "airports": ["TAO"]},
    {"country_code": "KR", "city_name": "Seoul", "airports": ["ICN", "GMP"]},
    {"country_code": "KR", "city_name": "Busan", "airports": ["PUS"]},
    {"country_code": "JP", "city_name": "Tokyo", "airports": ["HND", "NRT"]},
    {"country_code": "JP", "city_name": "Osaka", "airports": ["KIX", "ITM"]},
    {"country_code": "JP", "city_name": "Nagoya", "airports": ["NGO"]},
    {"country_code": "JP", "city_name": "Fukuoka", "airports": ["FUK"]},
    {"country_code": "JP", "city_name": "Sapporo", "airports": ["CTS"]},
    {"country_code": "IN", "city_name": "Delhi", "airports": ["DEL"]},
    {"country_code": "IN", "city_name": "Mumbai", "airports": ["BOM"]},
    {"country_code": "IN", "city_name": "Bengaluru", "airports": ["BLR"]},
    {"country_code": "IN", "city_name": "Chennai", "airports": ["MAA"]},
    {"country_code": "IN", "city_name": "Hyderabad", "airports": ["HYD"]},
    {"country_code": "IN", "city_name": "Kolkata", "airports": ["CCU"]},
    {"country_code": "IN", "city_name": "Ahmedabad", "airports": ["AMD"]},
    {"country_code": "IN", "city_name": "Pune", "airports": ["PNQ"]},
    {"country_code": "IN", "city_name": "Kochi", "airports": ["COK"]},
    {"country_code": "GB", "city_name": "London", "airports": ["LHR", "LGW", "STN"]},
    {"country_code": "GB", "city_name": "Manchester", "airports": ["MAN"]},
    {"country_code": "GB", "city_name": "Birmingham", "airports": ["BHX"]},
    {"country_code": "NL", "city_name": "Amsterdam", "airports": ["AMS"]},
    {"country_code": "NL", "city_name": "Rotterdam", "airports": ["RTM"]},
    {"country_code": "DE", "city_name": "Frankfurt", "airports": ["FRA"]},
    {"country_code": "DE", "city_name": "Munich", "airports": ["MUC"]},
    {"country_code": "DE", "city_name": "Hamburg", "airports": ["HAM"]},
    {"country_code": "DE", "city_name": "Berlin", "airports": ["BER"]},
    {"country_code": "DE", "city_name": "Dusseldorf", "airports": ["DUS"]},
]

CITY_LIMITS_BY_COUNTRY = {
    "AU": 250,
    "NZ": 100,
    "PG": 400,
    "FJ": None,
    "SB": None,
    "VU": None,
    "WS": None,
    "TO": None,
    "KI": None,
    "FM": None,
    "MH": None,
    "PW": None,
    "NR": None,
    "TV": None,
    "BN": None,
    "KH": 120,
    "ID": 250,
    "LA": None,
    "MY": 120,
    "MM": 150,
    "PH": 200,
    "SG": None,
    "TH": 150,
    "TL": None,
    "VN": 150,
    "CN": 300,
    "KR": 120,
    "JP": 180,
    "IN": None,
    "GB": 250,
    "NL": 120,
    "DE": 250,
}

INDIA_MAIN_CITIES = {
    "Ahmedabad",
    "Bengaluru",
    "Bangalore",
    "Chennai",
    "Delhi",
    "New Delhi",
    "Hyderabad",
    "Kochi",
    "Kolkata",
    "Mumbai",
    "Pune",
}

PACIFIC_AND_PNG_ALL_AIRPORTS = {
    "PG", "FJ", "SB", "VU", "WS", "TO", "KI", "FM", "MH", "PW", "NR", "TV"
}

AIRPORT_TYPES_FOR_REGIONAL_PROFILE = {"large_airport", "medium_airport"}


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Project-RateEngine/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def normalize_text(value: str) -> str:
    value = (value or "").strip()
    return re.sub(r"\s+", " ", value)


def trim(value: str, max_length: int) -> str:
    value = normalize_text(value)
    if len(value) <= max_length:
        return value
    return value[:max_length].rstrip()


def read_currency_minor_units():
    raw = fetch_bytes(CURRENCY_CODES_URL).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    currencies = {}
    minor_units = {}

    for row in reader:
        code = normalize_text(row.get("AlphabeticCode", "")).upper()
        if len(code) != 3:
            continue
        if normalize_text(row.get("WithdrawalDate", "")):
            continue

        name = trim(row.get("Currency", ""), 50)
        if not name:
            continue

        if code not in currencies:
            currencies[code] = {"code": code, "name": name, "minor_units": 2}

        minor = normalize_text(row.get("MinorUnit", ""))
        if minor.isdigit():
            minor_units[code] = int(minor)
            currencies[code]["minor_units"] = int(minor)

    return currencies, minor_units


def read_bsp_currency_codes() -> list[str]:
    from core.fx_providers.bsp_html import BspHtmlProvider

    html = BspHtmlProvider()._fetch_html()
    table = BspHtmlProvider._parse_rates(html)
    return sorted(table.keys())


def read_countries_and_currencies(minor_units):
    payload = json.loads(fetch_bytes(COUNTRIES_URL).decode("utf-8"))
    countries = []
    country_currencies = {}

    for entry in payload:
        code = normalize_text(entry.get("cca2", "")).upper()
        if len(code) != 2:
            continue

        name = trim(entry.get("name", {}).get("common", ""), 100)
        if not name:
            continue

        currency_code = ""
        currencies = entry.get("currencies") or {}
        for curr_code, curr_meta in currencies.items():
            curr_code = normalize_text(curr_code).upper()
            if len(curr_code) != 3:
                continue
            currency_code = curr_code
            if curr_code not in country_currencies:
                country_currencies[curr_code] = {
                    "code": curr_code,
                    "name": trim(curr_meta.get("name", curr_code), 50),
                    "minor_units": minor_units.get(curr_code, 2),
                }

        countries.append({"code": code, "name": name, "currency_code": currency_code})

    countries.sort(key=lambda row: (row["name"], row["code"]))
    return countries, country_currencies


def read_geonames_city_lists():
    zipped = fetch_bytes(GEONAMES_CITIES500_URL)
    by_country = {}

    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        filename = next(name for name in archive.namelist() if name.endswith(".txt"))
        with archive.open(filename) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8")
            for line in text:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 19:
                    continue

                country_code = normalize_text(parts[8]).upper()
                if len(country_code) != 2:
                    continue

                city_name = trim(parts[2] or parts[1], 100)
                if not city_name:
                    continue

                try:
                    population = int(parts[14] or "0")
                except ValueError:
                    population = 0

                bucket = by_country.setdefault(country_code, {})
                key = city_name.casefold()
                existing = bucket.get(key)
                if existing is None or population > existing["population"]:
                    bucket[key] = {
                        "country_code": country_code,
                        "name": city_name,
                        "population": population,
                    }

    normalized = {}
    for country_code, bucket in by_country.items():
        normalized[country_code] = sorted(
            bucket.values(),
            key=lambda row: (-row["population"], row["name"]),
        )
    return normalized


def keep_airport_for_regional_profile(row):
    country_code = normalize_text(row.get("iso_country", "")).upper()
    if country_code in PACIFIC_AND_PNG_ALL_AIRPORTS:
        return True

    airport_type = normalize_text(row.get("type", ""))
    scheduled = normalize_text(row.get("scheduled_service", "")).lower()
    return airport_type in AIRPORT_TYPES_FOR_REGIONAL_PROFILE or scheduled == "yes"


def read_airports(selected_country_codes, profile):
    raw = fetch_bytes(AIRPORTS_URL).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    airports = []
    seen_iata = set()
    airport_cities = {}

    for row in reader:
        iata_code = normalize_text(row.get("iata_code", "")).upper()
        country_code = normalize_text(row.get("iso_country", "")).upper()
        city_name = trim(row.get("municipality", ""), 100)
        name = trim(row.get("name", ""), 100)

        if len(iata_code) != 3 or iata_code in seen_iata:
            continue
        if country_code not in selected_country_codes:
            continue
        if not city_name or not name:
            continue

        if profile == "regional" and not keep_airport_for_regional_profile(row):
            continue

        airports.append(
            {
                "iata_code": iata_code,
                "name": name,
                "city_name": city_name,
                "country_code": country_code,
            }
        )
        seen_iata.add(iata_code)
        airport_cities.setdefault(country_code, set()).add(city_name)

    airports.sort(key=lambda row: row["iata_code"])
    return airports, airport_cities


def read_airport_lookup():
    raw = fetch_bytes(AIRPORTS_URL).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    lookup = {}
    for row in reader:
        iata_code = normalize_text(row.get("iata_code", "")).upper()
        if len(iata_code) != 3 or iata_code in lookup:
            continue
        lookup[iata_code] = row
    return lookup


def build_hub_rows(all_countries):
    airport_lookup = read_airport_lookup()
    selected_country_codes = {row["country_code"] for row in HUB_CITY_DEFINITIONS}
    countries = [row for row in all_countries if row["code"] in selected_country_codes]

    city_rows = []
    airports = []
    seen_airports = set()

    for definition in HUB_CITY_DEFINITIONS:
        city_rows.append(
            {
                "country_code": definition["country_code"],
                "name": definition["city_name"],
            }
        )
        for airport_code in definition["airports"]:
            airport = airport_lookup.get(airport_code)
            if airport is None:
                raise ValueError(f"Hub profile airport '{airport_code}' was not found in source data")
            actual_country = normalize_text(airport.get("iso_country", "")).upper()
            if actual_country != definition["country_code"]:
                raise ValueError(
                    f"Hub profile airport '{airport_code}' belongs to '{actual_country}', expected '{definition['country_code']}'"
                )
            if airport_code in seen_airports:
                continue
            airports.append(
                {
                    "iata_code": airport_code,
                    "name": trim(airport.get("name", airport_code), 100),
                    "city_name": definition["city_name"],
                    "country_code": definition["country_code"],
                }
            )
            seen_airports.add(airport_code)

    city_rows.sort(key=lambda row: (row["country_code"], row["name"]))
    airports.sort(key=lambda row: row["iata_code"])
    countries.sort(key=lambda row: (row["name"], row["code"]))
    return countries, city_rows, airports


def build_city_rows(profile, selected_country_codes, geonames_cities, airport_cities):
    city_rows = []

    for country_code in selected_country_codes:
        selected = {}

        for city_name in sorted(airport_cities.get(country_code, set())):
            key = city_name.casefold()
            selected[key] = {"country_code": country_code, "name": city_name}

        if profile == "regional" and country_code == "IN":
            for city in geonames_cities.get(country_code, []):
                if city["name"] in INDIA_MAIN_CITIES:
                    selected.setdefault(
                        city["name"].casefold(),
                        {"country_code": country_code, "name": city["name"]},
                    )
        else:
            city_limit = CITY_LIMITS_BY_COUNTRY.get(country_code)
            city_candidates = geonames_cities.get(country_code, [])
            if city_limit is None:
                iterator = city_candidates
            else:
                iterator = city_candidates[:city_limit]
            for city in iterator:
                selected.setdefault(
                    city["name"].casefold(),
                    {"country_code": country_code, "name": city["name"]},
                )

        city_rows.extend(sorted(selected.values(), key=lambda row: row["name"]))

    city_rows.sort(key=lambda row: (row["country_code"], row["name"]))
    return city_rows


def write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def build_rows(profile):
    currencies_from_iso, minor_units = read_currency_minor_units()
    countries, currencies_from_countries = read_countries_and_currencies(minor_units)

    currencies = currencies_from_iso
    for code, payload in currencies_from_countries.items():
        currencies.setdefault(code, payload)

    if profile == "hub":
        allowed_currency_codes = {"PGK", *read_bsp_currency_codes()}
        currencies = {
            code: payload
            for code, payload in currencies.items()
            if code in allowed_currency_codes
        }
        for country in countries:
            if country["currency_code"] and country["currency_code"] not in allowed_currency_codes:
                country["currency_code"] = ""

    if profile == "hub":
        countries, city_rows, airports = build_hub_rows(countries)
        currency_rows = sorted(currencies.values(), key=lambda row: (str(row["name"]), str(row["code"])))
        return currency_rows, countries, city_rows, airports

    if profile == "regional":
        selected_country_codes = set(REGIONAL_COUNTRY_CODES)
        countries = [row for row in countries if row["code"] in selected_country_codes]
    else:
        selected_country_codes = {row["code"] for row in countries}

    geonames_cities = read_geonames_city_lists()
    airports, airport_cities = read_airports(selected_country_codes, profile)
    city_rows = build_city_rows(profile, REGIONAL_COUNTRY_CODES if profile == "regional" else sorted(selected_country_codes), geonames_cities, airport_cities)

    currency_rows = sorted(currencies.values(), key=lambda row: (str(row["name"]), str(row["code"])))
    countries.sort(key=lambda row: (row["name"], row["code"]))

    return currency_rows, countries, city_rows, airports


def main():
    parser = argparse.ArgumentParser(description="Build reference-data CSVs.")
    parser.add_argument(
        "--profile",
        choices=["hub", "regional", "global"],
        default="hub",
        help="Use 'hub' for the lean launch pack, 'regional' for broader regional coverage, or 'global' for the full dataset",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("docs") / "templates" / "reference-data"),
        help="Directory to write currencies.csv, countries.csv, cities.csv, airports.csv, and locations.csv",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    print(f"Building {args.profile} reference-data pack...")
    print("Fetching and normalizing source datasets...")
    currency_rows, countries, city_rows, airports = build_rows(args.profile)

    location_headers = [
        "kind",
        "code",
        "name",
        "country_code",
        "city_name",
        "airport_iata",
        "is_active",
        "address_line",
        "metadata_json",
    ]

    print("Writing CSV files...")
    write_csv(output_dir / "currencies.csv", ["code", "name", "minor_units"], currency_rows)
    write_csv(output_dir / "countries.csv", ["code", "name", "currency_code"], countries)
    write_csv(output_dir / "cities.csv", ["country_code", "name"], city_rows)
    write_csv(output_dir / "airports.csv", ["iata_code", "name", "city_name", "country_code"], airports)
    write_csv(output_dir / "locations.csv", location_headers, [])

    print(f"Wrote {len(currency_rows)} currencies")
    print(f"Wrote {len(countries)} countries")
    print(f"Wrote {len(city_rows)} cities")
    print(f"Wrote {len(airports)} airports")
    print("Wrote 0 explicit location overrides")
    print()
    if args.profile == "hub":
        print("Hub profile notes:")
        print("- cities are limited to major commercial cities")
        print("- airports are limited to the selected international airports for those cities")
        print("- locations.csv remains empty so quote routing stays airport-based until you deliberately add city aliases later")
    elif args.profile == "regional":
        print("Regional profile notes:")
        print("- countries are limited to your current operating footprint")
        print("- airports are filtered toward operational/commercial relevance")
        print("- India is intentionally limited to main commercial cities plus airport municipalities")
    else:
        print("Global profile notes:")
        print("- cities are deduplicated by (country_code, name) to fit the current City model")
        print("- locations.csv remains empty because airport imports create airport locations automatically")
    return 0


if __name__ == "__main__":
    sys.exit(main())
