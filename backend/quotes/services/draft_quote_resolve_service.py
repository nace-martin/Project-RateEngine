import uuid
import json
from decimal import Decimal, InvalidOperation
from typing import List, Tuple

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from pricing_v4.models import ProductCode, ProductCodeCreationRequest
from quotes.intake_safety import mark_source_analysis_review, normalize_source_analysis_summary, unresolved_source_findings
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
    "calculation_basis": "unit_type",
    "minimum_charge": "min_charge",
    "include_in_totals": "include_in_totals",
    "conditions": "note",
    "notes": "note",
}
NUMERIC_CHARGE_FIELDS = {"amount", "rate", "minimum_charge"}
PRODUCT_CODE_DOMAINS = {
    ProductCode.DOMAIN_IMPORT,
    ProductCode.DOMAIN_EXPORT,
    ProductCode.DOMAIN_DOMESTIC,
}


def _normalize_product_code_domain(value):
    domain = str(value or "").strip().upper()
    return domain if domain in PRODUCT_CODE_DOMAINS else None


def _expected_product_code_domain(envelope):
    shipment_context = envelope.shipment_context_json if isinstance(envelope.shipment_context_json, dict) else {}
    origin_country = shipment_context.get("origin_country", "")
    destination_country = shipment_context.get("destination_country", "")

    if not origin_country or not destination_country:
        return None

    try:
        from quotes.spot_services import classify_png_shipment
        return _normalize_product_code_domain(classify_png_shipment(origin_country, destination_country))
    except Exception:
        return None


def _valid_choice_values(choices):
    return {choice for choice, _ in choices}


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

    for public_field, value in updates.items():
        if public_field not in EDITABLE_CHARGE_FIELDS:
            return "rejected", f"Field '{public_field}' is not editable.", "INVALID_FIELD"
        if public_field == "currency":
            currency = str(value or "").strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                return "rejected", "Currency must be a 3-letter ISO code.", "INVALID_CURRENCY"
            updates[public_field] = currency
        elif public_field == "unit" and value not in _valid_choice_values(SPEChargeLineDB.Unit.choices):
            return "rejected", "Unit is not supported for SPOT charge lines.", "INVALID_UNIT"
        elif public_field == "calculation_basis" and value not in _valid_choice_values(SPEChargeLineDB.UnitType.choices):
            return "rejected", "Calculation basis is not supported for SPOT charge lines.", "INVALID_CALCULATION_BASIS"
        elif public_field in NUMERIC_CHARGE_FIELDS:
            try:
                numeric_value = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return "rejected", f"{public_field} must be numeric.", "INVALID_NUMERIC_VALUE"
            if numeric_value < 0:
                return "rejected", f"{public_field} cannot be negative.", "NEGATIVE_NUMERIC_VALUE"
            updates[public_field] = numeric_value

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


def _remove_unclassified(batch: SPESourceBatchDB, item: dict):
    summary = dict(batch.analysis_summary_json or {})
    summary["unclassified_items"] = [
        i for i in summary.get("unclassified_items") or [] if str(i.get("id")) != str(item.get("id"))
    ]
    batch.analysis_summary_json = summary
    batch.save(update_fields=["analysis_summary_json", "updated_at"])


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


def _persist_unclassified_note(envelope, batch: SPESourceBatchDB, item: dict, reason: str | None = None):
    conditions = dict(envelope.conditions_json or {}) if isinstance(envelope.conditions_json, dict) else {}
    terms = list(conditions.get("commercial_terms") or [])
    terms.append(
        {
            "type": "note",
            "text": item.get("raw_text") or item.get("text") or "",
            "normalized_value": None,
            "status": "suggested",
            "evidence": item.get("evidence"),
            "review_reason": reason or "Operator classified unclassified item as commercial note.",
        }
    )
    conditions["commercial_terms"] = terms
    envelope.conditions_json = conditions
    envelope.save(update_fields=["conditions_json"])
    _remove_unclassified(batch, item)


