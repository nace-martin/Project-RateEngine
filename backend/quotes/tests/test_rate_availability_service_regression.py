import pytest
from datetime import date
from decimal import Decimal
from quotes.spot_services import RateAvailabilityService
from pricing_v4.models import ImportCOGS, LocalCOGSRate, ProductCode, Agent, Carrier

@pytest.mark.django_db
class TestRateAvailabilityRegression:
    
    @pytest.fixture(autouse=True)
    def setup_data(self):
        # Setup Counterparties
        self.agent, _ = Agent.objects.get_or_create(id=1, defaults={'code': 'TESTAGENT', 'name': 'Test Agent'})
        self.carrier, _ = Carrier.objects.get_or_create(id=1, defaults={'code': 'PX', 'name': 'Air Niugini'})

        # Setup Product Codes
        # Note: ProductCode ID is manually assigned
        self.pc_frt, _ = ProductCode.objects.get_or_create(
            id=2001,
            defaults={
                'code': 'IMP-FRT-AIR', 
                'category': 'FREIGHT', 
                'description': 'Import Air Freight',
                'domain': 'IMPORT',
                'is_gst_applicable': False
            }
        )
        
        self.pc_origin, _ = ProductCode.objects.get_or_create(
            id=2002,
            defaults={
                'code': 'IMP-AGENCY-ORIGIN', 
                'category': 'ORIGIN_LOCAL', 
                'description': 'Agency Fee (Origin)',
                'domain': 'IMPORT',
                'is_gst_applicable': False
            }
        )
        
        self.pc_dest, _ = ProductCode.objects.get_or_create(
            id=2003,
            defaults={
                'code': 'IMP-CLEAR', 
                'category': 'CLEARANCE', 
                'description': 'Customs Clearance',
                'domain': 'IMPORT',
                'is_gst_applicable': False
            }
        )
        
        self.today = date.today()

    def test_bne_pom_import_full_coverage(self):
        """
        BNE -> POM IMPORT D2D COLLECT with:
        - ImportCOGS freight row BNE -> POM
        - ImportCOGS origin-local row BNE -> NULL destination
        - LocalCOGSRate destination row POM IMPORT
        Expected: FREIGHT=True, ORIGIN_LOCAL=True, DESTINATION_LOCAL=True
        """
        # 1. Freight row (Lane specific)
        ImportCOGS.objects.create(
            product_code_id=self.pc_frt.id,
            origin_airport='BNE',
            destination_airport='POM',
            currency='AUD',
            rate_per_kg=Decimal('2.50'),
            valid_from='2025-01-01',
            valid_until='2026-12-31',
            carrier=self.carrier
        )
        
        # 2. Origin local row (Origin specific, NULL destination)
        ImportCOGS.objects.create(
            product_code_id=self.pc_origin.id,
            origin_airport='BNE',
            destination_airport=None, # This was the problem
            currency='AUD',
            rate_per_shipment=Decimal('100.00'),
            valid_from='2025-01-01',
            valid_until='2026-12-31',
            agent=self.agent
        )
        
        # 3. Destination local row (Location specific)
        LocalCOGSRate.objects.create(
            product_code_id=self.pc_dest.id,
            location='POM',
            direction='IMPORT',
            currency='PGK',
            amount=Decimal('250.00'),
            valid_from='2025-01-01',
            valid_until='2026-12-31',
            agent=self.agent
        )
        
        availability = RateAvailabilityService.get_availability(
            origin_airport="BNE",
            destination_airport="POM",
            direction="IMPORT",
            service_scope="D2D",
            payment_term="COLLECT"
        )
        
        assert availability['FREIGHT'] is True
        assert availability['ORIGIN_LOCAL'] is True
        assert availability['DESTINATION_LOCAL'] is True

    def test_bne_pom_import_missing_origin_local(self):
        """
        BNE -> POM IMPORT D2D COLLECT without origin-local BNE -> NULL row
        Expected: ORIGIN_LOCAL=False
        """
        # 1. Freight row
        ImportCOGS.objects.create(
            product_code_id=self.pc_frt.id,
            origin_airport='BNE',
            destination_airport='POM',
            currency='AUD',
            rate_per_kg=Decimal('2.50'),
            valid_from='2025-01-01',
            valid_until='2026-12-31',
            carrier=self.carrier
        )
        
        # 3. Destination local row
        LocalCOGSRate.objects.create(
            product_code_id=self.pc_dest.id,
            location='POM',
            direction='IMPORT',
            currency='PGK',
            amount=Decimal('250.00'),
            valid_from='2025-01-01',
            valid_until='2026-12-31',
            agent=self.agent
        )
        
        availability = RateAvailabilityService.get_availability(
            origin_airport="BNE",
            destination_airport="POM",
            direction="IMPORT",
            service_scope="D2D",
            payment_term="COLLECT"
        )
        
        assert availability['FREIGHT'] is True
        assert availability['ORIGIN_LOCAL'] is False
        assert availability['DESTINATION_LOCAL'] is True

    def test_can_pom_import_missing_everything(self):
        """
        CAN -> POM IMPORT D2D COLLECT with missing freight/origin
        Expected: All False
        """
        availability = RateAvailabilityService.get_availability(
            origin_airport="CAN",
            destination_airport="POM",
            direction="IMPORT",
            service_scope="D2D",
            payment_term="COLLECT"
        )
        
        assert availability['FREIGHT'] is False
        assert availability['ORIGIN_LOCAL'] is False
        assert availability['DESTINATION_LOCAL'] is False

    def test_bne_pom_import_a2d_destination_only(self):
        """
        BNE -> POM IMPORT A2D COLLECT destination-only
        Expected: ORIGIN_LOCAL not required (should be True or Ignored by Evaluator)
        Note: RateAvailabilityService still reports False if not in DB, 
        but SpotTriggerEvaluator skips it for A2D.
        """
        # Destination local row
        LocalCOGSRate.objects.create(
            product_code_id=self.pc_dest.id,
            location='POM',
            direction='IMPORT',
            currency='PGK',
            amount=Decimal('250.00'),
            valid_from='2025-01-01',
            valid_until='2026-12-31',
            agent=self.agent
        )
        
        availability = RateAvailabilityService.get_availability(
            origin_airport="BNE",
            destination_airport="POM",
            direction="IMPORT",
            service_scope="A2D",
            payment_term="COLLECT"
        )
        
        from quotes.spot_services import SpotTriggerEvaluator
        
        is_spot, result = SpotTriggerEvaluator.evaluate(
            origin_country="AU",
            destination_country="PG",
            direction="IMPORT",
            service_scope="A2D",
            component_availability=availability
        )
        
        # Even if FREIGHT and ORIGIN_LOCAL are False in availability, 
        # for A2D only DESTINATION_LOCAL is required.
        # Wait, A2D usually requires FREIGHT + DESTINATION_LOCAL?
        # Let's check completeness rules.
        
        from quotes.completeness import evaluate_from_availability
        coverage = evaluate_from_availability(availability, "IMPORT", "A2D")
        
        # A2D required: FREIGHT, DESTINATION_LOCAL
        assert "DESTINATION_LOCAL" not in coverage.missing_required
        assert "ORIGIN_LOCAL" not in coverage.required_components
