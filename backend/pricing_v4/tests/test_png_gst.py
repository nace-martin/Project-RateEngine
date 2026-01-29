# pricing_v4/tests/test_png_gst.py
"""
PNG GST Classification Tests

Tests for get_png_gst_category() function covering all scenarios:
- Export: Origin services (10%), freight (0%), destination (0%)
- Import: Origin (0%), freight (0%), destination services (10%)
- Domestic: All services (10%)
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock

from quotes.tax_policy import (
    get_png_gst_category,
    GST_CATEGORY_SERVICE_IN_PNG,
    GST_CATEGORY_EXPORT_SERVICE,
    GST_CATEGORY_OFFSHORE_SERVICE,
    GST_CATEGORY_IMPORTED_GOODS,
    PNG_GST_RATE_DECIMAL,
)


class TestPNGGSTExport:
    """Test GST classification for EXPORT shipments (from PNG)."""
    
    def test_export_freight_is_zero_rated(self):
        """Export air freight should be 0% GST (zero-rated export service)."""
        pc = Mock()
        pc.gst_treatment = 'ZERO_RATED'
        pc.category = 'FREIGHT'
        
        category, rate = get_png_gst_category(pc, 'EXPORT', 'FREIGHT')
        
        assert category == GST_CATEGORY_EXPORT_SERVICE
        assert rate == Decimal('0')
    
    def test_export_origin_services_attract_gst(self):
        """Export origin services in PNG should attract 10% GST."""
        pc = Mock()
        pc.gst_treatment = 'STANDARD'
        pc.category = 'HANDLING'
        pc.gst_rate = Decimal('0.10')
        
        category, rate = get_png_gst_category(pc, 'EXPORT', 'ORIGIN')
        
        assert category == GST_CATEGORY_SERVICE_IN_PNG
        assert rate == PNG_GST_RATE_DECIMAL
    
    def test_export_destination_offshore_no_gst(self):
        """Export destination services (performed offshore) should be 0% GST."""
        pc = Mock()
        pc.gst_treatment = 'STANDARD'
        pc.category = 'CLEARANCE'
        pc.gst_rate = Decimal('0.10')
        
        category, rate = get_png_gst_category(pc, 'EXPORT', 'DESTINATION')
        
        assert category == GST_CATEGORY_OFFSHORE_SERVICE
        assert rate == Decimal('0')
    
    def test_export_origin_zero_rated_with_evidence(self):
        """Export origin services can be zero-rated if explicitly marked."""
        pc = Mock()
        pc.gst_treatment = 'ZERO_RATED'
        pc.category = 'HANDLING'
        
        category, rate = get_png_gst_category(pc, 'EXPORT', 'ORIGIN')
        
        assert category == GST_CATEGORY_EXPORT_SERVICE
        assert rate == Decimal('0')


class TestPNGGSTImport:
    """Test GST classification for IMPORT shipments (to PNG)."""
    
    def test_import_origin_offshore_no_gst(self):
        """Import origin services (performed offshore) should be 0% GST."""
        pc = Mock()
        pc.gst_treatment = 'STANDARD'
        pc.category = 'HANDLING'
        pc.gst_rate = Decimal('0.10')
        
        category, rate = get_png_gst_category(pc, 'IMPORT', 'ORIGIN')
        
        assert category == GST_CATEGORY_OFFSHORE_SERVICE
        assert rate == Decimal('0')
    
    def test_import_freight_no_gst(self):
        """Import air freight should be 0% GST (export from origin country)."""
        pc = Mock()
        pc.gst_treatment = 'ZERO_RATED'
        pc.category = 'FREIGHT'
        
        category, rate = get_png_gst_category(pc, 'IMPORT', 'FREIGHT')
        
        assert category == GST_CATEGORY_EXPORT_SERVICE
        assert rate == Decimal('0')
    
    def test_import_destination_services_attract_gst(self):
        """Import destination services in PNG should attract 10% GST."""
        pc = Mock()
        pc.gst_treatment = 'STANDARD'
        pc.category = 'CLEARANCE'
        pc.gst_rate = Decimal('0.10')
        
        category, rate = get_png_gst_category(pc, 'IMPORT', 'DESTINATION')
        
        assert category == GST_CATEGORY_SERVICE_IN_PNG
        assert rate == PNG_GST_RATE_DECIMAL
    
    def test_import_goods_value_no_gst(self):
        """Imported goods value (CIF) never attracts GST in quotes - handled by Customs."""
        pc = Mock()
        pc.gst_treatment = 'EXEMPT'
        pc.category = 'GOODS'
        
        category, rate = get_png_gst_category(pc, 'IMPORT', 'DESTINATION')
        
        assert category == GST_CATEGORY_IMPORTED_GOODS
        assert rate == Decimal('0')
    
    def test_import_disbursements_no_gst(self):
        """Disbursements (DUTY, AQIS) should be exempt from GST."""
        pc = Mock()
        pc.gst_treatment = 'EXEMPT'
        pc.category = 'DISBURSEMENT'
        
        category, rate = get_png_gst_category(pc, 'IMPORT', 'DESTINATION')
        
        assert category == GST_CATEGORY_IMPORTED_GOODS
        assert rate == Decimal('0')


class TestPNGGSTDomestic:
    """Test GST classification for DOMESTIC shipments (within PNG)."""
    
    def test_domestic_all_services_attract_gst(self):
        """All domestic services within PNG should attract 10% GST."""
        pc = Mock()
        pc.gst_treatment = 'STANDARD'
        pc.category = 'FREIGHT'
        pc.gst_rate = Decimal('0.10')
        
        category, rate = get_png_gst_category(pc, 'DOMESTIC', 'FREIGHT')
        
        assert category == GST_CATEGORY_SERVICE_IN_PNG
        assert rate == PNG_GST_RATE_DECIMAL
    
    def test_domestic_cartage_attracts_gst(self):
        """Domestic cartage/delivery should attract 10% GST."""
        pc = Mock()
        pc.gst_treatment = 'STANDARD'
        pc.category = 'CARTAGE'
        pc.gst_rate = Decimal('0.10')
        
        category, rate = get_png_gst_category(pc, 'DOMESTIC', 'DESTINATION')
        
        assert category == GST_CATEGORY_SERVICE_IN_PNG
        assert rate == PNG_GST_RATE_DECIMAL


class TestGSTCalculation:
    """Test GST amount calculations are correct."""
    
    def test_gst_amount_calculation_10_percent(self):
        """10% GST should be calculated correctly."""
        sell_amount = Decimal('100.00')
        gst_rate = PNG_GST_RATE_DECIMAL
        
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'))
        
        assert gst_amount == Decimal('10.00')
    
    def test_gst_amount_rounding(self):
        """GST amounts should be rounded to 2 decimal places."""
        sell_amount = Decimal('123.456')
        gst_rate = PNG_GST_RATE_DECIMAL
        
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'))
        
        # 123.456 * 0.10 = 12.3456 -> 12.35 (rounded)
        assert gst_amount == Decimal('12.35')
    
    def test_zero_rate_produces_zero_gst(self):
        """0% GST rate should produce 0 GST amount."""
        sell_amount = Decimal('1000.00')
        gst_rate = Decimal('0')
        
        gst_amount = (sell_amount * gst_rate).quantize(Decimal('0.01'))
        
        assert gst_amount == Decimal('0.00')
