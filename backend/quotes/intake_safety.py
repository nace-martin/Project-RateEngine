from __future__ import annotations

from typing import Any, Iterable


REVIEW_STATUS_PENDING = "PENDING"
REVIEW_STATUS_APPROVED = "APPROVED"
REVIEW_STATUS_NOT_REQUIRED = "NOT_REQUIRED"


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


def _derive_blocking_reasons(summary: dict[str, Any]) -> tuple[list[str], list[str], str, bool]:
    risk_flags: list[str] = []
    blocking_reasons: list[str] = []
    high_risk = False

    if not summary["can_proceed"]:
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
    review_required = False
    reviewed_safe_to_quote = False
    review_status = REVIEW_STATUS_NOT_REQUIRED

    summary = {
        "warnings": warnings,
        "assertion_count": _int_value(raw.get("assertion_count")),
        "can_proceed": bool(raw.get("can_proceed", False)),
        "ai_used": ai_used,
        "review_required": review_required,
        "review_status": review_status,
        "reviewed_safe_to_quote": reviewed_safe_to_quote,
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
    risk_flags, blocking_reasons, risk_level, _requires_review_note = _derive_blocking_reasons(summary)
    summary["risk_flags"] = risk_flags
    summary["blocking_reasons"] = blocking_reasons
    summary["risk_level"] = risk_level
    summary["requires_review_note"] = False
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
) -> dict[str, Any]:
    summary = normalize_source_analysis_summary(value)
    review_required = bool(summary["review_required"])

    if review_required:
        summary["review_status"] = (
            REVIEW_STATUS_APPROVED if reviewed_safe_to_quote else REVIEW_STATUS_PENDING
        )
        summary["reviewed_safe_to_quote"] = bool(reviewed_safe_to_quote)
    else:
        summary["review_status"] = REVIEW_STATUS_NOT_REQUIRED
        summary["reviewed_safe_to_quote"] = False

    summary["reviewed_by_user_id"] = str(reviewed_by_user_id or "").strip() or None
    summary["reviewed_at"] = reviewed_at or None
    summary["review_note"] = str(review_note or "").strip() or None
    return summary


def evaluate_envelope_intake_safety(source_batches: Iterable[Any]) -> dict[str, Any]:
    return {
        "is_safe_to_quote": True,
        "blocking_issues": [],
        "pending_source_batch_ids": [],
        "pending_source_labels": [],
        "review_note_required_batch_ids": [],
    }
