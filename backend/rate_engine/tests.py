from decimal import Decimal

from django.test import TestCase

from .engine import Piece, calculate_chargeable_weight_per_piece, ZERO


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
        # Create minimal schema for unmanaged tables: routes, route_legs
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL,
                    origin_id INTEGER NOT NULL,
                    dest_id INTEGER NOT NULL,
                    leg_scope VARCHAR(32) NOT NULL,
                    service_type VARCHAR(32) NOT NULL,
                    FOREIGN KEY(route_id) REFERENCES routes(id) ON DELETE CASCADE,
                    FOREIGN KEY(origin_id) REFERENCES stations(id),
                    FOREIGN KEY(dest_id) REFERENCES stations(id)
                );
                """
            )

        # Seed core data used by engine
        from django.utils.timezone import now
        from .models import (
            Providers, Stations, Ratecards, RatecardConfig, Lanes, LaneBreaks,
            Services, ServiceItems, Organizations, CurrencyRates, Routes, RouteLegs,
        )

        # Ensure organizations has country_code column (older migration sets may lack it)
        with connection.cursor() as cur:
            cur.execute("PRAGMA table_info('organizations')")
            cols = [row[1] for row in cur.fetchall()]  # cid, name, type, ...
            if 'country_code' not in cols:
                cur.execute("ALTER TABLE organizations ADD COLUMN country_code CHAR(2) DEFAULT 'PG'")

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
            created_at=now(),
            updated_at=now(),
        )
        RatecardConfig.objects.create(ratecard=rc_buy_int, dim_factor_kg_per_m3=Decimal("167"), rate_strategy="BREAKS", created_at=now())

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
            created_at=now(),
            updated_at=now(),
        )
        RatecardConfig.objects.create(ratecard=rc_buy_dom, dim_factor_kg_per_m3=Decimal("167"), rate_strategy="BREAKS", created_at=now())

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
            created_at=now(),
            updated_at=now(),
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
        freight_lines = [l for l in res.buy_lines if l.code == "FREIGHT" and l.is_buy]
        self.assertEqual(len(freight_lines), 2)

        # Totals with CAF-on-FX (6.5%): 200 AUD -> 200*2.5*1.065 = 532.50 PGK; + 100 PGK = 632.50 PGK
        self.assertEqual(res.totals["buy_total"].currency, "PGK")
        self.assertEqual(str(res.totals["buy_total"].amount), "632.50")

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

        # BUY total freight across legs is 632.50 PGK (per previous test).
        # COST_PLUS_PCT 25% => 632.50 * 1.25 = 790.625, then rounded up to nearest 0.05 => 790.65
        expected_sell_amount = Decimal("790.65")
        self.assertEqual(sell_air.extended.amount, expected_sell_amount)
        self.assertEqual(sell_air.extended.currency, "PGK")
