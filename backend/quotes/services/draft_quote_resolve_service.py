from typing import List, Tuple
from django.db import transaction
from django.utils import timezone
from quotes.contracts.draft_quote_contract import DraftQuoteResolveSchema, DecisionItemSchema, DecisionResultSchema
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB, DraftQuoteDecisionDB
import uuid

def apply_draft_quote_decisions(
    envelope: SpotPricingEnvelopeDB,
    payload: DraftQuoteResolveSchema,
    user
) -> Tuple[List[DecisionResultSchema], List[DecisionResultSchema]]:
    """
    Persists and applies operator decisions to the draft quote.
    Only applies low-risk decisions:
      - accept_suggestion
      - ignore
    Other types (edit_charge, map_to_product_code, request_product_code, classify_unclassified)
    are persisted but their DB side-effects are skipped.
    
    Returns:
      (applied_decisions, rejected_decisions)
    """
    applied: List[DecisionResultSchema] = []
    rejected: List[DecisionResultSchema] = []

    with transaction.atomic():
        for dec_item in payload.decisions:
            decision_type = dec_item.type
            target_id = dec_item.target_id
            
            # 1. Attempt to find target SPEChargeLineDB record if applicable
            charge_line = None
            try:
                target_uuid = uuid.UUID(target_id)
                charge_line = envelope.charge_lines.filter(id=target_uuid).first()
            except (ValueError, TypeError):
                charge_line = None
                
            if not charge_line and decision_type in ["accept_suggestion", "ignore", "edit_charge", "map_to_product_code"]:
                # Unknown target_id returns rejected/skipped result
                err_result = DecisionResultSchema(
                    decision_id=dec_item.decision_id,
                    target_id=target_id,
                    type=decision_type,
                    status="rejected",
                    message="Target charge line ID not found in this envelope.",
                    error_code="TARGET_NOT_FOUND"
                )
                rejected.append(err_result)
                
                # Persist the rejected decision for audit trail
                DraftQuoteDecisionDB.objects.create(
                    envelope=envelope,
                    idempotency_key=payload.idempotency_key,
                    decision_id=dec_item.decision_id,
                    decision_type=decision_type,
                    target_id=target_id,
                    details_json=dec_item.details,
                    client_audit_metadata_json=dec_item.audit_metadata.model_dump(),
                    server_user=user,
                    status="rejected",
                    error_code="TARGET_NOT_FOUND",
                    message="Target charge line ID not found in this envelope."
                )
                continue

            # 2. Apply changes to DB for low-risk types if not already mutated
            status_val = "accepted"
            message_val = "Decision persisted and applied successfully."
            error_code_val = None
            response_status = "applied"

            if decision_type == "accept_suggestion" and charge_line:
                if charge_line.manual_resolution_status == SPEChargeLineDB.ManualResolutionStatus.RESOLVED:
                    message_val = "Decision logged. Target was already resolved in a prior transaction."
                else:
                    charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
                    charge_line.manual_resolution_by = user
                    charge_line.manual_resolution_at = timezone.now()
                    charge_line.save()
            elif decision_type == "ignore" and charge_line:
                if charge_line.exclude_from_totals:
                    message_val = "Decision logged. Target was already ignored in a prior transaction."
                else:
                    charge_line.exclude_from_totals = True
                    charge_line.save()
            elif decision_type == "request_product_code":
                from pricing_v4.models import ProductCodeCreationRequest
                
                # Extract details
                proposed_code = dec_item.details.get("proposed_code", "")
                description = dec_item.details.get("description", "")
                category = dec_item.details.get("category", "")
                reason = dec_item.details.get("reason", "")
                
                source_label = description
                if charge_line:
                    source_label = charge_line.source_label or charge_line.description
                
                # Create pending ProductCodeCreationRequest
                pc_request = ProductCodeCreationRequest.objects.create(
                    source_label=source_label,
                    suggested_name=proposed_code,
                    suggested_bucket=category,
                    suggested_basis="FLAT",
                    suggested_reason=reason,
                    source_envelope=envelope,
                    source_charge_line=charge_line,
                    source_quote=envelope.quote if hasattr(envelope, 'quote') else None,
                    source_context_json=dec_item.details,
                    created_by=user,
                    status=ProductCodeCreationRequest.STATUS_PENDING
                )
                
                # Store the request ID in details for later lookup
                dec_item.details["product_code_request_id"] = pc_request.id
                
                status_val = "skipped"
                response_status = "skipped"
                message_val = "ProductCode request created and pending admin review."
            elif decision_type in ["edit_charge", "map_to_product_code", "classify_unclassified"]:
                # High-risk skipped decisions must remain status='skipped'
                status_val = "skipped"
                response_status = "skipped"
                message_val = "Decision persisted but database side-effects are pending implementation."
            
            # 4. Create decision audit record
            DraftQuoteDecisionDB.objects.create(
                envelope=envelope,
                idempotency_key=payload.idempotency_key,
                decision_id=dec_item.decision_id,
                decision_type=decision_type,
                target_id=target_id,
                details_json=dec_item.details,
                client_audit_metadata_json=dec_item.audit_metadata.model_dump(),
                server_user=user,
                status=status_val,
                error_code=error_code_val,
                message=message_val
            )
            
            applied.append(
                DecisionResultSchema(
                    decision_id=dec_item.decision_id,
                    target_id=target_id,
                    type=decision_type,
                    status=response_status,
                    message=message_val
                )
            )

    return applied, rejected
