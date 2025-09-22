"""
Business Rules Engine for Pricing System

This module provides functionality to load, validate, and apply business rules
for determining pricing context including currency and charge scope based on
shipment characteristics.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..dataclasses import ShipmentInput, PricingContext

logger = logging.getLogger(__name__)


class BusinessRulesError(Exception):
    """Base exception for business rules related errors"""
    pass


class ConfigurationError(BusinessRulesError):
    """Raised when there are issues with the configuration file"""
    pass


class ValidationError(BusinessRulesError):
    """Raised when business rules validation fails"""
    pass


class RuleApplicationError(BusinessRulesError):
    """Raised when applying business rules to shipment data fails"""
    pass


def load_business_rules(config_path: str = None) -> dict:
    """
    Load business rules from JSON configuration file
    
    Args:
        config_path: Path to the business rules JSON file. If None, uses default location.
        
    Returns:
        dict: Parsed business rules configuration
        
    Raises:
        ConfigurationError: If file cannot be loaded or parsed
    """
    if config_path is None:
        # Default to config directory relative to this module
        current_dir = Path(__file__).parent.parent
        config_path = current_dir / "config" / "business_rules.json"
    
    try:
        config_path = Path(config_path)
        if not config_path.exists():
            raise ConfigurationError(f"Business rules configuration file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
        
        logger.info(f"Successfully loaded business rules from {config_path}")
        return rules
        
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in business rules file: {e}")
    except Exception as e:
        raise ConfigurationError(f"Error loading business rules configuration: {e}")


def validate_business_rules(rules: dict) -> List[str]:
    """
    Validate that business rules are complete and consistent
    
    Args:
        rules: Business rules configuration dictionary
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    # Check required top-level keys
    required_keys = ['version', 'rules', 'service_mappings', 'currency_mappings', 'validation_rules']
    for key in required_keys:
        if key not in rules:
            errors.append(f"Missing required top-level key: {key}")
    
    if 'rules' not in rules:
        return errors  # Can't validate further without rules
    
    # Validate rule structure
    rule_errors = _validate_rule_structure(rules['rules'])
    errors.extend(rule_errors)
    
    # Validate required combinations exist
    if 'validation_rules' in rules and 'required_combinations' in rules['validation_rules']:
        combination_errors = _validate_required_combinations(
            rules['rules'], 
            rules['validation_rules']['required_combinations']
        )
        errors.extend(combination_errors)
    
    # Validate service mappings
    if 'service_mappings' in rules:
        service_errors = _validate_service_mappings(rules['service_mappings'])
        errors.extend(service_errors)
    
    # Validate currency mappings
    if 'currency_mappings' in rules:
        currency_errors = _validate_currency_mappings(rules['currency_mappings'])
        errors.extend(currency_errors)
    
    # Cross-validate rules reference valid services and currencies
    cross_validation_errors = _cross_validate_rules(rules)
    errors.extend(cross_validation_errors)
    
    if not errors:
        logger.info("Business rules validation passed")
    else:
        logger.warning(f"Business rules validation found {len(errors)} errors")
    
    return errors