def _validate_charge_details(details):
    required = ["display_label", "bucket", "currency", "amount", "unit", "product_code"]
    missing = [field for field in required if details.get(field) in {None, ""}]
    if missing:
        return None, f"Classifying this item as a charge requires: {', '.join(missing)}.", "MISSING_CHARGE_FIELD"
    if details["bucket"] not in _valid_choice_values(SPEChargeLineDB.Bucket.choices):
        return None, "Bucket is not supported for SPOT charge lines.", "INVALID_BUCKET"
    if details["unit"] not in _valid_choice_values(SPEChargeLineDB.Unit.choices):
        return None, "Unit is not supported for SPOT charge lines.", "INVALID_UNIT"
    currency = str(details.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        return None, "Currency must be a 3-letter ISO code.", "INVALID_CURRENCY"
    try:
        amount = Decimal(str(details.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        return None, "amount must be numeric.", "INVALID_NUMERIC_VALUE"
    if amount < 0:
        return None, "amount cannot be negative.", "NEGATIVE_NUMERIC_VALUE"
    normalized = dict(details)
    normalized["currency"] = currency
    normalized["amount"] = amount
    return normalized, "", None


def _validate_product_code_domain(envelope, product_code):
    expected_domain = _expected_product_code_domain(envelope)
    if not expected_domain:
        return "rejected", "Shipment direction could not be determined from trusted route evidence. ProductCode mapping was not applied.", "PRODUCT_CODE_DIRECTION_UNAVAILABLE"
    if product_code.domain != expected_domain:
        return "rejected", f"ProductCode domain {product_code.domain} does not match shipment direction {expected_domain}.", "PRODUCT_CODE_DOMAIN_MISMATCH"
    return None, None, None


def _build_unclassified_charge(envelope, batch, item, details, user, product_code=None):
    now = timezone.now()
    source_text = item.get("raw_text") or item.get("text") or ""
    return SPEChargeLineDB(
        envelope=envelope,
        source_batch=batch,
        code=product_code.code if product_code else "UNCLASSIFIED-PROVISIONAL",
        description=details["display_label"],
        amount=details["amount"],
        currency=details["currency"],
        unit=details["unit"],
        bucket=details["bucket"],
        rate=details.get("rate"),
        min_charge=details.get("minimum_charge"),
        normalization_status=SPEChargeLineDB.NormalizationStatus.UNMAPPED if not product_code else SPEChargeLineDB.NormalizationStatus.MATCHED,
        source_label=source_text or details["display_label"],
        source_excerpt=source_text,
        source_reference=batch.file_name or batch.label or "draft quote unclassified item",
        rule_meta={"unclassified_item_evidence": item.get("evidence"), "unclassified_item_id": item.get("id")},
        entered_by=user,
        entered_at=now,
    )


def _create_classified_charge(envelope, batch, item, product_code, decision, payload, user):
    details, message, error_code = _validate_charge_details(decision.details)
    if error_code:
        return "rejected", message, error_code
    status, message, error_code = _validate_product_code_domain(envelope, product_code)
    if error_code:
        return status, message, error_code
    charge_line = _build_unclassified_charge(envelope, batch, item, details, user, product_code=product_code)
    _stamp_manual_resolution(charge_line, product_code, user, decision, payload)
    charge_line.save()
    _remove_unclassified(batch, item)
    return "accepted", "Unclassified item classified as charge.", None


def _create_product_code_request_for_unclassified(envelope, decision, user):
    batch, item = _unclassified_item(envelope, decision.target_id)
    if not item:
        return "rejected", "Target unclassified item was not found in this envelope.", "TARGET_NOT_FOUND", None

    details, message, error_code = _validate_charge_details({**decision.details, "product_code": "PENDING"})
    if error_code and error_code != "PRODUCT_CODE_REQUIRED":
        return "rejected", message, error_code, None

    expected_domain = _expected_product_code_domain(envelope)
    if not expected_domain:
        return "rejected", "Shipment direction could not be determined from trusted route evidence. ProductCode request was not created.", "PRODUCT_CODE_DIRECTION_UNAVAILABLE", None

    charge_line = _build_unclassified_charge(envelope, batch, item, details, user)
    charge_line.save()
    _remove_unclassified(batch, item)
    pc_request = ProductCodeCreationRequest.objects.create(
        source_label=item.get("raw_text") or item.get("text") or details["display_label"],
        suggested_name=decision.details.get("proposed_code") or details["display_label"],
        suggested_bucket=details["bucket"],
        suggested_basis=details["unit"],
        suggested_reason=decision.details.get("reason") or "Operator requested ProductCode for unclassified item.",
        source_envelope=envelope,
        source_charge_line=charge_line,
        source_quote=envelope.quote if hasattr(envelope, "quote") else None,
        source_context_json={**decision.details, "domain": expected_domain, "evidence": item.get("evidence")},
        created_by=user,
        status=ProductCodeCreationRequest.STATUS_PENDING,
    )
    decision.target_id = str(charge_line.id)
    decision.details["product_code_request_id"] = pc_request.id
    return "skipped", "ProductCode request created and pending admin review.", None, charge_line


SOURCE_FINDING_RESOLUTION_ACTIONS = {
    "link_existing_charge",
    "add_missing_charge",
    "confirm_corrected_mapping",
    "not_commercially_applicable",
    "approve_source",
}


def _resolve_source_finding(envelope, decision, user):
    details = decision.details
    action = str(details.get("action") or "").strip()
    if action not in SOURCE_FINDING_RESOLUTION_ACTIONS:
        return "rejected", "Source finding resolution action is not supported.", "SOURCE_FINDING_ACTION_INVALID"
    note = str(details.get("review_note") or "").strip()
    if not note:
        return "rejected", "Source finding resolution requires a non-empty review note.", "REVIEW_NOTE_REQUIRED"
    batch = envelope.source_batches.select_for_update().filter(id=details.get("source_batch_id")).first()
    if not batch:
        return "rejected", "Source batch was not found for this envelope.", "SOURCE_BATCH_NOT_FOUND"
    finding_id = str(details.get("source_finding_id") or "").strip()
    current = normalize_source_analysis_summary(batch.analysis_summary_json)
    if not any(item.get("id") == finding_id for item in current.get("source_findings", [])):
        return "rejected", "Source finding was not found for this source batch.", "SOURCE_FINDING_NOT_FOUND"
    if not any(item.get("id") == finding_id for item in unresolved_source_findings(current)):
        return "skipped", "Source finding was already resolved.", None

    charge_line_id = details.get("charge_line_id")
    if charge_line_id and not envelope.charge_lines.filter(id=charge_line_id).exists():
        return "rejected", "Linked charge line was not found for this envelope.", "CHARGE_LINE_NOT_FOUND"

    batch.analysis_summary_json = mark_source_analysis_review(
        batch.analysis_summary_json,
        reviewed_safe_to_quote=True,
        reviewed_by_user_id=str(user.id),
        reviewed_at=timezone.now().isoformat(),
        review_note=note,
        source_finding_id=finding_id,
        resolution_action=action,
        charge_line_id=str(charge_line_id) if charge_line_id else None,
    )
    batch.save(update_fields=["analysis_summary_json", "updated_at"])
    return "accepted", "Source finding resolved.", None


def _apply_classify_unclassified(envelope, decision, payload, user):
    batch, item = _unclassified_item(envelope, decision.target_id)
    if not item:
        return "rejected", "Target unclassified item was not found in this envelope.", "TARGET_NOT_FOUND"

    classification = str(decision.details.get("classification") or "charge").lower()
    if classification in {"ignored", "ignore", "non_commercial", "non-commercial"}:
        reason = str(decision.details.get("reason") or "").strip()
        if not reason:
            return "rejected", "Ignoring an unclassified item requires a reason.", "REASON_REQUIRED"
        _ignore_unclassified(batch, item, reason)
        return "accepted", "Unclassified item classified as ignored.", None

    if classification == "note":
        _persist_unclassified_note(envelope, batch, item, decision.details.get("reason"))
        return "accepted", "Unclassified item classified as note.", None

    if classification != "charge":
        return "rejected", "Unsupported unclassified classification.", "UNSUPPORTED_CLASSIFICATION"

    product_code = _product_code(decision.details.get("product_code"))
    if not product_code:
        return "rejected", "Classifying this item as a charge requires an existing ProductCode.", "PRODUCT_CODE_REQUIRED"

    return _create_classified_charge(envelope, batch, item, product_code, decision, payload, user)


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
                    expected_domain = _expected_product_code_domain(envelope)
                    if not expected_domain:
                        status_val = "rejected"
                        message_val = "Shipment direction could not be determined from trusted route evidence. ProductCode mapping was not applied."
                        error_code_val = "PRODUCT_CODE_DIRECTION_UNAVAILABLE"
                    elif product_code.domain != expected_domain:
                        status_val = "rejected"
                        message_val = f"ProductCode domain {product_code.domain} does not match shipment direction {expected_domain}."
                        error_code_val = "PRODUCT_CODE_DOMAIN_MISMATCH"
                    else:
                        _apply_product_code(charge_line, product_code, user, dec_item, payload)
                        message_val = "ProductCode mapping applied successfully."
            elif decision_type == "edit_charge":
                status_val, message_val, error_code_val = _apply_edit_charge(charge_line, dec_item, payload, user)
            elif decision_type == "classify_unclassified":
                status_val, message_val, error_code_val = _apply_classify_unclassified(envelope, dec_item, payload, user)
            elif decision_type == "resolve_source_finding":
                status_val, message_val, error_code_val = _resolve_source_finding(envelope, dec_item, user)
            elif decision_type == "request_product_code":
                if not charge_line:
                    status_val, message_val, error_code_val, charge_line = _create_product_code_request_for_unclassified(envelope, dec_item, user)
                else:
                    expected_domain = _expected_product_code_domain(envelope)
                    if not expected_domain:
                        status_val = "rejected"
                        message_val = "Shipment direction could not be determined from trusted route evidence. ProductCode request was not created."
                        error_code_val = "PRODUCT_CODE_DIRECTION_UNAVAILABLE"
                    else:
                        source_label = charge_line.source_label or charge_line.description or dec_item.details.get("description", "")
                        suggested_bucket = charge_line.bucket or dec_item.details.get("bucket") or dec_item.details.get("category")
                        suggested_basis = charge_line.unit or dec_item.details.get("unit") or "FLAT"
                        pc_request = ProductCodeCreationRequest.objects.create(
                            source_label=source_label,
                            suggested_name=dec_item.details.get("proposed_code", ""),
                            suggested_bucket=suggested_bucket,
                            suggested_basis=suggested_basis,
                            suggested_reason=dec_item.details.get("reason", ""),
                            source_envelope=envelope,
                            source_charge_line=charge_line,
                            source_quote=envelope.quote if hasattr(envelope, "quote") else None,
                            source_context_json={
                                **dec_item.details,
                                "domain": expected_domain,
                                "source_label": source_label,
                                "source_charge_line_id": str(charge_line.id),
                                "charge_bucket": charge_line.bucket,
                                "charge_unit": charge_line.unit,
                                "charge_currency": charge_line.currency,
                                "charge_amount": str(charge_line.amount) if charge_line.amount is not None else None,
                            },
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
