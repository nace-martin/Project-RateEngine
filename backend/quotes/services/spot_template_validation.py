import logging
from typing import Dict, Any, Optional
from core.business_rules import classify_png_shipment
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    ExpectedChargeTemplate,
    ExpectedTemplateLine,
    SpotTemplateValidationReview
)

logger = logging.getLogger(__name__)

# Validation Finding Codes
FINDING_TEMPLATE_NOT_FOUND = "template_not_found"
FINDING_EXPECTED_CHARGE_MISSING = "expected_charge_missing"
FINDING_UNEXPECTED_CHARGE_PRESENT = "unexpected_charge_present"
FINDING_CONDITIONAL_CHARGE_PRESENT = "conditional_charge_present"
FINDING_EXPECTED_BASIS_MISMATCH = "expected_basis_mismatch"
FINDING_DUPLICATE_CHARGE_FAMILY = "duplicate_charge_family"

VALID_FINDING_CODES = {
    FINDING_TEMPLATE_NOT_FOUND,
    FINDING_EXPECTED_CHARGE_MISSING,
    FINDING_UNEXPECTED_CHARGE_PRESENT,
    FINDING_CONDITIONAL_CHARGE_PRESENT,
    FINDING_EXPECTED_BASIS_MISMATCH,
    FINDING_DUPLICATE_CHARGE_FAMILY,
}

# Validation Severities
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_REVIEW = "review"

VALID_SEVERITIES = {
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_REVIEW,
}

# Validation Statuses
STATUS_PASSED = "passed"
STATUS_WARNINGS = "warnings"
STATUS_REVIEW = "review"

VALID_STATUSES = {
    STATUS_PASSED,
    STATUS_WARNINGS,
    STATUS_REVIEW,
}


def compute_finding_fingerprint(
    finding_code: str,
    canonical_type: Optional[str] = None,
    template_line_id: Optional[int] = None,
    charge_line_id: Optional[str] = None
) -> str:
    """
    Computes a deterministic fingerprint string for a finding identity.
    Format: finding_code:canonical_type:template_line_id:charge_line_id
    """
    c_type = canonical_type or ""
    t_line_id = str(template_line_id) if template_line_id is not None else ""
    c_line_id = str(charge_line_id) if charge_line_id is not None else ""
    return f"{finding_code}:{c_type}:{t_line_id}:{c_line_id}"


