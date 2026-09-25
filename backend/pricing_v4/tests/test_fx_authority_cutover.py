from decimal import Decimal
from datetime import date, datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from core.dataclasses import LocationRef, Piece, QuoteInput, ShipmentDetails
from core.fx_market_models import FxMarketRate
from core.fx_providers import RateRow
from core.fx_providers.bsp_html import BspHtmlProvider
from core.models import Country, Currency, Location, Airport, City, FxSnapshot
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.services.fx_resolver import (
    AmbiguousFxSourceError,
    MissingFxMarketRateError,
    resolve_market_fx_pair,
)


class FxAuthorityCutoverTests(TestCase):
    """
    Wave 3B3 Verification:
    - FxMarketRate is the sole market authority for new calculations.
    - Missing required FX fails closed (no 0.35, 0.36, 2.50, 2.78, or 1.0 fallbacks).
    - PGK -> PGK quotes require no FX.
    - Friday rate resolves for weekend quotes (effective_date <= quote_date).
    - Future rates never resolve backward.
    - Competing ambiguous sources fail closed.
    - Bid/ask inversion swaps BUY and SELL correctly.
    - Cross currency resolves deterministically via PGK.
    - Import uses TT BUY (CAF deducted).
    - Export uses TT SELL (CAF added).
    - Manual FX updates write to FxMarketRate and preserve FxSnapshot.
    - SPOT foreign currency costs fail closed without FX.
    - Legacy core.FxRate model is completely removed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.pgk, _ = Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina"})
        cls.aud, _ = Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})
        cls.usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar"})

        cls.pg_country, _ = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea", "currency": cls.pgk})
        cls.au_country, _ = Country.objects.get_or_create(code="AU", defaults={"name": "Australia", "currency": cls.aud})

        cls.pom_city, _ = City.objects.get_or_create(name="Port Moresby", country=cls.pg_country)
        cls.bne_city, _ = City.objects.get_or_create(name="Brisbane", country=cls.au_country)

        cls.pom_airport, _ = Airport.objects.get_or_create(iata_code="POM", defaults={"name": "Jacksons International", "city": cls.pom_city})
        cls.bne_airport, _ = Airport.objects.get_or_create(iata_code="BNE", defaults={"name": "Brisbane Airport", "city": cls.bne_city})

        cls.pom_loc, _ = Location.objects.get_or_create(
            airport=cls.pom_airport,
            defaults={"name": "POM Location", "code": "POM", "country": cls.pg_country, "city": cls.pom_city, "is_active": True}
        )
        cls.bne_loc, _ = Location.objects.get_or_create(
            airport=cls.bne_airport,
            defaults={"name": "BNE Location", "code": "BNE", "country": cls.au_country, "city": cls.bne_city, "is_active": True}
        )

        cls.policy = CommercialTermsPolicy.objects.create(
            policy_code="CUTOVER-POLICY",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
            margin_percent=Decimal("20.00"),
            margin_method=CommercialTermsPolicy.MarginMethod.MARKUP_ON_COST,
            import_caf_percent=Decimal("5.00"),
            export_caf_percent=Decimal("10.00"),
            gst_standard_percent=Decimal("10.00"),
            is_active=True,
        )

    def _make_quote_input(
        self,
        shipment_type: str,
        origin_code: str,
        dest_code: str,
        payment_term: str = "PREPAID",
        quote_date: date = date(2026, 6, 1),
        output_currency: str = "PGK",
    ) -> QuoteInput:
        origin_loc = self.pom_loc if origin_code == "POM" else self.bne_loc
        dest_loc = self.pom_loc if dest_code == "POM" else self.bne_loc

        origin_ref = LocationRef(id=origin_loc.id, code=origin_loc.code, name=origin_loc.name, country_code=origin_loc.country.code)
        dest_ref = LocationRef(id=dest_loc.id, code=dest_loc.code, name=dest_loc.name, country_code=dest_loc.country.code)

        shipment = ShipmentDetails(
            mode="AIR",
            shipment_type=shipment_type,
            incoterm="EXW",
            is_dangerous_goods=False,
            origin_location=origin_ref,
            destination_location=dest_ref,
            payment_term=payment_term,
            service_scope="A2A",
            pieces=[Piece(pieces=1, length_cm=Decimal("100"), width_cm=Decimal("100"), height_cm=Decimal("100"), gross_weight_kg=Decimal("100"))]
        )
        return QuoteInput(
            quote_date=quote_date,
            customer_id=uuid4(),
            contact_id=uuid4(),
            output_currency=output_currency,
            shipment=shipment,
        )

    def test_pgk_quote_requires_no_fx(self):
        """Calculations where origin and destination or output is PGK without foreign currency require no FX."""
        FxMarketRate.objects.all().delete()
        FxSnapshot.objects.all().delete()

        result = resolve_market_fx_pair("PGK", "PGK", date(2026, 6, 1))
        self.assertTrue(result.is_identity)
        self.assertEqual(result.tt_buy, Decimal("1.0"))
        self.assertEqual(result.tt_sell, Decimal("1.0"))

    def test_missing_export_fx_fails_closed(self):
        """Export quote requiring FCY output fails closed when no authoritative FX exists."""
        FxMarketRate.objects.all().delete()
        FxSnapshot.objects.all().delete()

        # POM -> BNE, COLLECT resolves to AUD output currency
        qi = self._make_quote_input("EXPORT", "POM", "BNE", payment_term="COLLECT", output_currency="AUD")
        adapter = PricingServiceV4Adapter(qi)

        with self.assertRaises(MissingFxMarketRateError) as ctx:
            adapter.calculate_charges()
        self.assertIn("AUD->PGK on or before 2026-06-01", str(ctx.exception))

    def test_missing_import_fx_fails_closed(self):
        """Import quote requiring FCY output fails closed when no authoritative FX exists."""
        FxMarketRate.objects.all().delete()
        FxSnapshot.objects.all().delete()

        # BNE -> POM, PREPAID resolves to AUD output currency
        qi = self._make_quote_input("IMPORT", "BNE", "POM", payment_term="PREPAID", output_currency="AUD")
        adapter = PricingServiceV4Adapter(qi)

        with self.assertRaises(MissingFxMarketRateError) as ctx:
            adapter.calculate_charges()
        self.assertIn("AUD->PGK on or before 2026-06-01", str(ctx.exception))

    def test_friday_rate_resolves_for_weekend_quote(self):
        """Friday rate resolves for Saturday/Sunday quote dates per Decision 1."""
        FxMarketRate.objects.all().delete()
        friday = date(2026, 5, 29)
        saturday = date(2026, 5, 30)
        sunday = date(2026, 5, 31)

        FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=friday,
            tt_buy_rate=Decimal("2.45100000"),
            tt_sell_rate=Decimal("2.52100000"),
            mid_rate=Decimal("2.48600000"),
            source="BSP_OFFICIAL",
        )

        res_sat = resolve_market_fx_pair("AUD", "PGK", saturday)
        self.assertEqual(res_sat.effective_date, friday)
        self.assertEqual(res_sat.tt_buy, Decimal("2.45100000"))

        res_sun = resolve_market_fx_pair("AUD", "PGK", sunday)
        self.assertEqual(res_sun.effective_date, friday)
        self.assertEqual(res_sun.tt_buy, Decimal("2.45100000"))

    def test_future_rate_never_resolves_backward(self):
        """Future market rates are never used backward."""
        FxMarketRate.objects.all().delete()
        friday = date(2026, 5, 29)
        thursday = date(2026, 5, 28)

        FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=friday,
            tt_buy_rate=Decimal("2.45100000"),
            tt_sell_rate=Decimal("2.52100000"),
            mid_rate=Decimal("2.48600000"),
            source="BSP_OFFICIAL",
        )

        with self.assertRaises(MissingFxMarketRateError):
            resolve_market_fx_pair("AUD", "PGK", thursday)

    def test_ambiguous_competing_sources_fail_closed(self):
        """Multiple competing sources on the same date fail closed without explicit source."""
        FxMarketRate.objects.all().delete()
        the_date = date(2026, 6, 1)

        FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=the_date,
            tt_buy_rate=Decimal("2.45000000"),
            tt_sell_rate=Decimal("2.52000000"),
            mid_rate=Decimal("2.48500000"),
            source="SOURCE_A",
        )
        FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=the_date,
            tt_buy_rate=Decimal("2.46000000"),
            tt_sell_rate=Decimal("2.53000000"),
            mid_rate=Decimal("2.49500000"),
            source="SOURCE_B",
        )

        with self.assertRaises(AmbiguousFxSourceError):
            resolve_market_fx_pair("AUD", "PGK", the_date)

        # Explicit source succeeds
        res_a = resolve_market_fx_pair("AUD", "PGK", the_date, source="SOURCE_A")
        self.assertEqual(res_a.source, "SOURCE_A")
        self.assertEqual(res_a.tt_buy, Decimal("2.45000000"))

    def test_inverse_conversion_swaps_buy_and_sell(self):
        """
        Inverting AUD/PGK (base=AUD, quote=PGK) to PGK/AUD:
        inverse TT BUY  = 1 / original TT SELL
        inverse TT SELL = 1 / original TT BUY
        """
        FxMarketRate.objects.all().delete()
        the_date = date(2026, 6, 1)

        FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=the_date,
            tt_buy_rate=Decimal("2.00000000"),
            tt_sell_rate=Decimal("2.50000000"),
            mid_rate=Decimal("2.25000000"),
            source="BSP_OFFICIAL",
        )

        inv = resolve_market_fx_pair("PGK", "AUD", the_date)
        self.assertTrue(inv.is_inverse)
        self.assertEqual(inv.tt_buy, Decimal("0.40000000"))
        self.assertEqual(inv.tt_sell, Decimal("0.50000000"))

    def test_cross_currency_via_pgk(self):
        """Cross-currency A -> B resolves deterministically via PGK."""
        FxMarketRate.objects.all().delete()
        the_date = date(2026, 6, 1)

        # AUD/PGK: 1 AUD = 2.0 PGK
        FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=the_date,
            tt_buy_rate=Decimal("2.00000000"),
            tt_sell_rate=Decimal("2.20000000"),
            mid_rate=Decimal("2.10000000"),
            source="BSP",
        )
        # USD/PGK: 1 USD = 4.0 PGK
        FxMarketRate.objects.create(
            base_currency="USD",
            quote_currency="PGK",
            effective_date=the_date,
            tt_buy_rate=Decimal("4.00000000"),
            tt_sell_rate=Decimal("4.40000000"),
            mid_rate=Decimal("4.20000000"),
            source="BSP",
        )

        # Cross AUD -> USD:
        # Leg 1: AUD -> PGK (buy: 2.0, sell: 2.2)
        # Leg 2: PGK -> USD (inverse of USD/PGK: buy = 1/4.4 = 0.22727273, sell = 1/4.0 = 0.25)
        cross = resolve_market_fx_pair("AUD", "USD", the_date)
        self.assertTrue(cross.is_cross)
        self.assertEqual(cross.from_currency, "AUD")
        self.assertEqual(cross.to_currency, "USD")
        self.assertIsNotNone(cross.cross_details)

    def test_manual_fx_update_creates_fx_market_rate_and_preserves_snapshot(self):
        """Manual FX entry endpoint creates FxMarketRate and FxSnapshot with full provenance."""
        User = get_user_model()
        user = User.objects.create_user(username="fin_admin", password="password", role="finance")
        client = APIClient()
        client.force_authenticate(user=user)

        FxMarketRate.objects.all().delete()
        FxSnapshot.objects.all().delete()

        url = "/api/v4/fx/manual-update/"
        payload = {
            "rates": {
                "AUD": {"tt_buy": "2.7700", "tt_sell": "2.8500"},
                "USD": {"tt_buy": "3.8500", "tt_sell": "3.9500"},
            },
            "effective_date": "2026-05-29",
            "note": "Manual entry test for Wave 3B3"
        }
        recorded_at = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        with patch("core.fx_views.timezone.now", return_value=recorded_at):
            response = client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["effective_date"], "2026-05-29")
        self.assertEqual(response.data["timestamp"], recorded_at.isoformat())

        # Verify FxMarketRate records created
        aud_market = FxMarketRate.objects.get(base_currency="AUD", quote_currency="PGK")
        self.assertEqual(aud_market.tt_buy_rate, Decimal("2.77000000"))
        self.assertEqual(aud_market.tt_sell_rate, Decimal("2.85000000"))
        self.assertEqual(aud_market.source, "MANUAL")
        self.assertEqual(aud_market.effective_date, date(2026, 5, 29))

        usd_market = FxMarketRate.objects.get(base_currency="USD", quote_currency="PGK")
        self.assertEqual(usd_market.tt_buy_rate, Decimal("3.85000000"))
        self.assertEqual(usd_market.tt_sell_rate, Decimal("3.95000000"))
        self.assertEqual(usd_market.effective_date, date(2026, 5, 29))

        # Verify FxSnapshot was also created (historical preservation)
        self.assertEqual(FxSnapshot.objects.count(), 1)
        snapshot = FxSnapshot.objects.first()
        self.assertIn("AUD", snapshot.rates)
        self.assertIn("USD", snapshot.rates)
        self.assertIn("fin_admin", snapshot.source)
        self.assertEqual(snapshot.as_of_timestamp, recorded_at)

    def test_manual_fx_update_requires_market_effective_date(self):
        User = get_user_model()
        user = User.objects.create_user(username="fin_no_date", password="password", role="finance")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post("/api/v4/fx/manual-update/", {
            "rates": {"AUD": {"tt_buy": "2.77", "tt_sell": "2.85"}},
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("effective_date", response.data)
        self.assertFalse(FxMarketRate.objects.exists())
        self.assertFalse(FxSnapshot.objects.exists())

    def test_quote_audit_uses_market_provenance_and_preserves_old_snapshot(self):
        old = FxSnapshot.objects.create(
            as_of_timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc),
            source="HISTORICAL",
            rates={"AUD": {"tt_buy": "1.00", "tt_sell": "1.10"}},
        )
        FxMarketRate.objects.create(
            base_currency="AUD", quote_currency="PGK", effective_date=date(2026, 5, 29),
            tt_buy_rate=Decimal("2.00"), tt_sell_rate=Decimal("2.20"),
            mid_rate=Decimal("2.10"), source="BSP",
        )
        adapter = PricingServiceV4Adapter(self._make_quote_input("IMPORT", "BNE", "POM"))
        adapter._capture_fx_audit(
            applied=True, from_currency="AUD", to_currency="PGK",
            base_rate_type="TT_BUY", base_rate=Decimal("2.00"),
            caf_percent=Decimal("0.05"), caf_operation="DEDUCTED",
            effective_rate_after_caf=Decimal("1.90"),
        )
        audit = adapter._audit_metadata["fx_audit"]
        self.assertEqual(audit["fx_market_source"], "BSP")
        self.assertEqual(audit["fx_market_effective_date"], "2026-05-29")
        self.assertEqual(audit["fx_stored_pair"], "AUD/PGK")
        self.assertEqual(audit["fx_raw_rate"], "2.00000000")
        self.assertEqual(audit["effective_rate_after_caf"], "1.90")
        old.refresh_from_db()
        self.assertEqual(old.rates["AUD"], {"tt_buy": "1.00", "tt_sell": "1.10"})

    def test_spot_foreign_currency_fails_closed_without_fx(self):
        """SPOT foreign currency conversion in adapter fails closed without authoritative FX."""
        FxMarketRate.objects.all().delete()
        FxSnapshot.objects.all().delete()

        qi = self._make_quote_input("IMPORT", "BNE", "POM", payment_term="COLLECT")
        adapter = PricingServiceV4Adapter(qi)

        with self.assertRaises(MissingFxMarketRateError):
            adapter._get_fx_buy_rate("USD", {})

        with self.assertRaises(MissingFxMarketRateError):
            adapter._get_fx_sell_rate("USD", {})

    def test_no_legacy_fx_rate_model_exists(self):
        """Verify core.FxRate model has been removed from Django registry."""
        from django.apps import apps
        with self.assertRaises(LookupError):
            apps.get_model("core", "FxRate")

    def test_fetch_writes_complete_market_fact_without_rewriting_history(self):
        old = FxSnapshot.objects.create(
            as_of_timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc),
            source="HISTORICAL",
            rates={"AUD": {"tt_buy": "2.10", "tt_sell": "2.20"}},
        )
        fetched_at = datetime(2026, 5, 30, 12, tzinfo=timezone.utc)
        bank_date = date(2026, 5, 29)
        rows = [
            RateRow(fetched_at, "AUD", "PGK", Decimal("2.45"), "BUY", "BSP", bank_date),
            RateRow(fetched_at, "AUD", "PGK", Decimal("2.52"), "SELL", "BSP", bank_date),
        ]
        with patch("core.management.commands.fetch_fx.load_provider", return_value=Mock(fetch=Mock(return_value=rows))):
            call_command("fetch_fx", pairs="AUD:PGK")

        market = FxMarketRate.objects.get(base_currency="AUD", quote_currency="PGK", source="BSP")
        self.assertEqual((market.tt_buy_rate, market.tt_sell_rate), (Decimal("2.45"), Decimal("2.52")))
        self.assertEqual(market.effective_date, bank_date)
        self.assertFalse(FxMarketRate.objects.filter(effective_date=fetched_at.date()).exists())
        self.assertEqual(resolve_market_fx_pair("AUD", "PGK", date(2026, 5, 30)).effective_date, bank_date)
        self.assertEqual(resolve_market_fx_pair("AUD", "PGK", date(2026, 5, 31)).effective_date, bank_date)
        old.refresh_from_db()
        self.assertEqual(old.rates["AUD"], {"tt_buy": "2.10", "tt_sell": "2.20"})
        self.assertEqual(FxSnapshot.objects.count(), 2)
        self.assertEqual(FxSnapshot.objects.exclude(pk=old.pk).get().as_of_timestamp, fetched_at)

    def test_fetch_rejects_incomplete_tt_pair_without_writing(self):
        row = RateRow(
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            "AUD", "PGK", Decimal("2.45"), "BUY", "BSP", date(2026, 6, 1),
        )
        with patch("core.management.commands.fetch_fx.load_provider", return_value=Mock(fetch=Mock(return_value=[row]))):
            with self.assertRaises(CommandError):
                call_command("fetch_fx", pairs="AUD:PGK")
        self.assertFalse(FxMarketRate.objects.exists())
        self.assertFalse(FxSnapshot.objects.exists())

    def test_bsp_page_date_is_used_instead_of_fetch_date(self):
        html = """
        <section rel="CBCurrenciesTable">
          <header><h2>Exchange rates for Kina<time>Fri, 29 May 2026</time></h2></header>
          <table><thead><tr><th>Currency</th><th>Code</th><th>TT Buy</th>
            <th>Notes Buy</th><th>A/M Buy</th><th>TT Sell</th><th>Notes Sell</th></tr></thead>
            <tbody><tr><td>Australian Dollar</td><td>AUD</td><td>0.4000</td>
              <td>0</td><td>0</td><td>0.3900</td><td>0</td></tr></tbody>
          </table>
        </section>
        """
        provider = BspHtmlProvider()
        with patch.object(provider, "_fetch_html", return_value=html):
            rows = provider.fetch(["PGK:AUD"])
        self.assertEqual(len(rows), 2)
        self.assertEqual({row.effective_date for row in rows}, {date(2026, 5, 29)})
        self.assertEqual(len({row.observed_at for row in rows}), 1)

    def test_bsp_page_without_published_date_fails_closed(self):
        html = """
        <section rel="CBCurrenciesTable"><table><thead><tr>
          <th>TT Buy</th><th>TT Sell</th></tr></thead></table></section>
        """
        provider = BspHtmlProvider()
        with patch.object(provider, "_fetch_html", return_value=html):
            with self.assertRaisesRegex(RuntimeError, "effective date missing"):
                provider.fetch(["PGK:AUD"])