def determine_pricing_context(shipment_input: ShipmentInput, rules: dict) -> PricingContext:
    """
    Apply business rules to determine currency and charge scope
    
    Args:
        shipment_input: Shipment data to apply rules to
        rules: Business rules configuration
        
    Returns:
        PricingContext: Determined pricing context
        
    Raises:
        RuleApplicationError: If rules cannot be applied to the shipment
    """
    try:
        # Determine direction from service scope
        direction = _determine_direction(shipment_input.service_scope)
        
        # Get and validate payment term
        payment_term = (shipment_input.payment_term or 'PREPAID').upper()
        if payment_term not in {'PREPAID', 'COLLECT'}:
            raise RuleApplicationError(f"Unsupported payment term: {payment_term}")
        
        # Get movement type, preferring explicit shipment_type if valid
        movement_type = None
        if shipment_input.shipment_type:
            # Normalize to handle variations like 'd2d', 'Door-to-Door', etc.
            normalized_st = _determine_movement_type(shipment_input.shipment_type)
            if normalized_st in {'D2D', 'A2D', 'D2A'}:
                movement_type = normalized_st
        
        if not movement_type:
            # Fallback to deriving from service_scope
            movement_type = _determine_movement_type(shipment_input.service_scope)
        
        # Build rule path
        rule_path = f"{direction}.{payment_term}.{movement_type}"
        
        logger.debug(f"Applying business rules for path: {rule_path}")
        
        # Navigate to the specific rule
        rule_config = _navigate_to_rule(rules['rules'], direction, payment_term, movement_type)
        
        if rule_config is None:
            # Check for fallback rules
            fallback_config = _find_fallback_rule(rules['rules'], direction, payment_term)
            if fallback_config:
                rule_config = fallback_config
                rule_path += " (fallback)"
                logger.warning(f"Using fallback rule for {rule_path}")
            else:
                raise RuleApplicationError(
                    f"No business rule found for combination: {direction}/{payment_term}/{movement_type}"
                )
        
        # Resolve currency
        currency_rule = rule_config.get('currency', 'USD')
        currency = resolve_currency(
            currency_rule,
            shipment_input,
            rules.get('currency_mappings', {})
        )

        # If currency resolution defaulted, check for a per-rule fallback
        if currency == 'USD' and currency_rule == 'SHIPPER_CURRENCY':
            fallback_options = rule_config.get('currency_fallback')
            if fallback_options and isinstance(fallback_options, list) and fallback_options:
                # A whitelist of currencies to prevent injection of arbitrary values
                VALID_CURRENCIES = ['AUD', 'USD', 'PGK', 'NZD', 'EUR', 'GBP']
                chosen_fallback = fallback_options[0]
                if chosen_fallback in VALID_CURRENCIES:
                    currency = chosen_fallback
                    logger.debug(f"Applied per-rule currency fallback for {rule_path}, selected {currency}")
        
        # Get charge scope
        charge_scope = rule_config.get('charges', [])
        
        # Get applicable services
        applicable_services = get_applicable_services(
            charge_scope,
            rules.get('service_mappings', {})
        )
        
        # Create pricing context
        context = PricingContext(
            currency=currency,
            charge_scope=charge_scope,
            applicable_services=applicable_services,
            requires_manual_review=rule_config.get('requires_manual_review', False),
            rule_path=rule_path,
            description=rule_config.get('description', ''),
            metadata={
                'direction': direction,
                'payment_term': payment_term,
                'movement_type': movement_type,
                'rule_config': rule_config
            }
        )
        
        logger.info(f"Successfully determined pricing context: {rule_path} -> {currency}, {len(applicable_services)} services")
        return context
        
    except Exception as e:
        if isinstance(e, RuleApplicationError):
            raise
        raise RuleApplicationError(f"Error applying business rules: {e}")


def get_applicable_services(charge_scope: List[str], service_mappings: dict) -> List[str]:
    """
    Convert charge scope to specific service codes
    
    Args:
        charge_scope: List of charge categories (e.g., ["ORIGIN", "AIR_FREIGHT"])
        service_mappings: Mapping from charge categories to service codes
        
    Returns:
        List[str]: List of specific service codes
    """
    applicable_services = []
    
    for charge_category in charge_scope:
        if charge_category in service_mappings:
            services = service_mappings[charge_category]
            if isinstance(services, list):
                applicable_services.extend(services)
            else:
                applicable_services.append(services)
        else:
            logger.warning(f"No service mapping found for charge category: {charge_category}")
            # Include the category itself as a fallback
            applicable_services.append(charge_category)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_services = []
    for service in applicable_services:
        if service not in seen:
            seen.add(service)
            unique_services.append(service)
    
    logger.debug(f"Mapped charge scope {charge_scope} to {len(unique_services)} services")
    return unique_services


def resolve_currency(currency_rule: str, shipment_input: ShipmentInput, currency_mappings: dict) -> str:
    """
    Resolve dynamic currency rules to specific currency codes
    
    Args:
        currency_rule: Currency specification (e.g., "PGK", "SHIPPER_CURRENCY")
        shipment_input: Shipment data for context
        currency_mappings: Currency resolution mappings
        
    Returns:
        str: Resolved currency code
    """
    # If it's already a specific currency code, return it
    if currency_rule in ['PGK', 'AUD', 'USD', 'EUR', 'GBP', 'NZD']:
        return currency_rule
    
    # Handle dynamic currency resolution
    if currency_rule == "SHIPPER_CURRENCY":
        return _resolve_shipper_currency(shipment_input, currency_mappings)
    
    # Check if it's defined in currency mappings
    if currency_rule in currency_mappings:
        mapping = currency_mappings[currency_rule]
        if 'fallback_by_region' in mapping:
            return _resolve_currency_by_region(shipment_input, mapping['fallback_by_region'], currency_mappings)
    
    # Default fallback
    logger.warning(f"Could not resolve currency rule '{currency_rule}', defaulting to USD")
    return "USD"


# Private helper functions

