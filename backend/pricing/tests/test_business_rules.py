"""
Unit tests for business rules configuration and validation logic.

This module provides comprehensive test coverage for the business rules engine,
including configuration loading, rule validation, rule application, and integration tests.
"""

import json
import pytest
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, mock_open

from ..dataclasses import ShipmentInput, PricingContext, Piece
from ..services.business_rules import (
    load_business_rules,
    validate_business_rules,
    determine_pricing_context,
    get_applicable_services,
    resolve_currency,
    apply_business_rules,
    clear_business_rules_cache,
    BusinessRulesError,
    ConfigurationError,
    ValidationError,
    RuleApplicationError,
    _determine_direction,
    _determine_movement_type,
    _resolve_shipper_currency,
    _validate_rule_structure,
    _validate_required_combinations,
    _validate_service_mappings,
    _validate_currency_mappings,
    _cross_validate_rules
)


class TestConfigurationLoading:
    """Test configuration loading functionality"""
    
    def test_load_valid_configuration(self):
        """Test loading a valid JSON configuration"""
        valid_config = {
            "version": "1.0",
            "description": "Test business rules",
            "rules": {
                "IMPORT": {
                    "COLLECT": {
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT", "DESTINATION"],
                            "description": "Import Collect Door-to-Door"
                        }
                    }
                }
            },
            "service_mappings": {
                "ORIGIN": ["PICKUP", "EXPORT_CLEARANCE"],
                "AIR_FREIGHT": ["AIR_FREIGHT", "FUEL_SURCHARGE"],
                "DESTINATION": ["IMPORT_CLEARANCE", "DELIVERY"]
            },
            "currency_mappings": {
                "SHIPPER_CURRENCY": {
                    "fallback_by_region": {
                        "AU": "AUD",
                        "US": "USD",
                        "default": "USD"
                    }
                }
            },
            "validation_rules": {
                "required_combinations": [
                    ["IMPORT", "COLLECT", "D2D"]
                ]
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(valid_config, f)
            temp_path = f.name
        
        try:
            result = load_business_rules(temp_path)
            assert result == valid_config
            assert result["version"] == "1.0"
            assert "IMPORT" in result["rules"]
        finally:
            Path(temp_path).unlink()
    
    def test_load_invalid_json(self):
        """Test handling of invalid JSON"""
        invalid_json = '{"version": "1.0", "rules": {'  # Missing closing brace
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(invalid_json)
            temp_path = f.name
        
        try:
            with pytest.raises(ConfigurationError, match="Invalid JSON"):
                load_business_rules(temp_path)
        finally:
            Path(temp_path).unlink()
    
    def test_load_missing_file(self):
        """Test handling of missing configuration file"""
        non_existent_path = "/path/that/does/not/exist.json"
        
        with pytest.raises(ConfigurationError, match="not found"):
            load_business_rules(non_existent_path)
    
    def test_load_default_path(self):
        """Test loading with default path when file doesn't exist"""
        with pytest.raises(ConfigurationError, match="not found"):
            load_business_rules()  # Should try default path
    
    def test_load_with_permission_error(self):
        """Test handling of permission errors"""
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with pytest.raises(ConfigurationError, match="Error loading"):
                load_business_rules("some_path.json")


class TestRuleValidation:
    """Test rule validation functionality"""
    
    def test_validate_complete_rules(self):
        """Test validation of complete and valid rules"""
        valid_rules = {
            "version": "1.0",
            "rules": {
                "IMPORT": {
                    "COLLECT": {
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT", "DESTINATION"]
                        }
                    }
                }
            },
            "service_mappings": {
                "ORIGIN": ["PICKUP"],
                "AIR_FREIGHT": ["AIR_FREIGHT"],
                "DESTINATION": ["DELIVERY"]
            },
            "currency_mappings": {
                "SHIPPER_CURRENCY": {
                    "fallback_by_region": {"default": "USD"}
                }
            },
            "validation_rules": {
                "required_combinations": [
                    ["IMPORT", "COLLECT", "D2D"]
                ]
            }
        }
        
        errors = validate_business_rules(valid_rules)
        assert errors == []
    
    def test_validate_missing_top_level_keys(self):
        """Test validation with missing top-level keys"""
        incomplete_rules = {
            "version": "1.0"
            # Missing rules, service_mappings, etc.
        }
        
        errors = validate_business_rules(incomplete_rules)
        assert len(errors) > 0
        assert any("Missing required top-level key: rules" in error for error in errors)
        assert any("Missing required top-level key: service_mappings" in error for error in errors)
    
    def test_validate_rule_structure(self):
        """Test validation of rule structure"""
        rules_with_missing_currency = {
            "IMPORT": {
                "COLLECT": {
                    "D2D": {
                        "charges": ["ORIGIN"]
                        # Missing currency
                    }
                }
            }
        }
        
        errors = _validate_rule_structure(rules_with_missing_currency)
        assert len(errors) > 0
        assert any("Missing currency" in error for error in errors)

    def test_validate_unknown_movement_type(self):
        """Test that an unknown movement type key is flagged during validation."""
        rules_with_unknown_movement = {
            "IMPORT": {
                "COLLECT": {
                    "D2X": {  # Invalid movement type
                        "currency": "PGK",
                        "charges": ["ORIGIN"]
                    }
                }
            }
        }
        
        errors = _validate_rule_structure(rules_with_unknown_movement)
        assert len(errors) > 0
        assert "Unknown movement type key: IMPORT.COLLECT.D2X" in errors
    
    def test_validate_required_combinations(self):
        """Test validation of required combinations"""
        rules = {
            "IMPORT": {
                "COLLECT": {
                    "A2D": {"currency": "PGK", "charges": ["DESTINATION"]}
                    # Missing D2D
                }
            }
        }
        
        required_combinations = [
            ["IMPORT", "COLLECT", "D2D"],
            ["IMPORT", "COLLECT", "A2D"]
        ]
        
        errors = _validate_required_combinations(rules, required_combinations)
        assert len(errors) > 0
        assert any("Missing required movement type: IMPORT.COLLECT.D2D" in error for error in errors)
    
    def test_validate_service_mappings(self):
        """Test validation of service mappings"""
        invalid_service_mappings = {
            "ORIGIN": "PICKUP",  # Should be a list
            "DESTINATION": [],   # Should not be empty
            "AIR_FREIGHT": ["AIR_FREIGHT", "FUEL_SURCHARGE"]  # Valid
        }
        
        errors = _validate_service_mappings(invalid_service_mappings)
        assert len(errors) >= 2
        assert any("must be a list" in error for error in errors)
        assert any("cannot be empty" in error for error in errors)
    
    def test_validate_currency_mappings(self):
        """Test validation of currency mappings"""
        invalid_currency_mappings = {
            "SHIPPER_CURRENCY": "invalid",  # Should be a dict
            "VALID_CURRENCY": {
                "fallback_by_region": "invalid"  # Should be a dict
            }
        }
        
        errors = _validate_currency_mappings(invalid_currency_mappings)
        assert len(errors) >= 2
        assert any("must be a dictionary" in error for error in errors)
    
    def test_cross_validate_rules(self):
        """Test cross-validation between rules and service mappings"""
        rules_config = {
            "rules": {
                "IMPORT": {
                    "COLLECT": {
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["UNDEFINED_CHARGE"]  # Not in service_mappings
                        }
                    }
                }
            },
            "service_mappings": {
                "ORIGIN": ["PICKUP"],
                "DESTINATION": ["DELIVERY"]
            }
        }
        
        errors = _cross_validate_rules(rules_config)
        assert len(errors) > 0
        assert any("Undefined charge category 'UNDEFINED_CHARGE'" in error for error in errors)


