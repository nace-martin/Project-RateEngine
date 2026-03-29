from decimal import Decimal

from django.test import TestCase

from core.models import City, Country, Location
from parties.models import Company, Organization, OrganizationBranding
from quotes.branding import get_quote_branding
from quotes.models import Quote, QuoteLine, QuoteTotal, QuoteVersion
from quotes.pdf_service import (
    _extract_location_info,
    _get_charge_buckets,
    _get_chargeable_weight,
    _get_location_country_code,
    generate_quote_pdf,
)
from services.models import ServiceComponent


class QuotePDFExportTest(TestCase):
    def setUp(self):
        self.country = Country.objects.create(code="PG", name="Papua New Guinea")
        self.city = City.objects.create(name="Port Moresby", country=self.country)
        self.origin = Location.objects.create(code="POM", name="Port Moresby", city=self.city, country=self.country)
        self.dest = Location.objects.create(code="LAE", name="Lae", country=self.country)
        self.customer = Company.objects.create(name="Test Customer", company_type="CUSTOMER")
        self.organization, _ = Organization.objects.get_or_create(
            slug="efm-express-air-cargo",
            defaults={"name": "EFM Express Air Cargo"},
        )
        self.branding, _ = OrganizationBranding.objects.update_or_create(
            organization=self.organization,
            defaults={
                "display_name": "EFM Express Air Cargo",
                "support_email": "quotes@efmexpress.com",
                "support_phone": "+675 325 8500",
                "address_lines": "PO Box 1791\nPort Moresby\nPapua New Guinea",
                "primary_color": "#0F2A56",
                "accent_color": "#D71920",
            },
        )

    def test_pdf_generation_unicode_and_safety(self):
        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number="TEST-PDF-UNICODE",
            status="DRAFT",
            valid_until=None,
            mode="AIR",
            shipment_type="IMPORT",
        )
        version = QuoteVersion.objects.create(quote=quote, version_number=1)

        QuoteLine.objects.create(
            quote_version=version,
            cost_source_description="Test Item",
            sell_pgk=Decimal("100.00"),
            leg="MAIN",
        )
        QuoteTotal.objects.create(
            quote_version=version,
            total_sell_pgk=Decimal("100.00"),
            total_sell_pgk_incl_gst=Decimal("110.00"),
        )

        pdf_bytes = generate_quote_pdf(str(quote.id))
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_chargeable_weight_uses_nested_shipment_pieces_payload(self):
        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number="TEST-PDF-CW-NESTED",
            status="DRAFT",
            mode="AIR",
            shipment_type="EXPORT",
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
        country_hk = Country.objects.create(code="HK", name="Hong Kong")
        city_hk = City.objects.create(name="Hong Kong", country=country_hk)
        origin_hk = Location.objects.create(
            code="HKG",
            name="Hong Kong Intl",
            city=city_hk,
            country=country_hk,
        )

        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=origin_hk,
            destination_location=self.dest,
            quote_number="TEST-PDF-COUNTRY-CODE",
            status="DRAFT",
            mode="AIR",
            shipment_type="IMPORT",
        )

        self.assertEqual(_get_location_country_code(quote, "origin"), "HK")
        self.assertEqual(_get_location_country_code(quote, "destination"), "PG")

    def test_extract_location_info_prefers_city_name_over_airport_label(self):
        country_au = Country.objects.create(code="AU", name="Australia")
        city_bne = City.objects.create(name="Brisbane", country=country_au)
        origin_bne = Location.objects.create(
            code="BNE",
            name="Brisbane International Airport",
            city=city_bne,
            country=country_au,
        )

        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=origin_bne,
            destination_location=self.dest,
            quote_number="TEST-PDF-CITY-LABEL",
            status="DRAFT",
            mode="AIR",
            shipment_type="EXPORT",
        )

        code, name = _extract_location_info(quote, "origin")
        self.assertEqual(code, "BNE")
        self.assertEqual(name, "Brisbane")

    def test_quote_branding_prefers_organization_branding(self):
        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number="TEST-PDF-BRANDING",
            status="DRAFT",
            mode="AIR",
            shipment_type="EXPORT",
        )

        branding = get_quote_branding(quote)

        self.assertEqual(branding.display_name, "EFM Express Air Cargo")
        self.assertEqual(branding.support_email, "quotes@efmexpress.com")
        self.assertEqual(branding.support_phone, "+675 325 8500")
        self.assertEqual(branding.primary_color, "#0F2A56")
        self.assertEqual(branding.accent_color, "#D71920")
        self.assertEqual(branding.primary_color_rgb, (15, 42, 86))
        self.assertEqual(branding.accent_color_rgb, (215, 25, 32))
        self.assertIn("Port Moresby", branding.address_lines)

    def test_quote_branding_falls_back_when_organization_missing(self):
        quote = Quote.objects.create(
            customer=self.customer,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number="TEST-PDF-BRANDING-FALLBACK",
            status="DRAFT",
            mode="AIR",
            shipment_type="EXPORT",
        )

        branding = get_quote_branding(quote)

        self.assertEqual(branding.display_name, "EFM Express Air Cargo")
        self.assertEqual(branding.support_email, "quotes@efmexpress.com")

    def test_quote_branding_uses_static_fallback_when_uploaded_logo_missing(self):
        self.branding.logo_primary = "branding/efm-express-air-cargo/missing-logo.png"
        self.branding.save(update_fields=["logo_primary"])

        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number="TEST-PDF-BRANDING-MISSING-UPLOAD",
            status="DRAFT",
            mode="AIR",
            shipment_type="EXPORT",
        )

        branding = get_quote_branding(quote)

        self.assertIsNotNone(branding.logo_path)
        self.assertIsNone(branding.logo_file)
        self.assertTrue(str(branding.logo_path).endswith(".png"))

    def test_charge_buckets_prefer_saved_quote_line_bucket_over_service_component_leg(self):
        quote = Quote.objects.create(
            customer=self.customer,
            organization=self.organization,
            origin_location=self.origin,
            destination_location=self.dest,
            quote_number="TEST-PDF-BUCKETS",
            status="FINALIZED",
            mode="AIR",
            shipment_type="IMPORT",
        )
        version = QuoteVersion.objects.create(quote=quote, version_number=1)
        wrong_component = ServiceComponent.objects.create(
            code="IMP-AGENCY-ORIGIN-TEST",
            description="Import Origin Agency Test",
            mode="AIR",
            leg="DESTINATION",
            category="ACCESSORIAL",
        )

        QuoteLine.objects.create(
            quote_version=version,
            service_component=wrong_component,
            sell_pgk=Decimal("125.00"),
            leg="ORIGIN",
            bucket="origin_charges",
        )
        QuoteLine.objects.create(
            quote_version=version,
            sell_pgk=Decimal("250.00"),
            leg="MAIN",
            bucket="airfreight",
        )
        QuoteLine.objects.create(
            quote_version=version,
            sell_pgk=Decimal("75.00"),
            leg="DESTINATION",
            bucket="destination_charges",
        )

        buckets = _get_charge_buckets(version)

        self.assertEqual(
            buckets,
            [
                {"name": "Origin Charges", "subtotal": Decimal("125.00")},
                {"name": "International Freight", "subtotal": Decimal("250.00")},
                {"name": "Destination Charges", "subtotal": Decimal("75.00")},
            ],
        )