def _validate_rule_structure(rules: dict) -> List[str]:
    """Validate the structure of the rules dictionary"""
    errors = []
    
    expected_directions = ['IMPORT', 'EXPORT']
    expected_payment_terms = ['PREPAID', 'COLLECT']
    expected_movement_types = {'D2D', 'A2D', 'D2A'}
    
    for direction in expected_directions:
        if direction not in rules:
            errors.append(f"Missing direction: {direction}")
            continue
            
        for payment_term in expected_payment_terms:
            if payment_term not in rules[direction]:
                continue  # Not all combinations are required
                
            payment_rules = rules[direction][payment_term]
            for movement_type, rule_config in payment_rules.items():
                if movement_type.startswith('_'):
                    continue  # Skip metadata/comment fields

                if movement_type not in expected_movement_types:
                    errors.append(f"Unknown movement type key: {direction}.{payment_term}.{movement_type}")
                    
                if not isinstance(rule_config, dict):
                    errors.append(f"Invalid rule config for {direction}.{payment_term}.{movement_type}")
                    continue
                
                # Validate required fields in rule config
                if 'currency' not in rule_config:
                    errors.append(f"Missing currency in {direction}.{payment_term}.{movement_type}")
                
                if 'charges' not in rule_config:
                    errors.append(f"Missing charges in {direction}.{payment_term}.{movement_type}")
                elif not isinstance(rule_config['charges'], list):
                    errors.append(f"Charges must be a list in {direction}.{payment_term}.{movement_type}")
    
    return errors


def _validate_required_combinations(rules: dict, required_combinations: List[List[str]]) -> List[str]:
    """Validate that all required rule combinations exist"""
    errors = []
    
    for combination in required_combinations:
        if len(combination) != 3:
            errors.append(f"Invalid combination format: {combination}")
            continue
            
        direction, payment_term, movement_type = combination
        
        if direction not in rules:
            errors.append(f"Missing required direction: {direction}")
            continue
            
        if payment_term not in rules[direction]:
            errors.append(f"Missing required payment term: {direction}.{payment_term}")
            continue
            
        if movement_type != "*" and movement_type not in rules[direction][payment_term]:
            errors.append(f"Missing required movement type: {direction}.{payment_term}.{movement_type}")
    
    return errors


def _validate_service_mappings(service_mappings: dict) -> List[str]:
    """Validate service mappings structure"""
    errors = []
    
    for category, services in service_mappings.items():
        if not isinstance(services, list):
            errors.append(f"Service mapping for '{category}' must be a list")
        elif not services:
            errors.append(f"Service mapping for '{category}' cannot be empty")
    
    return errors


def _validate_currency_mappings(currency_mappings: dict) -> List[str]:
    """Validate currency mappings structure"""
    errors = []
    
    for currency_rule, mapping in currency_mappings.items():
        if not isinstance(mapping, dict):
            errors.append(f"Currency mapping for '{currency_rule}' must be a dictionary")
            continue
            
        if 'fallback_by_region' in mapping:
            fallback_mapping = mapping['fallback_by_region']
            if not isinstance(fallback_mapping, dict):
                errors.append(f"fallback_by_region for '{currency_rule}' must be a dictionary")
    
    return errors


def _cross_validate_rules(rules: dict) -> List[str]:
    """Cross-validate that rules reference valid services and currencies"""
    errors = []
    
    service_mappings = rules.get('service_mappings', {})
    valid_charge_categories = set(service_mappings.keys())
    
    # Check that all charge categories in rules are defined in service mappings
    for direction, direction_rules in rules.get('rules', {}).items():
        for payment_term, payment_rules in direction_rules.items():
            for movement_type, rule_config in payment_rules.items():
                if movement_type.startswith('_') or not isinstance(rule_config, dict):
                    continue
                    
                charges = rule_config.get('charges', [])
                for charge in charges:
                    if charge not in valid_charge_categories:
                        errors.append(
                            f"Undefined charge category '{charge}' in {direction}.{payment_term}.{movement_type}"
                        )
    
    return errors


def _determine_direction(service_scope: str) -> str:
    """Determine direction (IMPORT/EXPORT) from service scope"""
    service_scope_upper = service_scope.upper()
    
    # Common patterns for determining direction
    if any(pattern in service_scope_upper for pattern in ['IMPORT', 'IMP', 'INBOUND']):
        return 'IMPORT'
    elif any(pattern in service_scope_upper for pattern in ['EXPORT', 'EXP', 'OUTBOUND']):
        return 'EXPORT'
    
    # Fallback: try to infer from movement patterns
    if any(pattern in service_scope_upper for pattern in ['A2D', 'AIRPORT_TO_DOOR']):
        return 'IMPORT'  # Usually airport to door is import
    elif any(pattern in service_scope_upper for pattern in ['D2A', 'DOOR_TO_AIRPORT']):
        return 'EXPORT'  # Usually door to airport is export
    
    # Default fallback
    logger.warning(f"Could not determine direction from service_scope '{service_scope}', defaulting to IMPORT")
    return 'IMPORT'


