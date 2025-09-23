from __future__ import annotations
import json
import logging
import os
from decimal import Decimal
from .dataclasses_v2 import QuoteContext, Recipe, CalcLine
from pricing.models import Audience, Ratecards, ServiceItems
from core.models import CurrencyRates

logger = logging.getLogger(__name__)

_BUSINESS_RULES = None

def _load_business_rules():
    global _BUSINESS_RULES
    if _BUSINESS_RULES is None:
        try:
            business_rules_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'pricing', 'config', 'business_rules.json'
            )
            with open(business_rules_path, 'r') as f:
                _BUSINESS_RULES = json.load(f)
        except Exception as e:
            logger.error(f"Error loading business rules: {e}")
            _BUSINESS_RULES = {}
    return _BUSINESS_RULES

def get_latest_exchange_rate(base_currency: str, quote_currency: str) -> Decimal:
    """
    Retrieves the latest SELL exchange rate between two currencies from the database.
    """
    try:
        rate_obj = CurrencyRates.objects.filter(
            base_ccy=base_currency.upper(),
            quote_ccy=quote_currency.upper(),
            rate_type='SELL'
        ).order_by('-as_of_ts').first()

        if rate_obj:
            return rate_obj.rate
        else:
            logger.warning(f"No SELL exchange rate found for {base_currency} to {quote_currency}")
            return Decimal('1.0') # Fallback to 1.0 if no rate found
    except Exception as e:
        logger.error(f"Error retrieving exchange rate for {base_currency} to {quote_currency}: {e}")
        return Decimal('1.0') # Fallback in case of error

def get_invoice_currency_recipe() -> Recipe:
    def get_invoice_currency(quote_context: QuoteContext):
        if quote_context.scope == "A2D" and quote_context.mode == "AIR" and quote_context.direction == "IMPORT":
            try:
                business_rules = _load_business_rules()

                rule = business_rules.get('rules', {}).get('IMPORT', {}).get(quote_context.payment_term, {}).get('A2D', {})
                target_currency = rule.get('currency', 'PGK')

                if target_currency == "SHIPPER_CURRENCY":
                    iata_to_region = business_rules.get('currency_mappings', {}).get('iata_to_region', {})
                    region = iata_to_region.get(quote_context.origin_iata, 'OVERSEAS')
                    fallback_mapping = business_rules.get('currency_mappings', {}).get('SHIPPER_CURRENCY', {}).get('fallback_by_region', {})
                    target_currency = fallback_mapping.get(region, 'USD')
                return target_currency
            except Exception as e:
                logger.error(f"Error loading business rules for currency determination in get_invoice_currency_recipe: {e}")
                return 'PGK' # Fallback
        elif quote_context.payment_term == "PREPAID":
            return quote_context.origin_country_currency
        elif quote_context.payment_term == "COLLECT":
            return quote_context.destination_country_currency
        return None
    return Recipe(name="get_invoice_currency", action=get_invoice_currency)

def get_target_audience_code(origin_iata: str, payment_term: str) -> str:
    """
    Map origin region and payment term to target audience code based on business rules.
    
    Returns:
        - AU origins + PREPAID → AU_AGENT_PREPAID
        - Non-AU origins + PREPAID → USD_AGENT_PREPAID  
        - Any origin + COLLECT → PNG_CUSTOMER_COLLECT
    """
    # Load business rules to determine region mapping
    try:
        business_rules = _load_business_rules()
        
        # Get region from IATA mapping
        iata_to_region = business_rules.get('currency_mappings', {}).get('iata_to_region', {})
        region = iata_to_region.get(origin_iata, 'OVERSEAS')
        
        if payment_term == "PREPAID":
            if region == "AU":
                return "AU_AGENT_PREPAID"
            else:
                return "USD_AGENT_PREPAID"
        elif payment_term == "COLLECT":
            return "PNG_CUSTOMER_COLLECT"
        else:
            logger.warning(f"Unknown payment term: {payment_term}")
            return "PNG_CUSTOMER_COLLECT"
            
    except Exception as e:
        logger.error(f"Error loading business rules: {e}")
        # Fallback logic
        if payment_term == "PREPAID":
            return "USD_AGENT_PREPAID"
        else:
            return "PNG_CUSTOMER_COLLECT"


