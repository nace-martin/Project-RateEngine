# backend/quotes/spot_views.py
"""
SPOT Mode API Endpoints

Endpoints:
- POST /api/v3/spot/validate-scope/     - Validate shipment is PNG scope
- POST /api/v3/spot/evaluate-trigger/   - Check if SPOT mode required
- POST /api/v3/spot/envelopes/          - Create SPE
- GET  /api/v3/spot/envelopes/<id>/     - Get SPE
- POST /api/v3/spot/envelopes/<id>/acknowledge/  - Sales acknowledgement
- POST /api/v3/spot/envelopes/<id>/compute/      - Compute SPOT quote
"""

import logging
import hashlib
import json
import uuid
from typing import Optional
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from uuid import UUID

from django.utils import timezone
from django.db import transaction

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from django.shortcuts import get_object_or_404

from core.security import validate_pdf_upload
from core.business_rules import classify_png_shipment
from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_services import (
    ScopeValidator,
    SpotTriggerEvaluator,
    SpotEnvelopeService,
    ReplyAnalysisService,
)
from quotes.spot_schemas import (
    SPEShipmentContext,
    SPEChargeLine,
    SPEConditions,
    SPEAcknowledgement,
    SpotPricingEnvelope,
    SPEStatus,
)
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SPESourceBatchDB,
    SPEChargeLineDB,
    SPEAcknowledgementDB,
    TRIGGER_ENVELOPE_CREATED,
    TRIGGER_ENVELOPE_UPDATED,
    TRIGGER_SALES_ACKNOWLEDGED,
)
from quotes.services.spot_validation_snapshot_service import capture_validation_snapshot

from quotes.intake_safety import (
    build_source_analysis_summary_payload,
    evaluate_envelope_intake_safety,
    mark_source_analysis_review,
    normalize_source_analysis_summary,
    sync_source_analysis_summary_counts,
)
from quotes.serializers import SpotPricingEnvelopeSerializer, SPEChargeLineSerializer, SpotTemplateValidationReviewSerializer
from quotes.quote_result_contract import (
    build_persisted_line_item_metadata,
    build_persisted_quote_total_metadata,
)
from quotes.selectors import get_quote_for_user, get_spes_for_user
from quotes.currency_rules import determine_quote_currency
from quotes.services.charge_normalization import resolve_charge_alias
from quotes.services.spot_learning_service import (
    record_manual_resolution_event,
    record_conditional_resolution_event,
)


logger = logging.getLogger(__name__)


def _user_is_manager_or_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_manager", False) or getattr(user, "is_admin", False):
        return True
    return getattr(user, "role", None) in ("manager", "admin")


def _get_spe_or_404(user, envelope_id, queryset=None):
    if queryset is None:
        queryset = SpotPricingEnvelopeDB.objects.all()

    # Use the shared filter logic for IDOR/RBAC protection
    accessible_qs = get_spes_for_user(user, queryset)

    try:
        return accessible_qs.get(id=envelope_id)
    except SpotPricingEnvelopeDB.DoesNotExist:
        # To avoid leaking existence, we raise 403 or 404.
        # For consistency with get_quote_for_user, let's use 404.
        from django.http import Http404
        raise Http404("No SpotPricingEnvelopeDB matches the given query.")


def _spe_queryset():
    return SpotPricingEnvelopeDB.objects.prefetch_related(
        'charge_lines__source_batch',
        'charge_lines__matched_alias',
        'charge_lines__resolved_product_code',
        'charge_lines__manual_resolved_product_code',
        'charge_lines__manual_resolution_by',
        'source_batches__charge_lines',
        'acknowledgement',
    )


def _sync_batch_analysis_summary(batch: SPESourceBatchDB):
    """Update batch analysis summary based on current charge line status."""
    lines = list(batch.charge_lines.all())
    unmapped = sum(
        1
        for l in lines
        if l.normalization_status == SPEChargeLineDB.NormalizationStatus.UNMAPPED
        and l.manual_resolution_status != SPEChargeLineDB.ManualResolutionStatus.RESOLVED
    )

    # We don't currently store normalization_confidence on the charge line model,
    # so we preserve the original AI-detected count for now.
    summary = normalize_source_analysis_summary(batch.analysis_summary_json)
    low_conf = summary.get("low_confidence_line_count", 0)

    conditional = sum(1 for l in lines if l.conditional and not l.conditional_acknowledged)

    batch.analysis_summary_json = sync_source_analysis_summary_counts(
        batch.analysis_summary_json,
        unmapped_line_count=unmapped,
        low_confidence_line_count=low_conf,
        conditional_charge_count=conditional,
    )
    batch.save(update_fields=["analysis_summary_json", "updated_at"])


def _resolve_country_pair(
    origin_country: Optional[str],
    destination_country: Optional[str],
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
) -> tuple[str, str]:
    return ScopeValidator.normalize_countries(
        origin_country=origin_country,
        destination_country=destination_country,
        origin_airport=origin_code,
        destination_airport=destination_code,
    )


def _normalize_shipment_context(ctx: dict) -> dict:
    normalized = dict(ctx or {})
    origin_code = str(normalized.get("origin_code") or "").upper()
    destination_code = str(normalized.get("destination_code") or "").upper()
    
    # Ensure countries are resolved robustly
    try:
        origin_country, destination_country = _resolve_country_pair(
            normalized.get("origin_country"),
            normalized.get("destination_country"),
            origin_code=origin_code,
            destination_code=destination_code,
        )
    except Exception:
        logger.warning("Failed resolving country pair for context: %s", normalized)
        origin_country = str(normalized.get("origin_country") or "OTHER").upper()
        destination_country = str(normalized.get("destination_country") or "OTHER").upper()

    normalized["origin_code"] = origin_code
    normalized["destination_code"] = destination_code
    normalized["origin_country"] = origin_country
    normalized["destination_country"] = destination_country
    
    # Normalize Enum-like fields
    normalized["service_scope"] = str(normalized.get("service_scope") or "P2P").upper()
    normalized["commodity"] = str(normalized.get("commodity") or "GCR").upper()
    
    payment_term = str(normalized.get("payment_term") or "").strip().upper()
    if payment_term in {"PREPAID", "COLLECT"}:
        normalized["payment_term"] = payment_term
    elif "payment_term" in normalized:
        normalized.pop("payment_term", None)
        
    # Ensure numeric fields are safe for Pydantic float/int
    try:
        raw_weight = normalized.get("total_weight_kg")
        if raw_weight in (None, ""):
            normalized["total_weight_kg"] = 1.0
        else:
            normalized["total_weight_kg"] = float(raw_weight)
    except (TypeError, ValueError):
        normalized["total_weight_kg"] = 1.0
        
    try:
        raw_pieces = normalized.get("pieces")
        if raw_pieces in (None, ""):
            normalized["pieces"] = 1
        else:
            normalized["pieces"] = int(raw_pieces)
    except (TypeError, ValueError):
        normalized["pieces"] = 1
        
    return normalized


def _normalize_source_kind(value: Optional[str]) -> str:
    normalized = str(value or SPESourceBatchDB.SourceKind.AGENT).strip().upper()
    valid = {choice for choice, _ in SPESourceBatchDB.SourceKind.choices}
    return normalized if normalized in valid else SPESourceBatchDB.SourceKind.OTHER


def _normalize_source_type(value: Optional[str], pdf_file=None) -> str:
    if pdf_file is not None:
        return SPESourceBatchDB.SourceType.PDF
    normalized = str(value or SPESourceBatchDB.SourceType.TEXT).strip().upper()
    valid = {choice for choice, _ in SPESourceBatchDB.SourceType.choices}
    return normalized if normalized in valid else SPESourceBatchDB.SourceType.TEXT


def _normalize_target_bucket(value: Optional[str]) -> str:
    normalized = str(value or SPESourceBatchDB.TargetBucket.MIXED).strip().lower()
    valid = {choice for choice, _ in SPESourceBatchDB.TargetBucket.choices}
    return normalized if normalized in valid else SPESourceBatchDB.TargetBucket.MIXED


def _default_source_label(source_kind: str, target_bucket: str) -> str:
    bucket_labels = {
        SPESourceBatchDB.TargetBucket.AIRFREIGHT: "Freight Source",
        SPESourceBatchDB.TargetBucket.ORIGIN_CHARGES: "Origin Charges Source",
        SPESourceBatchDB.TargetBucket.DESTINATION_CHARGES: "Destination Charges Source",
        SPESourceBatchDB.TargetBucket.MIXED: "Primary SPOT Source",
    }
    kind_prefix = {
        SPESourceBatchDB.SourceKind.AIRLINE: "Airline",
        SPESourceBatchDB.SourceKind.AGENT: "Agent",
        SPESourceBatchDB.SourceKind.MANUAL: "Manual",
        SPESourceBatchDB.SourceKind.OTHER: "Other",
    }
    return f"{kind_prefix.get(source_kind, 'Other')} {bucket_labels.get(target_bucket, 'Source')}"


def _charge_direction_scope_for_bucket(bucket: Optional[str]) -> str:
    bucket_value = str(bucket or "").strip().lower()
    if bucket_value == SPEChargeLineDB.Bucket.ORIGIN_CHARGES:
        return ChargeAlias.DirectionScope.ORIGIN
    if bucket_value == SPEChargeLineDB.Bucket.AIRFREIGHT:
        return ChargeAlias.DirectionScope.MAIN
    if bucket_value == SPEChargeLineDB.Bucket.DESTINATION_CHARGES:
        return ChargeAlias.DirectionScope.DESTINATION
    return ChargeAlias.DirectionScope.ANY


def _charge_mode_scope_for_context(shipment_context: Optional[dict]) -> str:
    if not shipment_context:
        return ChargeAlias.ModeScope.ANY

    origin_country, destination_country = _resolve_country_pair(
        shipment_context.get("origin_country"),
        shipment_context.get("destination_country"),
        origin_code=shipment_context.get("origin_code"),
        destination_code=shipment_context.get("destination_code"),
    )
    return _infer_shipment_type(origin_country, destination_country)


def _resolve_spe_charge_normalization_fields(
    charge: dict,
    *,
    shipment_context: Optional[dict],
    existing_line: Optional[SPEChargeLineDB] = None,
    manual_resolution_source: Optional[SPEChargeLineDB] = None,
) -> dict:
    preserved_manual_resolution = {}
    if manual_resolution_source is not None:
        preserved_manual_resolution = {
            "manual_resolution_status": manual_resolution_source.manual_resolution_status,
            "manual_resolved_product_code": manual_resolution_source.manual_resolved_product_code,
            "manual_resolution_by": manual_resolution_source.manual_resolution_by,
            "manual_resolution_at": manual_resolution_source.manual_resolution_at,
        }

    if existing_line is not None:
        return {
            "source_label": existing_line.source_label,
            "normalized_label": existing_line.normalized_label,
            "normalization_status": existing_line.normalization_status,
            "normalization_method": existing_line.normalization_method,
            "matched_alias": existing_line.matched_alias,
            "resolved_product_code": existing_line.resolved_product_code,
            "canonical_charge_type": existing_line.canonical_charge_type,
            **preserved_manual_resolution,
        }

    raw_label = str(charge.get("source_label") or charge.get("description") or "")
    normalization_result = resolve_charge_alias(
        raw_label,
        mode_scope=_charge_mode_scope_for_context(shipment_context),
        direction_scope=_charge_direction_scope_for_bucket(charge.get("bucket")),
    )

    canonical_charge_type = None
    if normalization_result.resolved_charge_alias and normalization_result.resolved_charge_alias.canonical_charge_type:
        canonical_charge_type = normalization_result.resolved_charge_alias.canonical_charge_type
    elif manual_resolution_source is not None:
        canonical_charge_type = manual_resolution_source.canonical_charge_type

    return {
        "source_label": raw_label,
        "normalized_label": normalization_result.normalized_label,
        "normalization_status": normalization_result.normalization_status.value,
        "normalization_method": normalization_result.normalization_method.value,
        "matched_alias": normalization_result.resolved_charge_alias,
        "resolved_product_code": normalization_result.resolved_product_code,
        "canonical_charge_type": canonical_charge_type,
        "manual_resolution_status": None,
        "manual_resolved_product_code": None,
        "manual_resolution_by": None,
        "manual_resolution_at": None,
        **preserved_manual_resolution,
    }
def _incoming_charge_source_label(charge: dict) -> str:
    return str(charge.get("source_label") or charge.get("description") or "")


def _normalize_reconciliation_value(value) -> str:
    return str(value or "").strip().lower()


