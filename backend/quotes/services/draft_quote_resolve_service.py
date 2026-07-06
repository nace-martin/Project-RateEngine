import uuid
import json
from typing import List, Tuple

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from pricing_v4.models import ProductCode, ProductCodeCreationRequest
from quotes.contracts.draft_quote_contract import (
    DecisionItemSchema,
    DecisionResultSchema,
    DraftQuoteResolveSchema,
)
from quotes.spot_models import (
    DraftQuoteDecisionDB,
    SPEChargeLineDB,
    SPESourceBatchDB,
    SpotPricingEnvelopeDB,
)


APPLIED_DB_STATUSES = {"accepted": "applied", "skipped": "skipped", "rejected": "rejected"}
EDITABLE_CHARGE_FIELDS = {
    "display_label": "description",
    "description": "description",
    "amount": "amount",
    "rate": "rate",
    "currency": "currency",
    "unit": "unit",
    "calculation_basis": "calculation_basis",
    "minimum_charge": "min_charge",
    "include_in_totals": "include_in_totals",
    "conditions": "note",
    "notes": "note",
}


def _result(decision: DecisionItemSchema, status: str, message: str, error_code: str | None = None):
    return DecisionResultSchema(
        decision_id=decision.decision_id,
        target_id=decision.target_id,
        type=decision.type,
        status=status,
        message=message,
        error_code=error_code,
    )


def _existing_result(decision: DraftQuoteDecisionDB):
    return DecisionResultSchema(
        decision_id=decision.decision_id,
        target_id=decision.target_id,
        type=decision.decision_type,
        status=APPLIED_DB_STATUSES.get(decision.status, "applied"),
        message=decision.message or "",
        error_code=decision.error_code,
    )


def _persist(envelope, payload, decision, user, status, message, error_code=None):
    details = json.loads(json.dumps(decision.details, cls=DjangoJSONEncoder))
    return DraftQuoteDecisionDB.objects.create(
        envelope=envelope,
        idempotency_key=payload.idempotency_key,
        decision_id=decision.decision_id,
        decision_type=decision.type,
        target_id=decision.target_id,
        details_json=details,
        client_audit_metadata_json=decision.audit_metadata.model_dump(),
        server_user=user,
        status=status,
        error_code=error_code,
        message=message,
    )


def _target_charge(envelope, target_id):
    try:
        return envelope.charge_lines.select_for_update().get(id=uuid.UUID(str(target_id)))
    except (ValueError, TypeError, SPEChargeLineDB.DoesNotExist):
        return None


def _product_code(value):
    query = ProductCode.objects
    if isinstance(value, int) or str(value).isdigit():
        return query.filter(id=int(value)).first()
    return query.filter(code=str(value)).first()


def _stamp_manual_resolution(charge_line, product_code, user, decision, payload):
    charge_line.manual_resolved_product_code = product_code
    charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
    charge_line.manual_resolution_by = user
    charge_line.manual_resolution_at = timezone.now()
    rule_meta = dict(charge_line.rule_meta or {})
    rule_meta["draft_quote_resolution"] = {
        "decision_id": decision.decision_id,
        "idempotency_key": str(payload.idempotency_key),
        "decision_type": decision.type,
        "operator_id": user.id,
        "applied_at": charge_line.manual_resolution_at.isoformat(),
    }
    charge_line.rule_meta = rule_meta


def _apply_product_code(charge_line, product_code, user, decision, payload):
    _stamp_manual_resolution(charge_line, product_code, user, decision, payload)
    charge_line.save(
        update_fields=[
            "manual_resolved_product_code",
            "manual_resolution_status",
            "manual_resolution_by",
            "manual_resolution_at",
            "rule_meta",
        ]
    )


def _apply_edit_charge(charge_line, decision, payload, user):
    updates = dict(decision.details.get("updated_values") or {})
    before = {}
    after = {}

    for public_field in updates:
        if public_field not in EDITABLE_CHARGE_FIELDS:
            return "rejected", f"Field '{public_field}' is not editable.", "INVALID_FIELD"

    for public_field, value in updates.items():
        model_field = EDITABLE_CHARGE_FIELDS[public_field]
        if public_field == "include_in_totals":
            before[public_field] = not charge_line.exclude_from_totals
            charge_line.exclude_from_totals = not bool(value)
            after[public_field] = bool(value)
        elif public_field == "conditions":
            before[public_field] = [charge_line.note] if charge_line.note else []
            charge_line.note = "; ".join(str(v) for v in (value or []))
            after[public_field] = value or []
        else:
            before[public_field] = getattr(charge_line, model_field)
            setattr(charge_line, model_field, value)
            after[public_field] = value

    rule_meta = dict(charge_line.rule_meta or {})
    rule_meta["draft_quote_resolution"] = {
        "decision_id": decision.decision_id,
        "idempotency_key": str(payload.idempotency_key),
        "decision_type": decision.type,
        "operator_id": user.id,
        "applied_at": timezone.now().isoformat(),
    }
    charge_line.rule_meta = rule_meta
    decision.details["before"] = before
    decision.details["after"] = after
    charge_line.save()
    return "accepted", "Charge edited successfully.", None


