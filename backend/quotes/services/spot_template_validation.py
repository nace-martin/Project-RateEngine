import logging
from typing import Dict, Any, Optional
from core.business_rules import classify_png_shipment
from quotes.spot_models import SpotPricingEnvelopeDB, ExpectedChargeTemplate, ExpectedTemplateLine

logger = logging.getLogger(__name__)


def resolve_expected_charge_template(shipment_context: dict) -> Optional[ExpectedChargeTemplate]:
    """
    Resolves the most specific ExpectedChargeTemplate for a given shipment context.
    Uses a specificity scoring hierarchy:
    - origin_code / destination_code match: +10 pts each
    - origin_country / destination_country match: +5 pts each
    - service_scope match (if not ANY): +3 pts
    - transport_mode match (if not ANY): +2 pts
    - mode match: +1 pt
    """
    if not shipment_context:
        return None

    # Derive mode
    origin_country = shipment_context.get("origin_country")
    destination_country = shipment_context.get("destination_country")
    try:
        mode = classify_png_shipment(origin_country, destination_country)
    except ValueError:
        mode = None

    transport_mode = shipment_context.get("transport_mode") or "ANY"
    service_scope = shipment_context.get("service_scope") or "ANY"
    origin_code = shipment_context.get("origin_code")
    destination_code = shipment_context.get("destination_code")

    candidates = ExpectedChargeTemplate.objects.filter(is_active=True)
    best_template = None
    best_score = -1

    for template in candidates:
        # Check compatibility
        if mode and template.mode != mode:
            continue
        if template.transport_mode != "ANY" and template.transport_mode != transport_mode:
            continue
        if template.service_scope != "ANY" and template.service_scope != service_scope:
            continue
        if template.origin_country and template.origin_country != origin_country:
            continue
        if template.destination_country and template.destination_country != destination_country:
            continue
        if template.origin_code and template.origin_code != origin_code:
            continue
        if template.destination_code and template.destination_code != destination_code:
            continue

        # Compute specificity score
        score = 0
        if template.origin_code:
            score += 10
        if template.destination_code:
            score += 10
        if template.origin_country:
            score += 5
        if template.destination_country:
            score += 5
        if template.service_scope != "ANY":
            score += 3
        if template.transport_mode != "ANY":
            score += 2
        if template.mode:
            score += 1

        if score > best_score:
            best_score = score
            best_template = template
        elif score == best_score:
            # Tie breaker: prefer the template with the lower ID (earlier database insertion) for determinism
            if best_template is None or template.pk < best_template.pk:
                best_template = template

    return best_template


def validate_envelope_charges(envelope: SpotPricingEnvelopeDB) -> Dict[str, Any]:
    """
    Compares the actual charges inside a SpotPricingEnvelopeDB against the resolved ExpectedChargeTemplate.
    Returns findings in-memory only.
    """
    findings = []
    
    # 1. Resolve Template
    context = envelope.shipment_context_json or {}
    template = resolve_expected_charge_template(context)
    
    if not template:
        findings.append({
            "code": "template_not_found",
            "severity": "Review",
            "message": "No applicable expectation template resolved for this shipment context.",
            "canonical_charge_type_code": None
        })
        return {
            "status": "WARNINGS",
            "template_id": None,
            "findings": findings
        }

    # 2. Gather actual charge lines
    actual_lines = envelope.charge_lines.all()
    
    # Group by canonical type
    actual_by_canonical = {}
    for line in actual_lines:
        if line.canonical_charge_type:
            actual_by_canonical.setdefault(line.canonical_charge_type, []).append(line)

    # 3. Compare with template line expectations
    template_lines = template.lines.filter(is_active=True)
    
    for t_line in template_lines:
        canonical_type = t_line.canonical_charge_type
        level = t_line.requirement_level
        expected_basis = t_line.expected_basis
        
        has_actual = canonical_type in actual_by_canonical
        
        if level == ExpectedTemplateLine.RequirementLevel.REQUIRED and not has_actual:
            findings.append({
                "code": "expected_charge_missing",
                "severity": "Warning",
                "message": f"Expected charge of type '{canonical_type.name}' ({canonical_type.code}) is missing.",
                "canonical_charge_type_code": canonical_type.code
            })
            
        elif level == ExpectedTemplateLine.RequirementLevel.EXCLUDED and has_actual:
            findings.append({
                "code": "unexpected_charge_present",
                "severity": "Warning",
                "message": f"Excluded charge of type '{canonical_type.name}' ({canonical_type.code}) was included.",
                "canonical_charge_type_code": canonical_type.code
            })
            
        elif level == ExpectedTemplateLine.RequirementLevel.CONDITIONAL and has_actual:
            findings.append({
                "code": "conditional_charge_present",
                "severity": "Review",
                "message": f"Conditional charge of type '{canonical_type.name}' ({canonical_type.code}) is present and requires confirmation.",
                "canonical_charge_type_code": canonical_type.code
            })
            
        # Check calculation basis mismatch if actual is present
        if has_actual and expected_basis != "any":
            for act_line in actual_by_canonical[canonical_type]:
                if act_line.calculation_basis != expected_basis:
                    findings.append({
                        "code": "expected_basis_mismatch",
                        "severity": "Review",
                        "message": (
                            f"Basis mismatch for '{canonical_type.name}': "
                            f"Expected basis '{expected_basis}' but actual was '{act_line.calculation_basis}'."
                        ),
                        "canonical_charge_type_code": canonical_type.code
                    })

    # 4. Check for duplicates in actual charge lines
    for canonical_type, lines in actual_by_canonical.items():
        if len(lines) > 1:
            findings.append({
                "code": "duplicate_charge_family",
                "severity": "Review",
                "message": f"Multiple lines detected resolving to canonical charge family '{canonical_type.name}' ({canonical_type.code}).",
                "canonical_charge_type_code": canonical_type.code
            })

    # Deduce final status
    has_warnings = any(f["severity"] in ("Warning", "Review") for f in findings)
    status = "WARNINGS" if has_warnings else "PASSED"

    return {
        "status": status,
        "template_id": template.id,
        "findings": findings
    }
