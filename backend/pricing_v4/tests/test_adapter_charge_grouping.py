from django.test import TestCase
from unittest.mock import MagicMock
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace

from pricing_v4.adapter import PricingServiceV4Adapter
from core.dataclasses import CalculatedChargeLine, QuoteInput
from pricing_v4.engine.domestic_engine import BillableCharge
from pricing_v4.models import ProductCode

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

    def test_export_airline_fuel_surcharge_grouping(self):
        """
        Export airline fuel surcharge must always sit under Origin Charges.
        """
        adapter = PricingServiceV4Adapter(self.quote_input)

        mock_line = MagicMock()
        mock_line.product_code = 'EXP-FSC-AIR'
        mock_line.description = 'Airline Export Fuel Surcharge'
        mock_line.category = 'FREIGHT'
        mock_line.leg = 'MAIN'
        mock_line.cost_amount = Decimal('10.00')
        mock_line.sell_amount = Decimal('25.00')
        mock_line.sell_incl_gst = Decimal('25.00')
        mock_line.gst_amount = Decimal('0')
        mock_line.gst_category = None
        mock_line.gst_rate = Decimal('0')
        mock_line.sell_currency = 'PGK'
        mock_line.cost_currency = 'PGK'
        mock_line.is_rate_missing = False

        mock_result = MagicMock()
        mock_result.lines = [mock_line]

        adapter._get_fx_rates_dict = MagicMock(return_value={})

        from services.models import ServiceComponent
        ServiceComponent.objects.create(
            code='EXP-FSC-AIR',
            description='Airline Export Fuel Surcharge',
            mode='AIR',
            leg='MAIN',
            category='FREIGHT'
        )

        lines = adapter._convert_result_to_lines(mock_result)

        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line.bucket, 'origin_charges')
        self.assertEqual(line.leg, 'ORIGIN')

    def test_domestic_freight_and_uplift_group_as_airfreight(self):
        adapter = PricingServiceV4Adapter(self.quote_input)
        self.quote_input.shipment.shipment_type = 'DOMESTIC'
        self.quote_input.shipment.service_scope = 'A2A'
        self.quote_input.shipment.commodity_code = 'HVC'
        self.quote_input.shipment.is_dangerous_goods = False
        self.quote_input.shipment.payment_term = 'COLLECT'
        self.quote_input.quote_date = None
        self.quote_input.shipment.origin_location = SimpleNamespace(code='POM', country_code='PG')
        self.quote_input.shipment.destination_location = SimpleNamespace(code='LAE', country_code='PG')

        ProductCode.objects.create(
            id=3001,
            code='DOM-FRT-AIR',
            description='Domestic Air Freight',
            domain='DOMESTIC',
            category='FREIGHT',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4100',
            gl_cost_code='5100',
            default_unit='KG',
        )
        ProductCode.objects.create(
            id=3101,
            code='DOM-VALUABLE',
            description='Domestic Valuable Cargo Uplift',
            domain='DOMESTIC',
            category='SURCHARGE',
            is_gst_applicable=True,
            gst_rate=Decimal('0.10'),
            gl_revenue_code='4410',
            gl_cost_code='5410',
            default_unit='PERCENT',
        )

        from services.models import ServiceComponent
        ServiceComponent.objects.create(code='DOM-FRT-AIR', description='Domestic Air Freight', mode='AIR', leg='MAIN', category='FREIGHT')
        ServiceComponent.objects.create(code='DOM-VALUABLE', description='Domestic Valuable Cargo Uplift', mode='AIR', leg='MAIN', category='SURCHARGE')

        mock_result = SimpleNamespace(
            cogs_breakdown=[BillableCharge('Air Freight (Cost)', Decimal('61.00'), product_code='DOM-FRT-AIR')],
            sell_breakdown=[
                BillableCharge('Air Freight', Decimal('61.00'), product_code='DOM-FRT-AIR'),
                BillableCharge('Domestic Valuable Cargo Uplift', Decimal('244.00'), product_code='DOM-VALUABLE'),
            ],
        )

        adapter._get_fx_rates_dict = MagicMock(return_value={})
        lines = adapter._convert_result_to_lines(mock_result)

        line_by_code = {line.service_component_code: line for line in lines}
        self.assertEqual(line_by_code['DOM-FRT-AIR'].bucket, 'airfreight')
        self.assertEqual(line_by_code['DOM-VALUABLE'].bucket, 'airfreight')

        totals = adapter._calculate_totals(lines).totals
        self.assertFalse(totals.has_missing_rates)