class TestRuleApplication:
    """Test rule application functionality"""
    
    @pytest.fixture
    def sample_rules(self):
        """Sample business rules for testing"""
        return {
            "version": "1.0",
            "rules": {
                "IMPORT": {
                    "COLLECT": {
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT", "DESTINATION"],
                            "description": "Import Collect Door-to-Door"
                        },
                        "A2D": {
                            "currency": "PGK",
                            "charges": ["DESTINATION"],
                            "description": "Import Collect Airport-to-Door"
                        }
                    },
                    "PREPAID": {
                        "A2D": {
                            "currency": "SHIPPER_CURRENCY",
                            "charges": ["DESTINATION"],
                            "description": "Import Prepaid Airport-to-Door"
                        }
                    }
                },
                "EXPORT": {
                    "PREPAID": {
                        "D2A": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT"],
                            "description": "Export Prepaid Door-to-Airport"
                        },
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT", "AGENT_CLEARANCE", "DELIVERY"],
                            "description": "Export Prepaid Door-to-Door"
                        }
                    },
                    "COLLECT": {
                        "_fallback": {
                            "currency": "PGK",
                            "charges": ["ORIGIN"],
                            "description": "Export Collect fallback",
                            "requires_manual_review": True
                        }
                    }
                }
            },
            "service_mappings": {
                "ORIGIN": ["PICKUP", "EXPORT_CLEARANCE", "HANDLING"],
                "AIR_FREIGHT": ["AIR_FREIGHT", "FUEL_SURCHARGE", "SECURITY_SURCHARGE"],
                "DESTINATION": ["IMPORT_CLEARANCE", "DELIVERY", "CUSTOMS_HANDLING"],
                "AGENT_CLEARANCE": ["AGENT_CLEARANCE", "DOCUMENTATION"],
                "DELIVERY": ["FINAL_DELIVERY", "NOTIFICATION"]
            },
            "currency_mappings": {
                "SHIPPER_CURRENCY": {
                    "fallback_by_region": {
                        "AU": "AUD",
                        "US": "USD",
                        "PNG": "PGK",
                        "default": "USD"
                    }
                },
                "iata_to_region": {
                    "SYD": "AU", "BNE": "AU",
                    "LAX": "US",
                    "POM": "PNG"
                }
            },
            "validation_rules": {
                "required_combinations": [
                    ["IMPORT", "COLLECT", "D2D"],
                    ["IMPORT", "COLLECT", "A2D"],
                    ["IMPORT", "PREPAID", "A2D"],
                    ["EXPORT", "PREPAID", "D2A"],
                    ["EXPORT", "PREPAID", "D2D"]
                ]
            }
        }
    
    @pytest.fixture
    def sample_shipment_import_collect_d2d(self):
        """Sample shipment for Import Collect D2D"""
        return ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("10.5"))]
        )
    
    @pytest.fixture
    def sample_shipment_import_collect_a2d(self):
        """Sample shipment for Import Collect A2D"""
        return ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_A2D",
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("5.0"))]
        )
    
    @pytest.fixture
    def sample_shipment_import_prepaid_a2d(self):
        """Sample shipment for Import Prepaid A2D"""
        return ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_A2D",
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=Decimal("7.5"))]
        )
    
    @pytest.fixture
    def sample_shipment_export_prepaid_d2a(self):
        """Sample shipment for Export Prepaid D2A"""
        return ShipmentInput(
            org_id=1,
            origin_iata="POM",
            dest_iata="SYD",
            service_scope="EXPORT_D2A",
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=Decimal("15.0"))]
        )
    
    @pytest.fixture
    def sample_shipment_export_prepaid_d2d(self):
        """Sample shipment for Export Prepaid D2D"""
        return ShipmentInput(
            org_id=1,
            origin_iata="POM",
            dest_iata="SYD",
            service_scope="EXPORT_D2D",
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=Decimal("20.0"))]
        )
    
    def test_import_collect_d2d(self, sample_rules, sample_shipment_import_collect_d2d):
        """Test Import Collect D2D → PGK currency, full service scope"""
        context = determine_pricing_context(sample_shipment_import_collect_d2d, sample_rules)
        
        assert context.currency == "PGK"
        assert context.charge_scope == ["ORIGIN", "AIR_FREIGHT", "DESTINATION"]
        assert context.requires_manual_review is False
        assert "IMPORT.COLLECT.D2D" in context.rule_path
        assert "Import Collect Door-to-Door" in context.description
        
        # Check applicable services
        expected_services = [
            "PICKUP", "EXPORT_CLEARANCE", "HANDLING",  # ORIGIN
            "AIR_FREIGHT", "FUEL_SURCHARGE", "SECURITY_SURCHARGE",  # AIR_FREIGHT
            "IMPORT_CLEARANCE", "DELIVERY", "CUSTOMS_HANDLING"  # DESTINATION
        ]
        assert all(service in context.applicable_services for service in expected_services)
    
    def test_import_collect_a2d(self, sample_rules, sample_shipment_import_collect_a2d):
        """Test Import Collect A2D → PGK currency, destination only"""
        context = determine_pricing_context(sample_shipment_import_collect_a2d, sample_rules)
        
        assert context.currency == "PGK"
        assert context.charge_scope == ["DESTINATION"]
        assert context.requires_manual_review is False
        assert "IMPORT.COLLECT.A2D" in context.rule_path
        
        # Check applicable services (destination only)
        expected_services = ["IMPORT_CLEARANCE", "DELIVERY", "CUSTOMS_HANDLING"]
        assert all(service in context.applicable_services for service in expected_services)
        # Should not include origin or air freight services
        assert "PICKUP" not in context.applicable_services
        assert "AIR_FREIGHT" not in context.applicable_services
    
    def test_import_prepaid_a2d(self, sample_rules, sample_shipment_import_prepaid_a2d):
        """Test Import Prepaid A2D → Shipper currency, destination only"""
        context = determine_pricing_context(sample_shipment_import_prepaid_a2d, sample_rules)
        
        # Should resolve to AUD based on SYD origin (Australian airport)
        assert context.currency == "AUD"
        assert context.charge_scope == ["DESTINATION"]
        assert context.requires_manual_review is False
        assert "IMPORT.PREPAID.A2D" in context.rule_path
    
    def test_export_prepaid_d2a(self, sample_rules, sample_shipment_export_prepaid_d2a):
        """Test Export Prepaid D2A → PGK currency, origin + air freight"""
        context = determine_pricing_context(sample_shipment_export_prepaid_d2a, sample_rules)
        
        assert context.currency == "PGK"
        assert context.charge_scope == ["ORIGIN", "AIR_FREIGHT"]
        assert context.requires_manual_review is False
        assert "EXPORT.PREPAID.D2A" in context.rule_path
        
        # Check applicable services (origin + air freight only)
        expected_services = [
            "PICKUP", "EXPORT_CLEARANCE", "HANDLING",  # ORIGIN
            "AIR_FREIGHT", "FUEL_SURCHARGE", "SECURITY_SURCHARGE"  # AIR_FREIGHT
        ]
        assert all(service in context.applicable_services for service in expected_services)
        # Should not include destination services
        assert "IMPORT_CLEARANCE" not in context.applicable_services
    
    def test_export_prepaid_d2d(self, sample_rules, sample_shipment_export_prepaid_d2d):
        """Test Export Prepaid D2D → PGK currency, full service scope"""
        context = determine_pricing_context(sample_shipment_export_prepaid_d2d, sample_rules)
        
        assert context.currency == "PGK"
        assert context.charge_scope == ["ORIGIN", "AIR_FREIGHT", "AGENT_CLEARANCE", "DELIVERY"]
        assert context.requires_manual_review is False
        assert "EXPORT.PREPAID.D2D" in context.rule_path
        
        # Check applicable services include agent clearance and delivery
        assert "AGENT_CLEARANCE" in context.applicable_services
        assert "FINAL_DELIVERY" in context.applicable_services
    
    def test_export_collect_fallback(self, sample_rules):
        """Test Export Collect scenarios → Manual review required"""
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="POM",
            dest_iata="SYD",
            service_scope="EXPORT_D2D",
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("10.0"))]
        )
        
        context = determine_pricing_context(shipment, sample_rules)
        
        assert context.currency == "PGK"
        assert context.charge_scope == ["ORIGIN"]
        assert context.requires_manual_review is True
        assert "fallback" in context.rule_path
        assert "Export Collect fallback" in context.description
    
    def test_invalid_combination_error(self, sample_rules):
        """Test invalid combinations → Proper error handling"""
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_D2A",  # Invalid combination
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("10.0"))]
        )
        
                        with pytest.raises(RuleApplicationError, match="No business rule found"):
                            determine_pricing_context(shipment, sample_rules)
                
                    def test_none_payment_term_defaults_to_prepaid(self, sample_rules):
                        """Test that a None payment_term defaults to PREPAID."""
                        # This shipment would be IMPORT.PREPAID.A2D
                        shipment = ShipmentInput(
                            org_id=1,
                            origin_iata="SYD",
                            dest_iata="POM",
                            service_scope="IMPORT_A2D",
                            payment_term=None,
                            pieces=[Piece(weight_kg=Decimal("10.0"))]
                        )
                        
                        context = determine_pricing_context(shipment, sample_rules)
                        
                        # Should follow the PREPAID path
                        assert context.metadata['payment_term'] == 'PREPAID'
                        assert "IMPORT.PREPAID.A2D" in context.rule_path
                
                    def test_invalid_payment_term_raises_error(self, sample_rules):
                        """Test that an invalid payment_term raises a RuleApplicationError."""
                        shipment = ShipmentInput(
                            org_id=1,
                            origin_iata="SYD",
                            dest_iata="POM",
                            service_scope="IMPORT_A2D",
                            payment_term="INVALID_TERM",
                            pieces=[Piece(weight_kg=Decimal("10.0"))]
                        )
                        
                        with pytest.raises(RuleApplicationError, match="Unsupported payment term: INVALID_TERM"):
                            determine_pricing_context(shipment, sample_rules)
                    
                    def test_explicit_shipment_type_overrides_service_scope(self, sample_rules):                """Test that an explicit shipment_type is honored over service_scope heuristics for movement type."""
                # service_scope suggests D2D, but shipment_type explicitly sets A2D
                shipment = ShipmentInput(
                    org_id=1,
                    origin_iata="SYD",
                    dest_iata="POM",
                    service_scope="IMPORT_D2D_SERVICE",  # Heuristics would say D2D
                    payment_term="COLLECT",
                    shipment_type="A2D",  # Explicitly A2D
                    pieces=[Piece(weight_kg=Decimal("10.0"))]
                )
                
                context = determine_pricing_context(shipment, sample_rules)
                
                # The movement type should be A2D from shipment_type, not D2D from service_scope
                assert context.metadata['movement_type'] == 'A2D'
                # The rule path should reflect this
                assert "IMPORT.COLLECT.A2D" in context.rule_path
                # The charge scope should match the A2D rule
                assert context.charge_scope == ["DESTINATION"]
            
            def test_currency_fallback_applied(self, sample_rules, caplog):        """Test that per-rule currency_fallback is applied when SHIPPER_CURRENCY resolution fails."""
        # Add currency_fallback to the relevant rule
        sample_rules["rules"]["IMPORT"]["PREPAID"]["A2D"]["currency_fallback"] = ["AUD", "USD"]
        
        # Create a shipment where shipper currency cannot be resolved (e.g., non-AU/US/PNG origin)
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="LHR",  # London - will fallback to default USD in _resolve_shipper_currency
            dest_iata="POM",
            service_scope="IMPORT_A2D",
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=Decimal("10.0"))]
        )
        
        caplog.set_level(logging.DEBUG, logger="pricing.services.business_rules")
        
        context = determine_pricing_context(shipment, sample_rules)
        
        # The currency should be AUD from the currency_fallback list, not the default USD
        assert context.currency == "AUD"
        
        # Check for the debug log message
        assert "Applied per-rule currency fallback" in caplog.text
        assert "selected AUD" in caplog.text
    
    def test_missing_service_mappings_graceful_degradation(self, sample_rules):
        """Test missing service mappings → Graceful degradation"""
        # Remove a service mapping
        del sample_rules["service_mappings"]["ORIGIN"]
        
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("10.0"))]
        )
        
        context = determine_pricing_context(shipment, sample_rules)
        
        # Should still work but include the unmapped category
        assert "ORIGIN" in context.applicable_services
        assert context.currency == "PGK"


