from django.test import SimpleTestCase

from quotes.branding import QuoteBrandingContext
from quotes.spot_services import SpotEmailDraftGenerator


class SpotEmailDraftGeneratorTest(SimpleTestCase):
    def test_generate_uses_branding_signature_when_present(self):
        branding = QuoteBrandingContext(
            display_name="EFM Express Air Cargo",
            support_email="quotes@efmexpress.com",
            support_phone="+675 325 8500",
            website_url="",
            address_lines=[],
            quote_footer_text="",
            public_quote_tagline="",
            email_signature_text="EFM Express Air Cargo\nEmail: quotes@efmexpress.com",
            primary_color="#0F2A56",
            accent_color="#D71920",
            logo_path=None,
            logo_url=None,
        )

        draft = SpotEmailDraftGenerator.generate(
            origin_code="POM",
            destination_code="SYD",
            commodity="GCR",
            weight_kg=100,
            pieces=1,
            branding=branding,
        )

        self.assertIn("SPOT Rate Request", draft.subject)
        self.assertIn("EFM Express Air Cargo", draft.body)
        self.assertIn("quotes@efmexpress.com", draft.body)

