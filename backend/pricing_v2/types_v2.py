from enum import Enum

class AudienceType(str, Enum):
    """Defines the business relationship for a given Organization."""
    LOCAL_PNG_CUSTOMER = "Local PNG Customer"
    OVERSEAS_PARTNER_AU = "Overseas Partner (AU)"
    OVERSEAS_PARTNER_NON_AU = "Overseas Partner (Non-AU)"

class ProvenanceType(Enum):
    RATE_CARD = "RATE_CARD"
    SPOT = "SPOT"
    MANUAL = "MANUAL"

class FeeBasis(Enum):
    PER_KG = "KG"
    PER_SHIPMENT = "AWB"
    PERCENT_OF_BASE = "PERCENTAGE"
    PAGE = "PAGE"
    FLAT = "FLAT"

class Side(Enum):
    ORIGIN = "ORIGIN"
    DESTINATION = "DESTINATION"

class PaymentTerm(Enum):
    PREPAID = "PREPAID"
    COLLECT = "COLLECT"

class OrgType(str, Enum):
    OVERSEAS_AGENT = "OVERSEAS_AGENT"
    PNG_SHIPPER = "PNG_SHIPPER"
    PNG_CUSTOMER = "PNG_CUSTOMER"