from datetime import date
from decimal import Decimal
from typing import Optional, Dict

from .domestic_engine import DomesticPricingEngine
from .export_engine import ExportPricingEngine
from .import_engine import ImportPricingEngine, PaymentTerm, ServiceScope

class PricingEngineFactory:
    """
    Factory to instantiate the correct Pricing Engine based on Service Type.
    """
    
    @staticmethod
    def get_engine(service_type: str, payload: Dict):
        """
        Returns an initialized engine instance.
        
        Args:
            service_type: 'DOMESTIC', 'EXPORT', 'IMPORT'
            payload: Validated data from QuoteRequestSerializerV4
        """
        quote_date = payload.get('quote_date') or date.today()
        origin = payload.get('origin')
        destination = payload.get('destination')
        weight = payload['cargo_details']['weight_kg']
        service_scope = payload.get('service_scope', 'A2A')
        
        # Payment Term mapping from Incoterms (Simple heuristic)
        # INCOTERMS_CHOICES = ['EXW', 'FCA', 'FOB', 'CFR', 'CIF', 'DAP', 'DPU', 'DDP']
        incoterms = payload.get('incoterms')
        payment_term = PaymentTerm.PREPAID # Default ??
        if service_type == 'IMPORT':
            # Import Logic:
            # EXW, FCA, FOB -> COLLECT (Consignee pays Freight)
            # CFR, CIF, DAP, DDP -> PREPAID (Shipper pays Freight)
            if incoterms in ['EXW', 'FCA', 'FOB']:
                payment_term = PaymentTerm.COLLECT
            else:
                payment_term = PaymentTerm.PREPAID
        
        if service_type == 'DOMESTIC':
            # Domestic Engine
            # DomesticEngine(cogs_origin, destination, weight_kg, service_scope='A2A', quote_date=None)
            return DomesticPricingEngine(
                cogs_origin=origin,
                destination=destination,
                weight_kg=weight,
                service_scope=service_scope,
                quote_date=quote_date
            )
            
        elif service_type == 'EXPORT':
            # Export Engine
            # ExportPricingEngine(quote_date, origin, destination, chargeable_weight_kg)
            # Export Engine currently defaults to P2P in get_product_codes logic if not passed, 
            # but the class __init__ doesn't take scope. Scope is passed to get_product_codes.
            # We will handle scope usage in the View when calling calculate.
            return ExportPricingEngine(
                quote_date=quote_date,
                origin=origin,
                destination=destination,
                chargeable_weight_kg=weight
            )
            
        elif service_type == 'IMPORT':
            # Import Engine
            # ImportPricingEngine(quote_date, origin, destination, chargeable_weight_kg, payment_term, service_scope, ...)
            
            # Map string scope to Enum
            scope_map = {
                'A2A': ServiceScope.A2A,
                'A2D': ServiceScope.A2D,
                'D2A': ServiceScope.D2A,
                'D2D': ServiceScope.D2D
            }
            scope_enum = scope_map.get(service_scope, ServiceScope.A2A)
            
            return ImportPricingEngine(
                quote_date=quote_date,
                origin=origin,
                destination=destination,
                chargeable_weight_kg=weight,
                payment_term=payment_term,
                service_scope=scope_enum
            )
            
        else:
            raise NotImplementedError(f"Service Type {service_type} not supported")