def _normalize_reconciliation_amount(value) -> str:
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value).strip()
    return format(amount.normalize(), "f")


def _source_line_fingerprint_payload(charge: dict) -> dict:
    return {
        "bucket": _normalize_reconciliation_value(charge.get("bucket")),
        "code": str(charge.get("code") or "").strip().upper(),
        "currency": str(charge.get("currency") or "").strip().upper(),
        "unit": _normalize_reconciliation_value(charge.get("unit")),
        "is_primary_cost": bool(charge.get("is_primary_cost", False)),
        "conditional": bool(charge.get("conditional", False)),
        "calculation_type": _normalize_reconciliation_value(charge.get("calculation_type")),
        "unit_type": _normalize_reconciliation_value(charge.get("unit_type")),
        "exclude_from_totals": bool(charge.get("exclude_from_totals", False)),
        "percent_basis": _normalize_reconciliation_value(charge.get("percent_basis")),
        "has_min_charge": charge.get("min_charge") not in (None, ""),
        "has_min_amount": charge.get("min_amount") not in (None, ""),
        "has_max_amount": charge.get("max_amount") not in (None, ""),
        "has_percent": charge.get("percent") not in (None, ""),
    }


def _build_source_line_fingerprint(charge: dict) -> str:
    payload = json.dumps(
        _source_line_fingerprint_payload(charge),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _incoming_charge_source_line_identity(charge: dict) -> str:
    explicit_identity = str(charge.get("source_line_identity") or "").strip()
    if explicit_identity:
        return explicit_identity[:255]
    return f"fp:{_build_source_line_fingerprint(charge)}"


def _incoming_charge_source_line_number(charge: dict) -> Optional[int]:
    value = charge.get("source_line_number")
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _existing_line_source_line_identity(line: SPEChargeLineDB) -> str:
    explicit_identity = str(line.source_line_identity or "").strip()
    if explicit_identity:
        return explicit_identity
    return _incoming_charge_source_line_identity(
        {
            "bucket": line.bucket,
            "code": line.code,
            "currency": line.currency,
            "unit": line.unit,
            "is_primary_cost": line.is_primary_cost,
            "conditional": line.conditional,
            "calculation_type": line.calculation_type,
            "unit_type": line.unit_type,
            "exclude_from_totals": line.exclude_from_totals,
            "percent_basis": line.percent_basis,
            "min_charge": line.min_charge,
            "min_amount": line.min_amount,
            "max_amount": line.max_amount,
            "percent": line.percent,
        }
    )


def _incoming_charge_logical_identity_signature(charge: dict) -> tuple[str, str, str, str]:
    return (
        str(charge.get("bucket") or "").strip().lower(),
        str(charge.get("code") or "").strip().upper(),
        str(charge.get("description") or "").strip().upper(),
        str(charge.get("source_reference") or "").strip().upper(),
    )


def _incoming_charge_source_semantic_signature(charge: dict) -> tuple[str, str, str, str, str]:
    return (
        _normalize_reconciliation_value(_incoming_charge_source_label(charge)),
        _normalize_reconciliation_amount(charge.get("amount")),
        str(charge.get("currency") or "").strip().upper(),
        _normalize_reconciliation_value(charge.get("unit")),
        _normalize_reconciliation_value(charge.get("source_reference")),
    )


def _existing_line_source_semantic_signature(line: SPEChargeLineDB) -> tuple[str, str, str, str, str]:
    return (
        _normalize_reconciliation_value(line.normalization_source_label),
        _normalize_reconciliation_amount(line.amount),
        str(line.currency or "").strip().upper(),
        _normalize_reconciliation_value(line.unit),
        _normalize_reconciliation_value(line.source_reference),
    )


def _should_preserve_existing_line_audit(existing_line: SPEChargeLineDB, charge: dict) -> bool:
    incoming_charge_line_id = str(charge.get("charge_line_id") or "").strip()
    if incoming_charge_line_id and incoming_charge_line_id == str(existing_line.id):
        return True

    incoming_source_label = _incoming_charge_source_label(charge)
    incoming_bucket = str(charge.get("bucket") or "").strip().lower()
    return (
        existing_line.normalization_source_label == incoming_source_label
        and str(existing_line.bucket or "").strip().lower() == incoming_bucket
    )


def _build_spe_charge_line_field_values(
    *,
    spe_db: SpotPricingEnvelopeDB,
    charge: dict,
    entered_by,
    entered_at,
    shipment_context: Optional[dict],
    source_batch: Optional[SPESourceBatchDB] = None,
    existing_line: Optional[SPEChargeLineDB] = None,
):
    audit_source_line = (
        existing_line
        if existing_line is not None and _should_preserve_existing_line_audit(existing_line, charge)
        else None
    )
    conditional = bool(charge.get("conditional", False))
    if existing_line is not None and conditional and "conditional_acknowledged" not in charge:
        conditional_acknowledged = existing_line.conditional_acknowledged
        conditional_acknowledged_by = existing_line.conditional_acknowledged_by
        conditional_acknowledged_at = existing_line.conditional_acknowledged_at
    else:
        conditional_acknowledged = bool(charge.get("conditional_acknowledged", False)) if conditional else False
        conditional_acknowledged_by = existing_line.conditional_acknowledged_by if (
            existing_line is not None and conditional_acknowledged
        ) else None
        conditional_acknowledged_at = existing_line.conditional_acknowledged_at if (
            existing_line is not None and conditional_acknowledged
        ) else None

    # Resolve normalization fields
    norm_fields = _resolve_spe_charge_normalization_fields(
        charge,
        shipment_context=shipment_context,
        existing_line=audit_source_line,
        manual_resolution_source=existing_line,
    )

    # Inferred calculation basis
    unit_raw = charge.get("unit")
    calculation_basis = "unknown"
    if unit_raw:
        u = str(unit_raw).strip().lower()
        if u in {"per_kg", "kg"}:
            calculation_basis = "per_kg"
        elif u in {"flat", "per_shipment", "shipment"}:
            calculation_basis = "flat"
        elif u in {"percentage", "percent"}:
            calculation_basis = "percentage"
        elif u in {"per_awb", "awb"}:
            calculation_basis = "per_awb"
        elif u in {"per_entry", "entry"}:
            calculation_basis = "per_entry"

    # Context snapshot
    ctx = shipment_context or spe_db.shipment_context_json or {}
    service_scope_snapshot = ctx.get("service_scope")
    origin_code_snapshot = ctx.get("origin_code")
    destination_code_snapshot = ctx.get("destination_code")
    
    route_context = None
    if origin_code_snapshot and destination_code_snapshot:
        route_context = f"{origin_code_snapshot}-{destination_code_snapshot}"

    # Agent/Supplier name snapshot
    agent_name_snapshot = ctx.get("agent_name") or ctx.get("supplier_name") or charge.get("agent_name")
    if not agent_name_snapshot and source_batch:
        agent_name_snapshot = source_batch.label or source_batch.file_name

    # Source section label
    source_section_label = (
        charge.get("source_section_label")
        or charge.get("section_label")
        or charge.get("source_section")
        or charge.get("section")
    )

    # Normalization confidence (numeric only)
    normalization_confidence = None
    raw_confidence = charge.get("confidence")
    if raw_confidence is not None:
        try:
            from decimal import Decimal, InvalidOperation
            normalization_confidence = Decimal(str(raw_confidence))
        except (ValueError, TypeError, InvalidOperation):
            pass

    # Normalization review reason
    normalization_review_reason = None
    if existing_line is not None and existing_line.manual_resolution_status == "RESOLVED":
        normalization_review_reason = existing_line.normalization_review_reason
    else:
        norm_status = norm_fields.get("normalization_status")
        canonical_ct = norm_fields.get("canonical_charge_type")
        resolved_pc = norm_fields.get("resolved_product_code")

        is_conditional_ct = False
        if canonical_ct:
            is_conditional_ct = canonical_ct.code in {"CONDITIONAL_STORAGE", "CONDITIONAL_DEMURRAGE"}

        if norm_status == "UNMAPPED" and not canonical_ct:
            normalization_review_reason = "canonical_type_missing"
        elif canonical_ct and not resolved_pc:
            normalization_review_reason = "product_code_missing"
        elif norm_status == "AMBIGUOUS":
            normalization_review_reason = "ambiguous_product_mapping"
        elif is_conditional_ct:
            normalization_review_reason = "conditional_charge"
        elif norm_status == "UNMAPPED":
            # Fallback if unmapped but somehow has canonical type
            normalization_review_reason = "canonical_type_missing"

    return {
        "envelope": spe_db,
        "source_batch": source_batch if source_batch is not None else (
            existing_line.source_batch if existing_line is not None else None
        ),
        "code": charge["code"],
        "description": charge["description"],
        "amount": charge["amount"],
        "currency": charge["currency"],
        "unit": charge["unit"],
        "bucket": charge["bucket"],
        "is_primary_cost": charge.get("is_primary_cost", False),
        "conditional": conditional,
        "conditional_acknowledged": conditional_acknowledged,
        "conditional_acknowledged_by": conditional_acknowledged_by,
        "conditional_acknowledged_at": conditional_acknowledged_at,
        "min_charge": charge.get("min_charge"),
        "note": charge.get("note") or "",
        "exclude_from_totals": charge.get("exclude_from_totals", False),
        "percentage_basis": charge.get("percentage_basis"),
        "calculation_type": charge.get("calculation_type"),
        "unit_type": charge.get("unit_type"),
        "rate": charge.get("rate"),
        "min_amount": charge.get("min_amount"),
        "max_amount": charge.get("max_amount"),
        "percent": charge.get("percent"),
        "percent_basis": charge.get("percent_basis"),
        "rule_meta": charge.get("rule_meta") or {},
        "source_reference": charge["source_reference"],
        "source_excerpt": str(charge.get("source_excerpt") or "")[:4000],
        "source_line_number": _incoming_charge_source_line_number(charge),
        "source_line_identity": _incoming_charge_source_line_identity(charge),
        "entered_by": entered_by,
        "entered_at": entered_at,
        
        # New Context Metadata fields
        "calculation_basis": calculation_basis,
        "service_scope_snapshot": service_scope_snapshot,
        "agent_name_snapshot": agent_name_snapshot,
        "origin_code_snapshot": origin_code_snapshot,
        "destination_code_snapshot": destination_code_snapshot,
        "route_context": route_context,
        "source_section_label": source_section_label,
        "normalization_confidence": normalization_confidence,
        "normalization_review_reason": normalization_review_reason,
        
        **norm_fields,
    }


def _create_spe_charge_line(
    *,
    spe_db: SpotPricingEnvelopeDB,
    charge: dict,
    entered_by,
    entered_at,
    shipment_context: Optional[dict],
    source_batch: Optional[SPESourceBatchDB] = None,
    existing_line: Optional[SPEChargeLineDB] = None,
):
    return SPEChargeLineDB.objects.create(
        **_build_spe_charge_line_field_values(
            spe_db=spe_db,
            charge=charge,
            entered_by=entered_by,
            entered_at=entered_at,
            shipment_context=shipment_context,
            source_batch=source_batch,
            existing_line=existing_line,
        )
    )


def _update_spe_charge_line(
    *,
    existing_line: SPEChargeLineDB,
    spe_db: SpotPricingEnvelopeDB,
    charge: dict,
    entered_by,
    entered_at,
    shipment_context: Optional[dict],
    source_batch: Optional[SPESourceBatchDB] = None,
):
    field_values = _build_spe_charge_line_field_values(
        spe_db=spe_db,
        charge=charge,
        entered_by=entered_by,
        entered_at=entered_at,
        shipment_context=shipment_context,
        source_batch=source_batch,
        existing_line=existing_line,
    )

    for field_name, value in field_values.items():
        setattr(existing_line, field_name, value)

    existing_line.save(update_fields=list(field_values.keys()))
    return existing_line


def _reconcile_spe_charge_lines(
    *,
    spe_db: SpotPricingEnvelopeDB,
    existing_lines: list[SPEChargeLineDB],
    incoming_charges: list[dict],
    entered_by,
    entered_at,
    shipment_context: Optional[dict],
    source_batch: Optional[SPESourceBatchDB] = None,
    existing_lines_for_matching: Optional[list[SPEChargeLineDB]] = None,
):
    def _select_unique_unmatched_candidate(candidates):
        unmatched_candidates = [
            candidate
            for candidate in candidates
            if str(candidate.id) not in matched_existing_line_ids
        ]
        if len(unmatched_candidates) == 1:
            return unmatched_candidates[0]
        return None

    matching_lines = list(existing_lines_for_matching or existing_lines)

    existing_lines_by_id = {
        str(line.id): line
        for line in matching_lines
    }
    existing_lines_by_source_identity = {}
    for line in matching_lines:
        existing_lines_by_source_identity.setdefault(
            _existing_line_source_line_identity(line),
            [],
        ).append(line)
    existing_lines_by_source_semantic_signature = {}
    for line in matching_lines:
        existing_lines_by_source_semantic_signature.setdefault(
            _existing_line_source_semantic_signature(line),
            [],
        ).append(line)
    existing_lines_by_signature = {}
    for line in matching_lines:
        existing_lines_by_signature.setdefault(line.logical_identity_signature(), []).append(line)

    matched_existing_line_ids = set()

    for charge in incoming_charges:
        existing_line = existing_lines_by_id.get(
            str(charge.get("charge_line_id") or "").strip()
        )
        if existing_line is None:
            source_line_identity = _incoming_charge_source_line_identity(charge)
            existing_line = _select_unique_unmatched_candidate(
                existing_lines_by_source_identity.get(source_line_identity, [])
            )
        if existing_line is None:
            signature = _incoming_charge_logical_identity_signature(charge)
            existing_line = _select_unique_unmatched_candidate(
                existing_lines_by_signature.get(signature, [])
            )
        if existing_line is None:
            semantic_signature = _incoming_charge_source_semantic_signature(charge)
            existing_line = _select_unique_unmatched_candidate(
                existing_lines_by_source_semantic_signature.get(semantic_signature, [])
            )

        if existing_line is not None:
            matched_existing_line_ids.add(str(existing_line.id))
            _update_spe_charge_line(
                existing_line=existing_line,
                spe_db=spe_db,
                charge=charge,
                entered_by=entered_by,
                entered_at=entered_at,
                shipment_context=shipment_context,
                source_batch=source_batch,
            )
            continue

        created_line = _create_spe_charge_line(
            spe_db=spe_db,
            charge=charge,
            entered_by=entered_by,
            entered_at=entered_at,
            shipment_context=shipment_context,
            source_batch=source_batch,
        )
        matched_existing_line_ids.add(str(created_line.id))

    for line in existing_lines:
        if str(line.id) not in matched_existing_line_ids:
            line.delete()


def _coerce_product_code_id(value) -> Optional[int]:
    if value in (None, "", {}):
        return None
    if isinstance(value, dict):
        value = value.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_or_create_source_batch(
    *,
    spe_db: SpotPricingEnvelopeDB,
    request,
    source_batch_id: Optional[str],
    source_kind: str,
    source_type: str,
    target_bucket: str,
    label: str,
    source_reference: str,
    raw_text: str,
    file_name: str = "",
    file_content_type: str = "",
    analysis_summary_json: Optional[dict] = None,
) -> SPESourceBatchDB:
    batch = None
    if source_batch_id:
        batch = get_object_or_404(spe_db.source_batches, id=source_batch_id)
    else:
        batch = (
            spe_db.source_batches
            .filter(
                source_kind=source_kind,
                target_bucket=target_bucket,
                label=label,
            )
            .order_by('-updated_at')
            .first()
        )
        if batch is None:
            batch = SPESourceBatchDB.objects.create(
                envelope=spe_db,
                source_kind=source_kind,
                source_type=source_type,
                target_bucket=target_bucket,
                label=label,
                source_reference=source_reference,
                raw_text=raw_text,
                file_name=file_name,
                file_content_type=file_content_type,
                analysis_summary_json=analysis_summary_json or {},
                created_by=request.user,
            )
            return batch

    batch.source_kind = source_kind
    batch.source_type = source_type
    batch.target_bucket = target_bucket
    batch.label = label
    batch.source_reference = source_reference
    batch.raw_text = raw_text
    batch.file_name = file_name
    batch.file_content_type = file_content_type
    batch.analysis_summary_json = analysis_summary_json or {}
    batch.save(
        update_fields=[
            'source_kind', 'source_type', 'target_bucket', 'label',
            'source_reference', 'raw_text', 'file_name', 'file_content_type',
            'analysis_summary_json', 'updated_at',
        ]
    )
    return batch


SAFE_MATCH_METHODS = {
    SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS,
}


def _charge_line_missing_critical_fields(line: SPEChargeLineDB) -> list[str]:
    missing = []
    if line.amount is None or line.amount <= 0:
        missing.append("amount")
    if not str(line.currency or "").strip():
        missing.append("currency")
    if not str(line.unit or "").strip():
        missing.append("unit")
    return missing


def _charge_line_review_blockers(line: SPEChargeLineDB) -> list[str]:
    blockers = []
    missing_fields = _charge_line_missing_critical_fields(line)
    if missing_fields:
        blockers.append("Missing " + ", ".join(missing_fields))
    if line.requires_review:
        if line.normalization_status == SPEChargeLineDB.NormalizationStatus.UNMAPPED:
            blockers.append("Unmapped")
        elif line.normalization_status == SPEChargeLineDB.NormalizationStatus.AMBIGUOUS:
            blockers.append("Ambiguous")
    elif (
        line.normalization_status == SPEChargeLineDB.NormalizationStatus.MATCHED
        and line.normalization_method not in SAFE_MATCH_METHODS
        and line.manual_resolution_status != SPEChargeLineDB.ManualResolutionStatus.RESOLVED
    ):
        blockers.append("Review non-exact match")
    if line.requires_conditional_review:
        blockers.append("Conditional")
    return blockers


def _spot_exception_blockers(spe_db: SpotPricingEnvelopeDB) -> list[str]:
    blockers: list[str] = []
    seen_source_identity: set[str] = set()
    duplicate_source_identity: set[str] = set()

    for line in spe_db.charge_lines.select_related("matched_alias", "resolved_product_code").all():
        identity = str(line.source_line_identity or "").strip()
        if identity:
            if identity in seen_source_identity:
                duplicate_source_identity.add(identity)
            seen_source_identity.add(identity)

        line_blockers = _charge_line_review_blockers(line)
        if not line_blockers:
            is_safe_match = (
                line.normalization_status == SPEChargeLineDB.NormalizationStatus.MATCHED
                and line.normalization_method in SAFE_MATCH_METHODS
                and not line.conditional
                and not _charge_line_missing_critical_fields(line)
            )
            if is_safe_match:
                continue
        for blocker in line_blockers:
            blockers.append(f"{line.description}: {blocker}")

    for identity in sorted(duplicate_source_identity):
        blockers.append(f"Duplicate source line detected: {identity}")

    return blockers


def _exception_review_error_response(spe_db: SpotPricingEnvelopeDB):
    blockers = _spot_exception_blockers(spe_db)
    if not blockers:
        return None
    return Response(
        {
            "error": "Resolve SPOT charge exceptions before creating quote.",
            "blocking_issues": blockers,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _resolve_output_currency_for_shipment(
    shipment_type: str,
    payment_term: str,
    origin_location,
    destination_location,
) -> str:
    return determine_quote_currency(
        shipment_type=shipment_type,
        payment_term=payment_term,
        origin_country_code=getattr(origin_location, "country_code", None),
        destination_country_code=getattr(destination_location, "country_code", None),
    )


def _get_intake_safety(spe_db: SpotPricingEnvelopeDB) -> dict:
    return evaluate_envelope_intake_safety(spe_db.source_batches.all())


def _intake_safety_error_response(spe_db: SpotPricingEnvelopeDB):
    intake_safety = _get_intake_safety(spe_db)
    if intake_safety["is_safe_to_quote"]:
        return None
    return Response(
        {
            "error": "Imported source review is incomplete. Review each imported source before continuing.",
            "intake_safety": intake_safety,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _normalize_missing_components(raw_value) -> Optional[list[str]]:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        raw_list = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_list = list(raw_value)
    else:
        return []
    return [str(item).upper() for item in raw_list if str(item).strip()]


def _derive_missing_components_from_context(ctx: dict) -> Optional[list[str]]:
    origin_code = str(ctx.get("origin_code") or "").upper()
    destination_code = str(ctx.get("destination_code") or "").upper()
    if not origin_code or not destination_code:
        return None

    service_scope = str(ctx.get("service_scope") or "P2P")
    payment_term = str(ctx.get("payment_term") or "").upper() or None
    origin_country, destination_country = _resolve_country_pair(
        ctx.get("origin_country"),
        ctx.get("destination_country"),
        origin_code=origin_code,
        destination_code=destination_code,
    )
    direction = _infer_shipment_type(origin_country, destination_country)

    try:
        from quotes.spot_services import RateAvailabilityService
        from quotes.completeness import evaluate_from_availability

        component_outcomes = RateAvailabilityService.get_component_outcomes(
            origin_airport=origin_code,
            destination_airport=destination_code,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
        )
        availability = {
            component: outcome.get("status") in {"covered_exact", "covered_fallback"}
            for component, outcome in component_outcomes.items()
        }
        coverage = evaluate_from_availability(
            component_availability=availability,
            shipment_type=direction,
            service_scope=service_scope,
        )
        return coverage.missing_required
    except Exception:
        logger.exception(
            "Failed deriving missing components for SPOT context %s->%s",
            origin_code,
            destination_code,
        )
        return None


def _resolve_missing_components_for_context(ctx: dict) -> Optional[list[str]]:
    normalized = _normalize_missing_components(ctx.get("missing_components"))
    if normalized is not None:
        return normalized
    return _derive_missing_components_from_context(ctx)


def _infer_shipment_type(origin_country: str, destination_country: str) -> str:
    return classify_png_shipment(origin_country, destination_country)


def _build_spe_from_db(
    spe_db: SpotPricingEnvelopeDB,
    status_override: Optional[str] = None,
    acknowledgement_override: Optional[SPEAcknowledgement] = None,
) -> SpotPricingEnvelope:
    ack = acknowledgement_override
    if ack is None and hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
        ack_db = spe_db.acknowledgement
        ack = SPEAcknowledgement(
            acknowledged_by_user_id=str(ack_db.acknowledged_by_id) if ack_db.acknowledged_by_id else "",
            acknowledged_at=ack_db.acknowledged_at,
            statement=ack_db.statement,
        )

    charges = []
    for cl in spe_db.charge_lines.all():
        # Guard against legacy/invalid draft rows with zero amount.
        # SPE schema requires amount > 0 and these rows should not block acknowledgement.
        if cl.amount is None or cl.amount <= 0:
            logger.warning(
                "Skipping invalid SPE charge line with non-positive amount: spe=%s line=%s amount=%s",
                spe_db.id,
                cl.id,
                cl.amount,
            )
            continue

        charges.append(
            SPEChargeLine(
                code=cl.code,
                description=cl.description,
                amount=float(cl.amount),
                currency=cl.currency,
                unit=cl.unit,
                bucket=cl.bucket,
                is_primary_cost=cl.is_primary_cost,
                conditional=cl.conditional,
                source_reference=cl.source_reference,
                source_excerpt=cl.source_excerpt,
                source_line_number=cl.source_line_number,
                source_line_identity=cl.source_line_identity,
                entered_by_user_id=str(cl.entered_by_id) if cl.entered_by_id else "",
                entered_at=cl.entered_at,
                min_charge=float(cl.min_charge) if cl.min_charge is not None else None,
                note=cl.note,
                exclude_from_totals=cl.exclude_from_totals,
                percentage_basis=cl.percentage_basis,
                calculation_type=cl.calculation_type,
                unit_type=cl.unit_type,
                rate=float(cl.rate) if cl.rate is not None else None,
                min_amount=float(cl.min_amount) if cl.min_amount is not None else None,
                max_amount=float(cl.max_amount) if cl.max_amount is not None else None,
                percent=float(cl.percent) if cl.percent is not None else None,
                percent_basis=cl.percent_basis,
                rule_meta=cl.rule_meta or {},
            )
        )

    ctx = _normalize_shipment_context(spe_db.shipment_context_json)
    if not ctx.get("payment_term") and getattr(spe_db, "quote", None) and getattr(spe_db.quote, "payment_term", None):
        ctx["payment_term"] = str(spe_db.quote.payment_term).upper()
    resolved_missing_components = _resolve_missing_components_for_context(ctx)
    status_value = status_override or spe_db.status

    return SpotPricingEnvelope(
        id=str(spe_db.id),
        status=SPEStatus(status_value),
        shipment=SPEShipmentContext(
            origin_country=ctx.get('origin_country', 'OTHER'),
            destination_country=ctx.get('destination_country', 'OTHER'),
            origin_code=ctx.get('origin_code', 'XXX'),
            destination_code=ctx.get('destination_code', 'XXX'),
            commodity=ctx.get('commodity', 'GCR'),
            total_weight_kg=ctx.get('total_weight_kg', 1.0),
            pieces=ctx.get('pieces', 1),
            service_scope=str(ctx.get('service_scope', 'p2p')).lower(),
            payment_term=(str(ctx.get('payment_term')).lower() if ctx.get('payment_term') else None),
            missing_components=resolved_missing_components,
        ),
        charges=charges,
        conditions=SPEConditions(**spe_db.conditions_json) if spe_db.conditions_json else SPEConditions(),
        acknowledgement=ack,
        spot_trigger_reason_code=spe_db.spot_trigger_reason_code,
        spot_trigger_reason_text=spe_db.spot_trigger_reason_text,
        created_by_user_id=str(spe_db.created_by_id) if spe_db.created_by_id else "",
        created_at=spe_db.created_at,
        expires_at=spe_db.expires_at,
    )


# =============================================================================
# SCOPE VALIDATION API
# =============================================================================

class SpotScopeValidateAPIView(APIView):
    """
    POST /api/v3/spot/validate-scope/
    
    Validate shipment is within PNG scope.
    Must be called BEFORE any SPOT logic.
    
    Request:
        { "origin_country": "AU", "destination_country": "PG" }
    
    Response:
        { "is_valid": true, "error": null }
        or
        { "is_valid": false, "error": "Out of scope: ..." }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        origin = request.data.get('origin_country', '')
        destination = request.data.get('destination_country', '')
        origin_code = request.data.get('origin_code', '')
        destination_code = request.data.get('destination_code', '')
        
        is_valid, error = ScopeValidator.validate(
            origin,
            destination,
            origin_airport=origin_code,
            destination_airport=destination_code,
        )
        
        return Response({
            'is_valid': is_valid,
            'error': error,
        })


# =============================================================================
# TRIGGER EVALUATION API
# =============================================================================

class SpotTriggerEvaluateAPIView(APIView):
    """
    POST /api/v3/spot/evaluate-trigger/
    
    Evaluate if SPOT mode is required for shipment.
    
    Request:
        {
            "origin_country": "CN",
            "destination_country": "PG",
            "commodity": "GCR",
            "origin_airport": "SZX",
            "destination_airport": "POM",
            "has_valid_buy_rate": false
        }
    
    Response:
        {
            "is_spot_required": true,
            "trigger": {
                "code": "NO_BUY_RATE",
                "text": "No valid BUY rate exists..."
            }
        }
        or
        {
            "is_spot_required": false,
            "trigger": null
        }
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _optional_int(value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _selector_issue_from_outcomes(
        *,
        component_outcomes: dict,
        direction: str,
        service_scope: str,
    ) -> Optional[dict]:
        from quotes.completeness import required_components

        for component in sorted(required_components(direction, service_scope)):
            outcome = component_outcomes.get(component) or {}
            if outcome.get("status") in {"missing_dimension", "ambiguous"}:
                return outcome
        return None

    def post(self, request):
        # Calculate direction
        origin_airport = request.data.get('origin_airport', '')
        destination_airport = request.data.get('destination_airport', '')
        origin_country, destination_country = _resolve_country_pair(
            request.data.get('origin_country', ''),
            request.data.get('destination_country', ''),
            origin_code=origin_airport,
            destination_code=destination_airport,
        )
        direction = _infer_shipment_type(origin_country, destination_country)
        
        # Build component availability map from DB
        service_scope = request.data.get('service_scope', 'P2P')
        payment_term = str(request.data.get('payment_term') or '').upper()
        if payment_term not in {'PREPAID', 'COLLECT'}:
            return Response(
                {'error': "payment_term is required and must be PREPAID or COLLECT"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from quotes.spot_services import CommodityRateRuleService, RateAvailabilityService
        component_outcomes = RateAvailabilityService.get_component_outcomes(
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            direction=direction,
            service_scope=service_scope,
            payment_term=payment_term,
            agent_id=self._optional_int(request.data.get("agent_id")),
            carrier_id=self._optional_int(request.data.get("carrier_id")),
            buy_currency=request.data.get("buy_currency"),
            quote_currency=request.data.get("quote_currency"),
        )
        selector_issue = self._selector_issue_from_outcomes(
            component_outcomes=component_outcomes,
            direction=direction,
            service_scope=service_scope,
        )
        component_availability = {
            component: (
                outcome.get('status') in {'covered_exact', 'covered_fallback'}
                or (
                    selector_issue is outcome
                    and outcome.get('status') in {'missing_dimension', 'ambiguous'}
                )
            )
            for component, outcome in component_outcomes.items()
        }
        commodity = str(request.data.get('commodity') or 'GCR').upper()
        commodity_coverage = CommodityRateRuleService.evaluate_coverage(
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            direction=direction,
            service_scope=service_scope,
            commodity_code=commodity,
            payment_term=payment_term,
        )

        is_spot, trigger = SpotTriggerEvaluator.evaluate(
            origin_country=origin_country,
            destination_country=destination_country,
            direction=direction,
            service_scope=service_scope,
            component_availability=component_availability,
            commodity_code=commodity,
            commodity_coverage=commodity_coverage,
        )

        logger.info(
            "SPOT trigger evaluation lane=%s->%s direction=%s scope=%s payment_term=%s commodity=%s "
            "rate_coverage_map=%s missing_components=%s missing_product_codes=%s "
            "component_outcomes=%s "
            "spot_required_product_codes=%s manual_required_product_codes=%s is_spot_required=%s",
            origin_airport,
            destination_airport,
            direction,
            service_scope,
            payment_term,
            commodity,
            component_availability,
            trigger.missing_components if trigger else [],
            trigger.missing_product_codes if trigger else [],
            component_outcomes,
            trigger.spot_required_product_codes if trigger else [],
            trigger.manual_required_product_codes if trigger else [],
            is_spot,
        )
        
        response_payload = {
            'is_spot_required': is_spot,
            'trigger': {
                'code': trigger.code,
                'text': trigger.text,
                'missing_components': trigger.missing_components,
                'missing_product_codes': trigger.missing_product_codes,
                'spot_required_product_codes': trigger.spot_required_product_codes,
                'manual_required_product_codes': trigger.manual_required_product_codes,
            } if trigger else None,
            'component_outcomes': component_outcomes,
        }
        if selector_issue is not None:
            response_payload['selector_issue'] = selector_issue

        return Response(response_payload)


# =============================================================================
# STANDARD CHARGES API (Hybrid SPOT)
# =============================================================================

class StandardChargesAPIView(APIView):
    """
    POST /api/v3/spot/standard-charges/
    
    Fetch standard charges from DB for hybrid SPOT pre-population.
    Returns airfreight and origin charges where DB coverage exists.
    
    Request:
        {
            "origin_code": "POM",
            "destination_code": "SIN",
            "direction": "EXPORT",
            "service_scope": "D2D",
            "payment_term": "PREPAID",
            "weight_kg": 100,
            "commodity": "GCR"
        }
    
    Response:
        {
            "charges": [
                {
                    "code": "FREIGHT",
                    "description": "Airfreight",
                    "amount": "5.50",
                    "currency": "USD",
                    "unit": "per_kg",
                    "bucket": "airfreight",
                    "is_primary_cost": true,
                    "source_reference": "Standard Rate (ExportCOGS)"
                },
                ...
            ]
        }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        from quotes.spot_services import StandardChargeService
        
        origin_code = request.data.get("origin_code", "").upper()
        destination_code = request.data.get("destination_code", "").upper()
        direction = request.data.get("direction", "EXPORT").upper()
        service_scope = request.data.get("service_scope", "D2D").upper()
        payment_term = str(request.data.get("payment_term") or "").upper()
        if payment_term not in {"PREPAID", "COLLECT"}:
            return Response(
                {"error": "payment_term is required and must be PREPAID or COLLECT"},
                status=400
            )
        weight_kg = float(request.data.get("weight_kg", 100))
        commodity = request.data.get("commodity", "GCR").upper()
        
        if not origin_code or not destination_code:
            return Response(
                {"error": "origin_code and destination_code are required"},
                status=400
            )
        
        charges = StandardChargeService.get_standard_charges(
            origin_code=origin_code,
            destination_code=destination_code,
            direction=direction,
            service_scope=service_scope,
            weight_kg=weight_kg,
            commodity=commodity,
            payment_term=payment_term,
        )
        
        return Response({"charges": charges})


# =============================================================================
# SPE LIFECYCLE APIs
# =============================================================================

class SpotEnvelopeListCreateAPIView(APIView):
    """
    GET  /api/v3/spot/envelopes/          - List user's SPEs
    POST /api/v3/spot/envelopes/          - Create new SPE
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """List SPEs created by user."""
        user = request.user
        base_qs = _spe_queryset()

        # SECURITY FIX: Enforce IDOR/RBAC protection on SPE listing
        spe_qs = get_spes_for_user(user, base_qs)

        # Filter by status if provided
        status_param = request.query_params.get('status')
        if status_param:
            spe_qs = spe_qs.filter(status=status_param)

        spes = spe_qs.order_by('-created_at')[:20]
        
        serializer = SpotPricingEnvelopeSerializer(spes, many=True)
        return Response(serializer.data)
    
    @transaction.atomic
    def post(self, request):
        """Create new SPE in DRAFT status."""
        try:
            data = request.data
            quote = None
            quote_id = data.get('quote_id')
            if quote_id:
                from django.core.exceptions import ValidationError as DjangoValidationError
                try:
                    quote = get_quote_for_user(request.user, quote_id)
                except (ValueError, AttributeError, TypeError, DjangoValidationError):
                     return Response(
                        {'error': f"Invalid quote_id format: {quote_id}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                except Exception as e:
                    from django.http import Http404
                    if isinstance(e, Http404):
                        return Response(
                            {'error': f"Quote not found: {quote_id}"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                    raise e

                from quotes.state_machine import is_quote_editable
                if not is_quote_editable(quote):
                    return Response(
                        {'error': f"Cannot create SPE for locked quote ({quote.status})."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Validate required fields
            required = ['shipment_context', 'trigger_code', 'trigger_text']
            for field in required:
                if field not in data:
                    return Response(
                        {'error': f'Missing required field: {field}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if data[field] is None:
                    return Response(
                        {'error': f'Field {field} cannot be null'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            if not isinstance(data['shipment_context'], dict):
                return Response(
                    {'error': 'shipment_context must be a dictionary'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create DB record
            try:
                ctx = _normalize_shipment_context(data['shipment_context'])
            except Exception as e:
                return Response(
                    {'error': f"Failed to normalize shipment context: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if (
                not ctx.get("payment_term")
                and quote is not None
                and getattr(quote, "payment_term", None)
            ):
                ctx["payment_term"] = str(quote.payment_term).upper()
            
            if "missing_components" not in ctx:
                resolved_missing_components = _resolve_missing_components_for_context(ctx)
                if resolved_missing_components is not None:
                    ctx["missing_components"] = resolved_missing_components
            
            now = timezone.now()
            
            # Safe validity_hours parsing
            try:
                raw_validity = data.get('validity_hours', 72)
                if raw_validity is None:
                    validity_hours = 72
                else:
                    validity_hours = int(raw_validity)
            except (TypeError, ValueError):
                 return Response(
                    {'error': 'validity_hours must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                spe_db = SpotPricingEnvelopeDB.objects.create(
                    status='draft',
                    shipment_context_json=ctx,
                    conditions_json=data.get('conditions', {}),
                    spot_trigger_reason_code=data['trigger_code'],
                    spot_trigger_reason_text=data['trigger_text'],
                    created_by=request.user,
                    expires_at=now + timedelta(hours=validity_hours),
                    quote=quote,
                )
            except Exception as e:
                logger.error("Database error creating SPE: %s", str(e), exc_info=True)
                return Response(
                    {'error': f"Failed to save SPOT envelope to database: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create charge lines (optional)
            charges_data = data.get('charges', [])
            if not isinstance(charges_data, list):
                return Response(
                    {'error': 'charges must be a list'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            for i, charge in enumerate(charges_data):
                try:
                    rate_val = charge.get('rate') if charge.get('rate') not in ("", None) else None
                    min_amount_val = charge.get('min_amount') if charge.get('min_amount') not in ("", None) else None
                    max_amount_val = charge.get('max_amount') if charge.get('max_amount') not in ("", None) else None
                    percent_val = charge.get('percent') if charge.get('percent') not in ("", None) else None
                    _create_spe_charge_line(
                        spe_db=spe_db,
                        charge={
                            **charge,
                            'rate': rate_val,
                            'min_amount': min_amount_val,
                            'max_amount': max_amount_val,
                            'percent': percent_val,
                        },
                        entered_by=request.user,
                        entered_at=now,
                        shipment_context=ctx,
                    )
                except KeyError as e:
                    return Response(
                        {'error': f"Missing required field {str(e)} in charge line at index {i}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Validate via Pydantic (will raise if invalid)
            try:
                self._validate_spe(spe_db)
            except Exception as e:
                logger.error("Validation failed for SPE %s: %s", spe_db.id, str(e), exc_info=True)
                spe_db.delete()
                return Response(
                    {'error': f"Validation Error: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info("Created SPE %s for user %s", spe_db.id, request.user.username)
            
            # Capture snapshot best-effort on creation
            capture_validation_snapshot(spe_db, TRIGGER_ENVELOPE_CREATED)

            serializer = SpotPricingEnvelopeSerializer(spe_db)
            return Response(serializer.data, status=status.HTTP_201_CREATED)


        except PermissionDenied as e:
            raise e
        except Exception as e:
            from django.http import Http404
            if isinstance(e, Http404):
                raise e
            
            logger.exception("Unexpected error creating SPE")
            return Response(
                {'error': "Internal server error while creating the SPOT envelope."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    

    
    def _validate_spe(self, spe_db):
        """Validate SPE via Pydantic schemas."""
        ctx = _normalize_shipment_context(spe_db.shipment_context_json)
        if not ctx.get("payment_term") and getattr(spe_db, "quote", None) and getattr(spe_db.quote, "payment_term", None):
            ctx["payment_term"] = str(spe_db.quote.payment_term).upper()
        resolved_missing_components = _resolve_missing_components_for_context(ctx)
        charges = [
            SPEChargeLine(
                code=cl.code,
                description=cl.description,
                amount=float(cl.amount),
                currency=cl.currency,
                unit=cl.unit,
                bucket=cl.bucket,
                is_primary_cost=cl.is_primary_cost,
                conditional=cl.conditional,
                source_reference=cl.source_reference,
                entered_by_user_id=str(cl.entered_by_id) if cl.entered_by_id else "",
                entered_at=cl.entered_at,
                min_charge=float(cl.min_charge) if cl.min_charge is not None else None,
                note=cl.note,
                exclude_from_totals=cl.exclude_from_totals,
                percentage_basis=cl.percentage_basis,
                calculation_type=cl.calculation_type,
                unit_type=cl.unit_type,
                rate=float(cl.rate) if cl.rate is not None else None,
                min_amount=float(cl.min_amount) if cl.min_amount is not None else None,
                max_amount=float(cl.max_amount) if cl.max_amount is not None else None,
                percent=float(cl.percent) if cl.percent is not None else None,
                percent_basis=cl.percent_basis,
                rule_meta=cl.rule_meta or {},
            )
            for cl in spe_db.charge_lines.all()
        ]
        
        # This will raise ValueError if invalid
        SpotPricingEnvelope(
            id=str(spe_db.id),
            status=SPEStatus(spe_db.status),
            shipment=SPEShipmentContext(
                origin_country=ctx.get('origin_country', 'OTHER'),
                destination_country=ctx.get('destination_country', 'OTHER'),
                origin_code=ctx.get('origin_code', 'XXX'),
                destination_code=ctx.get('destination_code', 'XXX'),
                commodity=ctx.get('commodity', 'GCR'),
                total_weight_kg=float(ctx.get('total_weight_kg') if ctx.get('total_weight_kg') is not None else 1.0),
                pieces=int(ctx.get('pieces') if ctx.get('pieces') is not None else 1),
                service_scope=str(ctx.get('service_scope', 'p2p')).lower(),
                payment_term=(str(ctx.get('payment_term')).lower() if ctx.get('payment_term') else None),
                missing_components=resolved_missing_components,
            ),
            charges=charges,
            conditions=SPEConditions(**spe_db.conditions_json) if spe_db.conditions_json else SPEConditions(),
            spot_trigger_reason_code=spe_db.spot_trigger_reason_code,
            spot_trigger_reason_text=spe_db.spot_trigger_reason_text,
            created_by_user_id=str(spe_db.created_by_id) if spe_db.created_by_id else "",
            created_at=spe_db.created_at,
            expires_at=spe_db.expires_at,
        )


class SpotEnvelopeDetailAPIView(APIView):
    """
    GET /api/v3/spot/envelopes/<id>/
    
    Get SPE details.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, envelope_id):
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            _spe_queryset(),
        )
        
        serializer = SpotPricingEnvelopeSerializer(spe_db)
        return Response(serializer.data)
    
    @transaction.atomic
    def patch(self, request, envelope_id):
        """Update DRAFT SPE with new charges or conditions."""
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot update SPE in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        data = request.data
        now = timezone.now()

        try:
            if 'conditions' in data:
                spe_db.conditions_json = data['conditions']

            if 'charges' in data:
                from decimal import Decimal, InvalidOperation

                def _to_decimal(val):
                    if val is None or val == "":
                        return None
                    try:
                        return Decimal(str(val))
                    except (InvalidOperation, ValueError):
                        return None

                existing_lines = list(spe_db.charge_lines.all())
                normalized_charges = []

                for charge in data['charges']:
                    amount_val = _to_decimal(charge.get('amount'))
                    if amount_val is None or amount_val <= 0:
                        logger.warning(
                            "Skipping non-positive SPE charge on PATCH: spe=%s code=%s amount=%s",
                            spe_db.id,
                            charge.get('code'),
                            charge.get('amount'),
                        )
                        continue

                    min_charge_val = _to_decimal(charge.get('min_charge'))
                    rate_val = _to_decimal(charge.get('rate'))
                    min_amount_val = _to_decimal(charge.get('min_amount'))
                    max_amount_val = _to_decimal(charge.get('max_amount'))
                    percent_val = _to_decimal(charge.get('percent'))

                    unit_val = charge['unit']
                    if unit_val == 'min_or_per_kg':
                        unit_val = 'per_kg'
                    elif unit_val == 'flat':
                        unit_val = 'flat'

                    normalized_charge = {
                        **charge,
                        'amount': amount_val,
                        'unit': unit_val,
                        'min_charge': min_charge_val,
                        'rate': rate_val,
                        'min_amount': min_amount_val,
                        'max_amount': max_amount_val,
                        'percent': percent_val,
                    }
                    normalized_charges.append(normalized_charge)

                _reconcile_spe_charge_lines(
                    spe_db=spe_db,
                    existing_lines=existing_lines,
                    incoming_charges=normalized_charges,
                    entered_by=request.user,
                    entered_at=now,
                    shipment_context=spe_db.shipment_context_json,
                )

                # Sync summaries for all batches after manual charge reconciliation
                for batch in spe_db.source_batches.all():
                    _sync_batch_analysis_summary(batch)

            spe_db.save()
            SpotEnvelopeListCreateAPIView()._validate_spe(spe_db)
        except Exception as exc:
            transaction.set_rollback(True)
            return Response(
                {'error': f"Validation Error: {str(exc)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        spe_db.refresh_from_db()
        # Capture snapshot best-effort on update
        capture_validation_snapshot(spe_db, TRIGGER_ENVELOPE_UPDATED)
        
        serializer = SpotPricingEnvelopeSerializer(spe_db)
        return Response(serializer.data)


    def delete(self, request, envelope_id):
        """Delete a DRAFT SPE."""
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot delete SPE in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        spe_db.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SpotChargeLineManualResolutionAPIView(APIView):
    """
    PATCH /api/v3/spot/envelopes/<id>/charges/<charge_line_id>/manual-resolution/

    Persist a manual ProductCode selection for exception charge lines.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, envelope_id, charge_line_id):
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            _spe_queryset(),
        )

        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot manually review charges in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge_line = get_object_or_404(spe_db.charge_lines, id=charge_line_id)

        if charge_line.normalization_status not in {
            SPEChargeLineDB.NormalizationStatus.MATCHED,
            SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
        }:
            return Response(
                {'error': 'Manual review is only available for matched, needs-review, or ambiguous charge lines.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product_code_id = _coerce_product_code_id(
            request.data.get("manual_resolved_product_code_id")
        )
        if product_code_id is None:
            product_code_id = _coerce_product_code_id(request.data.get("product_code_id"))
        if product_code_id is None:
            return Response(
                {'error': 'manual_resolved_product_code_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        manual_product_code = get_object_or_404(ProductCode, id=product_code_id)
        charge_line.manual_resolution_status = SPEChargeLineDB.ManualResolutionStatus.RESOLVED
        charge_line.manual_resolved_product_code = manual_product_code
        charge_line.manual_resolution_by = request.user
        charge_line.manual_resolution_at = timezone.now()
        charge_line.save(
            update_fields=[
                "manual_resolution_status",
                "manual_resolved_product_code",
                "manual_resolution_by",
                "manual_resolution_at",
            ]
        )

        # Record learning event for future confidence scoring
        try:
            record_manual_resolution_event(
                charge_line=charge_line,
                envelope=spe_db,
                resolved_product_code=manual_product_code,
                user=request.user,
            )
        except Exception:
            logger.exception("Failed to record manual resolution learning event")

        if charge_line.source_batch:
            _sync_batch_analysis_summary(charge_line.source_batch)

        charge_line.refresh_from_db()
        serializer = SPEChargeLineSerializer(charge_line)
        return Response(serializer.data)


class SpotChargeLineConditionalResolutionAPIView(APIView):
    """
    PATCH /api/v3/spot/envelopes/<id>/charges/<charge_line_id>/conditional-resolution/

    Resolve a conditional-charge blocker without erasing the original conditional
    audit flag. Supported actions:
    - KEEP: acknowledge the conditional charge and leave it in the quote
    - REMOVE: delete the charge line from the draft SPE
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, envelope_id, charge_line_id):
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            _spe_queryset(),
        )

        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot review conditional charges in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge_line = get_object_or_404(spe_db.charge_lines, id=charge_line_id)
        if not charge_line.conditional:
            return Response(
                {'error': 'Conditional review is only available for conditional charge lines.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = str(request.data.get("action") or "").strip().upper()
        if action not in ("KEEP", "REMOVE"):
            return Response(
                {'error': "action must be KEEP or REMOVE."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Record learning event BEFORE potential delete (REMOVE deletes the line)
        try:
            record_conditional_resolution_event(
                charge_line=charge_line,
                envelope=spe_db,
                action=action,
                user=request.user,
            )
        except Exception:
            logger.exception("Failed to record conditional resolution learning event")

        if action == "KEEP":
            charge_line.conditional_acknowledged = True
            charge_line.conditional_acknowledged_by = request.user
            charge_line.conditional_acknowledged_at = timezone.now()
            charge_line.save(
                update_fields=[
                    "conditional_acknowledged",
                    "conditional_acknowledged_by",
                    "conditional_acknowledged_at",
                ]
            )
            if charge_line.source_batch:
                _sync_batch_analysis_summary(charge_line.source_batch)
        elif action == "REMOVE":
            batch = charge_line.source_batch
            charge_line.delete()
            if batch:
                _sync_batch_analysis_summary(batch)

        spe_db.refresh_from_db()
        serializer = SpotPricingEnvelopeSerializer(spe_db)
        return Response(serializer.data)


class SpotEnvelopeAcknowledgeAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/acknowledge/
    
    Add Sales acknowledgement to SPE.
    """
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, envelope_id):
        spe_db = _get_spe_or_404(request.user, envelope_id)
        
        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot acknowledge SPE in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if hasattr(spe_db, 'acknowledgement') and spe_db.acknowledgement:
            return Response(
                {'error': 'SPE already acknowledged'},
                status=status.HTTP_400_BAD_REQUEST
            )

        intake_safety_error = _intake_safety_error_response(spe_db)
        if intake_safety_error is not None:
            return intake_safety_error

        exception_review_error = _exception_review_error_response(spe_db)
        if exception_review_error is not None:
            return exception_review_error
        
        temp_ack = SPEAcknowledgement(
            acknowledged_by_user_id=str(request.user.id),
            acknowledged_at=timezone.now(),
            statement=SPEAcknowledgementDB.ACKNOWLEDGEMENT_STATEMENT,
        )

        try:
            status_override = 'ready'
            spe = _build_spe_from_db(
                spe_db,
                status_override=status_override,
                acknowledgement_override=temp_ack,
            )
        except ValueError as e:
            return Response(
                {'error': f'Validation Error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if spe.is_expired:
            return Response(
                {'error': 'SPE has expired and cannot be acknowledged.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Always validate for pricing (no manager approval required)
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        if not is_valid:
            return Response(
                {'error': error},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create acknowledgement
        SPEAcknowledgementDB.objects.create(
            envelope=spe_db,
            acknowledged_by=request.user,
            acknowledged_at=temp_ack.acknowledged_at,
            statement=temp_ack.statement,
        )

        # Always transition to ready - no manager approval required
        spe_db.status = 'ready'
        spe_db.save()
        
        spe_db.refresh_from_db()
        # Capture snapshot best-effort on sales acknowledgment
        capture_validation_snapshot(spe_db, TRIGGER_SALES_ACKNOWLEDGED)
        
        logger.info("SPE %s acknowledged by %s", spe_db.id, request.user.username)
        
        return Response({
            'success': True,
            'status': spe_db.status,
        })



class SpotEnvelopeComputeAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/compute/
    
    Compute quote using SPE charges via pricing_v4 adapter.
    
    Request:
        { "quote_request": { ... standard quote fields ... } }
    
    Response:
        { ... quote result with pricing_mode: "SPOT" ... }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        from pricing_v4.adapter import PricingServiceV4Adapter
        from core.dataclasses import QuoteInput, ShipmentDetails, Piece, LocationRef
        from core.models import Location
        
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            _spe_queryset(),
        )

        intake_safety_error = _intake_safety_error_response(spe_db)
        if intake_safety_error is not None:
            return intake_safety_error

        exception_review_error = _exception_review_error_response(spe_db)
        if exception_review_error is not None:
            return exception_review_error

        # Build Pydantic SPE for validation after review blockers have been reported.
        try:
            spe = _build_spe_from_db(spe_db)
        except ValueError as e:
            return Response(
                {'error': f'Invalid SPE: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate SPE is ready for pricing
        from quotes.spot_services import SpotEnvelopeService
        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        
        if not is_valid:
            return Response(
                {'is_complete': False, 'reason': error},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Build quote input from request
        quote_data = request.data.get('quote_request', {})
        ctx = _normalize_shipment_context(spe_db.shipment_context_json)
        
        try:
            origin_loc = Location.objects.get(code=ctx.get('origin_code'))
            dest_loc = Location.objects.get(code=ctx.get('destination_code'))
        except Location.DoesNotExist as e:
            return Response(
                {'error': f'Location not found: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine shipment type
        origin_country, dest_country = _resolve_country_pair(
            ctx.get('origin_country'),
            ctx.get('destination_country'),
            origin_code=ctx.get('origin_code'),
            destination_code=ctx.get('destination_code'),
        )
        shipment_type = _infer_shipment_type(origin_country, dest_country)
        
        from datetime import date
        
        origin_ref = LocationRef(
            id=origin_loc.id,
            code=origin_loc.code,
            name=origin_loc.name,
            country_code=origin_loc.country.code if origin_loc.country else None,
            currency_code=origin_loc.country.currency.code if origin_loc.country and origin_loc.country.currency else None,
        )
        dest_ref = LocationRef(
            id=dest_loc.id,
            code=dest_loc.code,
            name=dest_loc.name,
            country_code=dest_loc.country.code if dest_loc.country else None,
            currency_code=dest_loc.country.currency.code if dest_loc.country and dest_loc.country.currency else None,
        )

        shipment = ShipmentDetails(
            mode='AIR',
            shipment_type=shipment_type,
            incoterm=quote_data.get('incoterm', 'DAP'),
            payment_term=quote_data.get('payment_term', 'PREPAID'),
            commodity_code=ctx.get('commodity') or 'GCR',
            is_dangerous_goods=ctx.get('commodity') == 'DG',
            pieces=[
                Piece(
                    pieces=ctx.get('pieces', 1),
                    length_cm=0,
                    width_cm=0,
                    height_cm=0,
                    gross_weight_kg=ctx.get('total_weight_kg', 0) / max(ctx.get('pieces', 1), 1),
                )
            ],
            service_scope=quote_data.get('service_scope', 'D2D'),
            origin_location=origin_ref,
            destination_location=dest_ref,
        )

        resolved_output_currency = _resolve_output_currency_for_shipment(
            shipment_type=shipment.shipment_type,
            payment_term=shipment.payment_term,
            origin_location=origin_ref,
            destination_location=dest_ref,
        )
        
        quote_input = QuoteInput(
            customer_id=getattr(spe_db.quote, 'customer_id', None) or uuid.uuid4(),
            contact_id=getattr(spe_db.quote, 'contact_id', None) or uuid.uuid4(),
            shipment=shipment,
            quote_date=date.today(),
            output_currency=resolved_output_currency,
        )
        
        # Call adapter with spot_envelope_id
        adapter = PricingServiceV4Adapter(
            quote_input=quote_input,
            spot_envelope_id=UUID(str(spe_db.id))
        )
        
        try:
            result = adapter.calculate_charges()
        except ValueError as e:
            logger.error(f"Compute failed with ValueError: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get FX rate info for display
        fx_info = None
        if adapter.fx_snapshot:
            # Find the charge currency from SPE charges (usually the first one)
            spe_charges = list(spe_db.charge_lines.all())
            if spe_charges:
                charge_currency = spe_charges[0].currency
                if charge_currency != 'PGK':
                    fx_rates_dict = adapter._get_fx_rates_dict()
                    fx_buy_rate = adapter._get_fx_buy_rate(charge_currency, fx_rates_dict)
                    fx_info = {
                        'source_currency': charge_currency,
                        'target_currency': 'PGK',
                        'rate': str(fx_buy_rate),
                        'as_of': adapter.fx_snapshot.as_of_timestamp.isoformat() if adapter.fx_snapshot.as_of_timestamp else None,
                    }
        
        from quotes.completeness import evaluate_from_lines

        resolved_scope = quote_data.get('service_scope') or ctx.get('service_scope') or 'D2D'
        coverage = evaluate_from_lines(
            result.lines,
            shipment_type,
            resolved_scope
        )

        return Response({
            'is_complete': coverage.is_complete,
            'has_missing_rates': not coverage.is_complete,
            'missing_components': coverage.missing_required,
            'completeness_notes': coverage.notes,
            'pricing_mode': adapter.get_pricing_mode(),
            'spe_id': str(spe_db.id),
            'fx_info': fx_info,
            'lines': [
                {
                    'code': line.service_component_code,
                    'description': line.service_component_desc,
                    'cost_pgk': str(line.cost_pgk),
                    'sell_pgk': str(line.sell_pgk),
                    'sell_pgk_incl_gst': str(line.sell_pgk_incl_gst),
                    'leg': line.leg,
                    'source': line.cost_source,
                    'is_informational': getattr(line, 'is_informational', False),
                    'bucket': line.bucket,
                }
                for line in result.lines
            ],
            'totals': {
                'total_cost_pgk': str(result.totals.total_cost_pgk),
                'total_sell_pgk': str(result.totals.total_sell_pgk),
                'total_sell_pgk_incl_gst': str(result.totals.total_sell_pgk_incl_gst),
            },
        })
    
class SpotReplyAnalysisAPIView(APIView):
    """
    POST /api/v3/spot/analyze-reply/
    
    Analyze agent rate reply text and return assertions.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def post(self, request):
        try:
            text = request.data.get('text', '')
            pdf_file = request.FILES.get('file')
            spe_id = request.data.get('spe_id')
            source_batch_id = request.data.get('source_batch_id')
            source_kind = _normalize_source_kind(request.data.get('source_kind'))
            target_bucket = _normalize_target_bucket(request.data.get('target_bucket'))
            source_type = _normalize_source_type(request.data.get('source_type'), pdf_file=pdf_file)
            manual_assertions = request.data.get('assertions', [])
            use_ai = request.data.get('use_ai', True)
            pdf_warnings = []
            shipment_context = None

            if isinstance(manual_assertions, str):
                try:
                    manual_assertions = json.loads(manual_assertions)
                except json.JSONDecodeError:
                    manual_assertions = []

            if isinstance(use_ai, str):
                use_ai = use_ai.strip().lower() not in {"false", "0", "no", "off"}

            if spe_id:
                try:
                    spe_db = _get_spe_or_404(request.user, spe_id)
                    shipment_context = _normalize_shipment_context(spe_db.shipment_context_json)
                    if (
                        shipment_context is not None
                        and not shipment_context.get("payment_term")
                        and getattr(spe_db, "quote", None)
                        and getattr(spe_db.quote, "payment_term", None)
                    ):
                        shipment_context["payment_term"] = str(spe_db.quote.payment_term).upper()
                except (SpotPricingEnvelopeDB.DoesNotExist, ValueError):
                    pass

            if pdf_file:
                try:
                    validate_pdf_upload(pdf_file)
                except Exception as exc:
                    return Response(
                        {'error': '; '.join(getattr(exc, 'messages', [str(exc)]))},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                from quotes.ai_intake_service import extract_rate_quote_text_from_pdf

                extraction_result = extract_rate_quote_text_from_pdf(pdf_file.read(), context=shipment_context)
                if not extraction_result.success:
                    return Response(
                        {'error': extraction_result.error or 'PDF extraction failed'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                text = extraction_result.text or ''
                pdf_warnings = list(extraction_result.warnings or [])
            
            if not text:
                return Response(
                    {'error': 'Either "text" or "file" is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            if shipment_context:
                # Enrich with real names for the AI prompt
                from core.models import Airport
                orig_ap = Airport.objects.filter(iata_code=shipment_context.get('origin_code')).first()
                dest_ap = Airport.objects.filter(iata_code=shipment_context.get('destination_code')).first()
                if orig_ap: shipment_context['origin'] = orig_ap.city.name
                if dest_ap: shipment_context['destination'] = dest_ap.city.name
                
            # Calculate direction and availability to guide the analyst
            direction = 'IMPORT'
            availability = None
            if shipment_context:
                origin_country, destination_country = _resolve_country_pair(
                    shipment_context.get('origin_country', ''),
                    shipment_context.get('destination_country', ''),
                    origin_code=shipment_context.get('origin_code'),
                    destination_code=shipment_context.get('destination_code'),
                )
                direction = _infer_shipment_type(origin_country, destination_country)
                
                from quotes.spot_services import RateAvailabilityService
                component_outcomes = RateAvailabilityService.get_component_outcomes(
                    origin_airport=shipment_context.get('origin_code', ''),
                    destination_airport=shipment_context.get('destination_code', ''),
                    direction=direction,
                    service_scope=shipment_context.get('service_scope', 'P2P'),
                    payment_term=shipment_context.get('payment_term'),
                )
                availability = {
                    component: outcome.get('status') in {'covered_exact', 'covered_fallback'}
                    for component, outcome in component_outcomes.items()
                }
                
                # Enrich context with missing status to guide AI
                if availability:
                    shipment_context['missing_components'] = [k for k, v in availability.items() if not v]
                    shipment_context['component_outcomes'] = component_outcomes

            if use_ai and not manual_assertions:
                # If AI is requested and no manual edits provided, do full AI analysis
                result = ReplyAnalysisService.analyze_with_ai(
                    raw_text=text,
                    shipment_context=shipment_context,
                    availability=availability
                )
                logger.info(
                    "analyze-reply AI result: assertions=%d, warnings=%d, can_proceed=%s",
                    len(result.assertions), len(result.warnings), result.summary.can_proceed,
                )
                if not result.assertions:
                    logger.warning("analyze-reply returned 0 assertions for text of length %d", len(text))
            else:
                # Manual edit flow or fallback
                result = ReplyAnalysisService.analyze_manual(
                    raw_text=text,
                    assertions=manual_assertions
                )

            if pdf_warnings:
                result.warnings.extend(pdf_warnings)

            # Auto-populate SPE with AI-extracted charges (draft only)
            if use_ai and not manual_assertions and spe_id and shipment_context:
                try:
                    spe_db = _get_spe_or_404(request.user, spe_id)
                except (SpotPricingEnvelopeDB.DoesNotExist, ValueError):
                    spe_db = None

                if spe_db and spe_db.status == 'draft':
                    from decimal import Decimal, InvalidOperation

                    def _to_decimal(val):
                        if val is None or val == "":
                            return None
                        try:
                            return Decimal(str(val))
                        except (InvalidOperation, ValueError):
                            return None

                    source_reference = str(
                        request.data.get('source_reference')
                        or (pdf_file.name if pdf_file else "Agent reply")
                    )
                    source_label = str(
                        request.data.get('label')
                        or _default_source_label(source_kind, target_bucket)
                    )
                    auto_charges = ReplyAnalysisService.build_spe_charges_from_analysis(
                        result,
                        source_reference=source_reference,
                        shipment_context=shipment_context,
                    )
                    safety_signals = getattr(result, "safety_signals", None)
                    if hasattr(safety_signals, "model_dump"):
                        safety_signals = safety_signals.model_dump()
                    elif not isinstance(safety_signals, dict):
                        safety_signals = {}
                    if not safety_signals.get("imported_charge_count"):
                        safety_signals["imported_charge_count"] = len(auto_charges)
                    if not safety_signals.get("conditional_charge_count"):
                        safety_signals["conditional_charge_count"] = sum(
                            1 for charge in auto_charges if charge.get("conditional")
                        )
                    if "pdf_fallback_used" not in safety_signals:
                        safety_signals["pdf_fallback_used"] = any(
                            "pdf extraction fallback" in str(w).lower() for w in (result.warnings or [])
                        )
                    detected_currencies = sorted(
                        {
                            str(charge.get("currency") or "").upper()
                            for charge in auto_charges
                            if str(charge.get("currency") or "").strip()
                        }
                    )
                    batch = _get_or_create_source_batch(
                        spe_db=spe_db,
                        request=request,
                        source_batch_id=source_batch_id,
                        source_kind=source_kind,
                        source_type=source_type,
                        target_bucket=target_bucket,
                        label=source_label,
                        source_reference=source_reference,
                        raw_text=text,
                        file_name=pdf_file.name if pdf_file else "",
                        file_content_type=getattr(pdf_file, "content_type", "") if pdf_file else "",
                        analysis_summary_json=build_source_analysis_summary_payload(
                            warnings=result.warnings or [],
                            assertion_count=len(result.assertions or []),
                            can_proceed=getattr(result.summary, "can_proceed", False),
                            ai_used=True,
                            detected_currencies=detected_currencies,
                            safety_signals=safety_signals,
                        ),
                    )

                    now = timezone.now()
                    existing_batch_lines = list(batch.charge_lines.all())
                    normalized_auto_charges = []

                    if auto_charges:
                        for charge in auto_charges:
                            amount_val = _to_decimal(charge.get("amount"))
                            if amount_val is None or amount_val <= 0:
                                continue

                            min_charge_val = _to_decimal(charge.get("min_charge"))
                            normalized_auto_charges.append(
                                {
                                    **charge,
                                    "amount": amount_val,
                                    "min_charge": min_charge_val,
                                    "rate": _to_decimal(charge.get("rate")),
                                    "min_amount": _to_decimal(charge.get("min_amount")),
                                    "max_amount": _to_decimal(charge.get("max_amount")),
                                    "percent": _to_decimal(charge.get("percent")),
                                }
                            )

                    existing_matching_lines = list(existing_batch_lines)
                    if normalized_auto_charges:
                        batch_line_ids = {line.id for line in existing_batch_lines}
                        incoming_source_signatures = {
                            _incoming_charge_source_semantic_signature(charge)
                            for charge in normalized_auto_charges
                        }
                        if incoming_source_signatures:
                            stale_reclassification_candidates = [
                                line
                                for line in spe_db.charge_lines.select_related("source_batch").all()
                                if line.id not in batch_line_ids
                                and (
                                    line.source_batch is None
                                    or line.source_batch.source_kind == source_kind
                                )
                                and _existing_line_source_semantic_signature(line) in incoming_source_signatures
                            ]
                            existing_matching_lines.extend(stale_reclassification_candidates)

                    _reconcile_spe_charge_lines(
                        spe_db=spe_db,
                        existing_lines=existing_batch_lines,
                        existing_lines_for_matching=existing_matching_lines,
                        incoming_charges=normalized_auto_charges,
                        entered_by=request.user,
                        entered_at=now,
                        shipment_context=shipment_context,
                        source_batch=batch,
                    )

                    # Update conditional flag in SPE conditions
                    if any(c.get("conditional") for c in auto_charges) or spe_db.charge_lines.filter(conditional=True).exists():
                        conditions = spe_db.conditions_json or {}
                        conditions["conditional_charges_present"] = True
                        spe_db.conditions_json = conditions
                        spe_db.save(update_fields=["conditions_json"])

                    result_payload = result.model_dump()
                    result_payload["source_batch_id"] = str(batch.id)
                    result_payload["source_batch_label"] = batch.label
                    return Response(result_payload)
            
            return Response(result.model_dump())
        except ValueError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )

# Add this to the end of spot_views.py

class SpotEnvelopeCreateQuoteAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/create-quote/
    
    Convert SPE to a formal Quote (v3).
    Creates Quote, QuoteVersion, QuoteLines, and QuoteTotals.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, envelope_id):
        from pricing_v4.adapter import PricingServiceV4Adapter
        from core.dataclasses import QuoteInput, ShipmentDetails, Piece, LocationRef
        from core.models import Location
        from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal, ServiceComponent
        from parties.models import Company, Contact
        from crm.services import create_auto_quote_opportunity_interaction, resolve_quote_opportunity
        from uuid import UUID
        from datetime import date
        
        spe_db = _get_spe_or_404(
            request.user, 
            envelope_id,
            _spe_queryset(),
        )
        
        # --- 1. Re-run Computation (Same as ComputeView) ---
        # Note: Ideally this setup logic should be shared, but duplicating for safety now.

        intake_safety_error = _intake_safety_error_response(spe_db)
        if intake_safety_error is not None:
            return intake_safety_error

        exception_review_error = _exception_review_error_response(spe_db)
        if exception_review_error is not None:
            return exception_review_error

        try:
            spe = _build_spe_from_db(spe_db)
        except ValueError as e:
            return Response({'error': f'Invalid SPE: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        is_valid, error = SpotEnvelopeService.validate_for_pricing(spe)
        if not is_valid:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
            
        quote_data = request.data.get('quote_request', {})
        ctx = _normalize_shipment_context(spe_db.shipment_context_json)
        
        try:
            origin_loc = Location.objects.get(code=ctx.get('origin_code'))
            dest_loc = Location.objects.get(code=ctx.get('destination_code'))
        except Location.DoesNotExist as e:
            return Response({'error': f'Location not found: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
            
        origin_country, dest_country = _resolve_country_pair(
            ctx.get('origin_country'),
            ctx.get('destination_country'),
            origin_code=ctx.get('origin_code'),
            destination_code=ctx.get('destination_code'),
        )
        shipment_type = _infer_shipment_type(origin_country, dest_country)
            
        origin_ref = LocationRef(
            id=origin_loc.id, code=origin_loc.code, name=origin_loc.name,
            country_code=origin_loc.country.code if origin_loc.country else None,
            currency_code=origin_loc.country.currency.code if origin_loc.country and origin_loc.country.currency else None,
        )
        dest_ref = LocationRef(
            id=dest_loc.id, code=dest_loc.code, name=dest_loc.name,
            country_code=dest_loc.country.code if dest_loc.country else None,
            currency_code=dest_loc.country.currency.code if dest_loc.country and dest_loc.country.currency else None,
        )

        shipment = ShipmentDetails(
            mode='AIR',
            shipment_type=shipment_type,
            incoterm=quote_data.get('incoterm', 'DAP'),
            payment_term=quote_data.get('payment_term', 'PREPAID'),
            commodity_code=ctx.get('commodity') or 'GCR',
            is_dangerous_goods=ctx.get('commodity') == 'DG',
            pieces=[Piece(
                pieces=ctx.get('pieces', 1),
                length_cm=0, width_cm=0, height_cm=0,
                gross_weight_kg=ctx.get('total_weight_kg', 0) / max(ctx.get('pieces', 1), 1),
            )],
            service_scope=quote_data.get('service_scope', 'D2D'),
            origin_location=origin_ref,
            destination_location=dest_ref,
        )

        resolved_output_currency = _resolve_output_currency_for_shipment(
            shipment_type=shipment.shipment_type,
            payment_term=shipment.payment_term,
            origin_location=origin_ref,
            destination_location=dest_ref,
        )
        
        # Ensure customer/contact logic
        cust_id = None
        cont_id = None
        requested_contact_id = (
            request.data.get('contact_id')
            or quote_data.get('contact_id')
        )
        
        if spe_db.quote:
            cust_id = spe_db.quote.customer_id
            cont_id = spe_db.quote.contact_id

        if not cust_id:
             req_cust = (
                 request.data.get('customer_id')
                 or quote_data.get('customer_id')
             )
             if req_cust:
                 try:
                     cust_id = UUID(str(req_cust))
                 except (TypeError, ValueError):
                     return Response(
                         {'error': f'Invalid customer_id: {req_cust}'},
                         status=status.HTTP_400_BAD_REQUEST
                     )

        # Backward compatibility for older envelopes without explicit customer_id:
        # resolve by customer_name from shipment context if available.
        if not cust_id:
            customer_name = str(ctx.get('customer_name') or '').strip()
            if customer_name:
                cust = Company.objects.filter(name__iexact=customer_name).first()
                if not cust:
                    cust = Company.objects.filter(name__icontains=customer_name).first()
                if cust:
                    cust_id = cust.id
        
        if not cust_id:
            return Response(
                {'error': 'Customer is required to create quote. Provide customer_id or link SPE to an existing quote.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if cont_id and not Contact.objects.filter(id=cont_id, company_id=cust_id).exists():
            cont_id = None

        if requested_contact_id:
            try:
                candidate_contact_id = UUID(str(requested_contact_id))
            except (TypeError, ValueError):
                return Response(
                    {'error': f'Invalid contact_id: {requested_contact_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not Contact.objects.filter(id=candidate_contact_id, company_id=cust_id).exists():
                return Response(
                    {'error': 'Selected contact does not belong to the selected customer.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cont_id = candidate_contact_id

        # Create QuoteInput
        # Note: If QuoteInput enforces contact_id is not None, we might need to fake it if cont_id is None.
        # But generally, for Spot, we just need basic input.
        # Check if QuoteInput accepts None. If not, we use cust_id as placeholder for logic ONLY, but NOT for DB.
        
        qi_contact_id = cont_id if cont_id else cust_id # Placeholder for computation if needed
        
        quote_input = QuoteInput(
            customer_id=cust_id,
            contact_id=qi_contact_id, 
            shipment=shipment,
            quote_date=date.today(),
            output_currency=resolved_output_currency,
        )
        quote_request_payload = quote_input.model_dump(mode='json')
        quote_request_payload['contact_id'] = str(cont_id) if cont_id else None
        quote_request_payload['incoterm'] = shipment.incoterm
        quote_request_payload['payment_term'] = shipment.payment_term
        quote_request_payload['service_scope'] = shipment.service_scope
        
        adapter = PricingServiceV4Adapter(quote_input=quote_input, spot_envelope_id=UUID(str(spe_db.id)))
        
        try:
            result = adapter.calculate_charges()
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        from quotes.completeness import evaluate_from_lines
        resolved_scope = quote_data.get('service_scope') or ctx.get('service_scope') or 'D2D'
        coverage = evaluate_from_lines(
            result.lines,
            shipment_type,
            resolved_scope
        )
        if not coverage.is_complete:
            return Response(
                {
                    'error': coverage.notes or 'Missing required components for SPOT coverage.',
                    'has_missing_rates': True,
                    'missing_components': coverage.missing_required,
                    'completeness_notes': coverage.notes,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        customer = get_object_or_404(Company, id=cust_id)
        raw_opportunity_id = (
            request.data.get('opportunity_id')
            or quote_data.get('opportunity_id')
        )
        if raw_opportunity_id:
            try:
                opportunity_id = UUID(str(raw_opportunity_id))
            except (TypeError, ValueError):
                return Response(
                    {'error': f'Invalid opportunity_id: {raw_opportunity_id}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            opportunity_id = None

        opportunity, opportunity_was_auto_created = resolve_quote_opportunity(
            customer=customer,
            opportunity_id=opportunity_id,
            existing_quote=spe_db.quote,
            mode='AIR',
            shipment_type=shipment_type,
            service_scope=shipment.service_scope,
            origin_location=origin_loc,
            destination_location=dest_loc,
            actor=request.user,
            quote_status=Quote.Status.DRAFT,
            persist=True,
        )

        # --- 2. Create/Update Quote ---
        if spe_db.quote:
            quote = spe_db.quote
            quote.status = Quote.Status.DRAFT
            quote.contact_id = cont_id
            quote.output_currency = quote_input.output_currency
            quote.incoterm = shipment.incoterm
            quote.payment_term = shipment.payment_term
            quote.service_scope = shipment.service_scope
            quote.shipment_type = shipment_type
            quote.opportunity = opportunity
            quote.origin_location = origin_loc
            quote.destination_location = dest_loc
            quote.request_details_json = quote_request_payload
            quote.save(update_fields=[
                'status',
                'contact_id',
                'output_currency',
                'incoterm',
                'payment_term',
                'service_scope',
                'shipment_type',
                'opportunity',
                'origin_location',
                'destination_location',
                'request_details_json',
            ])
        else:
            quote = Quote.objects.create(
                customer_id=cust_id,
                contact_id=cont_id, # FIX: Pass actual contact ID (can be None)
                origin_location=origin_loc,
                destination_location=dest_loc,
                shipment_type=shipment_type,
                mode='AIR',
                opportunity=opportunity,
                incoterm=shipment.incoterm,
                payment_term=shipment.payment_term,
                service_scope=shipment.service_scope,
                output_currency=quote_input.output_currency,
                is_dangerous_goods=shipment.is_dangerous_goods,
                created_by=request.user,
                organization=getattr(request.user, 'organization', None),
                status=Quote.Status.DRAFT,
                request_details_json=quote_request_payload,
            )
            spe_db.quote = quote
            spe_db.save()

        if opportunity_was_auto_created:
            create_auto_quote_opportunity_interaction(opportunity, quote, request.user)

        # --- 3. Create Version ---
        # Determine version number
        last_version = quote.versions.order_by('-version_number').first()
        new_v_num = (last_version.version_number + 1) if last_version else 1
        
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=new_v_num,
            status=Quote.Status.DRAFT,
            created_by=request.user,
            payload_json=quote_request_payload,
            reason="Created from SPOT Envelope"
        )
        
        # --- 4. Save Lines ---
        
        component_map = {
            component.id: component
            for component in ServiceComponent.objects.filter(
                id__in=[line.service_component_id for line in result.lines if getattr(line, "service_component_id", None)]
            ).select_related("service_code")
        }

        for line_data in result.lines:
            # Resolve Component ID
            sc = component_map.get(line_data.service_component_id)
            canonical_metadata = build_persisted_line_item_metadata(
                raw_cost_source=line_data.cost_source,
                service_component=sc,
                engine_version="V4",
                product_code=getattr(line_data, "product_code", None) or getattr(line_data, "service_component_code", None),
                component=getattr(line_data, "component", None),
                basis=getattr(line_data, "basis", None),
                rule_family=getattr(line_data, "rule_family", None),
                service_family=getattr(line_data, "service_family", None),
                unit_type=getattr(line_data, "unit_type", None),
                quantity=getattr(line_data, "quantity", None),
                rate=getattr(line_data, "rate", None),
                sell_amount=line_data.sell_fcy if (line_data.sell_fcy_currency or "PGK").upper() != "PGK" else line_data.sell_pgk,
                is_rate_missing=bool(line_data.is_rate_missing),
                leg=getattr(line_data, "leg", None),
                calculation_notes=getattr(line_data, "calculation_notes", None),
                stored_is_spot_sourced=getattr(line_data, "is_spot_sourced", None),
                stored_is_manual_override=getattr(line_data, "is_manual_override", None),
                canonical_cost_source=getattr(line_data, "canonical_cost_source", None),
                rate_source=getattr(line_data, "rate_source", None),
            )
            
            QuoteLine.objects.create(
                quote_version=version,
                service_component=sc,
                description=line_data.service_component_desc,
                cost_pgk=line_data.cost_pgk,
                cost_fcy=line_data.cost_fcy,
                cost_fcy_currency=line_data.cost_fcy_currency,
                sell_pgk=line_data.sell_pgk,
                sell_pgk_incl_gst=line_data.sell_pgk_incl_gst,
                sell_fcy=line_data.sell_fcy,
                sell_fcy_incl_gst=line_data.sell_fcy_incl_gst,
                sell_fcy_currency=line_data.sell_fcy_currency,
                exchange_rate=line_data.exchange_rate,
                cost_source=line_data.cost_source,
                cost_source_description=line_data.cost_source_description,
                is_rate_missing=line_data.is_rate_missing,
                is_informational=getattr(line_data, 'is_informational', False),
                leg=getattr(line_data, 'leg', None),
                bucket=getattr(line_data, 'bucket', None),
                gst_category=getattr(line_data, 'gst_category', None),
                gst_rate=getattr(line_data, 'gst_rate', 0),
                gst_amount=getattr(line_data, 'gst_amount', 0),
                conditional=getattr(line_data, 'conditional', False),
                product_code=canonical_metadata["product_code"] or None,
                component=canonical_metadata["component"],
                basis=canonical_metadata["basis"],
                rule_family=canonical_metadata["rule_family"],
                service_family=canonical_metadata["service_family"],
                unit_type=canonical_metadata["unit_type"],
                rate=canonical_metadata["rate"],
                rate_source=canonical_metadata["rate_source"],
                canonical_cost_source=canonical_metadata["canonical_cost_source"],
                is_spot_sourced=canonical_metadata["is_spot_sourced"],
                is_manual_override=canonical_metadata["is_manual_override"],
                calculation_notes=canonical_metadata["calculation_notes"],
            )

        # --- 5. Save Totals ---
        total_metadata = build_persisted_quote_total_metadata(result.totals)
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=result.totals.total_cost_pgk,
            total_sell_pgk=result.totals.total_sell_pgk,
            total_sell_pgk_incl_gst=result.totals.total_sell_pgk_incl_gst,
            total_sell_fcy=result.totals.total_sell_fcy,
            total_sell_fcy_incl_gst=result.totals.total_sell_fcy_incl_gst,
            total_sell_fcy_currency=result.totals.total_sell_fcy_currency,
            has_missing_rates=result.totals.has_missing_rates,
            notes=result.totals.notes,
            service_notes=total_metadata["service_notes"],
            customer_notes=total_metadata["customer_notes"],
            internal_notes=total_metadata["internal_notes"],
            warnings_json=total_metadata["warnings_json"],
            audit_metadata_json=total_metadata["audit_metadata_json"],
        )
        
        return Response({
            'success': True,
            'quote_id': str(quote.id),
            'quote_number': quote.quote_number
        })


class SpotSourceBatchReviewAPIView(APIView):
    """
    POST /api/v3/spot/envelopes/<id>/sources/<source_batch_id>/review/

    Record reviewer confirmation for an imported source batch.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, envelope_id, source_batch_id):
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            _spe_queryset(),
        )

        if spe_db.status != 'draft':
            return Response(
                {'error': f"Cannot review source batches in status '{spe_db.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        batch = get_object_or_404(spe_db.source_batches, id=source_batch_id)
        reviewed_safe_to_quote = bool(request.data.get("reviewed_safe_to_quote", False))
        review_note = str(request.data.get("review_note") or "").strip() or None
        summary = normalize_source_analysis_summary(batch.analysis_summary_json)

        if reviewed_safe_to_quote and summary["requires_review_note"] and not review_note:
            return Response(
                {
                    "error": "High-risk import findings require a reviewer note before this source can be approved.",
                    "source_batch_id": str(batch.id),
                    "blocking_reasons": summary["blocking_reasons"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        batch.analysis_summary_json = mark_source_analysis_review(
            batch.analysis_summary_json,
            reviewed_safe_to_quote=reviewed_safe_to_quote,
            reviewed_by_user_id=str(request.user.id),
            reviewed_at=timezone.now().isoformat(),
            review_note=review_note,
        )
        batch.save(update_fields=["analysis_summary_json", "updated_at"])

        spe_db.refresh_from_db()
        serializer = SpotPricingEnvelopeSerializer(spe_db)
        return Response(serializer.data)


class SpotTemplateValidationFindingReviewedAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, envelope_id):
        spe_db = _get_spe_or_404(
            request.user,
            envelope_id,
            SpotPricingEnvelopeDB.objects.all(),
        )

        payload = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        payload['envelope'] = spe_db.id

        serializer = SpotTemplateValidationReviewSerializer(
            data=payload,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SpotTemplateValidationReviewMetricsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _user_is_manager_or_admin(request.user):
            raise PermissionDenied("Only managers and admins can view validation metrics.")

        from django.utils.dateparse import parse_date
        import datetime
        from django.utils import timezone
        
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        now = timezone.now()

        if start_date_str:
            try:
                start_date = parse_date(start_date_str)
                if not start_date:
                    raise ValueError
                start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
            except ValueError:
                return Response({"error": "Invalid start_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            start_dt = now - datetime.timedelta(days=30)

        if end_date_str:
            try:
                end_date = parse_date(end_date_str)
                if not end_date:
                    raise ValueError
                end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))
            except ValueError:
                return Response({"error": "Invalid end_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_dt = now

        if end_dt < start_dt:
            return Response({"error": "end_date cannot be before start_date."}, status=status.HTTP_400_BAD_REQUEST)

        if (end_dt - start_dt).days > 180:
            return Response({"error": "The maximum date range allowed is 180 days."}, status=status.HTTP_400_BAD_REQUEST)

        from quotes.services.spot_validation_metrics import SpotTemplateValidationMetricsService
        metrics = SpotTemplateValidationMetricsService.get_review_metrics(start_dt, end_dt)

        from quotes.serializers import SpotTemplateValidationReviewMetricsSerializer
        serializer = SpotTemplateValidationReviewMetricsSerializer(metrics)
        return Response(serializer.data)


class SpotTemplateValidationSnapshotMetricsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _user_is_manager_or_admin(request.user):
            raise PermissionDenied("Only managers and admins can view validation metrics.")

        from django.utils.dateparse import parse_date
        import datetime
        from django.utils import timezone
        
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        now = timezone.now()

        # Parse start_date
        if start_date_str:
            try:
                start_date = parse_date(start_date_str)
                if not start_date:
                    raise ValueError
                start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
            except ValueError:
                return Response({"error": "Invalid start_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            start_dt = now - datetime.timedelta(days=30)

        # Parse end_date
        if end_date_str:
            try:
                end_date = parse_date(end_date_str)
                if not end_date:
                    raise ValueError
                end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))
            except ValueError:
                return Response({"error": "Invalid end_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            end_dt = now

        if end_dt < start_dt:
            return Response({"error": "end_date cannot be before start_date."}, status=status.HTTP_400_BAD_REQUEST)

        if (end_dt - start_dt).days > 180:
            return Response({"error": "The maximum date range allowed is 180 days."}, status=status.HTTP_400_BAD_REQUEST)

        # Parse limit
        limit_str = request.query_params.get("limit", "10")
        try:
            limit = int(limit_str)
            if limit <= 0:
                raise ValueError
            # Cap at 50
            if limit > 50:
                limit = 50
        except ValueError:
            return Response({"error": "limit must be a positive integer."}, status=status.HTTP_400_BAD_REQUEST)

        # Parse template_id if provided
        template_id_str = request.query_params.get("template_id")
        template_id = None
        if template_id_str:
            try:
                template_id = int(template_id_str)
            except ValueError:
                return Response({"error": "template_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        # Gather optional filters
        filters = {
            "trigger": request.query_params.get("trigger"),
            "validation_status": request.query_params.get("validation_status"),
            "template_id": template_id,
            "finding_code": request.query_params.get("finding_code"),
            "canonical_type": request.query_params.get("canonical_type"),
        }

        # Check filter validity if values are supplied
        if filters["trigger"] and filters["trigger"] not in ["envelope_created", "envelope_updated", "sales_acknowledged"]:
            return Response({"error": "Invalid trigger filter value."}, status=status.HTTP_400_BAD_REQUEST)

        if filters["validation_status"] and filters["validation_status"] not in ["passed", "warnings", "review"]:
            return Response({"error": "Invalid validation_status filter value."}, status=status.HTTP_400_BAD_REQUEST)

        from quotes.services.spot_validation_snapshot_metrics import SpotTemplateValidationSnapshotMetricsService
        metrics = SpotTemplateValidationSnapshotMetricsService.get_snapshot_metrics(
            start_date=start_dt,
            end_date=end_dt,
            filters=filters,
            limit=limit
        )

        from quotes.serializers import SpotTemplateValidationSnapshotMetricsSerializer
        serializer = SpotTemplateValidationSnapshotMetricsSerializer(metrics)
        return Response(serializer.data)



