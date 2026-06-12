import logging
import json
import hashlib
from django.db import IntegrityError, transaction
from quotes.spot_models import SpotTemplateValidationSnapshot
from quotes.services.spot_template_validation import (
    validate_envelope_charges,
    resolve_expected_charge_template,
)

logger = logging.getLogger(__name__)

def capture_validation_snapshot(envelope, trigger_type: str):
    """
    Evaluates current SPOT template validation rules for the given envelope and
    records a snapshot. This is a best-effort function and will not raise exceptions.
    """
    try:
        # 1. Run validation
        res = validate_envelope_charges(envelope)
        status = res.get("status", "passed")
        findings = res.get("findings", [])
        
        # Resolve the active template
        context = envelope.shipment_context_json or {}
        template = resolve_expected_charge_template(context)
        
        # 2. Compute template hash
        template_id = None
        template_hash = ""
        if template:
            template_id = template.id
            lines_data = []
            for line in template.lines.filter(is_active=True).order_by('canonical_charge_type__code'):
                lines_data.append({
                    'canonical_charge_type_code': line.canonical_charge_type.code,
                    'requirement_level': line.requirement_level,
                    'expected_basis': line.expected_basis,
                    'is_active': line.is_active,
                })
            template_dict = {
                'id': template.id,
                'mode': template.mode,
                'transport_mode': template.transport_mode,
                'service_scope': template.service_scope,
                'origin_country': template.origin_country or "",
                'origin_code': template.origin_code or "",
                'destination_country': template.destination_country or "",
                'destination_code': template.destination_code or "",
                'lines': lines_data,
            }
            template_json = json.dumps(template_dict, sort_keys=True)
            template_hash = hashlib.sha256(template_json.encode('utf-8')).hexdigest()

        # 3. Compute findings hash (exclude transient review fields)
        cleaned_findings = []
        for f in findings:
            clean_f = {
                'code': f.get('code'),
                'severity': f.get('severity'),
                'message': f.get('message'),
                'canonical_type': f.get('canonical_type'),
                'template_line_id': f.get('template_line_id'),
                'charge_line_id': str(f.get('charge_line_id')) if f.get('charge_line_id') else None,
                'metadata': f.get('metadata'),
            }
            cleaned_findings.append(clean_f)
            
        def sort_key(x):
            return (
                x.get('code') or '',
                x.get('canonical_type') or '',
                x.get('template_line_id') or 0,
                x.get('charge_line_id') or '',
                x.get('message') or ''
            )
        cleaned_findings.sort(key=sort_key)
        findings_json_str = json.dumps(cleaned_findings, sort_keys=True)
        findings_hash = hashlib.sha256(findings_json_str.encode('utf-8')).hexdigest()

        # 4. Extract summary fields
        finding_count = len(findings)
        finding_codes = sorted(list({f.get('code') for f in findings if f.get('code')}))
        canonical_types = sorted(list({f.get('canonical_type') for f in findings if f.get('canonical_type')}))

        # 5. Save snapshot (best effort / get_or_create)
        try:
            with transaction.atomic():
                snapshot, created = SpotTemplateValidationSnapshot.objects.get_or_create(
                    envelope=envelope,
                    validation_status=status,
                    template_hash=template_hash,
                    findings_hash=findings_hash,
                    defaults={
                        'trigger': trigger_type,
                        'template_id': template_id,
                        'findings_json': findings,
                        'finding_count': finding_count,
                        'finding_codes': finding_codes,
                        'canonical_types': canonical_types,
                    }
                )
                if created:
                    logger.info(
                        "Created SPOT template validation snapshot (trigger: %s) for SPE-%s",
                        trigger_type,
                        str(envelope.id)[:8]
                    )
                else:
                    logger.debug(
                        "Skipped duplicate validation snapshot (trigger: %s) for SPE-%s",
                        trigger_type,
                        str(envelope.id)[:8]
                    )
                return snapshot
        except IntegrityError:
            # Gracefully handle concurrent get_or_create race conditions
            logger.warning(
                "IntegrityError during validation snapshot creation (trigger: %s) for SPE-%s.",
                trigger_type,
                str(envelope.id)[:8],
                exc_info=True
            )
            return SpotTemplateValidationSnapshot.objects.filter(
                envelope=envelope,
                validation_status=status,
                template_hash=template_hash,
                findings_hash=findings_hash,
            ).first()

    except Exception as e:
        logger.exception("Failed to capture SPOT template validation snapshot")
        return None
