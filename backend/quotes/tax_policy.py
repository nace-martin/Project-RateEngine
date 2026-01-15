# quotes/tax_policy.py
from decimal import Decimal
from typing import Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from pricing_v4.models import ProductCode


# =============================================================================
# V4 Engine-First Tax Policy
# =============================================================================

def get_gst_from_product_code(product_code: 'ProductCode') -> Tuple[bool, Decimal]:
    """
    Engine-First: Pull GST settings directly from ProductCode.
    
    This is the preferred method for V4 pricing engines. It reads the
    gst_treatment field to determine tax classification.
    
    GST Treatment Types:
        - STANDARD: Normal 10% GST, tracked in BAS G1
        - ZERO_RATED: 0% GST but tracked in BAS (export services)
        - EXEMPT: 0% GST, excluded from BAS entirely (disbursements)
    
    Args:
        product_code: A ProductCode instance with gst_treatment field
        
    Returns:
        Tuple of (is_taxable: bool, gst_rate: Decimal)
        
    Examples:
        >>> pc = ProductCode.objects.get(code='EXP-FRT-AIR')  # gst_treatment='ZERO_RATED'
        >>> get_gst_from_product_code(pc)
        (False, Decimal('0'))
        
        >>> pc = ProductCode.objects.get(code='IMP-AGENCY')  # gst_treatment='STANDARD'
        >>> get_gst_from_product_code(pc)
        (True, Decimal('0.10'))
    """
    # Check new gst_treatment field if available
    gst_treatment = getattr(product_code, 'gst_treatment', None)
    
    if gst_treatment == 'EXEMPT':
        # Disbursements like DUTY, AQIS - excluded from GST return
        return (False, Decimal('0'))
    
    elif gst_treatment == 'ZERO_RATED':
        # Export services - 0% but tracked for GST purposes
        return (False, Decimal('0'))
    
    elif gst_treatment == 'STANDARD':
        # Normal taxable service
        return (True, product_code.gst_rate)
    
    # Fallback to legacy is_gst_applicable field
    if product_code.is_gst_applicable:
        return (True, product_code.gst_rate)
    else:
        return (False, Decimal('0'))


# =============================================================================
# Legacy Jurisdiction-Based Tax Policy (for SPOT Flow)
# =============================================================================

# Constants for easy maintenance
NON_TAXABLE_CODES = frozenset({"DUTY", "IMPORT_GST", "AQIS", "DAU", "ICS", "DISB"})
PNG_GST_RATE = 10
DEFAULT_GST_RATE = 0

# Jurisdiction handler registry - add new countries here
JURISDICTION_HANDLERS = {
    "PG": "_apply_png_logic",
    # "AU": "_apply_au_logic",  # Uncomment when AU GST registration complete
}


class JurisdictionBasedTaxEngine:
    """
    A modular engine to handle jurisdiction-based tax rules.
    
    Used for SPOT charges that don't have ProductCode references.
    For V4 engine charges, use get_gst_from_product_code() instead.
    
    Design:
    - Extract constants for maintainability
    - Dispatch pattern for jurisdiction routing
    - Single-responsibility methods for testability
    """

    def apply_gst_policy(self, version, charge) -> None:
        """
        Main entry point. Mutates `charge.is_taxable` and `charge.gst_percentage`.
        
        Args:
            version: Object with origin/destination country_code and quotation service_type
            charge: Object with code, stage attributes; will be mutated with is_taxable, gst_percentage
        """
        # 1. Initialize Defaults
        charge.is_taxable = False
        charge.gst_percentage = DEFAULT_GST_RATE

        # 2. Global Exclusions (Product Code or Stage)
        if self._is_globally_exempt(charge):
            return

        # 3. Route by Jurisdiction
        country_code = self._get_country_code(version, charge)
        
        handler_name = JURISDICTION_HANDLERS.get(country_code)
        if handler_name:
            handler = getattr(self, handler_name)
            handler(version, charge)

    def _is_globally_exempt(self, charge) -> bool:
        """
        Checks if the charge is exempt regardless of country.
        
        Global exemptions:
        - Disbursement codes (DUTY, IMPORT_GST, AQIS, etc.)
        - International air freight (AIR stage)
        """
        code = (charge.code or "").upper()
        if code in NON_TAXABLE_CODES:
            return True
        if charge.stage == "AIR":
            return True
        return False

    def _get_country_code(self, version, charge) -> str:
        """
        Determines which country's tax laws apply based on the stage.
        
        - ORIGIN stage → origin country tax rules
        - DESTINATION stage → destination country tax rules
        """
        if charge.stage == "ORIGIN":
            return version.origin.country_code
        if charge.stage == "DESTINATION":
            return version.destination.country_code
        return ""

    def _apply_png_logic(self, version, charge) -> None:
        """
        Specific tax rules for Papua New Guinea (PG).
        
        Rules:
        - IMPORT/DOMESTIC: 10% GST on services supplied in PNG
        - EXPORT with evidence: 0% (zero-rated)
        - EXPORT without evidence: 10% GST on origin services
        """
        service_type = version.quotation.service_type  # IMPORT / EXPORT / DOMESTIC

        if service_type in ("IMPORT", "DOMESTIC"):
            # Services supplied in PNG → 10% GST
            charge.is_taxable = True
            charge.gst_percentage = PNG_GST_RATE
            
        elif service_type == "EXPORT":
            # Exports are 0% only if evidence is provided
            export_evidence = bool(version.policy_snapshot.get("export_evidence", False))
            
            if charge.stage == "ORIGIN" and not export_evidence:
                # No export evidence → taxable at origin
                charge.is_taxable = True
                charge.gst_percentage = PNG_GST_RATE
            # With evidence or destination stage → stays at 0% (zero-rated)

    # Future jurisdiction handlers:
    # def _apply_au_logic(self, version, charge) -> None:
    #     """Australian GST rules (when registered)."""
    #     pass


# Singleton instance for convenience
_tax_engine = JurisdictionBasedTaxEngine()


def apply_gst_policy(version, charge) -> None:
    """
    Backward-compatible wrapper for JurisdictionBasedTaxEngine.
    
    Mutates `charge.is_taxable` and `charge.gst_percentage` in place.

    Priority:
    1. Engine-First: If charge has a linked ProductCode, use its tax settings.
    2. Legacy: Use JurisdictionBasedTaxEngine for ad-hoc charges or legacy data.
    """
    # 1. Engine-First Check
    # Check if the charge object has a service component and product code
    sc = getattr(charge, 'service_component', None)
    if sc and sc.product_code:
        # Use the V4 engine logic defined above
        is_taxable, gst_decimal_rate = get_gst_from_product_code(sc.product_code)
        
        charge.is_taxable = is_taxable
        # Convert Decimal('0.10') to percentage '10' for compatibility with legacy consumers
        charge.gst_percentage = gst_decimal_rate * 100
        return

    # 2. Legacy Fallback (SPOT / Ad-Hoc / No Product Code)
    _tax_engine.apply_gst_policy(version, charge)