class TestHelperFunctions:
    """Test helper functions"""
    
    def test_determine_direction(self):
        """Test direction determination from service scope"""
        assert _determine_direction("IMPORT_D2D") == "IMPORT"
        assert _determine_direction("EXPORT_A2D") == "EXPORT"
        assert _determine_direction("IMP_SERVICES") == "IMPORT"
        assert _determine_direction("EXP_SERVICES") == "EXPORT"
        assert _determine_direction("A2D_SERVICE") == "IMPORT"  # Airport to door typically import
        assert _determine_direction("D2A_SERVICE") == "EXPORT"  # Door to airport typically export
        assert _determine_direction("UNKNOWN_SERVICE") == "IMPORT"  # Default fallback
    
    def test_determine_movement_type(self):
        """Test movement type determination from service scope"""
        assert _determine_movement_type("IMPORT_D2D") == "D2D"
        assert _determine_movement_type("EXPORT_A2D") == "A2D"
        assert _determine_movement_type("SERVICE_D2A") == "D2A"
        assert _determine_movement_type("DOOR_TO_DOOR") == "D2D"
        assert _determine_movement_type("AIRPORT_TO_DOOR") == "A2D"
        assert _determine_movement_type("DOOR_TO_AIRPORT") == "D2A"
        assert _determine_movement_type("PICKUP_DELIVERY") == "D2D"  # Has both pickup and delivery
        assert _determine_movement_type("DELIVERY_ONLY") == "A2D"  # Has delivery, no pickup
        assert _determine_movement_type("PICKUP_ONLY") == "D2A"  # Has pickup, no delivery
        assert _determine_movement_type("UNKNOWN") == "D2D"  # Default fallback
    
    def test_get_applicable_services(self):
        """Test service mapping resolution"""
        charge_scope = ["ORIGIN", "AIR_FREIGHT", "DESTINATION"]
        service_mappings = {
            "ORIGIN": ["PICKUP", "EXPORT_CLEARANCE"],
            "AIR_FREIGHT": ["AIR_FREIGHT", "FUEL_SURCHARGE"],
            "DESTINATION": ["IMPORT_CLEARANCE", "DELIVERY"],
            "UNUSED": ["UNUSED_SERVICE"]
        }
        
        services = get_applicable_services(charge_scope, service_mappings)
        
        expected = [
            "PICKUP", "EXPORT_CLEARANCE",
            "AIR_FREIGHT", "FUEL_SURCHARGE",
            "IMPORT_CLEARANCE", "DELIVERY"
        ]
        assert services == expected
    
    def test_get_applicable_services_missing_mapping(self):
        """Test service mapping with missing categories"""
        charge_scope = ["ORIGIN", "MISSING_CATEGORY"]
        service_mappings = {
            "ORIGIN": ["PICKUP", "EXPORT_CLEARANCE"]
        }
        
        services = get_applicable_services(charge_scope, service_mappings)
        
        # Should include mapped services and unmapped category as fallback
        assert "PICKUP" in services
        assert "EXPORT_CLEARANCE" in services
        assert "MISSING_CATEGORY" in services
    
    def test_get_applicable_services_no_duplicates(self):
        """Test that duplicate services are removed"""
        charge_scope = ["ORIGIN", "DESTINATION"]
        service_mappings = {
            "ORIGIN": ["PICKUP", "SHARED_SERVICE"],
            "DESTINATION": ["DELIVERY", "SHARED_SERVICE"]  # Duplicate
        }
        
        services = get_applicable_services(charge_scope, service_mappings)
        
        # Should have no duplicates
        assert services.count("SHARED_SERVICE") == 1
        assert len(services) == 3  # PICKUP, SHARED_SERVICE, DELIVERY
    
    def test_resolve_currency_direct(self):
        """Test direct currency resolution"""
        assert resolve_currency("PGK", None, {}) == "PGK"
        assert resolve_currency("AUD", None, {}) == "AUD"
        assert resolve_currency("USD", None, {}) == "USD"
    
    def test_resolve_currency_shipper_currency(self):
        """Test shipper currency resolution"""
        shipment_au = ShipmentInput(
            org_id=1,
            origin_iata="SYD",  # Australian airport
            dest_iata="POM",
            service_scope="IMPORT_A2D",
            pieces=[]
        )
        
        currency_mappings = {
            "SHIPPER_CURRENCY": {
                "fallback_by_region": {
                    "AU": "AUD",
                    "US": "USD",
                    "PNG": "PGK",
                    "default": "USD"
                }
            }
        }
        
        currency = resolve_currency("SHIPPER_CURRENCY", shipment_au, currency_mappings)
        assert currency == "AUD"
    
    def test_resolve_currency_unknown_rule(self):
        """Test unknown currency rule fallback"""
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="XXX",
            dest_iata="YYY",
            service_scope="IMPORT_A2D",
            pieces=[]
        )
        
        currency = resolve_currency("UNKNOWN_RULE", shipment, {})
        assert currency == "USD"  # Default fallback
    
    def test_resolve_shipper_currency_regions(self):
        """Test shipper currency resolution for different regions using iata_to_region mapping."""
        currency_mappings = {
            "SHIPPER_CURRENCY": {
                "fallback_by_region": {
                    "AU": "AUD",
                    "US": "USD",
                    "PNG": "PGK",
                    "default": "USD"
                }
            },
            "iata_to_region": {
                "SYD": "AU",
                "LAX": "US",
                "POM": "PNG"
            }
        }
        
        # Test Australian airport
        shipment_au = ShipmentInput(org_id=1, origin_iata="SYD", dest_iata="POM", service_scope="TEST", pieces=[])
        currency = _resolve_shipper_currency(shipment_au, currency_mappings)
        assert currency == "AUD"
        
        # Test US airport
        shipment_us = ShipmentInput(org_id=1, origin_iata="LAX", dest_iata="POM", service_scope="TEST", pieces=[])
        currency = _resolve_shipper_currency(shipment_us, currency_mappings)
        assert currency == "USD"
        
        # Test PNG airport
        shipment_png = ShipmentInput(org_id=1, origin_iata="POM", dest_iata="SYD", service_scope="TEST", pieces=[])
        currency = _resolve_shipper_currency(shipment_png, currency_mappings)
        assert currency == "PGK"
        
        # Test unknown region
        shipment_unknown = ShipmentInput(org_id=1, origin_iata="LHR", dest_iata="YYY", service_scope="TEST", pieces=[])
        currency = _resolve_shipper_currency(shipment_unknown, currency_mappings)
        assert currency == "USD"  # Default fallback


