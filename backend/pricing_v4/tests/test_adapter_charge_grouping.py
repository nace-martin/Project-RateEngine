from django.test import TestCase
from unittest.mock import MagicMock
from decimal import Decimal
from uuid import uuid4

from pricing_v4.adapter import PricingServiceV4Adapter
from core.dataclasses import CalculatedChargeLine, QuoteInput

class AdapterChargeGroupingTest(TestCase):
    def setUp(self):
        self.quote_input = MagicMock(spec=QuoteInput)
        self.quote_input.output_currency = 'PGK'
        self.quote_input.shipment = MagicMock()
        self.quote_input.shipment.pieces = []
        
    def test_export_clearance_grouping(self):
        """
        Verify that Export Customs Clearance (category CLEARANCE) 
        is correctly grouped into 'origin_charges' and 'ORIGIN' leg.
        """
        adapter = PricingServiceV4Adapter(self.quote_input)
        
        # Mock the result from the engine
        mock_line = MagicMock()
        mock_line.product_code = 'EXP-CLEAR'
        mock_line.description = 'Export Customs Clearance'
        mock_line.category = 'CLEARANCE'
        mock_line.leg = 'MAIN' # Engines often don't set this explicitly for some charges, defaulting to MAIN
        mock_line.cost_amount = Decimal('100.00')
        mock_line.sell_amount = Decimal('300.00')
        mock_line.sell_incl_gst = Decimal('300.00')
        mock_line.gst_amount = Decimal('0')
        mock_line.gst_category = None
        mock_line.gst_rate = Decimal('0')
        mock_line.sell_currency = 'PGK'
        mock_line.cost_currency = 'PGK'
        mock_line.is_rate_missing = False
        
        mock_result = MagicMock()
        mock_result.lines = [mock_line]
        
        # Mock internal helpers
        adapter._get_fx_rates_dict = MagicMock(return_value={})
        adapter._get_fx_sell_rate = MagicMock(return_value=Decimal('1.0'))
        
        # We need to mock ServiceComponent lookup because _convert_result_to_lines does a DB lookup
        # We can bypass this by mocking _convert_result_to_lines? 
        # No, we want to test _convert_result_to_lines logic specifically.
        
        # So we must create the ServiceComponent in DB or mock the DB call.
        from services.models import ServiceComponent
        sc = ServiceComponent.objects.create(
            code='EXP-CLEAR', 
            description='Export Customs Clearance', 
            mode='AIR', 
            leg='ORIGIN', # The DB says ORIGIN! But the engine result might not.
            category='CLEARANCE'
        )
        
        # The adapter logic uses the line.leg from the engine result primarily, 
        # OR falls back to category logic. "Export Customs Clearance" in `seed_export_pom_bne.py` 
        # is just a ProductCode. The engine returns a ChargeLineResult.
        # Check `adapter.py`:
        # leg = getattr(line, 'leg', 'MAIN')
        # if v4_category == 'FREIGHT' or leg == 'FREIGHT': ...
        # elif leg == 'DESTINATION' ...
        # elif leg == 'ORIGIN' or v4_category in ['...']: ...
        
        # If the engine result says leg='MAIN' (default), we rely on category mapping.
        
        lines = adapter._convert_result_to_lines(mock_result)
        
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line.service_component_code, 'EXP-CLEAR')
        
        # THIS IS THE ASSERTION THAT FAILS CURRENTLY
        self.assertEqual(line.bucket, 'origin_charges', "CLEARANCE should be in origin_charges")
        self.assertEqual(line.leg, 'ORIGIN', "CLEARANCE should be mapped to ORIGIN leg")

    def test_import_clearance_grouping(self):
        """
        Verify that Import Clearance (category CLEARANCE) 
        keeps its allocation to DESTINATION if the engine/code says so.
        """
        adapter = PricingServiceV4Adapter(self.quote_input)
        
        mock_line = MagicMock()
        mock_line.product_code = 'IMP-CLEAR'
        mock_line.description = 'Import Customs Clearance'
        mock_line.category = 'CLEARANCE'
        mock_line.leg = 'DESTINATION' # Import engine DOES set this explicitly
        
        mock_line.cost_amount = Decimal('100.00')
        mock_line.sell_amount = Decimal('300.00')
        mock_line.sell_incl_gst = Decimal('330.00')
        mock_line.gst_amount = Decimal('30.00')
        mock_line.gst_category = None
        mock_line.gst_rate = Decimal('0.10')
        mock_line.sell_currency = 'PGK'
        mock_line.cost_currency = 'PGK'
        mock_line.is_rate_missing = False
        
        mock_result = MagicMock()
        mock_result.lines = [mock_line] # Or origin_lines/etc depending on struct, but _convert handles unified list
        
        # Mock internal helpers
        adapter._get_fx_rates_dict = MagicMock(return_value={})
        
        from services.models import ServiceComponent
        sc = ServiceComponent.objects.create(
            code='IMP-CLEAR', 
            description='Import Customs Clearance', 
            mode='AIR', 
            leg='DESTINATION',
            category='CLEARANCE'
        )
        
        lines = adapter._convert_result_to_lines(mock_result)
        
        self.assertEqual(len(lines), 1)
        line = lines[0]
        
        # Import Clearance should stay DESTINATION
        self.assertEqual(line.bucket, 'destination_charges')
        self.assertEqual(line.leg, 'DESTINATION')
