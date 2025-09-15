from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.utils import timezone
from rate_engine.models import Organizations
from accounts.models import OrganizationMembership
from django.db.utils import ProgrammingError, OperationalError


class ComputeAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()

        # Create users with roles
        self.manager = self.User.objects.create_user(username='manager_user', password='pass', role='manager', email='manager@example.com')
        self.finance = self.User.objects.create_user(username='finance_user', password='pass', role='finance', email='finance@example.com')
        self.sales = self.User.objects.create_user(username='sales_user', password='pass', role='sales', email='sales@example.com')

        # Try to find or create a simple organization for testing
        try:
            org = Organizations.objects.order_by('id').first()
            if not org:
                # If schema is available with managed=False, this save will work when table exists
                org = Organizations.objects.create(name=f"Test Org {timezone.now().timestamp()}", audience='b2b', default_sell_currency='PGK', gst_pct='0.00', country_code='PG')
            self.org = org
        except (ProgrammingError, OperationalError):
            # Managed=False tables not present in this DB -> skip these auth tests
            self.skipTest('Organizations schema not available; load schema to run auth tests')

        # Minimal valid compute payload (engine may still reject, which is fine for auth tests)
        self.payload = {
            "org_id": self.org.id,
            "origin_iata": "BNE",
            "dest_iata": "LAE",
            "shipment_type": "IMPORT",
            "service_scope": "AIRPORT_AIRPORT",
            "pieces": [{"weight_kg": "1"}],
        }

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_manager_authorized(self):
        self._auth(self.manager)
        res = self.client.post('/api/quote/compute', data=self.payload, format='json')
        # Authorization should pass; engine may return 201 or 400 depending on data
        self.assertNotEqual(res.status_code, 403)

    def test_sales_unauthorized_without_membership(self):
        self._auth(self.sales)
        res = self.client.post('/api/quote/compute', data=self.payload, format='json')
        self.assertEqual(res.status_code, 403)

    def test_sales_authorized_with_membership(self):
        # Link sales user to org via explicit membership with can_quote
        OrganizationMembership.objects.create(user=self.sales, organization_id=self.org.id, role='sales', can_quote=True)
        self._auth(self.sales)
        res = self.client.post('/api/quote/compute', data=self.payload, format='json')
        self.assertNotEqual(res.status_code, 403)

    def test_sales_forbidden_with_membership_without_quote(self):
        OrganizationMembership.objects.create(user=self.sales, organization_id=self.org.id, role='sales', can_quote=False)
        self._auth(self.sales)
        res = self.client.post('/api/quote/compute', data=self.payload, format='json')
        self.assertEqual(res.status_code, 403)

from .engine import Piece, calculate_chargeable_weight_per_piece, ZERO
from .engine import FxConverter
from django.utils.timezone import now


class ChargeableWeightTests(TestCase):
    def test_per_piece_chargeable_and_whole_kg_rounding(self):
        # dim factor typical for air freight using m3 -> kg
        dim_factor = Decimal("167")

        # Piece A: actual 10.0 kg, dims give volumetric 10.02 kg -> use 10.02
        a = Piece(weight_kg=Decimal("10.0"), length_cm=Decimal("50"), width_cm=Decimal("40"), height_cm=Decimal("30"))

        # Piece B: actual 5.0 kg, dims give volumetric 16.032 kg -> use 16.032
        b = Piece(weight_kg=Decimal("5.0"), length_cm=Decimal("60"), width_cm=Decimal("40"), height_cm=Decimal("40"))

        total = calculate_chargeable_weight_per_piece([a, b], dim_factor)

        # Sum before rounding = 10.02 + 16.032 = 26.052
        # Rounded up to next whole kg => 27
        self.assertEqual(total, Decimal("27"))

    def test_empty_and_missing_dimensions(self):
        dim_factor = Decimal("167")

        # Empty pieces -> ZERO
        self.assertEqual(calculate_chargeable_weight_per_piece([], dim_factor), ZERO)

        # Missing dimensions -> volumetric 0, so use actual
        p = Piece(weight_kg=Decimal("10"))
        self.assertEqual(calculate_chargeable_weight_per_piece([p], dim_factor), Decimal("10"))

    def test_exact_integer_total_not_rounded_up(self):
        dim_factor = Decimal("167")
        p1 = Piece(weight_kg=Decimal("12"))
        p2 = Piece(weight_kg=Decimal("8"))
        total = calculate_chargeable_weight_per_piece([p1, p2], dim_factor)
        self.assertEqual(total, Decimal("20"))

    def test_slightly_above_integer_rounds_up(self):
        dim_factor = Decimal("167")
        p1 = Piece(weight_kg=Decimal("12"))
        p2 = Piece(weight_kg=Decimal("8"))
        p3 = Piece(weight_kg=Decimal("0.001"))
        total = calculate_chargeable_weight_per_piece([p1, p2, p3], dim_factor)
        self.assertEqual(total, Decimal("21"))


class MultiLegRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create minimal schema for unmanaged tables used in tests (PostgreSQL-compatible)
        from django.db import connection
        with connection.cursor() as cur:
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
                # Ratecard-related tables
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
                CREATE TABLE IF NOT EXISTS lanes (
                    id BIGSERIAL PRIMARY KEY,
                    ratecard_id INTEGER REFERENCES ratecards(id),
                    origin_id INTEGER REFERENCES stations(id),
                    dest_id INTEGER REFERENCES stations(id),
                    via_id INTEGER REFERENCES stations(id),
                    airline TEXT,
                    is_direct BOOLEAN
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS lane_breaks (
                    id BIGSERIAL PRIMARY KEY,
                    lane_id INTEGER REFERENCES lanes(id),
                    break_code TEXT,
                    per_kg NUMERIC(12,4),
                    min_charge NUMERIC(12,2)
                );
                """,
                # Fees & services
                """
                CREATE TABLE IF NOT EXISTS fee_types (
                    id BIGSERIAL PRIMARY KEY,
                    code TEXT UNIQUE,
                    description TEXT,
                    basis TEXT,
                    default_tax_pct NUMERIC(5,2)
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS ratecard_fees (
                    id BIGSERIAL PRIMARY KEY,
                    ratecard_id INTEGER REFERENCES ratecards(id),
                    fee_type_id INTEGER REFERENCES fee_types(id),
                    currency TEXT,
                    amount NUMERIC(12,4),
                    min_amount NUMERIC(12,2),
                    max_amount NUMERIC(12,2),
                    percent_of_code TEXT,
                    per_kg_threshold NUMERIC(12,2),
                    applies_if JSONB,
                    notes TEXT,
                    created_at TIMESTAMP
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS services (
                    id BIGSERIAL PRIMARY KEY,
                    code TEXT UNIQUE,
                    name TEXT,
                    basis TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS service_items (
                    id BIGSERIAL PRIMARY KEY,
                    ratecard_id INTEGER REFERENCES ratecards(id),
                    service_id INTEGER REFERENCES services(id),
                    currency TEXT,
                    amount NUMERIC(12,4),
                    min_amount NUMERIC(12,2),
                    max_amount NUMERIC(12,2),
                    percent_of_service_code TEXT,
                    tax_pct NUMERIC(5,2),
                    item_code TEXT,
                    conditions_json JSONB
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS sell_cost_links_simple (
                    id BIGSERIAL PRIMARY KEY,
                    sell_item_id INTEGER REFERENCES service_items(id),
                    buy_fee_code TEXT,
                    mapping_type TEXT,
                    mapping_value NUMERIC(12,4)
                );
                """,
                # Organizations and FX
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
                CREATE TABLE IF NOT EXISTS currency_rates (
                    id BIGSERIAL PRIMARY KEY,
                    as_of_ts TIMESTAMP,
                    base_ccy TEXT,
                    quote_ccy TEXT,
                    rate NUMERIC(18,8),
                    rate_type VARCHAR(8) DEFAULT 'BUY',
                    source TEXT
                );
                """,
                # Pricing policy
                """
                CREATE TABLE IF NOT EXISTS pricing_policy (
                    id BIGSERIAL PRIMARY KEY,
                    audience TEXT UNIQUE,
                    caf_on_fx BOOLEAN,
                    gst_applies BOOLEAN,
                    gst_pct NUMERIC(5,2)
                );
                """,
                # Routing tables
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
            for sql in ddls:
                try:
                    cur.execute(sql)
                except Exception:
                    # If a statement fails, rollback and continue; tables may already exist
                    connection.rollback()
                    continue

        # Seed core data used by engine
        from django.utils.timezone import now
        from .models import (
            Providers, Stations, Ratecards, RatecardConfig, Lanes, LaneBreaks,
            Services, ServiceItems, Organizations, CurrencyRates, Routes, RouteLegs,
        )

        # Ensure organizations has country_code column (older migration sets may lack it)
        # Use a DB-agnostic approach: try to add the column and ignore if it already exists.
        with connection.cursor() as cur:
            # Postgres-friendly: add the column only if it doesn't exist
            cur.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS country_code CHAR(2) DEFAULT 'PG'")
            # Ensure new columns used by engine exist for unmanaged tables
            cur.execute("ALTER TABLE ratecards ADD COLUMN IF NOT EXISTS commodity_code VARCHAR(8) DEFAULT 'GCR'")
            cur.execute("ALTER TABLE routes ADD COLUMN IF NOT EXISTS requires_manual_rate BOOLEAN DEFAULT FALSE")

        # Stations
        bne, _ = Stations.objects.get_or_create(iata="BNE", defaults={"city": "Brisbane", "country": "AU"})
        pom, _ = Stations.objects.get_or_create(iata="POM", defaults={"city": "Port Moresby", "country": "PG"})
        lae, _ = Stations.objects.get_or_create(iata="LAE", defaults={"city": "Lae", "country": "PG"})

        # Provider
        prv = Providers.objects.create(name="Test Provider", provider_type="AIR")

        today = now().date()

        # BUY ratecards
        rc_buy_int = Ratecards.objects.create(
            provider=prv,
            name="BUY INT",
            role="BUY",
            scope="INTERNATIONAL",
            direction="EXPORT",
            audience=None,
            rate_strategy="BREAKS",
            currency="AUD",
            source="TEST",
            status="ACTIVE",
            effective_date=today,
            expiry_date=None,
            notes="",
            meta={},
        )
        RatecardConfig.objects.create(ratecard=rc_buy_int, dim_factor_kg_per_m3=Decimal("167"), rate_strategy="BREAKS")

        rc_buy_dom = Ratecards.objects.create(
            provider=prv,
            name="BUY DOM",
            role="BUY",
            scope="DOMESTIC",
            direction="DOMESTIC",
            audience=None,
            rate_strategy="BREAKS",
            currency="PGK",
            source="TEST",
            status="ACTIVE",
            effective_date=today,
            expiry_date=None,
            notes="",
            meta={},
        )
        RatecardConfig.objects.create(ratecard=rc_buy_dom, dim_factor_kg_per_m3=Decimal("167"), rate_strategy="BREAKS")

        # Lanes and breaks
        ln1 = Lanes.objects.create(ratecard=rc_buy_int, origin=bne, dest=pom, via=None, airline=None, is_direct=True)
        LaneBreaks.objects.create(lane=ln1, break_code="N", per_kg=Decimal("2.00"))

        ln2 = Lanes.objects.create(ratecard=rc_buy_dom, origin=pom, dest=lae, via=None, airline=None, is_direct=True)
        LaneBreaks.objects.create(lane=ln2, break_code="N", per_kg=Decimal("1.00"))

        # SELL ratecard (minimal) in PGK for IMPORT direction and audience=B2B
        rc_sell = Ratecards.objects.create(
            provider=prv,
            name="SELL IMPORT PG",
            role="SELL",
            scope="INTERNATIONAL",
            direction="IMPORT",
            audience="B2B",
            rate_strategy="BREAKS",
            currency="PGK",
            source="TEST",
            status="ACTIVE",
            effective_date=today,
            expiry_date=None,
            notes="",
            meta={},
        )
        # Expose for tests
        cls.sell_card_pgk = rc_sell
        # Minimal service to keep SELL logic happy (no items required)
        Services.objects.create(code="AIR_FREIGHT", name="Air Freight", basis="PER_KG")
        # No ServiceItems => no SELL lines, acceptable for this test

        # FX: AUD->PGK
        CurrencyRates.objects.create(as_of_ts=now(), base_ccy="AUD", quote_ccy="PGK", rate=Decimal("2.50"), source="TEST")

        # Organization (PG) selects sell currency PGK and audience B2B
        cls.org = Organizations.objects.create(
            name="Test Org",
            country_code="PG",
            audience="B2B",
            default_sell_currency="PGK",
            gst_pct=Decimal("0.10"),
            disbursement_min=None,
            disbursement_cap=None,
            notes="",
        )

        # Route and legs: AU -> PG (BNE->POM, POM->LAE)
        cls.route = Routes.objects.create(name="AU to Lae", origin_country="AU", dest_country="PG", shipment_type="IMPORT")
        RouteLegs.objects.create(route=cls.route, sequence=1, origin=bne, dest=pom, leg_scope="INTERNATIONAL", service_type="LINEHAUL")
        RouteLegs.objects.create(route=cls.route, sequence=2, origin=pom, dest=lae, leg_scope="DOMESTIC", service_type="LINEHAUL")

    def test_multi_leg_buy_aggregation(self):
        from .engine import compute_quote, ShipmentInput

        payload = ShipmentInput(
            org_id=self.org.id,
            origin_iata="BNE",
            dest_iata="LAE",
            shipment_type="IMPORT",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=Decimal("100"))],
        )

        res = compute_quote(payload)

        # Expect two freight buy lines (one per leg)
        freight_lines = [l for l in res.buy_lines if l.code == "FREIGHT" and l.line_type == "BUY"]
        self.assertEqual(len(freight_lines), 2)

        # Totals with directional CAF-on-FX (6.5% subtract to PGK):
        # 200 AUD -> 200 * (2.50 * (1 - 0.065)) = 467.50 PGK; + 100 PGK = 567.50 PGK
        self.assertEqual(res.totals["buy_total"].currency, "PGK")
        self.assertEqual(str(res.totals["buy_total"].amount), "567.50")

        # Snapshot includes route and legs_breaks entries
        self.assertIsNotNone(res.snapshot.get("route"))
        self.assertEqual(len(res.snapshot.get("legs_breaks") or []), 2)
        self.assertEqual(res.snapshot.get("chargeable_kg"), 100.0)

    def test_sell_mapping_cost_plus_for_multi_leg_freight(self):
        """
        Validates that a COST_PLUS_PCT SELL rule correctly applies its margin
        to the SUM of the BUY freight costs from all legs.
        """
        from .engine import compute_quote, ShipmentInput
        from .models import (
            Services as Service,
            ServiceItems as ServiceItem,
            FeeTypes as FeeType,
            SellCostLinksSimple as SellCostLink,
        )

        # 1) SELL ServiceItem for AIR_FREIGHT (PGK currency)
        air_freight_service, _ = Service.objects.get_or_create(
            code="AIR_FREIGHT", defaults={"name": "Air Freight", "basis": "PER_KG"}
        )
        sell_item = ServiceItem.objects.create(
            ratecard=self.sell_card_pgk,
            service=air_freight_service,
            currency="PGK",
            tax_pct=Decimal("0.00"),
            conditions_json={},
        )

        # 2) Link SELL item to aggregated BUY freight with 25% margin
        freight_fee_type, _ = FeeType.objects.get_or_create(
            code="FREIGHT",
            defaults={"description": "Generic Freight Cost", "basis": "VARIES", "default_tax_pct": Decimal("0")},
        )
        SellCostLink.objects.create(
            sell_item=sell_item,
            buy_fee_code=freight_fee_type,
            mapping_type="COST_PLUS_PCT",
            mapping_value=Decimal("0.25"),  # 25% margin
        )

        # 3) Execute compute
        payload = ShipmentInput(
            org_id=self.org.id,
            origin_iata="BNE",
            dest_iata="LAE",
            shipment_type="IMPORT",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=Decimal("100"))],
        )
        result = compute_quote(payload)

        # 4) Assert SELL line exists and amount is correct
        sell_air = next((line for line in result.sell_lines if line.code == "AIR_FREIGHT"), None)
        self.assertIsNotNone(sell_air, "SELL line for AIR_FREIGHT should exist.")

        # BUY total freight across legs is 567.50 PGK (per previous test).
        # COST_PLUS_PCT 25% => 567.50 * 1.25 = 709.375, then rounded up to nearest 0.05 => 709.40
        expected_sell_amount = Decimal("709.40")
        self.assertEqual(sell_air.extended.amount, expected_sell_amount)
        self.assertEqual(sell_air.extended.currency, "PGK")


class FxConverterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.db import connection
        # Ensure currency_rates exists for unmanaged model on test DB
        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS currency_rates (
                    id BIGSERIAL PRIMARY KEY,
                    as_of_ts TIMESTAMP,
                    base_ccy TEXT,
                    quote_ccy TEXT,
                    rate NUMERIC(18,8),
                    rate_type VARCHAR(8) DEFAULT 'BUY',
                    source TEXT
                );
                """
            )
        from .models import CurrencyRates
        # Ensure we have both BUY and SELL sample rates
        CurrencyRates.objects.create(
            as_of_ts=now(), base_ccy="AUD", quote_ccy="PGK", rate=Decimal("2.50"), rate_type="BUY", source="TEST"
        )
        CurrencyRates.objects.create(
            as_of_ts=now(), base_ccy="PGK", quote_ccy="USD", rate=Decimal("0.27000000"), rate_type="SELL", source="TEST"
        )

    def test_rate_to_pgk_uses_buy_and_subtracts_caf(self):
        fx = FxConverter(caf_on_fx=True, caf_pct=Decimal("0.10"))
        r = fx.rate("AUD", "PGK", at=now())
        # BUY 2.50 with CAF 10% subtracted => 2.25
        self.assertEqual(r, Decimal("2.25"))

    def test_rate_from_pgk_uses_sell_and_adds_caf(self):
        fx = FxConverter(caf_on_fx=True, caf_pct=Decimal("0.10"))
        r = fx.rate("PGK", "USD", at=now())
        # SELL 0.27 with CAF 10% added => 0.29700000
        self.assertEqual(r, Decimal("0.29700000"))

    def test_rate_caf_disabled_returns_raw(self):
        fx = FxConverter(caf_on_fx=False, caf_pct=Decimal("0.15"))
        r1 = fx.rate("AUD", "PGK", at=now())
        r2 = fx.rate("PGK", "USD", at=now())
        self.assertEqual(r1, Decimal("2.50"))
        self.assertEqual(r2, Decimal("0.27000000"))


class ManualTriggerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Minimal schema and data to exercise compute_leg_cost manual checks
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS stations (
                    id BIGSERIAL PRIMARY KEY,
                    iata TEXT UNIQUE,
                    city TEXT,
                    country TEXT
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS routes (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT UNIQUE,
                    origin_country CHAR(2) NOT NULL,
                    dest_country CHAR(2) NOT NULL,
                    shipment_type VARCHAR(16) NOT NULL
                );
                """
            )
            cur.execute(
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
                """
            )
            # Add new columns if not present
            try:
                cur.execute("ALTER TABLE routes ADD COLUMN IF NOT EXISTS requires_manual_rate BOOLEAN DEFAULT FALSE")
            except Exception:
                connection.rollback()

        from .models import Stations as Station, Routes as Route, RouteLegs as RouteLeg

        # Seed stations and simple route
        cls.bne = Station.objects.create(iata="BNE", city="Brisbane", country="AU")
        cls.lae = Station.objects.create(iata="LAE", city="Lae", country="PG")
        cls.route = Route.objects.create(name="AU->PG", origin_country="AU", dest_country="PG", shipment_type="IMPORT")
        cls.leg = RouteLeg.objects.create(route=cls.route, sequence=1, origin=cls.bne, dest=cls.lae, leg_scope="INTERNATIONAL", service_type="LINEHAUL")

    def _make_payload(self, **overrides):
        from .engine import ShipmentInput, Piece
        base = dict(
            org_id=1,
            origin_iata="BNE",
            dest_iata="LAE",
            shipment_type="IMPORT",
            service_scope="AIRPORT_AIRPORT",
            pieces=[Piece(weight_kg=Decimal("100"))],
            commodity_code="GCR",
            is_urgent=False,
        )
        base.update(overrides)
        return ShipmentInput(**base)

    def _run_leg(self, payload):
        from .engine import compute_leg_cost, FxConverter
        return compute_leg_cost(
            leg=self.leg,
            chargeable_kg=Decimal("100"),
            shipment_payload=payload,
            fx=FxConverter(caf_on_fx=True, caf_pct=Decimal("0.065")),
            sell_currency="PGK",
            ts=now(),
        )

    def test_non_gcr_triggers_manual(self):
        payload = self._make_payload(commodity_code="DGR")
        lines, ctx, is_manual, reason = self._run_leg(payload)
        self.assertTrue(is_manual)
        self.assertIn("Specific Cargo", reason)
        self.assertTrue(any(l.code == "FREIGHT_MANUAL_RATE" for l in lines))
        # Ensure meta marks manual
        m = next(l.meta for l in lines if l.code == "FREIGHT_MANUAL_RATE")
        self.assertTrue(m.get("manual_rate_required"))

    def test_urgent_triggers_manual(self):
        payload = self._make_payload(is_urgent=True)
        lines, ctx, is_manual, reason = self._run_leg(payload)
        self.assertTrue(is_manual)
        self.assertIn("Urgent", reason)
        self.assertTrue(any(l.code == "FREIGHT_MANUAL_RATE" for l in lines))

    def test_route_flag_triggers_manual(self):
        # Flip the route flag on
        from .models import Routes as Route
        r = Route.objects.get(id=self.route.id)
        # Direct SQL update in case unmanaged model ignores save side-effects
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("UPDATE routes SET requires_manual_rate = TRUE WHERE id = %s", [r.id])

        payload = self._make_payload()
        # Ensure our in-memory leg reflects the flag to avoid lane lookups
        from .models import RouteLegs as RouteLeg
        self.leg = RouteLeg.objects.get(id=self.leg.id)
        # Set attribute defensively (unmanaged models may not refresh relations immediately)
        if hasattr(self.leg, 'route'):
            try:
                self.leg.route.requires_manual_rate = True
            except Exception:
                pass

        lines, ctx, is_manual, reason = self._run_leg(payload)
        self.assertTrue(is_manual)
        self.assertIn("Route flagged", reason)
        self.assertTrue(any(l.code == "FREIGHT_MANUAL_RATE" for l in lines))
