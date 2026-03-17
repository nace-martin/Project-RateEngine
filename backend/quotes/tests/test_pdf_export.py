from django.test import TestCase
from decimal import Decimal
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from quotes.pdf_service import generate_quote_pdf, _extract_location_info, _get_chargeable_weight, _get_location_country_code
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

    def test_chargeable_weight_uses_nested_shipment_pieces_payload(self):
        """Chargeable weight should resolve from shipment.pieces payload structure."""
        quote = Quote.objects.create(
            customer=self.customer,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number='TEST-PDF-CW-NESTED',
            status='DRAFT',
            mode='AIR',
            shipment_type='EXPORT',
            request_details_json={
                "shipment": {
                    "pieces": [
                        {
                            "pieces": 1,
                            "length_cm": "0",
                            "width_cm": "0",
                            "height_cm": "0",
                            "gross_weight_kg": "100.0",
                        }
                    ]
                }
            },
        )
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            payload_json={
                "shipment": {
                    "pieces": [
                        {
                            "pieces": 1,
                            "length_cm": "0",
                            "width_cm": "0",
                            "height_cm": "0",
                            "gross_weight_kg": "100.0",
                        }
                    ]
                }
            },
        )

        self.assertEqual(_get_chargeable_weight(quote, version), "100.0")

    def test_location_country_code_uses_quote_location_country(self):
        """Shipment bar country labels must come from quote locations."""
        country_hk = Country.objects.create(code='HK', name='Hong Kong')
        city_hk = City.objects.create(name='Hong Kong', country=country_hk)
        origin_hk = Location.objects.create(
            code='HKG',
            name='Hong Kong Intl',
            city=city_hk,
            country=country_hk,
        )

        quote = Quote.objects.create(
            customer=self.customer,
            origin_location=origin_hk,
            destination_location=self.dest,
            quote_number='TEST-PDF-COUNTRY-CODE',
            status='DRAFT',
            mode='AIR',
            shipment_type='IMPORT',
        )

        self.assertEqual(_get_location_country_code(quote, 'origin'), 'HK')
        self.assertEqual(_get_location_country_code(quote, 'destination'), 'PG')

    def test_extract_location_info_prefers_city_name_over_airport_label(self):
        country_au = Country.objects.create(code='AU', name='Australia')
        city_bne = City.objects.create(name='Brisbane', country=country_au)
        origin_bne = Location.objects.create(
            code='BNE',
            name='Brisbane International Airport',
            city=city_bne,
            country=country_au,
        )

        quote = Quote.objects.create(
            customer=self.customer,
            origin_location=origin_bne,
            destination_location=self.dest,
            quote_number='TEST-PDF-CITY-LABEL',
            status='DRAFT',
            mode='AIR',
            shipment_type='EXPORT',
        )

        code, name = _extract_location_info(quote, 'origin')
        self.assertEqual(code, 'BNE')
        self.assertEqual(name, 'Brisbane')
