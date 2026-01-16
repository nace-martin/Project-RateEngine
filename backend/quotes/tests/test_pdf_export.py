from django.test import TestCase
from decimal import Decimal
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from quotes.pdf_service import generate_quote_pdf
from parties.models import Company
from core.models import Location, Country, City

class QuotePDFExportTest(TestCase):
    def setUp(self):
        self.country = Country.objects.create(code='PG', name='Papua New Guinea')
        self.city = City.objects.create(name='Port Moresby', country=self.country)
        self.origin = Location.objects.create(code='POM', name='Port Moresby', city=self.city, country=self.country)
        self.dest = Location.objects.create(code='LAE', name='Lae', country=self.country)
        self.customer = Company.objects.create(name='Test Customer 🚀', company_type='CUSTOMER')
        
    def test_pdf_generation_unicode_and_safety(self):
        """
        Ensure PDF generation succeeds with Unicode characters and minimal data.
        """
        quote = Quote.objects.create(
            customer=self.customer,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number='TEST-PDF-UNICODE',
            status='DRAFT',
            valid_until=None,  # Should fallback to created_at
            mode='AIR ✈️',
            shipment_type='IMPORT'
        )
        version = QuoteVersion.objects.create(quote=quote, version_number=1)
        
        # Add lines with unicode
        QuoteLine.objects.create(
            quote_version=version,
            cost_source_description="Test Item 📦",
            sell_pgk=Decimal('100.00'),
            leg='MAIN'
        )
        QuoteTotal.objects.create(
            quote_version=version,
            total_sell_pgk=Decimal('100.00'),
            total_sell_pgk_incl_gst=Decimal('110.00')
        )
        
        # Should not raise
        pdf_bytes = generate_quote_pdf(str(quote.id))
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
