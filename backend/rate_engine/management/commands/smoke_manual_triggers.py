from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.timezone import now
from django.db import connection
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Stations, Providers
from organizations.models import Organizations
from pricing.models import Ratecards, RatecardConfig, Routes, RouteLegs


DDL = [
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
]


class Command(BaseCommand):
    help = "Smoke test for manual trigger scenarios via APIClient (no server needed)."

    def handle(self, *args, **options):
        # Allow APIClient host during this smoke
        try:
            settings.ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
        except Exception:
            pass
        # Ensure minimal tables exist
        with connection.cursor() as cur:
            for sql in DDL:
                try:
                    cur.execute(sql)
                except Exception:
                    connection.rollback()
            cur.execute("ALTER TABLE ratecards ADD COLUMN IF NOT EXISTS commodity_code VARCHAR(8) DEFAULT 'GCR'")
            cur.execute("ALTER TABLE routes ADD COLUMN IF NOT EXISTS requires_manual_rate BOOLEAN DEFAULT FALSE")

        # Seed minimal data
        bne, _ = Stations.objects.get_or_create(iata="BNE", defaults={"city": "Brisbane", "country": "AU"})
        lae, _ = Stations.objects.get_or_create(iata="LAE", defaults={"city": "Lae", "country": "PG"})

        prv, _ = Providers.objects.get_or_create(name="Test Provider", defaults={"provider_type": "CARRIER"})
        today = now().date()
        rc_sell, _ = Ratecards.objects.get_or_create(
            name="SELL IMPORT PG",
            defaults=dict(
                provider=prv,
                role="SELL",
                scope="INTERNATIONAL",
                direction="IMPORT",
                audience="PGK_LOCAL",
                rate_strategy="BREAKS",
                currency="PGK",
                source="CATALOG",
                status="PUBLISHED",
                effective_date=today,
                meta={},
                created_at=now(),
                updated_at=now(),
            ),
        )
        RatecardConfig.objects.get_or_create(ratecard=rc_sell, defaults={
            "dim_factor_kg_per_m3": Decimal("167"), "rate_strategy": "IATA_BREAKS", "created_at": now()
        })

        org, _ = Organizations.objects.get_or_create(
            id=1,
            defaults=dict(
                name="Test Org",
                country_code="PG",
                audience="PGK_LOCAL",
                default_sell_currency="PGK",
                gst_pct=Decimal("10.00"),
                notes="seeded",
            ),
        )

        route, _ = Routes.objects.get_or_create(
            name="AU->PG",
            defaults=dict(origin_country="AU", dest_country="PG", shipment_type="IMPORT"),
        )
        RouteLegs.objects.get_or_create(
            route=route, sequence=1,
            defaults=dict(origin=bne, dest=lae, leg_scope="INTERNATIONAL", service_type="LINEHAUL")
        )

        # Auth setup
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="smoke_user", defaults={"password": "does-not-matter"})
        token, _ = Token.objects.get_or_create(user=user)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        base_payload = {
            "org_id": org.id,
            "origin_iata": "BNE",
            "dest_iata": "LAE",
            "shipment_type": "IMPORT",
            "service_scope": "AIRPORT_AIRPORT",
            "pieces": [{"weight_kg": "100"}],
        }

        cases = [
            ("nonGCR", {**base_payload, "commodity_code": "DGR"}),
            ("urgent", {**base_payload, "is_urgent": True}),
            ("route_flag", base_payload),
        ]

        # Make route flagged only for the last case
        route.requires_manual_rate = False
        route.save()

        results = []
        for name, payload in cases:
            if name == "route_flag":
                Routes.objects.filter(id=route.id).update(requires_manual_rate=True)
            resp = client.post("/api/quote/compute", payload, format="json")
            results.append((name, resp.status_code, resp.json()))

        # Print concise summary
        for name, status, body in results:
            snapshot = body.get("snapshot", {}) if isinstance(body, dict) else {}
            print(f"{name}: status={status}, manual={snapshot.get('manual_rate_required')}, reasons={snapshot.get('manual_reasons')}")

