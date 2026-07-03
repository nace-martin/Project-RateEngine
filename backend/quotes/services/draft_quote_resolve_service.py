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
            if decision_type in ["accept_suggestion", "ignore", "edit_charge", "map_to_product_code"]:
                try:
                    target_uuid = uuid.UUID(target_id)
                    charge_line = envelope.charge_lines.filter(id=target_uuid).first()
                except (ValueError, TypeError):
                    charge_line = None
                
                if not charge_line:
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

            # 2. Check if this decision was already processed/applied for this envelope
            # (Provides protection against duplicate application in retry flows)
            already_applied = DraftQuoteDecisionDB.objects.filter(
                envelope=envelope,
                target_id=target_id,
                decision_type=decision_type,
                status="accepted"
            ).exists()

            if already_applied:
                # Retrieve the existing result status
                applied.append(
                    DecisionResultSchema(
                        decision_id=dec_item.decision_id,
                        target_id=target_id,
                        type=decision_type,
                        status="applied",
                        message="Decision was already applied previously."
                    )
                )
                continue

            # 3. Apply changes to DB for low-risk types
            status_val = "accepted"
            message_val = "Decision persisted and applied successfully."
            error_code_val = None
            response_status = "applied"

            if decision_type == "accept_suggestion" and charge_line:
                charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
                charge_line.manual_resolution_by = user
                charge_line.manual_resolution_at = timezone.now()
                charge_line.save()
            elif decision_type == "ignore" and charge_line:
                charge_line.exclude_from_totals = True
                charge_line.save()
            elif decision_type in ["edit_charge", "map_to_product_code", "request_product_code", "classify_unclassified"]:
                # Persisted but not applied yet
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