def _determine_movement_type(service_scope: str) -> str:
    """Determine movement type (D2D, A2D, D2A) from service scope"""
    service_scope_upper = service_scope.upper()
    
    # Direct pattern matching
    if 'D2D' in service_scope_upper or 'DOOR_TO_DOOR' in service_scope_upper:
        return 'D2D'
    elif 'A2D' in service_scope_upper or 'AIRPORT_TO_DOOR' in service_scope_upper:
        return 'A2D'
    elif 'D2A' in service_scope_upper or 'DOOR_TO_AIRPORT' in service_scope_upper:
        return 'D2A'
    
    # Fallback: analyze service scope content
    has_pickup = any(term in service_scope_upper for term in ['PICKUP', 'COLLECTION', 'DOOR'])
    has_delivery = any(term in service_scope_upper for term in ['DELIVERY', 'DOOR'])
    
    if has_pickup and has_delivery:
        return 'D2D'
    elif has_delivery and not has_pickup:
        return 'A2D'
    elif has_pickup and not has_delivery:
        return 'D2A'
    
    # Default fallback
    logger.warning(f"Could not determine movement type from service_scope '{service_scope}', defaulting to D2D")
    return 'D2D'


def _navigate_to_rule(rules: dict, direction: str, payment_term: str, movement_type: str) -> Optional[dict]:
    """Navigate to a specific rule in the rules hierarchy"""
    try:
        return rules[direction][payment_term][movement_type]
    except KeyError:
        return None


def _find_fallback_rule(rules: dict, direction: str, payment_term: str) -> Optional[dict]:
    """Find a fallback rule for the given direction and payment term"""
    try:
        payment_rules = rules[direction][payment_term]
        if '_fallback' in payment_rules:
            return payment_rules['_fallback']
    except KeyError:
        pass
    
    return None


def _get_region_from_iata(origin_iata: str, currency_mappings: dict) -> Optional[str]:
    """Determine region from origin IATA code using iata_to_region mapping."""
    if not currency_mappings:
        return None
    iata_to_region = currency_mappings.get("iata_to_region", {})
    return iata_to_region.get(origin_iata.upper())


def _resolve_shipper_currency(shipment_input: ShipmentInput, currency_mappings: dict) -> str:
    """Resolve shipper currency based on organization or region."""
    shipper_currency_mapping = currency_mappings.get('SHIPPER_CURRENCY', {})
    fallback_by_region = shipper_currency_mapping.get('fallback_by_region', {})
    
    region = _get_region_from_iata(shipment_input.origin_iata, currency_mappings)
    if region:
        return fallback_by_region.get(region, fallback_by_region.get('default', 'USD'))
    
    # Default fallback if region not found via IATA mapping
    return fallback_by_region.get('default', 'USD')


def _resolve_currency_by_region(shipment_input: ShipmentInput, fallback_by_region: dict, currency_mappings: dict) -> str:
    """Resolve currency based on regional fallback mapping."""
    region = _get_region_from_iata(shipment_input.origin_iata, currency_mappings)
    if region:
        return fallback_by_region.get(region, fallback_by_region.get('default', 'USD'))
    
    return fallback_by_region.get('default', 'USD')


# Convenience functions for common operations

def get_business_rules_instance() -> dict:
    """Get a cached instance of business rules (singleton pattern)"""
    if not hasattr(get_business_rules_instance, '_cached_rules'):
        get_business_rules_instance._cached_rules = load_business_rules()
        
        # Validate on first load
        validation_errors = validate_business_rules(get_business_rules_instance._cached_rules)
        if validation_errors:
            logger.error(f"Business rules validation failed: {validation_errors}")
            raise ValidationError(f"Business rules validation failed: {validation_errors}")
    
    return get_business_rules_instance._cached_rules


def apply_business_rules(shipment_input: ShipmentInput) -> PricingContext:
    """
    Convenience function to apply business rules using cached configuration
    
    Args:
        shipment_input: Shipment data to apply rules to
        
    Returns:
        PricingContext: Determined pricing context
    """
    rules = get_business_rules_instance()
    return determine_pricing_context(shipment_input, rules)


def clear_business_rules_cache():
    """Clear the cached business rules (useful for testing or config updates)"""
    if hasattr(get_business_rules_instance, '_cached_rules'):
        delattr(get_business_rules_instance, '_cached_rules')
    logger.info("Business rules cache cleared")