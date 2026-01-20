from django.test import TestCase
from unittest.mock import MagicMock, patch
from decimal import Decimal
from uuid import uuid4
from datetime import datetime, timedelta
from django.utils import timezone

from pricing_v4.adapter import PricingServiceV4Adapter, PricingMode
from core.dataclasses import CalculatedChargeLine, QuoteInput
from quotes.models import SpotPricingEnvelopeDB, SPEChargeLineDB, SPEAcknowledgementDB
from services.models import ServiceComponent

class HybridPricingTest(TestCase):
    def setUp(self):
        # Create a dummy quote input
        self.quote_input = MagicMock(spec=QuoteInput)
        self.quote_input.output_currency = 'PGK'
        self.quote_input.shipment = MagicMock()
        self.quote_input.shipment.pieces = []
        
        # Create an SPE in the database
        now = timezone.now()
        self.spe = SpotPricingEnvelopeDB.objects.create(
            id=uuid4(),
            status='ready',
            spot_trigger_reason_code='TEST_TRIGGER',
            spot_trigger_reason_text='Test Trigger',
            shipment_context_json={
                'origin_country': 'PG',
                'destination_country': 'SG',
                'origin_code': 'POM',
                'destination_code': 'SIN',
                'commodity': 'GCR',
                'total_weight_kg': 100.0,
                'pieces': 1,
                'service_scope': 'd2d',
            },
            conditions_json={},
            expires_at=now + timedelta(days=1)
        )
        
        # Create Acknowledgement
        SPEAcknowledgementDB.objects.create(
            envelope=self.spe,
            acknowledged_at=now,
            statement='I acknowledge this is a conditional SPOT quote and not guaranteed'
        )
        
        # Create Service Components
        ServiceComponent.objects.create(code='DST_SPOT', description='Spot Dest', mode='AIR', leg='DESTINATION', category='TRANSPORT')
        ServiceComponent.objects.create(code='FRT_SPOT', description='Spot Freight', mode='AIR', leg='MAIN', category='TRANSPORT')
        ServiceComponent.objects.create(code='ORG_FEE', description='Origin Fee', mode='AIR', leg='ORIGIN', category='HANDLING')

    def test_merge_charge_lines_bucket_override(self):
        """
        Verify that SPE charges override Standard charges for the same bucket.
        Scenario: 
        - Standard: Origin ($100), Freight ($500), Destination ($200)
        - Spot: Destination ($300)
        - Result: Origin ($100), Freight ($500), Destination ($300)
        """
        # 1. Setup Adapter
        adapter = PricingServiceV4Adapter(self.quote_input, spot_envelope_id=self.spe.id)
        
        # 2. Mock Standard Lines
        # Helper to create lines
        def make_line(code, bucket, amount):
            return CalculatedChargeLine(
                service_component_code=code,
                service_component_desc=f"{code} Desc",
                cost_pgk=Decimal(amount),
                sell_pgk=Decimal(amount),
                sell_pgk_incl_gst=Decimal(amount),
                sell_fcy=Decimal(amount),
                sell_fcy_incl_gst=Decimal(amount),
                sell_fcy_currency='PGK',
                bucket=bucket,
                cost_source='STANDARD',
                leg='L1',
                service_component_id=uuid4()
            )
            
        std_lines = [
            make_line('ORG_FEE', 'origin_charges', '100.00'),
            make_line('FRT_AIR', 'airfreight', '500.00'),
            make_line('DST_FEE', 'destination_charges', '200.00'),
        ]
        
        # Mock _calculate_standard_lines
        adapter._calculate_standard_lines = MagicMock(return_value=std_lines)
        adapter._get_service_component_id = MagicMock(return_value=uuid4())
        
        # 3. Add Spot Charges to DB (Destination Only)
        SPEChargeLineDB.objects.create(
            envelope=self.spe,
            code='DST_SPOT',
            description='Spot Dest',
            amount=Decimal('300.00'),
            currency='PGK',
            unit='per_shipment',
            bucket='destination_charges',
            is_primary_cost=False,
            entered_at=timezone.now(),
            source_reference='Test'
        )
        
        # 4. Run Calculation
        # We need to ensure _get_fx_rates_dict returns something usable
        adapter._get_fx_rates_dict = MagicMock(return_value={})
        adapter._get_fx_sell_rate = MagicMock(return_value=Decimal('1.0'))
        
        result = adapter.calculate_charges()
        
        # 5. Verify Logic
        # Expected: Origin(100) + Freight(500) + SpotDest(345 from 300*1.15) = 945
        
        self.assertEqual(result.totals.total_sell_pgk, Decimal('945.00'))
        
        # Check components
        codes = [l.service_component_code for l in result.lines]
        self.assertIn('ORG_FEE', codes)
        self.assertIn('FRT_AIR', codes)
        self.assertIn('DST_SPOT', codes)
        self.assertNotIn('DST_FEE', codes) # Should be overridden
        
        # Check mode
        self.assertEqual(adapter.pricing_mode, PricingMode.SPOT)

    def test_merge_charge_lines_no_standard(self):
        """
        Verify behavior when standard engine fails or returns nothing.
        """
        adapter = PricingServiceV4Adapter(self.quote_input, spot_envelope_id=self.spe.id)
        adapter._calculate_standard_lines = MagicMock(return_value=[])
        adapter._get_service_component_id = MagicMock(return_value=uuid4())
        
        SPEChargeLineDB.objects.create(
            envelope=self.spe,
            code='FRT_SPOT',
            description='Spot Freight',
            amount=Decimal('1000.00'),
            currency='PGK',
            unit='per_shipment',
            bucket='airfreight',
            is_primary_cost=True,
            entered_at=timezone.now(),
            source_reference='Test'
        )
        
        adapter._get_fx_rates_dict = MagicMock(return_value={})
        adapter._get_fx_sell_rate = MagicMock(return_value=Decimal('1.0'))
        
        result = adapter.calculate_charges()
        
        # 1000 * 1.15 = 1150
        self.assertEqual(result.totals.total_sell_pgk, Decimal('1150.00'))
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].service_component_code, 'FRT_SPOT')

    def test_mixed_currency_import_prepaid(self):
        """
        [P1 Regression] Verify handling of Import Prepaid where Standard Engine returns FCY (AUD).
        Standard lines are in AUD, totals should be accurately calculated without double conversion.
        """
        # 1. Setup Adapter for Import Prepaid
        self.quote_input.shipment.shipment_type = 'IMPORT'
        self.quote_input.shipment.payment_term = 'PREPAID'
        self.quote_input.output_currency = 'AUD'
        
        adapter = PricingServiceV4Adapter(self.quote_input, spot_envelope_id=self.spe.id)
        
        # 2. Mock Standard Lines returning AUD amounts
        # Standard Engine returns raw dicts usually, but adapter converts them.
        # We need to mock _calculate_standard_lines to return lines that *look* like what current adapter produces
        # OR mock the engine output if we were testing _calculate_standard_lines itself.
        # Since the bug is in how adapter.py handles the currency *labeling* and *totaling*, let's mock the lines
        # as they are currently produced (incorrectly labeled as PGK? or correctly?)
        # The user says: "standard lines are always labeled as PGK ... but totals are later converted"
        
        # Let's verify the FIX behavior: Lines should be labeled as AUD.
        
        # We simulate the Adapter logic being fixed, so we expect lines to have sell_fcy_currency='AUD'
        # But wait, if I mock the *result* of _calculate_standard_lines, I am bypassing the bug in _calculate_standard_lines!
        # I need to repro the bug in _calculate_standard_lines or _calculate_totals.
        
        # The user said: "backend/pricing_v4/adapter.py:247" is where the labeling happens.
        # So I should PROBABLY test `_calculate_standard_lines` behavior if I can mock the pricing engine.
        # But mocking the engine is complex.
        
        # Let's test the `_calculate_totals` part first. If I feed `_calculate_totals` lines that ARE labeled PGK (buggy state)
        # but contain AUD amounts, and output is AUD, does it double convert?
        # Yes: Total PGK (actually AUD) -> Convert to AUD -> Result is AUD / Rate.
        
        # Test Plan:
        # Feed lines labeled as AUD (Correct State). Verify Totals are correct (Sum of AUD).
        # Feed lines labeled as PGK (Buggy State). Verify Totals are wrong.
        
        # Actually, let's just write the test expecting the CORRECT behavior.
        
        mock_line = MagicMock()
        mock_line.product_code = 'ORG_FEE'
        mock_line.description = 'Origin Fee'
        mock_line.category = 'HANDLING'
        mock_line.cost_amount = Decimal('80.00')
        mock_line.sell_amount = Decimal('100.00')
        mock_line.sell_incl_gst = Decimal('100.00')
        mock_line.gst_amount = Decimal('0')
        mock_line.cost_currency = 'AUD'
        mock_line.sell_currency = 'AUD'
        mock_line.is_rate_missing = False
        
        mock_result = MagicMock()
        mock_result.lines = [mock_line]
        
        # Mock FX: 1 AUD = 2.5 PGK (sell), 1 AUD = 2.0 PGK (buy)
        adapter._get_fx_rates_dict = MagicMock(return_value={
            'AUD': {'tt_sell': 2.5, 'tt_buy': 2.0}
        })
        
        standard_lines = adapter._convert_result_to_lines(mock_result)
        adapter._calculate_standard_lines = MagicMock(return_value=standard_lines)
        
        # Calculate
        result = adapter.calculate_charges()
        
        # Expectation:
        # Total Sell FCY should be 100.00 (Sum of line FCY)
        # Total Sell PGK should be 250.00 (100 * 2.5)
        
        self.assertEqual(result.totals.total_sell_fcy, Decimal('100.00'))
        self.assertEqual(result.totals.total_sell_pgk, Decimal('250.00'))
        self.assertEqual(result.totals.total_sell_fcy_currency, 'AUD')

    def test_domestic_bucket_no_override(self):
        """
        [P2 Regression] Verify that for DOMESTIC quotes, bucket overrides do NOT apply to origin_charges.
        Domestic quotes put Freight + Origin fees in 'origin_charges'.
        A SPOT line in 'origin_charges' (e.g. specialized packing) should ADD to standard lines, not replace them.
        """
        self.quote_input.shipment.shipment_type = 'DOMESTIC'
        adapter = PricingServiceV4Adapter(self.quote_input, spot_envelope_id=self.spe.id)
        
        # Standard Domestic Lines (All in origin_charges usually)
        # Helper to create lines
        def make_line(code, bucket, amount):
            return CalculatedChargeLine(
                service_component_code=code,
                service_component_desc=f"{code} Desc",
                cost_pgk=Decimal(amount),
                sell_pgk=Decimal(amount),
                sell_pgk_incl_gst=Decimal(amount),
                sell_fcy=Decimal(amount),
                sell_fcy_incl_gst=Decimal(amount),
                sell_fcy_currency='PGK',
                bucket=bucket,
                cost_source='STANDARD',
                leg='L1',
                service_component_id=uuid4()
            )

        std_lines = [
            make_line('FRT_AIR', 'origin_charges', '500.00'), # Freight in origin_charges
            make_line('ORG_FEE', 'origin_charges', '100.00'),
        ]
        
        adapter._calculate_standard_lines = MagicMock(return_value=std_lines)
        adapter._get_service_component_id = MagicMock(return_value=uuid4())
        adapter._get_fx_rates_dict = MagicMock(return_value={})
        
        # Spot Line also in origin_charges (e.g. Extra Packing)
        SPEChargeLineDB.objects.create(
            envelope=self.spe,
            code='PACKING',
            description='Special Packing',
            amount=Decimal('50.00'),
            currency='PGK',
            unit='per_shipment',
            bucket='origin_charges',
            is_primary_cost=False,
            entered_at=timezone.now(),
            source_reference='Test'
        )
        
        result = adapter.calculate_charges()
        
        # Expectation: 
        # With current BUG: Standard lines (600) are replaced by SPOT (50 * 1.15 = 57.5) -> Total ~57.5
        # With FIX: Standard lines (600) + SPOT (57.5) -> Total 657.5
        
        total = result.totals.total_sell_pgk
        # assertGreater is safer for "it shouldn't be small"
        self.assertGreater(total, Decimal('100.00'), "Domestic Standard charges should be preserved")
        self.assertEqual(total, Decimal('657.50'))
