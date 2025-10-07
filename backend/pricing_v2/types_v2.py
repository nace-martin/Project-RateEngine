from enum import Enum

class AudienceType(str, Enum):
    """Defines the business relationship for a given Organization."""
    PNG_SHIPPER = "PNG_SHIPPER"
    OVERSEAS_AGENT_AU = "OVERSEAS_AGENT_AU"
    OVERSEAS_AGENT_NON_AU = "OVERSEAS_AGENT_NON_AU"

class ProvenanceType(Enum):
    RATE_CARD = "RATE_CARD"
    SPOT = "SPOT"
    MANUAL = "MANUAL"

class FeeBasis(Enum):
    PER_KG = "PER_KG"
    PER_SHIPMENT = "PER_SHIPMENT"
    PERCENT_OF_BASE = "PERCENT_OF_BASE"

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