import os
import sys
from decimal import Decimal

# Ensure backend project on path
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

import django

django.setup()

from django.db import connection
from django.utils.timezone import now
from core.models import Providers, Stations
from organizations.models import Organizations
from pricing.models import Ratecards, RatecardConfig, Routes, RouteLegs


def ensure_tables():
    ddls = [
        # Core reference tables
        """
        CREATE TABLE IF NOT EXISTS providers (
            id BIGSERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            provider_type TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS stations (
            id BIGSERIAL PRIMARY KEY,
            iata TEXT UNIQUE,
            city TEXT,
            country TEXT
        );
        """,
        # Ratecards and config
        """
        CREATE TABLE IF NOT EXISTS ratecards (
            id BIGSERIAL PRIMARY KEY,
            provider_id INTEGER REFERENCES providers(id),
            name TEXT,
            role TEXT,
            scope TEXT,
            direction TEXT,
            audience TEXT,
            rate_strategy VARCHAR(32),
            currency TEXT,
            source TEXT,
            status TEXT,
            effective_date DATE,
            expiry_date DATE,
            notes TEXT,
            meta JSONB,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS ratecard_config (
            id BIGSERIAL PRIMARY KEY,
            ratecard_id INTEGER UNIQUE REFERENCES ratecards(id),
            dim_factor_kg_per_m3 NUMERIC(8,2),
            rate_strategy TEXT,
            created_at TIMESTAMP
        );
        """,
        # Routes
        """
        CREATE TABLE IF NOT EXISTS routes (
            id BIGSERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            origin_country CHAR(2) NOT NULL,
            dest_country CHAR(2) NOT NULL,
            shipment_type VARCHAR(16) NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS route_legs (
            id BIGSERIAL PRIMARY KEY,
            route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            origin_id INTEGER NOT NULL REFERENCES stations(id),
            dest_id INTEGER NOT NULL REFERENCES stations(id),
            leg_scope VARCHAR(32) NOT NULL,
            service_type VARCHAR(32) NOT NULL
        );
        """,
        # Organizations (payer)
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id BIGSERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            country_code CHAR(2) DEFAULT 'PG',
            audience TEXT,
            default_sell_currency TEXT,
            gst_pct NUMERIC(5,2),
            disbursement_min NUMERIC(12,2),
            disbursement_cap NUMERIC(12,2),
            notes TEXT
        );
        """,
    ]
    with connection.cursor() as cur:
        for sql in ddls:
            try:
                cur.execute(sql)
            except Exception:
                connection.rollback()
                continue
        # Ensure new columns used by code exist
        cur.execute("ALTER TABLE ratecards ADD COLUMN IF NOT EXISTS commodity_code VARCHAR(8) DEFAULT 'GCR'")
        cur.execute("ALTER TABLE routes ADD COLUMN IF NOT EXISTS requires_manual_rate BOOLEAN DEFAULT FALSE")


def seed_minimal():
    # Stations
    bne, _ = Stations.objects.get_or_create(iata="BNE", defaults={"city": "Brisbane", "country": "AU"})
    lae, _ = Stations.objects.get_or_create(iata="LAE", defaults={"city": "Lae", "country": "PG"})

    # Provider
    prv, _ = Providers.objects.get_or_create(name="Test Provider", defaults={"provider_type": "AIR"})

    today = now().date()

    # Minimal SELL ratecard (PGK, IMPORT) for audience B2B
    rc_sell, _ = Ratecards.objects.get_or_create(
        name="SELL IMPORT PG",
        defaults=dict(
            provider=prv,
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            audience="B2B",
            rate_strategy="BREAKS",
            currency="PGK",
            source="SEED",
            status="ACTIVE",
            effective_date=today,
            meta={},
        ),
    )
    RatecardConfig.objects.get_or_create(ratecard=rc_sell, defaults={
        "dim_factor_kg_per_m3": Decimal("167"), "rate_strategy": "BREAKS"
    })

    # Organization with audience matching SELL card
    Organizations.objects.get_or_create(
        id=1,
        defaults=dict(
            name="Test Org",
            country_code="PG",
            audience="B2B",
            default_sell_currency="PGK",
            gst_pct=Decimal("10.00"),
            notes="seeded",
        ),
    )

    # Route and Leg for BNE->LAE IMPORT
    route, _ = Routes.objects.get_or_create(
        name="AU->PG",
        defaults=dict(origin_country="AU", dest_country="PG", shipment_type="IMPORT"),
    )
    RouteLegs.objects.get_or_create(
        route=route, sequence=1, defaults=dict(origin=bne, dest=lae, leg_scope="INTERNATIONAL", service_type="LINEHAUL")
    )


def main():
    ensure_tables()
    seed_minimal()
    print("Minimal API data seeded.")


if __name__ == "__main__":
    main()


