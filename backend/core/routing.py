# backend/core/routing.py

from decimal import Decimal
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CargoConstraintViolation:
    """Represents a violation of aircraft cargo constraints"""
    dimension: str  # 'length', 'width', 'height', 'weight'
    piece_number: int
    actual_value: Decimal
    limit_value: Decimal
    message: str


class RoutingValidator:
    """Validates cargo against aircraft constraints and determines required routing"""
    
    def check_aircraft_compatibility(
        self,
        pieces: List[dict],  # [{length_cm, width_cm, height_cm, weight_kg}]
        aircraft_type: 'AircraftType'
    ) -> Tuple[bool, List[CargoConstraintViolation]]:
        """
        Check if cargo pieces can fit through aircraft cargo door.
        
        Args:
            pieces: List of cargo pieces with dimensions
            aircraft_type: Aircraft type to check against
        
        Returns:
            Tuple of (is_compatible, list of violations)
        """
        violations = []
        
        for idx, piece in enumerate(pieces, 1):
            # Check length
            if aircraft_type.max_length_cm and Decimal(str(piece['length_cm'])) > aircraft_type.max_length_cm:
                violations.append(CargoConstraintViolation(
                    dimension='length',
                    piece_number=idx,
                    actual_value=Decimal(str(piece['length_cm'])),
                    limit_value=aircraft_type.max_length_cm,
                    message=f"Piece {idx}: Length {piece['length_cm']}cm exceeds {aircraft_type.code} limit of {aircraft_type.max_length_cm}cm"
                ))
            
            # Check width
            if aircraft_type.max_width_cm and Decimal(str(piece['width_cm'])) > aircraft_type.max_width_cm:
                violations.append(CargoConstraintViolation(
                    dimension='width',
                    piece_number=idx,
                    actual_value=Decimal(str(piece['width_cm'])),
                    limit_value=aircraft_type.max_width_cm,
                    message=f"Piece {idx}: Width {piece['width_cm']}cm exceeds {aircraft_type.code} limit of {aircraft_type.max_width_cm}cm"
                ))
            
            # Check height
            if aircraft_type.max_height_cm and Decimal(str(piece['height_cm'])) > aircraft_type.max_height_cm:
                violations.append(CargoConstraintViolation(
                    dimension='height',
                    piece_number=idx,
                    actual_value=Decimal(str(piece['height_cm'])),
                    limit_value=aircraft_type.max_height_cm,
                    message=f"Piece {idx}: Height {piece['height_cm']}cm exceeds {aircraft_type.code} limit of {aircraft_type.max_height_cm}cm"
                ))
            
            # Check weight
            if aircraft_type.max_piece_weight_kg and Decimal(str(piece['weight_kg'])) > aircraft_type.max_piece_weight_kg:
                violations.append(CargoConstraintViolation(
                    dimension='weight',
                    piece_number=idx,
                    actual_value=Decimal(str(piece['weight_kg'])),
                    limit_value=aircraft_type.max_piece_weight_kg,
                    message=f"Piece {idx}: Weight {piece['weight_kg']}kg exceeds {aircraft_type.code} limit of {aircraft_type.max_piece_weight_kg}kg"
                ))
        
        is_compatible = len(violations) == 0
        return is_compatible, violations
    
    def determine_required_service_level(
        self,
        origin_code: str,
        destination_code: str,
        pieces: List[dict]
    ) -> Tuple[str, Optional[str], List[CargoConstraintViolation]]:
        """
        Automatically determine which service level is required based on cargo dimensions.
        
        Logic:
        1. Get all available lanes for this O&D
        2. Check cargo against each lane's aircraft constraints
        3. Return cheapest compatible lane (DIRECT preferred)
        4. If no direct lane works, return via routing
        
        Args:
            origin_code: Origin airport IATA code
            destination_code: Destination airport IATA code
            pieces: List of cargo pieces with dimensions
        
        Returns:
            Tuple of (service_level, reason, violations)
        """
        from core.models import RouteLaneConstraint
        
        # Get possible lanes ordered by priority (DIRECT = priority 1 should come first)
        lanes = RouteLaneConstraint.objects.filter(
            origin__code=origin_code,
            destination__code=destination_code,
            is_active=True
        ).select_related('aircraft_type').order_by('priority')
        
        if not lanes.exists():
            return 'STANDARD', "No specific routing constraints found", []
        
        # Track violations from DIRECT lane for reporting
        direct_violations = []
        
        for lane in lanes:
            is_compatible, violations = self.check_aircraft_compatibility(
                pieces, lane.aircraft_type
            )
            
            if is_compatible:
                # Found a compatible lane!
                return lane.service_level, None, []
            
            # If this was the DIRECT lane and it doesn't work, save violations for reporting
            if lane.service_level == 'DIRECT':
                direct_violations = violations
        
        # If we get here, DIRECT didn't work, check for VIA routing
        via_lane = lanes.filter(service_level__startswith='VIA_').first()
        if via_lane:
            reason = f"Cargo exceeds {lanes.first().aircraft_type.code} constraints. " + \
                     "Routing via {via_location} required.".format(
                         via_location=via_lane.via_location.code if via_lane.via_location else "hub"
                     )
            return via_lane.service_level, reason, direct_violations
        
        # Fallback - no compatible routing found
        return 'STANDARD', "No compatible aircraft routing available", direct_violations
