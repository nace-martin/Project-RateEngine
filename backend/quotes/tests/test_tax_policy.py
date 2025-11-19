from types import SimpleNamespace

from quotes.tax_policy import apply_gst_policy


class MockVersion:
    """Simulates the Adapter we created in PricingService."""

    def __init__(self, origin_country, dest_country, service_type, export_evidence=False):
        self.origin = SimpleNamespace(country_code=origin_country)
        self.destination = SimpleNamespace(country_code=dest_country)
        self.quotation = SimpleNamespace(service_type=service_type)
        self.policy_snapshot = {"export_evidence": export_evidence}


class MockCharge:
    """Simulates the Charge Adapter."""

    def __init__(self, code, stage):
        self.code = code
        self.stage = stage
        self.is_taxable = False
        self.gst_percentage = 0


def test_air_freight_is_zero_rated():
    """Rule: AIR stage (International Linehaul) is always 0%."""
    version = MockVersion("PG", "AU", "EXPORT")
    charge = MockCharge("FRT_AIR", "AIR")

    apply_gst_policy(version, charge)

    assert charge.is_taxable is False
    assert charge.gst_percentage == 0


def test_png_domestic_is_taxable():
    """Rule: Domestic PG services are 10% GST."""
    version = MockVersion("PG", "PG", "DOMESTIC")
    charge = MockCharge("CART_ORG", "ORIGIN")

    apply_gst_policy(version, charge)

    assert charge.is_taxable is True
    assert charge.gst_percentage == 10


def test_png_import_services_taxable():
    """Rule: Services in PG for an Import are taxable."""
    version = MockVersion("AU", "PG", "IMPORT")

    charge = MockCharge("HAND_DEST", "DESTINATION")
    apply_gst_policy(version, charge)
    assert charge.is_taxable is True
    assert charge.gst_percentage == 10

    charge_au = MockCharge("HAND_ORG", "ORIGIN")
    apply_gst_policy(version, charge_au)
    assert charge_au.is_taxable is False
    assert charge_au.gst_percentage == 0


def test_png_export_default_taxable():
    """Rule: Exports from PG are 10% GST if no evidence provided."""
    version = MockVersion("PG", "AU", "EXPORT", export_evidence=False)

    charge = MockCharge("CART_ORG", "ORIGIN")
    apply_gst_policy(version, charge)

    assert charge.is_taxable is True
    assert charge.gst_percentage == 10


def test_png_export_with_evidence_zero_rated():
    """Rule: Exports from PG are 0% GST IF evidence is provided."""
    version = MockVersion("PG", "AU", "EXPORT", export_evidence=True)

    charge = MockCharge("CART_ORG", "ORIGIN")
    apply_gst_policy(version, charge)

    assert charge.is_taxable is False
    assert charge.gst_percentage == 0


def test_disbursements_always_exempt():
    """Rule: DUTY/GST codes are always 0%."""
    version = MockVersion("PG", "PG", "DOMESTIC")
    charge = MockCharge("IMPORT_GST", "DESTINATION")

    apply_gst_policy(version, charge)

    assert charge.is_taxable is False
    assert charge.gst_percentage == 0