class TestIntegrationTests:
    """Integration tests for end-to-end functionality"""
    
    @pytest.fixture
    def complete_rules_config(self):
        """Complete business rules configuration for integration testing"""
        return {
            "version": "1.0",
            "description": "Complete business rules for integration testing",
            "rules": {
                "IMPORT": {
                    "COLLECT": {
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT", "DESTINATION"],
                            "description": "Import Collect Door-to-Door: PGK currency with full service scope"
                        },
                        "A2D": {
                            "currency": "PGK",
                            "charges": ["DESTINATION"],
                            "description": "Import Collect Airport-to-Door: PGK currency with destination services only"
                        }
                    },
                    "PREPAID": {
                        "A2D": {
                            "currency": "SHIPPER_CURRENCY",
                            "charges": ["DESTINATION"],
                            "description": "Import Prepaid Airport-to-Door: Shipper's currency with destination services only"
                        }
                    }
                },
                "EXPORT": {
                    "PREPAID": {
                        "D2A": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT"],
                            "description": "Export Prepaid Door-to-Airport: PGK currency with origin and air freight"
                        },
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["ORIGIN", "AIR_FREIGHT", "AGENT_CLEARANCE", "DELIVERY"],
                            "description": "Export Prepaid Door-to-Door: PGK currency with full service including agent clearance and delivery"
                        }
                    },
                    "COLLECT": {
                        "_fallback": {
                            "currency": "PGK",
                            "charges": ["ORIGIN"],
                            "description": "Export Collect fallback: PGK currency with origin services only",
                            "requires_manual_review": True
                        }
                    }
                }
            },
            "service_mappings": {
                "ORIGIN": ["PICKUP", "EXPORT_CLEARANCE", "HANDLING"],
                "AIR_FREIGHT": ["AIR_FREIGHT", "FUEL_SURCHARGE", "SECURITY_SURCHARGE"],
                "DESTINATION": ["IMPORT_CLEARANCE", "DELIVERY", "CUSTOMS_HANDLING"],
                "AGENT_CLEARANCE": ["AGENT_CLEARANCE", "DOCUMENTATION"],
                "DELIVERY": ["FINAL_DELIVERY", "NOTIFICATION"]
            },
            "currency_mappings": {
                "SHIPPER_CURRENCY": {
                    "determination_logic": "Use shipper's organization currency or fallback to region-based currency",
                    "fallback_by_region": {
                        "AU": "AUD",
                        "US": "USD",
                        "PNG": "PGK",
                        "default": "USD"
                    }
                },
                "iata_to_region": {
                    "SYD": "AU", "BNE": "AU",
                    "LAX": "US",
                    "POM": "PNG"
                }
            },
            "validation_rules": {
                "required_combinations": [
                    ["IMPORT", "COLLECT", "D2D"],
                    ["IMPORT", "COLLECT", "A2D"],
                    ["IMPORT", "PREPAID", "A2D"],
                    ["EXPORT", "PREPAID", "D2A"],
                    ["EXPORT", "PREPAID", "D2D"]
                ]
            }
        }
    
    def test_end_to_end_rule_application(self, complete_rules_config):
        """Test end-to-end rule application with complete configuration"""
        # Test multiple scenarios
        test_cases = [
            {
                "shipment": ShipmentInput(
                    org_id=1, origin_iata="SYD", dest_iata="POM",
                    service_scope="IMPORT_D2D", payment_term="COLLECT",
                    pieces=[Piece(weight_kg=Decimal("10.0"))]
                ),
                "expected_currency": "PGK",
                "expected_charges": ["ORIGIN", "AIR_FREIGHT", "DESTINATION"],
                "expected_manual_review": False
            },
            {
                "shipment": ShipmentInput(
                    org_id=1, origin_iata="SYD", dest_iata="POM",
                    service_scope="IMPORT_A2D", payment_term="PREPAID",
                    pieces=[Piece(weight_kg=Decimal("5.0"))]
                ),
                "expected_currency": "AUD",  # Australian origin
                "expected_charges": ["DESTINATION"],
                "expected_manual_review": False
            },
            {
                "shipment": ShipmentInput(
                    org_id=1, origin_iata="POM", dest_iata="SYD",
                    service_scope="EXPORT_D2D", payment_term="COLLECT",
                    pieces=[Piece(weight_kg=Decimal("15.0"))]
                ),
                "expected_currency": "PGK",
                "expected_charges": ["ORIGIN"],
                "expected_manual_review": True  # Fallback rule
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            context = determine_pricing_context(test_case["shipment"], complete_rules_config)
            
            assert context.currency == test_case["expected_currency"], f"Test case {i}: Currency mismatch"
            assert context.charge_scope == test_case["expected_charges"], f"Test case {i}: Charge scope mismatch"
            assert context.requires_manual_review == test_case["expected_manual_review"], f"Test case {i}: Manual review mismatch"
            assert len(context.applicable_services) > 0, f"Test case {i}: No applicable services"
            assert context.rule_path != "", f"Test case {i}: Empty rule path"
            assert context.description != "", f"Test case {i}: Empty description"
    
    def test_configuration_validation_integration(self, complete_rules_config):
        """Test that complete configuration passes validation"""
        errors = validate_business_rules(complete_rules_config)
        assert errors == [], f"Configuration validation failed: {errors}"
    
    def test_fallback_behavior_integration(self, complete_rules_config):
        """Test fallback behavior in integration scenario"""
        # Test Export Collect scenario that should use fallback
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="POM",
            dest_iata="SYD",
            service_scope="EXPORT_A2D",  # Not explicitly defined, should use fallback
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("8.0"))]
        )
        
        context = determine_pricing_context(shipment, complete_rules_config)
        
        assert context.requires_manual_review is True
        assert "fallback" in context.rule_path
        assert context.currency == "PGK"
        assert context.charge_scope == ["ORIGIN"]
    
    def test_error_handling_integration(self, complete_rules_config):
        """Test error handling in integration scenarios"""
        # Test completely invalid combination
        invalid_shipment = ShipmentInput(
            org_id=1,
            origin_iata="XXX",
            dest_iata="YYY",
            service_scope="INVALID_SCOPE",
            payment_term="INVALID_TERM",
            pieces=[]
        )
        
        with pytest.raises(RuleApplicationError):
            determine_pricing_context(invalid_shipment, complete_rules_config)
    
    @patch('pricing.services.business_rules.load_business_rules')
    def test_cached_rules_integration(self, mock_load_rules, complete_rules_config):
        """Test cached business rules functionality"""
        mock_load_rules.return_value = complete_rules_config
        
        # Clear cache first
        clear_business_rules_cache()
        
        # Create test shipment
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            pieces=[Piece(weight_kg=Decimal("10.0"))]
        )
        
        # First call should load rules
        context1 = apply_business_rules(shipment)
        assert mock_load_rules.call_count == 1
        
        # Second call should use cached rules
        context2 = apply_business_rules(shipment)
        assert mock_load_rules.call_count == 1  # Should not increase
        
        # Results should be identical
        assert context1.currency == context2.currency
        assert context1.charge_scope == context2.charge_scope
        assert context1.rule_path == context2.rule_path
    
    def test_metadata_preservation_integration(self, complete_rules_config):
        """Test that metadata is properly preserved through the integration flow"""
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="POM",
            dest_iata="SYD",
            service_scope="EXPORT_D2A",
            payment_term="PREPAID",
            pieces=[Piece(weight_kg=Decimal("12.0"))]
        )
        
        context = determine_pricing_context(shipment, complete_rules_config)
        
        # Check that metadata contains expected information
        assert 'direction' in context.metadata
        assert 'payment_term' in context.metadata
        assert 'movement_type' in context.metadata
        assert 'rule_config' in context.metadata
        
        assert context.metadata['direction'] == 'EXPORT'
        assert context.metadata['payment_term'] == 'PREPAID'
        assert context.metadata['movement_type'] == 'D2A'
        assert isinstance(context.metadata['rule_config'], dict)


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_business_rules_error_hierarchy(self):
        """Test that error classes have proper inheritance"""
        assert issubclass(ConfigurationError, BusinessRulesError)
        assert issubclass(ValidationError, BusinessRulesError)
        assert issubclass(RuleApplicationError, BusinessRulesError)
    
    def test_configuration_error_scenarios(self):
        """Test various configuration error scenarios"""
        # Test with completely empty configuration
        with pytest.raises(ConfigurationError):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write("")
                temp_path = f.name
            
            try:
                load_business_rules(temp_path)
            finally:
                Path(temp_path).unlink()
    
    def test_validation_error_with_invalid_rules(self):
        """Test validation error with severely invalid rules"""
        invalid_rules = {
            "version": "1.0",
            "rules": "this should be a dict",  # Invalid type
            "service_mappings": {},
            "currency_mappings": {},
            "validation_rules": {}
        }
        
        errors = validate_business_rules(invalid_rules)
        assert len(errors) > 0
    
    def test_rule_application_error_scenarios(self):
        """Test various rule application error scenarios"""
        minimal_rules = {
            "version": "1.0",
            "rules": {},
            "service_mappings": {},
            "currency_mappings": {},
            "validation_rules": {}
        }
        
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            pieces=[]
        )
        
        with pytest.raises(RuleApplicationError):
            determine_pricing_context(shipment, minimal_rules)
    
    def test_graceful_degradation_missing_mappings(self):
        """Test graceful degradation when mappings are missing"""
        rules_with_missing_mappings = {
            "version": "1.0",
            "rules": {
                "IMPORT": {
                    "COLLECT": {
                        "D2D": {
                            "currency": "PGK",
                            "charges": ["UNKNOWN_CHARGE"]
                        }
                    }
                }
            },
            "service_mappings": {},  # Empty mappings
            "currency_mappings": {},
            "validation_rules": {}
        }
        
        shipment = ShipmentInput(
            org_id=1,
            origin_iata="SYD",
            dest_iata="POM",
            service_scope="IMPORT_D2D",
            payment_term="COLLECT",
            pieces=[]
        )
        
        # Should not raise an error, but should handle gracefully
        context = determine_pricing_context(shipment, rules_with_missing_mappings)
        assert context.currency == "PGK"
        assert "UNKNOWN_CHARGE" in context.applicable_services  # Fallback behavior