def _build_finding(
    code: str,
    severity: str,
    message: str,
    canonical_type: Optional[str] = None,
    template_line_id: Optional[int] = None,
    charge_line_id: Optional[str] = None,
    metadata: Optional[dict] = None
) -> dict:
    """Helper to build a standardized finding dictionary with the full key set."""
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "canonical_type": canonical_type,
        "template_line_id": template_line_id,
        "charge_line_id": charge_line_id,
        "metadata": metadata or {},
        "is_reviewed": False,
        "review": None
    }



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
    
    # Fetch existing reviews for this envelope
    reviews = {
        r.finding_fingerprint: r
        for r in SpotTemplateValidationReview.objects.filter(envelope=envelope).select_related('reviewed_by')
    }

    def annotate_findings(lst):
        for f in lst:
            fingerprint = compute_finding_fingerprint(
                finding_code=f["code"],
                canonical_type=f["canonical_type"],
                template_line_id=f["template_line_id"],
                charge_line_id=f["charge_line_id"]
            )
            review_obj = reviews.get(fingerprint)
            if review_obj:
                f["is_reviewed"] = True
                f["review"] = {
                    "comment": review_obj.comment,
                    "reviewed_by": review_obj.reviewed_by.username if review_obj.reviewed_by else None,
                    "reviewed_at": review_obj.reviewed_at.isoformat()
                }
            else:
                f["is_reviewed"] = False
                f["review"] = None
        return lst

    # 1. Resolve Template
    context = envelope.shipment_context_json or {}
    template = resolve_expected_charge_template(context)
    
    if not template:
        findings.append(
            _build_finding(
                code=FINDING_TEMPLATE_NOT_FOUND,
                severity=SEVERITY_REVIEW,
                message="No applicable expectation template resolved for this shipment context."
            )
        )
        # Deduce status dynamically to support lowercase 'review' status
        severities = {f["severity"] for f in findings}
        status = STATUS_REVIEW if SEVERITY_REVIEW in severities else STATUS_WARNINGS
        return {
            "status": status,
            "template_id": None,
            "findings": annotate_findings(findings)
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
            findings.append(
                _build_finding(
                    code=FINDING_EXPECTED_CHARGE_MISSING,
                    severity=SEVERITY_WARNING,
                    message=f"Expected charge of type '{canonical_type.name}' ({canonical_type.code}) is missing.",
                    canonical_type=canonical_type.code,
                    template_line_id=t_line.id
                )
            )
            
        elif level == ExpectedTemplateLine.RequirementLevel.EXCLUDED and has_actual:
            for act_line in actual_by_canonical[canonical_type]:
                findings.append(
                    _build_finding(
                        code=FINDING_UNEXPECTED_CHARGE_PRESENT,
                        severity=SEVERITY_WARNING,
                        message=f"Excluded charge of type '{canonical_type.name}' ({canonical_type.code}) was included.",
                        canonical_type=canonical_type.code,
                        template_line_id=t_line.id,
                        charge_line_id=str(act_line.id)
                    )
                )
            
        elif level == ExpectedTemplateLine.RequirementLevel.CONDITIONAL and has_actual:
            for act_line in actual_by_canonical[canonical_type]:
                findings.append(
                    _build_finding(
                        code=FINDING_CONDITIONAL_CHARGE_PRESENT,
                        severity=SEVERITY_REVIEW,
                        message=f"Conditional charge of type '{canonical_type.name}' ({canonical_type.code}) is present and requires confirmation.",
                        canonical_type=canonical_type.code,
                        template_line_id=t_line.id,
                        charge_line_id=str(act_line.id)
                    )
                )
            
        # Check calculation basis mismatch if actual is present
        if has_actual and expected_basis != "any":
            for act_line in actual_by_canonical[canonical_type]:
                if act_line.calculation_basis != expected_basis:
                    findings.append(
                        _build_finding(
                            code=FINDING_EXPECTED_BASIS_MISMATCH,
                            severity=SEVERITY_REVIEW,
                            message=(
                                f"Basis mismatch for '{canonical_type.name}': "
                                f"Expected basis '{expected_basis}' but actual was '{act_line.calculation_basis}'."
                            ),
                            canonical_type=canonical_type.code,
                            template_line_id=t_line.id,
                            charge_line_id=str(act_line.id),
                            metadata={
                                "expected_basis": expected_basis,
                                "actual_basis": act_line.calculation_basis
                            }
                        )
                    )

    # 4. Check for duplicates in actual charge lines
    for canonical_type, lines in actual_by_canonical.items():
        if len(lines) > 1:
            for act_line in lines:
                findings.append(
                    _build_finding(
                        code=FINDING_DUPLICATE_CHARGE_FAMILY,
                        severity=SEVERITY_REVIEW,
                        message=f"Multiple lines detected resolving to canonical charge family '{canonical_type.name}' ({canonical_type.code}).",
                        canonical_type=canonical_type.code,
                        charge_line_id=str(act_line.id)
                    )
                )

    # Deduce final status
    severities = {f["severity"] for f in findings}
    if SEVERITY_REVIEW in severities:
        status = STATUS_REVIEW
    elif SEVERITY_WARNING in severities or SEVERITY_INFO in severities:
        status = STATUS_WARNINGS
    else:
        status = STATUS_PASSED

    return {
        "status": status,
        "template_id": template.id,
        "findings": annotate_findings(findings)
    }


