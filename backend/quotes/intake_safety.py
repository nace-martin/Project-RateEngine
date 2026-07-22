from __future__ import annotations

from typing import Any, Iterable
import hashlib
import re


REVIEW_STATUS_PENDING = "PENDING"
REVIEW_STATUS_APPROVED = "APPROVED"
REVIEW_STATUS_NOT_REQUIRED = "NOT_REQUIRED"
SOURCE_FINDING_STATUS_OPEN = "open"
SOURCE_FINDING_STATUS_RESOLVED = "resolved"
SOURCE_FINDING_BLOCKING_TYPES = {
    "missing_required_fields",
    "critic_missed_charges",
    "critic_hallucinations",
    "unmapped_lines",
    "no_imported_charges",
    "multiple_currencies",
}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text[:48] or "finding"


def _content_finding_id(finding_type: str, text: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    digest = hashlib.sha256(f"{finding_type}:{normalized}".encode("utf-8")).hexdigest()[:12]
    return f"{finding_type}-{digest}-{_slug(normalized)}"


def _existing_source_findings(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = raw.get("source_findings")
    if not isinstance(findings, list):
        return {}
    return {str(item.get("id") or ""): dict(item) for item in findings if isinstance(item, dict) and item.get("id")}


def _finding_payload(
    raw: dict[str, Any],
    *,
    finding_id: str,
    finding_type: str,
    message: str,
    evidence_text: str | None = None,
    charge_line_id: str | None = None,
    blocking: bool = True,
) -> dict[str, Any]:
    existing = _existing_source_findings(raw).get(finding_id, {})
    status = existing.get("status") or SOURCE_FINDING_STATUS_OPEN
    return {
        "id": finding_id,
        "type": finding_type,
        "message": message,
        "evidence": existing.get("evidence") or {"source_text": evidence_text or message},
        "charge_line_id": existing.get("charge_line_id") or charge_line_id,
        "status": status,
        "blocking": bool(blocking),
        "resolution_action": existing.get("resolution_action"),
        "review_note": existing.get("review_note"),
        "resolved_by_user_id": existing.get("resolved_by_user_id"),
        "resolved_at": existing.get("resolved_at"),
    }


def _derive_source_findings(raw: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if summary["ai_used"] and not summary["can_proceed"]:
        findings.append(_finding_payload(
            raw,
            finding_id="source-missing-required-fields",
            finding_type="missing_required_fields",
            message="Imported lines are missing required rate or currency fields.",
        ))
    seen_content_findings: set[str] = set()
    for text in summary["critic_missed_charges"]:
        finding_id = _content_finding_id("critic_missed_charges", text)
        if finding_id in seen_content_findings:
            continue
        seen_content_findings.add(finding_id)
        findings.append(_finding_payload(
            raw,
            finding_id=finding_id,
            finding_type="critic_missed_charges",
            message=f"Possible missed charge: {text}",
            evidence_text=text,
        ))
    for text in summary["critic_hallucinations"]:
        finding_id = _content_finding_id("critic_hallucinations", text)
        if finding_id in seen_content_findings:
            continue
        seen_content_findings.add(finding_id)
        findings.append(_finding_payload(
            raw,
            finding_id=finding_id,
            finding_type="critic_hallucinations",
            message=f"Questionable extracted mapping or charge: {text}",
            evidence_text=text,
        ))
    if summary["unmapped_line_count"] > 0:
        findings.append(_finding_payload(
            raw,
            finding_id="source-unmapped-lines",
            finding_type="unmapped_lines",
            message=f"{summary['unmapped_line_count']} extracted charge(s) could not be mapped cleanly.",
        ))
    if summary["imported_charge_count"] == 0 and summary["ai_used"]:
        findings.append(_finding_payload(
            raw,
            finding_id="source-no-imported-charges",
            finding_type="no_imported_charges",
            message="No charge lines were imported for review.",
        ))
    if len(summary["detected_currencies"]) > 1:
        findings.append(_finding_payload(
            raw,
            finding_id="source-multiple-currencies",
            finding_type="multiple_currencies",
            message="Multiple currencies were detected in a single source: " + ", ".join(summary["detected_currencies"]),
        ))
    if summary["low_confidence_line_count"] > 0:
        findings.append(_finding_payload(
            raw,
            finding_id="source-low-confidence-lines",
            finding_type="low_confidence_lines",
            message=f"{summary['low_confidence_line_count']} extracted charge line(s) were low-confidence.",
            blocking=False,
        ))
    if summary["pdf_fallback_used"]:
        findings.append(_finding_payload(
            raw,
            finding_id="source-pdf-fallback-used",
            finding_type="pdf_fallback_used",
            message="Scanned-PDF fallback extraction was used; verify the imported lines carefully.",
            blocking=False,
        ))
    return findings


def unresolved_source_findings(value: Any) -> list[dict[str, Any]]:
    summary = normalize_source_analysis_summary(value)
    return [
        item for item in summary.get("source_findings", [])
        if item.get("blocking") and item.get("status") != SOURCE_FINDING_STATUS_RESOLVED
    ]


def _derive_blocking_reasons(summary: dict[str, Any]) -> tuple[list[str], list[str], str, bool]:
    risk_flags: list[str] = []
    blocking_reasons: list[str] = []
    high_risk = False

    if summary["ai_used"] and not summary["can_proceed"]:
        risk_flags.append("missing_required_fields")
        blocking_reasons.append("Imported lines are missing required rate or currency fields.")
        high_risk = True

    if summary["critic_missed_charges"]:
        risk_flags.append("critic_missed_charges")
        blocking_reasons.append(
            "Possible missed charges: " + ", ".join(summary["critic_missed_charges"])
        )
        high_risk = True

    if summary["critic_hallucinations"]:
        risk_flags.append("critic_hallucinations")
        blocking_reasons.append(
            "Please verify these charges: " + ", ".join(summary["critic_hallucinations"])
        )
        high_risk = True

    if summary["unmapped_line_count"] > 0:
        risk_flags.append("unmapped_lines")
        blocking_reasons.append(
            f"{summary['unmapped_line_count']} extracted charge(s) could not be mapped cleanly."
        )
        high_risk = True

    if summary["imported_charge_count"] == 0 and summary["ai_used"]:
        risk_flags.append("no_imported_charges")
        blocking_reasons.append("No charge lines were imported for review.")
        high_risk = True

    if summary["low_confidence_line_count"] > 0:
        risk_flags.append("low_confidence_lines")
        blocking_reasons.append(
            f"{summary['low_confidence_line_count']} extracted charge line(s) were low-confidence."
        )

    if summary["conditional_charge_count"] > 0:
        risk_flags.append("conditional_charges")
        blocking_reasons.append(
            f"{summary['conditional_charge_count']} extracted charge line(s) are conditional."
        )

    if len(summary["detected_currencies"]) > 1:
        risk_flags.append("multiple_currencies")
        blocking_reasons.append(
            "Multiple currencies were detected in a single source: " + ", ".join(summary["detected_currencies"])
        )
        high_risk = True

    if summary["pdf_fallback_used"]:
        risk_flags.append("pdf_fallback_used")
        blocking_reasons.append("Scanned-PDF fallback extraction was used; verify the imported lines carefully.")

    if high_risk:
        risk_level = "HIGH"
    elif risk_flags:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    requires_review_note = high_risk
    return risk_flags, blocking_reasons, risk_level, requires_review_note


def normalize_source_analysis_summary(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}

    warnings = _string_list(raw.get("warnings"))
    detected_currencies = sorted({item.upper() for item in _string_list(raw.get("detected_currencies"))})
    ai_used = bool(raw.get("ai_used"))

    summary = {
        "warnings": warnings,
        "assertion_count": _int_value(raw.get("assertion_count")),
        "can_proceed": bool(raw.get("can_proceed", False)),
        "ai_used": ai_used,
        "review_required": False,
        "review_status": REVIEW_STATUS_NOT_REQUIRED,
        "reviewed_safe_to_quote": False,
        "reviewed_by_user_id": str(raw.get("reviewed_by_user_id") or "").strip() or None,
        "reviewed_at": raw.get("reviewed_at") or None,
        "review_note": str(raw.get("review_note") or "").strip() or None,
        "detected_currencies": detected_currencies,
        "raw_charge_count": _int_value(raw.get("raw_charge_count")),
        "normalized_charge_count": _int_value(raw.get("normalized_charge_count")),
        "imported_charge_count": _int_value(raw.get("imported_charge_count")),
        "unmapped_line_count": _int_value(raw.get("unmapped_line_count")),
        "low_confidence_line_count": _int_value(raw.get("low_confidence_line_count")),
        "conditional_charge_count": _int_value(raw.get("conditional_charge_count")),
        "critic_safe_to_proceed": (
            None if raw.get("critic_safe_to_proceed") is None else bool(raw.get("critic_safe_to_proceed"))
        ),
        "critic_missed_charges": _string_list(raw.get("critic_missed_charges")),
        "critic_hallucinations": _string_list(raw.get("critic_hallucinations")),
        "pdf_fallback_used": bool(raw.get("pdf_fallback_used", False)),
    }
    risk_flags, blocking_reasons, risk_level, requires_review_note = _derive_blocking_reasons(summary)
    # Only high-risk extraction findings require explicit source review before
    # acknowledgement/final quote creation. Medium-risk audit signals such as
    # low-confidence lines or scanned-PDF fallback stay visible as warnings, but
    # they must not turn a proceedable SPOT envelope into a dead final button.
    review_required = bool(requires_review_note)
    reviewed_safe_to_quote = bool(raw.get("reviewed_safe_to_quote", False)) if review_required else False
    raw_review_status = str(raw.get("review_status") or "").strip().upper()
    if review_required:
        review_status = REVIEW_STATUS_APPROVED if reviewed_safe_to_quote else REVIEW_STATUS_PENDING
        if raw_review_status in {REVIEW_STATUS_PENDING, REVIEW_STATUS_APPROVED}:
            review_status = raw_review_status
            reviewed_safe_to_quote = raw_review_status == REVIEW_STATUS_APPROVED
    else:
        review_status = REVIEW_STATUS_NOT_REQUIRED
        reviewed_safe_to_quote = False

    summary["source_findings"] = _derive_source_findings(raw, summary)
    unresolved_findings = [
        item for item in summary["source_findings"]
        if item.get("blocking") and item.get("status") != SOURCE_FINDING_STATUS_RESOLVED
    ]
    review_required = bool(unresolved_findings)
    if review_required:
        review_status = REVIEW_STATUS_APPROVED if not unresolved_findings else REVIEW_STATUS_PENDING
        reviewed_safe_to_quote = review_status == REVIEW_STATUS_APPROVED
    else:
        review_status = REVIEW_STATUS_NOT_REQUIRED
        reviewed_safe_to_quote = False

    summary["review_required"] = review_required
    summary["review_status"] = review_status
    summary["reviewed_safe_to_quote"] = reviewed_safe_to_quote
    summary["risk_flags"] = risk_flags
    summary["blocking_reasons"] = [item["message"] for item in unresolved_findings]
    summary["risk_level"] = risk_level
    summary["requires_review_note"] = requires_review_note
    return summary


def build_source_analysis_summary_payload(
    *,
    warnings: Iterable[str],
    assertion_count: int,
    can_proceed: bool,
    ai_used: bool,
    detected_currencies: Iterable[str] | None = None,
    safety_signals: Any | None = None,
) -> dict[str, Any]:
    signals = safety_signals if isinstance(safety_signals, dict) else {}
    if safety_signals is not None and hasattr(safety_signals, "model_dump"):
        signals = safety_signals.model_dump()
    return normalize_source_analysis_summary(
        {
            "warnings": list(warnings),
            "assertion_count": int(assertion_count),
            "can_proceed": bool(can_proceed),
            "ai_used": bool(ai_used),
            "review_required": False,
            "review_status": REVIEW_STATUS_NOT_REQUIRED,
            "reviewed_safe_to_quote": False,
            "reviewed_by_user_id": None,
            "reviewed_at": None,
            "review_note": None,
            "detected_currencies": list(detected_currencies or []),
            "raw_charge_count": _int_value(signals.get("raw_charge_count")),
            "normalized_charge_count": _int_value(signals.get("normalized_charge_count")),
            "imported_charge_count": _int_value(signals.get("imported_charge_count")),
            "unmapped_line_count": _int_value(signals.get("unmapped_line_count")),
            "low_confidence_line_count": _int_value(signals.get("low_confidence_line_count")),
            "conditional_charge_count": _int_value(signals.get("conditional_charge_count")),
            "critic_safe_to_proceed": signals.get("critic_safe_to_proceed"),
            "critic_missed_charges": _string_list(signals.get("critic_missed_charges")),
            "critic_hallucinations": _string_list(signals.get("critic_hallucinations")),
            "pdf_fallback_used": bool(signals.get("pdf_fallback_used", False)),
        }
    )


def mark_source_analysis_review(
    value: Any,
    *,
    reviewed_safe_to_quote: bool,
    reviewed_by_user_id: str | None,
    reviewed_at: str | None,
    review_note: str | None = None,
    source_finding_id: str | None = None,
    resolution_action: str | None = None,
    charge_line_id: str | None = None,
) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    summary = normalize_source_analysis_summary(raw)
    note = str(review_note or "").strip() or None
    finding_id = str(source_finding_id or "").strip() or None

    updated_findings = []
    for finding in summary.get("source_findings", []):
        item = dict(finding)
        if reviewed_safe_to_quote and finding_id and item.get("id") == finding_id:
            item["status"] = SOURCE_FINDING_STATUS_RESOLVED
            item["resolution_action"] = resolution_action
            item["review_note"] = note
            item["resolved_by_user_id"] = str(reviewed_by_user_id or "").strip() or None
            item["resolved_at"] = reviewed_at or None
            if charge_line_id:
                item["charge_line_id"] = str(charge_line_id)
        updated_findings.append(item)

    raw["source_findings"] = updated_findings
    raw["reviewed_by_user_id"] = str(reviewed_by_user_id or "").strip() or None
    raw["reviewed_at"] = reviewed_at or None
    raw["review_note"] = note
    return normalize_source_analysis_summary(raw)


def sync_source_analysis_summary_counts(
    value: Any,
    *,
    unmapped_line_count: int,
    low_confidence_line_count: int,
    conditional_charge_count: int,
) -> dict[str, Any]:
    """
    Update a source analysis summary with current counts and re-derive risk flags.
    Used when charge lines are manually resolved or updated.
    """
    raw = value if isinstance(value, dict) else {}
    updated = dict(raw)
    updated["unmapped_line_count"] = int(unmapped_line_count)
    updated["low_confidence_line_count"] = int(low_confidence_line_count)
    updated["conditional_charge_count"] = int(conditional_charge_count)

    # normalize will re-derive risk_flags, risk_level etc. from these new counts
    return normalize_source_analysis_summary(updated)


def evaluate_envelope_intake_safety(source_batches: Iterable[Any]) -> dict[str, Any]:
    blocking_issues: list[str] = []
    pending_source_batch_ids: list[str] = []
    pending_source_labels: list[str] = []
    review_note_required_batch_ids: list[str] = []

    for batch in source_batches:
        summary = normalize_source_analysis_summary(getattr(batch, "analysis_summary_json", None))
        if not summary["review_required"] or summary["review_status"] == REVIEW_STATUS_APPROVED:
            continue

        batch_id = str(getattr(batch, "id", "") or "")
        label = str(getattr(batch, "label", "") or getattr(batch, "source_reference", "") or "Imported source")
        if batch_id:
            pending_source_batch_ids.append(batch_id)
        pending_source_labels.append(label)
        if summary["requires_review_note"]:
            review_note_required_batch_ids.append(batch_id)

        reasons = summary["blocking_reasons"] or ["Imported source needs review before quote creation."]
        for reason in reasons:
            blocking_issues.append(f"{label}: {reason}")

    return {
        "is_safe_to_quote": not blocking_issues,
        "blocking_issues": blocking_issues,
        "pending_source_batch_ids": pending_source_batch_ids,
        "pending_source_labels": pending_source_labels,
        "review_note_required_batch_ids": review_note_required_batch_ids,
    }