def get_import_a2d_fees(audience_code: str, target_currency: str) -> List[CalcLine]:
    """
    Query ServiceItems for the selected ratecard and return CalcLine objects.
    
    Args:
        audience_code: The target audience code (e.g., AU_AGENT_PREPAID)
        target_currency: The expected currency for the fees
        
    Returns:
        List of CalcLine objects with fees from the ratecard
    """
    try:
        # Find the audience
        audience = Audience.objects.filter(code=audience_code, is_active=True).first()
        if not audience:
            logger.warning(f"No active audience found for code: {audience_code}")
            return []
        
        # Find active ratecard for this audience
        ratecards = Ratecards.objects.filter(
            audience=audience,
            status='ACTIVE',
            direction='IMPORT',
            scope='A2D'
        )

        if ratecards.count() > 1:
            logger.error(f"Multiple active Import A2D ratecards found for audience: {audience_code}. This should not happen.")
            # Decide how to handle this: raise an error, pick one, etc.
            # For now, we'll pick the first one, but log the error.
            ratecard = ratecards.first()
        else:
            ratecard = ratecards.first()
        
        if not ratecard:
            logger.warning(f"No active Import A2D ratecard found for audience: {audience_code}")
            return []
        
        # Validate ratecard currency matches target currency
        if ratecard.currency != target_currency:
            logger.warning(f"Ratecard currency ({ratecard.currency}) does not match target currency ({target_currency}) for audience {audience_code}")
            return []
        
        # Query service items for destination charges
        service_items = ServiceItems.objects.filter(
            ratecard=ratecard,
            currency=target_currency
        ).select_related('service')
        
        calc_lines = []
        for item in service_items:
            # Use the service code as the CalcLine code, or fall back to item_code
            code = item.service.code if hasattr(item, 'service') and item.service else item.item_code or f"SERVICE_{item.id}"
            description = item.service.name if hasattr(item, 'service') and item.service else f"Service Item {item.id}"
            
            calc_lines.append(CalcLine(
                code=code,
                description=description,
                amount=float(item.amount or 0),
                currency=item.currency
            ))
        
        logger.info(f"Found {len(calc_lines)} service items for audience {audience_code}")
        return calc_lines
        
    except Exception as e:
        logger.error(f"Error querying service items for audience {audience_code}: {e}")
        return []


def get_fee_menu_recipe() -> Recipe:
    def get_fee_menu(quote_context: QuoteContext):
        if quote_context.scope == "A2D" and quote_context.mode == "AIR" and quote_context.direction == "IMPORT":
            # Determine target audience and currency based on business rules
            audience_code = get_target_audience_code(quote_context.origin_iata, quote_context.payment_term)
            
            # Determine target currency based on business rules
            try:
                business_rules = _load_business_rules()
                
                # Get currency from business rules
                rule = business_rules.get('rules', {}).get('IMPORT', {}).get(quote_context.payment_term, {}).get('A2D', {})
                target_currency = rule.get('currency', 'PGK')
                
                # Handle SHIPPER_CURRENCY case
                if target_currency == "SHIPPER_CURRENCY":
                    iata_to_region = business_rules.get('currency_mappings', {}).get('iata_to_region', {})
                    region = iata_to_region.get(quote_context.origin_iata, 'OVERSEAS')
                    fallback_mapping = business_rules.get('currency_mappings', {}).get('SHIPPER_CURRENCY', {}).get('fallback_by_region', {})
                    target_currency = fallback_mapping.get(region, 'USD')
                
            except Exception as e:
                logger.error(f"Error loading business rules for currency determination: {e}")
                target_currency = 'PGK'  # Fallback
            
            # Get fees from ratecard
            return get_import_a2d_fees(audience_code, target_currency)
        
        return []
    return Recipe(name="get_fee_menu", action=get_fee_menu)