def _unclassified_item(envelope, target_id):
    for batch in envelope.source_batches.select_for_update():
        summary = batch.analysis_summary_json if isinstance(batch.analysis_summary_json, dict) else {}
        for item in summary.get("unclassified_items") or []:
            if str(item.get("id")) == str(target_id):
                return batch, item
    return None, None


def _ignore_unclassified(batch: SPESourceBatchDB, item: dict, reason: str):
    summary = dict(batch.analysis_summary_json or {})
    unclassified = [i for i in summary.get("unclassified_items") or [] if str(i.get("id")) != str(item.get("id"))]
    ignored = list(summary.get("ignored_items") or [])
    ignored.append(
        {
            "id": item.get("id"),
            "raw_text": item.get("raw_text") or item.get("text") or "",
            "ignored_reason": reason,
            "evidence": item.get("evidence"),
        }
    )
    summary["unclassified_items"] = unclassified
    summary["ignored_items"] = ignored
    batch.analysis_summary_json = summary
    batch.save(update_fields=["analysis_summary_json", "updated_at"])


def _create_classified_charge(envelope, batch, item, product_code, decision, payload, user):
    details = decision.details
    now = timezone.now()
    charge_line = SPEChargeLineDB(
        envelope=envelope,
        source_batch=batch,
        code=product_code.code,
        description=details["display_label"],
        amount=details["amount"],
        currency=details["currency"],
        unit=details.get("unit") or SPEChargeLineDB.Unit.FLAT,
        bucket=details["bucket"],
        rate=details.get("rate"),
        min_charge=details.get("minimum_charge"),
        source_label=item.get("raw_text") or item.get("text") or details["display_label"],
        source_excerpt=item.get("raw_text") or item.get("text") or "",
        source_reference=batch.file_name or batch.label or "draft quote unclassified item",
        entered_by=user,
        entered_at=now,
    )
    _stamp_manual_resolution(charge_line, product_code, user, decision, payload)
    charge_line.save()
    _ignore_unclassified(batch, item, details.get("reason") or "Classified as charge")


def _apply_classify_unclassified(envelope, decision, payload, user):
    batch, item = _unclassified_item(envelope, decision.target_id)
    if not item:
        return "rejected", "Target unclassified item was not found in this envelope.", "TARGET_NOT_FOUND"

    classification = str(decision.details.get("classification") or "charge").lower()
    if classification in {"ignored", "ignore", "non_commercial", "non-commercial"}:
        _ignore_unclassified(batch, item, decision.details.get("reason") or "Classified as non-commercial")
        return "accepted", "Unclassified item classified as ignored.", None

    if classification != "charge":
        return "rejected", "Unsupported unclassified classification.", "UNSUPPORTED_CLASSIFICATION"

    product_code = _product_code(decision.details.get("product_code"))
    if not product_code:
        return "skipped", "Classifying this item as a charge requires an existing ProductCode.", "PRODUCT_CODE_REQUIRED"

    _create_classified_charge(envelope, batch, item, product_code, decision, payload, user)
    return "accepted", "Unclassified item classified as charge.", None


