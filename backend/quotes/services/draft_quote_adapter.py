# backend/quotes/services/draft_quote_adapter.py

from decimal import Decimal
from typing import Any, Dict, List, Optional
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB
from quotes.contracts.draft_quote_contract import DraftQuoteSchema

def build_draft_quote_payload(spe_db: SpotPricingEnvelopeDB) -> Dict[str, Any]:
    shipment_ctx = spe_db.shipment_context_json or {}
    
    # 1. Basic Fields
    mode = shipment_ctx.get('mode') or shipment_ctx.get('shipment_type') or 'AIR'
    origin = shipment_ctx.get('origin_code') or shipment_ctx.get('origin') or 'Unknown Origin'
    destination = shipment_ctx.get('destination_code') or shipment_ctx.get('destination') or 'Unknown Destination'
    
    # Resolve supplier name
    supplier_name = shipment_ctx.get('supplier_name')
    if not supplier_name and spe_db.quote and spe_db.quote.carrier:
        supplier_name = spe_db.quote.carrier.name
    if not supplier_name:
        first_batch = spe_db.source_batches.first()
        if first_batch:
            supplier_name = first_batch.label
    supplier_name = supplier_name or "Unknown Carrier"

    # Classify shipment direction (IMPORT vs EXPORT vs DOMESTIC)
    direction = "Import"
    origin_country = shipment_ctx.get('origin_country', '')
    destination_country = shipment_ctx.get('destination_country', '')
    try:
        from quotes.spot_services import classify_png_shipment
        direction = classify_png_shipment(origin_country, destination_country)
    except Exception:
        # Fallback
        if str(origin_country).upper() == "PG" and str(destination_country).upper() != "PG":
            direction = "EXPORT"
        elif str(origin_country).upper() != "PG" and str(destination_country).upper() == "PG":
            direction = "IMPORT"
        elif str(origin_country).upper() == "PG" and str(destination_country).upper() == "PG":
            direction = "DOMESTIC"

    quote_summary = f"Draft Quote Suggestion for {mode} Freight {direction} - {origin} to {destination} via {supplier_name}"

    # 2. Shipment Context
    shipment_context = {
        "origin": shipment_ctx.get('origin_code') or shipment_ctx.get('origin') or '',
        "destination": shipment_ctx.get('destination_code') or shipment_ctx.get('destination') or '',
        "mode": mode,
        "pieces": int(shipment_ctx.get('pieces') or 1),
        "actual_weight_kg": float(shipment_ctx.get('actual_weight_kg') or shipment_ctx.get('weight') or 0.0),
        "volumetric_weight_kg": float(shipment_ctx.get('volumetric_weight_kg') or 0.0),
        "chargeable_weight_kg": float(shipment_ctx.get('chargeable_weight_kg') or shipment_ctx.get('chargeable_weight') or 0.0),
        "commodity": shipment_ctx.get('commodity') or 'GCR'
    }

    # 3. Supplier Context
    supplier_context = {
        "supplier_name": supplier_name,
        "agent_code": shipment_ctx.get('agent_code') or ''
    }

    # 4. Freight
    freight = {
        "carrier": shipment_ctx.get('carrier') or supplier_name,
        "service_type": shipment_ctx.get('service_type') or 'Standard Freight'
    }

    # Primary currency detection
    freight_charges = [c for c in spe_db.charge_lines.all() if c.is_primary_cost]
    if freight_charges:
        primary_currency = freight_charges[0].currency
    else:
        all_currencies = [c.currency for c in spe_db.charge_lines.all() if c.currency]
        if all_currencies:
            primary_currency = max(set(all_currencies), key=all_currencies.count)
        else:
            primary_currency = "USD"

    # Fetch ProductCodeCreationRequests for this envelope to map review status
    from pricing_v4.models import ProductCodeCreationRequest
    from quotes.spot_models import DraftQuoteDecisionDB

    # Map request ID -> request object
    envelope_requests = {
        str(req.id): req for req in ProductCodeCreationRequest.objects.filter(source_envelope=spe_db)
    }

    # Retrieve all request_product_code decisions for target mapping
    decisions_with_req = DraftQuoteDecisionDB.objects.filter(
        envelope=spe_db,
        decision_type="request_product_code"
    )

    pending_targets = {}
    approved_targets = {}
    rejected_targets = {}

    for dec in decisions_with_req:
        req_id = dec.details_json.get("product_code_request_id")
        if req_id and str(req_id) in envelope_requests:
            req_obj = envelope_requests[str(req_id)]
            # Derive status directly from ProductCodeCreationRequest.status
            if req_obj.status == ProductCodeCreationRequest.STATUS_PENDING:
                pending_targets[dec.target_id] = req_obj.suggested_name
            elif req_obj.status == ProductCodeCreationRequest.STATUS_APPROVED:
                approved_code = req_obj.approved_product_code.code if req_obj.approved_product_code else req_obj.suggested_name
                approved_targets[dec.target_id] = approved_code
            elif req_obj.status == ProductCodeCreationRequest.STATUS_REJECTED:
                rejected_targets[dec.target_id] = {
                    "proposed_code": req_obj.suggested_name,
                    "reason": req_obj.rejection_reason or "No reason provided."
                }

    # 5. Suggested Charges
    suggested_charges = []
    for line in spe_db.charge_lines.all():
        # Determine status
        if line.exclude_from_totals:
            status = "ignored"
        elif line.manual_resolution_status == "RESOLVED":
            status = "accepted_by_user"
        elif line.normalization_status in ["AMBIGUOUS", "UNMAPPED"] or not (line.resolved_product_code_id or line.manual_resolved_product_code_id):
            status = "needs_review"
        else:
            status = "suggested"

        product_code_conflict = False
        if line.normalization_status == "AMBIGUOUS":
            product_code_conflict = True
        elif not line.resolved_product_code_id and not line.manual_resolved_product_code_id and not line.exclude_from_totals:
            product_code_conflict = True

        suggested_code = None
        if line.manual_resolved_product_code:
            suggested_code = line.manual_resolved_product_code.code
        elif line.resolved_product_code:
            suggested_code = line.resolved_product_code.code

        bucket_val = (line.bucket or "unclassified").lower()
        if bucket_val not in ["airfreight", "origin_charges", "destination_charges", "unclassified"]:
            bucket_val = "unclassified"

        # Safe quantity multiplier
        quantity = Decimal("1.00")
        if line.rate and line.amount:
            try:
                quantity = Decimal(str(line.amount)) / Decimal(str(line.rate))
            except Exception:
                pass

        # Build charge level warnings & review reasons
        line_warnings = []
        review_reason = None
        if line.normalization_status == "AMBIGUOUS":
            line_warnings.append("Ambiguous product code match: could map to multiple codes.")
            review_reason = "Ambiguous ProductCode mapping due to multiple matching catalog rules."
        elif line.normalization_status == "UNMAPPED":
            line_warnings.append("No approved ProductCode mapping found in RateEngine.")
            review_reason = "Unmapped charge: requires manual product code mapping."
        elif not line.resolved_product_code_id and not line.manual_resolved_product_code_id and not line.exclude_from_totals:
            line_warnings.append("No approved ProductCode mapping found.")
            review_reason = "Requires product code validation."

        if line.currency and line.currency != primary_currency:
            line_warnings.append(f"Mixed currency: This charge is in {line.currency}, which differs from primary {primary_currency}.")
            if status == "needs_review" and not review_reason:
                review_reason = "Currency inheritance warning: verify if currency is correct."

        # Check if there is a ProductCode request for this charge line and map state
        pending_proposed_code = pending_targets.get(str(line.id))
        approved_proposed_code = approved_targets.get(str(line.id))
        rejected_info = rejected_targets.get(str(line.id))

        correction_actions = []
        if pending_proposed_code:
            line_warnings.append(f"Pending ProductCode Creation Request: proposed code '{pending_proposed_code}'.")
            review_reason = f"ProductCode creation request '{pending_proposed_code}' is pending admin approval."
            correction_actions = ["PENDING_ADMIN_REVIEW"]
        elif approved_proposed_code:
            line_warnings.append(f"ProductCode Creation Request Approved: '{approved_proposed_code}' is available to apply.")
            review_reason = f"ProductCode creation request approved: '{approved_proposed_code}' is available to apply."
            correction_actions = ["APPROVED_PRODUCTCODE_AVAILABLE"]
        elif rejected_info:
            line_warnings.append(f"ProductCode Creation Request Rejected: '{rejected_info['proposed_code']}'. Reason: {rejected_info['reason']}")
            review_reason = f"ProductCode creation request rejected: {rejected_info['reason']}"
            correction_actions = ["PRODUCTCODE_REJECTED"]

        # Evidence text must not be empty if status is 'suggested'
        source_text = line.source_excerpt or line.source_label or ""
        if not source_text and status == "suggested":
            source_text = "Extracted charge"

        evidence = None
        if source_text:
            evidence = {
                "source_text": source_text,
                "page": line.source_line_number,
                "section": None,
                "row_index": None,
                "table_index": None,
                "document_reference": line.source_batch.file_name if line.source_batch else None,
                "bounding_box": None,
                "extraction_note": None
            }

        suggested_charges.append({
            "id": str(line.id),
            "status": status,
            "display_label": line.description or line.source_label or "Charge Line",
            "raw_label": line.source_label or line.description or "",
            "suggested_product_code": suggested_code,
            "product_code_conflict": product_code_conflict,
            "bucket": bucket_val,
            "currency": line.currency or "PGK",
            "amount": Decimal(str(line.amount or 0.00)),
            "rate": Decimal(str(line.rate)) if line.rate is not None else None,
            "unit": line.unit or None,
            "calculation_basis": line.unit_type or None,
            "minimum_charge": Decimal(str(line.min_charge)) if line.min_charge is not None else None,
            "percentage_base": line.percent_basis or None,
            "quantity": quantity,
            "include_in_totals": not line.exclude_from_totals,
            "conditions": [line.note] if line.note else [],
            "warnings": line_warnings,
            "review_reason": review_reason,
            "evidence": evidence,
            "similarity_group_id": line.rule_meta.get('similarity_group_id') if isinstance(line.rule_meta, dict) else None,
            "correction_actions": correction_actions
        })

    # 6. Commercial Terms
    commercial_terms = []
    if isinstance(spe_db.conditions_json, dict):
        for key, val in spe_db.conditions_json.items():
            if key != 'user_audit_log':
                text = str(val.get('text') if isinstance(val, dict) else val)
                normalized_value = val.get('normalized_value') if isinstance(val, dict) else None
                commercial_terms.append({
                    "type": str(key),
                    "text": text,
                    "normalized_value": normalized_value,
                    "status": "suggested",
                    "evidence": None,
                    "review_reason": None
                })

    # 7. Unclassified & Ignored Items
    unclassified_items = []
    ignored_items = []
    warnings = []

    for batch in spe_db.source_batches.all():
        if isinstance(batch.analysis_summary_json, dict):
            # Collect unclassified items
            raw_unclassified = batch.analysis_summary_json.get('unclassified_items') or []
            for item in raw_unclassified:
                if isinstance(item, dict):
                    unclass_id = item.get("id") or f"unclass-{len(unclassified_items)}"
                    pending_proposed_code = pending_targets.get(str(unclass_id))
                    approved_proposed_code = approved_targets.get(str(unclass_id))
                    rejected_info = rejected_targets.get(str(unclass_id))
                    
                    item_review_reason = item.get("review_reason") or "Unclassified commercial-looking item requires operator classification"
                    if pending_proposed_code:
                        item_review_reason = f"ProductCode creation request '{pending_proposed_code}' is pending admin approval."
                    elif approved_proposed_code:
                        item_review_reason = f"ProductCode creation request approved: '{approved_proposed_code}' is available to apply."
                    elif rejected_info:
                        item_review_reason = f"ProductCode creation request rejected: {rejected_info['reason']}"
                        
                    unclassified_items.append({
                        "id": str(unclass_id),
                        "raw_text": item.get("raw_text") or item.get("text") or "Unclassified line",
                        "evidence": item.get("evidence"),
                        "review_reason": item_review_reason
                    })
            # Collect ignored items
            raw_ignored = batch.analysis_summary_json.get('ignored_items') or []
            for item in raw_ignored:
                if isinstance(item, dict):
                    ign_id = item.get("id") or f"ign-{len(ignored_items)}"
                    ignored_items.append({
                        "id": str(ign_id),
                        "raw_text": item.get("raw_text") or item.get("text") or "Ignored text",
                        "ignored_reason": item.get("ignored_reason") or "Standard boilerplate content ignored",
                        "evidence": item.get("evidence")
                    })
            # Collect warnings
            batch_warnings = batch.analysis_summary_json.get('warnings') or []
            for w in batch_warnings:
                if w not in warnings:
                    warnings.append(str(w))

    # 8. Totals Validation
    calculated_total = sum(c['amount'] for c in suggested_charges if c['include_in_totals'] and c['status'] != 'ignored')
    
    extracted_total = None
    for batch in spe_db.source_batches.all():
        if isinstance(batch.analysis_summary_json, dict):
            ext_tot_val = batch.analysis_summary_json.get('extracted_total')
            if ext_tot_val is not None:
                try:
                    extracted_total = Decimal(str(ext_tot_val))
                    break
                except Exception:
                    pass

    difference = None
    math_balances = True
    if extracted_total is not None:
        difference = calculated_total - extracted_total
        math_balances = abs(difference) <= Decimal("0.01")
    
    active_currencies = {c['currency'] for c in suggested_charges if c['include_in_totals']}
    currency_consistent = len(active_currencies) <= 1
    
    totals_validation_warnings = []
    if not math_balances and extracted_total is not None:
        totals_validation_warnings.append("Extracted total is different from calculated total.")
        mismatch_warning = "Totals mismatch warning: Extracted total from document does not match sum of suggested charges."
        if mismatch_warning not in warnings:
            warnings.append(mismatch_warning)
    if not currency_consistent:
        totals_validation_warnings.append("Mixed currencies detected.")
        mixed_currency_warning = "Mixed currency warning: Multiple currencies found in charge items."
        if mixed_currency_warning not in warnings:
            warnings.append(mixed_currency_warning)

    totals_validation = {
        "math_balances": math_balances,
        "currency_consistent": currency_consistent,
        "extracted_total": extracted_total,
        "calculated_total": calculated_total,
        "difference": difference,
        "tolerance": Decimal("0.00"),
        "warnings": totals_validation_warnings
    }

    # 9. Review Queue
    review_queue = []
    for c in suggested_charges:
        if c['status'] == 'needs_review':
            review_queue.append({
                "id": c['id'],
                "type": "charge_needs_review",
                "message": c['review_reason'] or "Requires operator validation"
            })
    for item in unclassified_items:
        review_queue.append({
            "id": item['id'],
            "type": "unclassified_item",
            "message": item['review_reason'] or "Unclassified commercial-looking item requires operator classification"
        })

    # 10. Correction Actions
    correction_actions = []
    for item in review_queue:
        if item['type'] == 'charge_needs_review':
            charge = next((c for c in suggested_charges if c['id'] == item['id']), None)
            if charge:
                if charge['product_code_conflict']:
                    correction_actions.append({
                        "charge_id": charge['id'],
                        "action_type": "RESOLVE_PRODUCT_CODE",
                        "options": ["FSC-AIR", "SUR-FUEL"]
                    })
                if charge['currency'] != primary_currency:
                    correction_actions.append({
                        "charge_id": charge['id'],
                        "action_type": "CONFIRM_INHERITED_CURRENCY",
                        "options": [charge['currency'], primary_currency, "PGK"]
                    })
        elif item['type'] == 'unclassified_item':
            correction_actions.append({
                "item_id": item['id'],
                "action_type": "CLASSIFY_ITEM",
                "options": ["ADD_AS_CHARGE", "IGNORE_ITEM"]
            })

    # 11. Metadata
    metadata = {
        "document_metadata": {
            "file_name": ", ".join(b.file_name for b in spe_db.source_batches.all() if b.file_name) or "Agent reply",
            "file_size": sum(b.analysis_summary_json.get('file_size', 0) for b in spe_db.source_batches.all() if isinstance(b.analysis_summary_json, dict)) or None,
            "processing_time_ms": sum(b.analysis_summary_json.get('processing_time_ms', 0) for b in spe_db.source_batches.all() if isinstance(b.analysis_summary_json, dict)) or None
        },
        "user_audit_log": spe_db.conditions_json.get('user_audit_log', []) if isinstance(spe_db.conditions_json, dict) else []
    }

    return {
        "contract_version": "1.0.0",
        "quote_summary": quote_summary,
        "shipment_context": shipment_context,
        "supplier_context": supplier_context,
        "freight": freight,
        "suggested_charges": suggested_charges,
        "commercial_terms": commercial_terms,
        "warnings": warnings,
        "unclassified_items": unclassified_items,
        "ignored_items": ignored_items,
        "totals_validation": totals_validation,
        "review_queue": review_queue,
        "correction_actions": correction_actions,
        "metadata": metadata
    }

def get_validated_draft_quote(spe_db: SpotPricingEnvelopeDB) -> DraftQuoteSchema:
    payload = build_draft_quote_payload(spe_db)
    return DraftQuoteSchema(**payload)