def apply_draft_quote_decisions(
    envelope: SpotPricingEnvelopeDB,
    payload: DraftQuoteResolveSchema,
    user,
) -> Tuple[List[DecisionResultSchema], List[DecisionResultSchema]]:
    applied: List[DecisionResultSchema] = []
    rejected: List[DecisionResultSchema] = []

    with transaction.atomic():
        for dec_item in payload.decisions:
            existing = DraftQuoteDecisionDB.objects.filter(
                envelope=envelope,
                idempotency_key=payload.idempotency_key,
                decision_id=dec_item.decision_id,
            ).first()
            if existing:
                result = _existing_result(existing)
                (rejected if result.status == "rejected" else applied).append(result)
                continue

            decision_type = dec_item.type
            charge_line = _target_charge(envelope, dec_item.target_id)

            status_val = "accepted"
            message_val = "Decision persisted and applied successfully."
            error_code_val = None

            if decision_type in {"accept_suggestion", "ignore", "edit_charge", "map_to_product_code", "use_approved_product_code"} and not charge_line:
                status_val = "rejected"
                message_val = "Target charge line ID not found in this envelope."
                error_code_val = "TARGET_NOT_FOUND"
            elif decision_type == "accept_suggestion":
                if charge_line.manual_resolution_status == SPEChargeLineDB.ManualResolutionStatus.RESOLVED:
                    message_val = "Decision logged. Target was already resolved in a prior transaction."
                else:
                    charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
                    charge_line.manual_resolution_by = user
                    charge_line.manual_resolution_at = timezone.now()
                    charge_line.save(update_fields=["manual_resolution_status", "manual_resolution_by", "manual_resolution_at"])
            elif decision_type == "ignore":
                charge_line.exclude_from_totals = True
                charge_line.save(update_fields=["exclude_from_totals"])
            elif decision_type == "map_to_product_code":
                product_code = _product_code(dec_item.details.get("product_code"))
                if not product_code:
                    status_val = "rejected"
                    message_val = "ProductCode was not found."
                    error_code_val = "PRODUCT_CODE_NOT_FOUND"
                else:
                    _apply_product_code(charge_line, product_code, user, dec_item, payload)
                    message_val = "ProductCode mapping applied successfully."
            elif decision_type == "edit_charge":
                status_val, message_val, error_code_val = _apply_edit_charge(charge_line, dec_item, payload, user)
            elif decision_type == "classify_unclassified":
                status_val, message_val, error_code_val = _apply_classify_unclassified(envelope, dec_item, payload, user)
            elif decision_type == "request_product_code":
                pc_request = ProductCodeCreationRequest.objects.create(
                    source_label=(charge_line.source_label or charge_line.description) if charge_line else dec_item.details.get("description", ""),
                    suggested_name=dec_item.details.get("proposed_code", ""),
                    suggested_bucket=dec_item.details.get("category", ""),
                    suggested_basis="FLAT",
                    suggested_reason=dec_item.details.get("reason", ""),
                    source_envelope=envelope,
                    source_charge_line=charge_line,
                    source_quote=envelope.quote if hasattr(envelope, "quote") else None,
                    source_context_json=dec_item.details,
                    created_by=user,
                    status=ProductCodeCreationRequest.STATUS_PENDING,
                )
                dec_item.details["product_code_request_id"] = pc_request.id
                status_val = "skipped"
                message_val = "ProductCode request created and pending admin review."
            elif decision_type == "use_approved_product_code":
                req_id = dec_item.details.get("product_code_request_id")
                pc_request = ProductCodeCreationRequest.objects.filter(id=req_id).first() if req_id else None
                if not pc_request:
                    status_val, error_code_val = "rejected", "REQUEST_NOT_FOUND"
                    message_val = f"ProductCodeCreationRequest with ID {req_id} not found."
                elif str(pc_request.source_envelope_id) != str(envelope.id):
                    status_val, error_code_val = "rejected", "INVALID_REQUEST_SOURCE"
                    message_val = "ProductCodeCreationRequest does not belong to the same envelope."
                elif pc_request.source_charge_line_id and pc_request.source_charge_line_id != charge_line.id:
                    status_val, error_code_val = "rejected", "INVALID_REQUEST_SOURCE"
                    message_val = "ProductCodeCreationRequest does not belong to the same charge line."
                elif pc_request.status != ProductCodeCreationRequest.STATUS_APPROVED:
                    status_val, error_code_val = "rejected", "REQUEST_NOT_APPROVED"
                    message_val = f"ProductCodeCreationRequest status is {pc_request.status}, must be APPROVED."
                elif not pc_request.approved_product_code_id:
                    status_val, error_code_val = "rejected", "MISSING_APPROVED_PRODUCT_CODE"
                    message_val = "ProductCodeCreationRequest does not have an approved product code."
                elif dec_item.details.get("product_code_id") and int(dec_item.details["product_code_id"]) != pc_request.approved_product_code_id:
                    status_val, error_code_val = "rejected", "PRODUCT_CODE_MISMATCH"
                    message_val = "Provided product_code_id does not match approved ProductCode ID."
                else:
                    _apply_product_code(charge_line, pc_request.approved_product_code, user, dec_item, payload)
                    message_val = "Approved ProductCode applied successfully."

            _persist(envelope, payload, dec_item, user, status_val, message_val, error_code_val)
            response_status = APPLIED_DB_STATUSES.get(status_val, "applied")
            result = _result(dec_item, response_status, message_val, error_code_val)
            (rejected if response_status == "rejected" else applied).append(result)

    return applied, rejected
