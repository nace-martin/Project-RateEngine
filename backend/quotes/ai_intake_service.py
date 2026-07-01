"""
AI Rate Intake Service

Uses Google Gemini (configurable model; defaults to Gemini 2.5 Flash Lite)
to parse unstructured rate quotes into structured charge lines.

Architecture Principles:
- AI is input accelerator only — does NOT make pricing decisions
- AI output MUST pass Pydantic validation
- AI never writes directly to database
- High-confidence deterministic matches can be auto-accepted; exceptions require review
"""

import json
import logging
import re
from collections import Counter
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field, ValidationError

from .ai_intake_schemas import (
    ExtractionAuditResult,
    NormalizedCharge,
    QuoteInputPayload,
    RawExtractedCharge,
    SpotChargeLine,
    VALID_CURRENCIES,
)

logger = logging.getLogger(__name__)

# Gemini model configuration
DEFAULT_GEMINI_MODEL_NAME = "gemini-2.5-flash-lite"


def _resolve_gemini_model_name() -> str:
    """Read Gemini model name from Django settings with a safe fallback."""
    try:
        from django.conf import settings as django_settings
        configured = getattr(django_settings, "GEMINI_MODEL_NAME", DEFAULT_GEMINI_MODEL_NAME)
    except Exception:
        configured = DEFAULT_GEMINI_MODEL_NAME
    return str(configured).strip() or DEFAULT_GEMINI_MODEL_NAME


GEMINI_MODEL = _resolve_gemini_model_name()
MAX_RETRIES = 2

CURRENCY_HINT_PATTERNS = [
    r"\bABOVE\s+QUOTE\s+IN\s+([A-Z]{3})\b",
    r"\bQUOTE(?:D)?\s+IN\s+([A-Z]{3})\b",
    r"\bALL\s+RATES\s+IN\s+([A-Z]{3})\b",
    r"\bAMOUNT\s*\(\s*([A-Z]{3})\b",
    r"\bCURRENCY\s*[:=]\s*([A-Z]{3})\b",
    r"\bCCY\s*[:=]\s*([A-Z]{3})\b",
]

CURRENCY_SYMBOL_PATTERNS = {
    "USD": r"US\$",
    "AUD": r"A\$",
    "NZD": r"NZ\$",
    "SGD": r"(?<!U)S\$",
    "HKD": r"HK\$",
}

CURRENCY_SYMBOL_MAP = {
    "US$": "USD",
    "A$": "AUD",
    "NZ$": "NZD",
    "S$": "SGD",
    "HK$": "HKD",
}

PATTERN_CHARGE_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?"
    r"(?P<label>[A-Za-z][A-Za-z0-9/&+().,\-\u2013\u2014 ]{1,80}?)"
    r"\s*[:：]\s*"
    r"(?P<amount>"
    r"(?P<currency>US\$|A\$|NZ\$|S\$|HK\$|[A-Z]{3}|\$)"
    r"\s*[0-9][0-9,]*(?:\.[0-9]+)?"
    r"(?:\s*(?:/[A-Za-z]+|per\s+[A-Za-z]+))?"
    r")"
    r"\s*(?P<note>\([^)\r\n]*\))?"
)

PATTERN_CHARGE_FALLBACK_REASON = "AI missed pattern-based extraction"


class _RawExtractedChargesEnvelope(BaseModel):
    charges: List[RawExtractedCharge] = Field(default_factory=list)


class _NormalizedChargesEnvelope(BaseModel):
    charges: List[NormalizedCharge] = Field(default_factory=list)


class AIRateIntakePipelineResult(BaseModel):
    """Service return shape kept compatible with existing API formatters."""

    success: bool
    quote_input: Optional[QuoteInputPayload] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    raw_text_length: int = 0
    source_type: str = "TEXT"
    model_used: Optional[str] = None
    analysis_text: Optional[str] = None
    quote_currency: Optional[str] = None
    raw_extracted_charges: List[RawExtractedCharge] = Field(default_factory=list)
    normalized_charges: List[NormalizedCharge] = Field(default_factory=list)
    extraction_audit: Optional[ExtractionAuditResult] = None

    @property
    def lines(self) -> List[SpotChargeLine]:
        if not self.quote_input:
            return []
        return list(self.quote_input.charge_lines or [])


class PDFRateQuoteTextResult(BaseModel):
    success: bool
    text: str = ""
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    extraction_method: str = "PDF_TEXT"


class _GenAIResponseAdapter:
    """Normalize google.genai responses to the legacy `.text` interface."""

    def __init__(self, raw_response):
        self._raw_response = raw_response
        self.text = self._extract_text(raw_response)
        self.parsed = self._extract_parsed(raw_response)

    @staticmethod
    def _extract_text(response) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text

        # Defensive fallback if SDK response shape changes.
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    return part_text
        return ""

    @staticmethod
    def _extract_parsed(response):
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_parsed = getattr(part, "parsed", None)
                if part_parsed is not None:
                    return part_parsed
        return None


class _GenAIModelAdapter:
    """Compatibility adapter exposing `generate_content(...)` like google.generativeai."""

    def __init__(self, client, model_name: str):
        self._client = client
        self._model_name = model_name

    def generate_content(self, prompt, generation_config=None):
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=generation_config or {},
        )
        return _GenAIResponseAdapter(response)


class _GenAIClientAdapter:
    """Compatibility adapter exposing `.GenerativeModel(...)` over `google.genai.Client`."""

    def __init__(self, sdk_module, api_key: str):
        self._client = sdk_module.Client(api_key=api_key)

    def GenerativeModel(self, model_name: str):
        return _GenAIModelAdapter(self._client, model_name)


def _normalize_currency_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = value.strip().upper()
    for symbol, code in CURRENCY_SYMBOL_MAP.items():
        if symbol in raw:
            return code
    letters = re.sub(r"[^A-Z]", "", raw)
    if len(letters) >= 3:
        return letters[:3]
    return None


def _infer_quote_currency_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    upper = text.upper()

    for pattern in CURRENCY_HINT_PATTERNS:
        match = re.search(pattern, upper)
        if match:
            code = match.group(1)
            if code in VALID_CURRENCIES:
                return code

    counts = Counter()
    codes = re.findall(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", upper)
    for code in codes:
        if code in VALID_CURRENCIES:
            counts[code] += 1

    for code, pattern in CURRENCY_SYMBOL_PATTERNS.items():
        matches = re.findall(pattern, upper)
        if matches:
            counts[code] += len(matches)

    if not counts:
        return None

    most_common = counts.most_common(2)
    if len(most_common) == 1 or most_common[0][1] > most_common[1][1]:
        return most_common[0][0]

    return None


def _normalize_fallback_label(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _normalize_fallback_amount(value: str) -> str:
    amount_without_notes = re.sub(r"\([^)]*\)", "", value.upper())
    currency = _normalize_currency_value(amount_without_notes) or ""
    number_match = re.search(r"[0-9][0-9,]*(?:\.[0-9]+)?", amount_without_notes)
    number = number_match.group(0).replace(",", "") if number_match else ""
    unit_match = re.search(r"(?:/[A-Z]+|PER\s+[A-Z]+)", amount_without_notes)
    unit = re.sub(r"\s+", "", unit_match.group(0)) if unit_match else ""
    if currency or number:
        return f"{currency}:{number}:{unit}"
    return re.sub(r"\s+", "", amount_without_notes)


def _raw_charge_dedupe_key(charge: RawExtractedCharge) -> tuple:
    return (
        _normalize_fallback_label(charge.raw_label),
        _normalize_fallback_amount(charge.raw_amount_string),
        _normalize_fallback_label(charge.section_context or ""),
        _normalize_fallback_label(charge.raw_unit or ""),
        _normalize_fallback_label(charge.raw_minimum or ""),
        _normalize_fallback_label(charge.raw_rate or ""),
        _normalize_fallback_label(charge.raw_percentage or ""),
    )


def _extract_tabular_charge_candidates(text: str) -> List[RawExtractedCharge]:
    if not text:
        return []

    candidates: List[RawExtractedCharge] = []
    current_section = None
    header_indices = {}
    marker_candidates = {}

    lines = [line.strip() for line in text.splitlines()]
    last_candidate = None

    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue

        # Split line by tab or 2+ spaces
        parts = re.split(r'\t|\s{2,}', line)
        parts = [p.strip() for p in parts if p.strip()]

        # Check for footnote comments (lines starting with * or ** and having 1 or fewer columns after split)
        if (line.startswith("*") or line.startswith("**")) and len(parts) <= 1:
            marker = "**" if line.startswith("**") else "*"
            note_text = line.lstrip("* ").strip()
            is_cond_note = any(term in note_text.lower() for term in [
                "if required", "optional", "poa", "subject to", "screening"
            ])
            
            matched_charges = marker_candidates.get(marker, [])
            if not matched_charges and last_candidate:
                matched_charges = [last_candidate]
                
            for mc in matched_charges:
                if mc.raw_notes:
                    mc.raw_notes += f"; {note_text}"
                else:
                    mc.raw_notes = note_text
                if is_cond_note:
                    mc.is_conditional = True
            continue

        # If a line doesn't have multiple parts, it might be a section heading
        if len(parts) == 1:
            val = parts[0]
            # Exclude header-like or charge-like lines
            if not any(kw in val.lower() for kw in ["currency", "minimum", "per unit", "%"]):
                current_section = val
            continue

        # If it is a header row, we detect column positions
        is_header = False
        lower_parts = [p.lower() for p in parts]
        if any(re.search(r'\b(charge|description)\b', lp) for lp in lower_parts) or \
           any(re.search(r'\b(currency|ccy)\b', lp) for lp in lower_parts) or \
           any(re.search(r'\bunit\b', lp) for lp in lower_parts) or \
           any(re.search(r'\b(minimum|min)\b', lp) for lp in lower_parts):
            is_header = True

        if is_header:
            header_indices = {}
            for i, p in enumerate(lower_parts):
                if re.search(r'\b(description|charge)\b', p):
                    header_indices["description"] = i
                elif re.search(r'\b(currency|ccy)\b', p):
                    header_indices["currency"] = i
                elif re.search(r'\b(per\s+unit|rate|per-unit)\b', p):
                    header_indices["rate"] = i
                elif re.search(r'\bunit\b', p):
                    header_indices["unit"] = i
                elif re.search(r'\b(minimum|min)\b', p):
                    header_indices["minimum"] = i
            continue

        # Otherwise, parse as a data row
        label_part = parts[0]
        marker = None
        if label_part.startswith("**"):
            marker = "**"
            label_part = label_part[2:].strip()
        elif label_part.startswith("*"):
            marker = "*"
            label_part = label_part[1:].strip()

        raw_label = label_part
        raw_unit = None
        raw_minimum = None
        raw_rate = None
        raw_percentage = None
        currency_hint = None

        # Value-based heuristics if header mapping is not fully populated or column count doesn't match
        use_heuristics = True
        if header_indices and len(parts) >= 4:
            try:
                desc_idx = header_indices.get("description", 0)
                curr_idx = header_indices.get("currency")
                unit_idx = header_indices.get("unit")
                min_idx = header_indices.get("minimum")
                rate_idx = header_indices.get("rate")

                raw_label = parts[desc_idx]
                if raw_label.startswith("**"):
                    marker = "**"
                    raw_label = raw_label[2:].strip()
                elif raw_label.startswith("*"):
                    marker = "*"
                    raw_label = raw_label[1:].strip()

                if curr_idx is not None and curr_idx < len(parts):
                    currency_hint = _normalize_currency_value(parts[curr_idx])
                if unit_idx is not None and unit_idx < len(parts):
                    raw_unit = parts[unit_idx]
                if min_idx is not None and min_idx < len(parts):
                    raw_minimum = parts[min_idx]
                    if raw_minimum == "-":
                        raw_minimum = None
                if rate_idx is not None and rate_idx < len(parts):
                    raw_rate = parts[rate_idx]
                    if raw_rate == "-":
                        raw_rate = None
                use_heuristics = False
            except Exception:
                use_heuristics = True

        if use_heuristics:
            if len(parts) == 2:
                if "%" in parts[1]:
                    raw_percentage = parts[1]
                else:
                    raw_minimum = parts[1]
            elif len(parts) >= 3:
                remaining_parts = parts[1:]
                for p in remaining_parts[:]:
                    norm_curr = _normalize_currency_value(p)
                    if norm_curr and len(p) == 3 and norm_curr in VALID_CURRENCIES:
                        currency_hint = norm_curr
                        remaining_parts.remove(p)
                        break
                
                for p in remaining_parts[:]:
                    if "%" in p:
                        raw_percentage = p
                        remaining_parts.remove(p)
                        break

                for p in remaining_parts[:]:
                    if any(uk in p.lower() for uk in ["kg", "awb", "shipment", "entry", "trip", "cbm"]):
                        raw_unit = p
                        remaining_parts.remove(p)
                        break

                if len(remaining_parts) == 1:
                    raw_minimum = remaining_parts[0]
                elif len(remaining_parts) >= 2:
                    raw_minimum = remaining_parts[0]
                    raw_rate = remaining_parts[1]

        amt_parts = []
        if currency_hint:
            amt_parts.append(currency_hint)
        if raw_rate:
            amt_parts.append(f"{raw_rate} per {raw_unit or 'KG'}")
        if raw_minimum:
            amt_parts.append(f"min {raw_minimum}")
        if raw_percentage:
            amt_parts.append(raw_percentage)
        if not amt_parts:
            amt_parts = parts[1:]

        raw_amount_string = " ".join(amt_parts)

        # Mark rows conditional if section/header/notes/label/line contain optional/if required/POA/subject to/screening
        cond_check_str = f"{current_section or ''} {raw_label} {raw_amount_string} {line}".lower()
        is_conditional = any(term in cond_check_str for term in [
            "if required", "optional", "poa", "subject to", "screening"
        ])

        charge = RawExtractedCharge(
            raw_label=raw_label,
            raw_amount_string=raw_amount_string,
            currency_hint=currency_hint,
            is_conditional=is_conditional,
            source_excerpt=line,
            source_line_number=line_number,
            source_line_identity=f"tabular-line:{line_number}:{_normalize_fallback_label(raw_label)}",
            raw_unit=raw_unit,
            raw_minimum=raw_minimum,
            raw_rate=raw_rate,
            raw_percentage=raw_percentage,
            section_context=current_section,
        )
        candidates.append(charge)
        last_candidate = charge
        if marker:
            marker_candidates.setdefault(marker, []).append(charge)

    return candidates


def _extract_diagnostic_table_candidates(text: str) -> List[RawExtractedCharge]:
    """Phase 8B: Extract RawExtractedCharge candidates using table diagnostics."""
    from quotes.services.table_diagnostics import parse_table_text_to_intermediate
    try:
        diag_lines = parse_table_text_to_intermediate(text)
    except Exception as e:
        logger.warning("Structured table diagnostics parser failed: %s", e)
        return []

    candidates: List[RawExtractedCharge] = []
    lines = text.splitlines()

    for line in diag_lines:
        currency_hint = None
        if line.currency_hint:
            norm_curr = _normalize_currency_value(line.currency_hint)
            if norm_curr and len(norm_curr) == 3 and norm_curr in VALID_CURRENCIES:
                currency_hint = norm_curr

        amt_parts = []
        if currency_hint:
            amt_parts.append(currency_hint)
        if line.rate_per_unit is not None:
            unit_lbl = line.unit_hint or "KG"
            if unit_lbl == "per_kg":
                unit_lbl = "KG"
            elif unit_lbl == "per_awb":
                unit_lbl = "AWB"
            elif unit_lbl == "per_entry":
                unit_lbl = "Entry"
            elif unit_lbl == "per_shipment":
                unit_lbl = "Shipment"
            elif unit_lbl == "percentage":
                unit_lbl = "%"
            amt_parts.append(f"{line.rate_per_unit} per {unit_lbl}")
        if line.min_amount is not None:
            amt_parts.append(f"min {line.min_amount}")
        if line.percentage is not None:
            amt_parts.append(f"{line.percentage}%")
        if line.is_poa:
            amt_parts.append("POA")
            
        raw_amount_str = " ".join(amt_parts)
        if not raw_amount_str:
            raw_amount_str = "0.00"

        source_excerpt = None
        if line.source_line_number and 1 <= line.source_line_number <= len(lines):
            source_excerpt = lines[line.source_line_number - 1].strip()

        raw_lbl_stripped = line.raw_label[2:].strip() if line.raw_label.startswith("**") else (line.raw_label[1:].strip() if line.raw_label.startswith("*") else line.raw_label)

        charge = RawExtractedCharge(
            raw_label=raw_lbl_stripped,
            raw_amount_string=raw_amount_str,
            currency_hint=currency_hint,
            is_conditional=line.is_conditional,
            source_excerpt=source_excerpt,
            source_line_number=line.source_line_number,
            source_line_identity=f"diag-table-line:{line.source_line_number or 0}:{_normalize_fallback_label(line.raw_label)}",
            raw_unit=line.raw_unit or line.unit_hint,
            raw_minimum=str(line.min_amount) if line.min_amount is not None else ("POA" if line.is_poa else None),
            raw_rate=str(line.rate_per_unit) if line.rate_per_unit is not None else None,
            raw_percentage=f"{line.percentage}%" if line.percentage is not None else None,
            section_context=line.section_context,
            raw_notes=line.raw_notes,
        )
        candidates.append(charge)

    return candidates


def _sections_overlap(sec1: Optional[str], sec2: Optional[str]) -> bool:
    s1 = _normalize_fallback_label(sec1 or "")
    s2 = _normalize_fallback_label(sec2 or "")
    if not s1 or not s2:
        return True
    return s1 == s2


def _normalize_label_tolerant(label: str) -> str:
    if not label:
        return ""
    lbl = label.lower()
    lbl = re.sub(r'\b(fee|fees|charge|charges|surcharge|surcharges|rate|rates)\b', '', lbl)
    lbl = re.sub(r'[^a-z0-9]', '', lbl)
    return lbl.strip()


def _merge_all_charge_candidates(
    ai_charges: List[RawExtractedCharge],
    tabular_charges: List[RawExtractedCharge],
    pattern_charges: List[RawExtractedCharge],
    diag_charges: Optional[List[RawExtractedCharge]] = None,
) -> List[RawExtractedCharge]:
    merged: List[RawExtractedCharge] = []

    def find_overlapping(new_c: RawExtractedCharge) -> Optional[RawExtractedCharge]:
        new_label = _normalize_label_tolerant(new_c.raw_label)
        new_sec = new_c.section_context
        for existing in merged:
            existing_label = _normalize_label_tolerant(existing.raw_label)
            if new_label == existing_label:
                if _sections_overlap(new_sec, existing.section_context):
                    return existing
        return None

    def merge_two_raw(existing: RawExtractedCharge, new_c: RawExtractedCharge):
        # Merge properties into existing charge
        if not existing.currency_hint:
            existing.currency_hint = new_c.currency_hint
        if not existing.raw_unit:
            existing.raw_unit = new_c.raw_unit
        if not existing.raw_minimum:
            existing.raw_minimum = new_c.raw_minimum
        if not existing.raw_rate:
            existing.raw_rate = new_c.raw_rate
        if not existing.raw_percentage:
            existing.raw_percentage = new_c.raw_percentage
        if not existing.section_context:
            existing.section_context = new_c.section_context
            
        existing.is_conditional = existing.is_conditional or new_c.is_conditional
        
        # Merge raw_notes
        notes_parts = []
        if getattr(existing, "raw_notes", None):
            notes_parts.append(existing.raw_notes)
        if getattr(new_c, "raw_notes", None):
            notes_parts.append(new_c.raw_notes)
        if notes_parts:
            existing.raw_notes = "; ".join(notes_parts)
            
        # Update raw_amount_string
        ext_amt = (existing.raw_amount_string or "").strip()
        new_amt = (new_c.raw_amount_string or "").strip()
        if new_amt and new_amt not in ext_amt:
            existing.raw_amount_string = f"{ext_amt} {new_amt}"

    # First add diag charges (highest priority)
    if diag_charges:
        for charge in diag_charges:
            existing = find_overlapping(charge)
            if existing:
                merge_two_raw(existing, charge)
            else:
                merged.append(charge)

    # Next add tabular charges (highest priority)
    for charge in tabular_charges:
        existing = find_overlapping(charge)
        if existing:
            merge_two_raw(existing, charge)
        else:
            merged.append(charge)

    # Next add AI charges
    for charge in ai_charges:
        existing = find_overlapping(charge)
        if existing:
            merge_two_raw(existing, charge)
        else:
            merged.append(charge)

    # Finally pattern charges
    for charge in pattern_charges:
        existing = find_overlapping(charge)
        if existing:
            merge_two_raw(existing, charge)
        else:
            merged.append(charge)

    return merged



def _extract_pattern_charge_candidates(text: str) -> List[RawExtractedCharge]:
    """Deterministically recover compact '<label>:<currency><amount>' charge lines."""
    if not text:
        return []

    candidates: List[RawExtractedCharge] = []
    seen: set[tuple] = set()
    line_starts: list[tuple[int, int]] = []
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        line_starts.append((offset, line_number))
        offset += len(line)

    def line_number_for_offset(position: int) -> int | None:
        current_line = None
        for start, line_number in line_starts:
            if start > position:
                break
            current_line = line_number
        return current_line

    for match in PATTERN_CHARGE_LINE_RE.finditer(text):
        label = match.group("label").strip(" \t-*:：")
        amount = match.group("amount").strip()
        note = (match.group("note") or "").strip()
        raw_amount_string = f"{amount}{note}" if note else amount
        currency_hint = _normalize_currency_value(match.group("currency"))

        if not label or not amount:
            continue

        charge = RawExtractedCharge(
            raw_label=label,
            raw_amount_string=raw_amount_string,
            currency_hint=currency_hint,
            is_conditional=_text_indicates_conditional(note),
            source_excerpt=match.group(0).strip(),
            source_line_number=line_number_for_offset(match.start()),
            source_line_identity=(
                f"pattern-line:{line_number_for_offset(match.start())}:{_normalize_fallback_label(label)}"
            ),
        )
        key = _raw_charge_dedupe_key(charge)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(charge)

    return candidates


def _text_indicates_conditional(value: str) -> bool:
    conditional_terms = (
        "if applicable",
        "if any",
        "subject to",
        "optional",
        "where applicable",
        "as applicable",
        "if application",
        "if required",
        "if apply",
    )
    lowered = value.lower()
    return any(term in lowered for term in conditional_terms)


def _extract_parenthetical_notes(value: str) -> Optional[str]:
    notes = [
        note.strip()
        for note in re.findall(r"\(([^)\r\n]+)\)", value or "")
        if note.strip()
    ]
    return "; ".join(notes)[:500] if notes else None


def _merge_pattern_fallback_charges(
    ai_charges: List[RawExtractedCharge],
    fallback_charges: List[RawExtractedCharge],
) -> List[RawExtractedCharge]:
    """Append deterministic fallback charges without replacing AI output."""
    if not fallback_charges:
        return ai_charges

    merged = list(ai_charges)
    seen = {_raw_charge_dedupe_key(charge) for charge in ai_charges}

    for charge in fallback_charges:
        key = _raw_charge_dedupe_key(charge)
        if key in seen:
            continue
        logger.info(
            "Fallback extracted charge label=%s amount=%s reason=%s",
            charge.raw_label,
            charge.raw_amount_string,
            PATTERN_CHARGE_FALLBACK_REASON,
        )
        merged.append(charge)
        seen.add(key)

    return merged


def get_gemini_client():
    """Get configured Gemini client. Returns None if not configured."""
    from django.conf import settings
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        logger.error("GEMINI_API_KEY not configured in settings")
        return None

    try:
        from google import genai as genai_sdk
        return _GenAIClientAdapter(genai_sdk, api_key)
    except ImportError as genai_import_error:
        logger.error("Gemini SDK import failed (google-genai: %s)", genai_import_error)
        return None


def _sanitize_json_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    # 1. Strip markdown JSON code blocks if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()
    
    # 2. Trim surrounding non-JSON text by finding outer-most { ... } or [ ... ]
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    first_bracket = cleaned.find('[')
    last_bracket = cleaned.rfind(']')
    
    start_idx, end_idx = -1, -1
    if first_brace != -1 and last_brace != -1:
        if first_bracket == -1 or first_brace < first_bracket:
            start_idx = first_brace
            end_idx = last_brace + 1
        else:
            start_idx = first_bracket
            end_idx = last_bracket + 1
    elif first_bracket != -1 and last_bracket != -1:
        start_idx = first_bracket
        end_idx = last_bracket + 1
        
    if start_idx != -1 and end_idx != -1:
        cleaned = cleaned[start_idx:end_idx]
        
    # 3. Clean control characters except whitespace (tab, newline, carriage return)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    
    # 4. Escape raw newlines, carriage returns, and tabs inside double-quoted string values
    pattern = r'"((?:[^"\\]|\\.)*)"'
    def repl(match):
        content = match.group(1)
        content = content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return f'"{content}"'
    cleaned = re.sub(pattern, repl, cleaned)
    
    return cleaned


def _generate_fallback_normalized_charges(
    raw_charges: List[RawExtractedCharge],
    shipment_context: Optional[dict] = None,
    quote_currency_hint: Optional[str] = None,
) -> List[NormalizedCharge]:
    """
    Generate low-confidence, unmapped NormalizedCharge fallbacks from RawExtractedCharges.
    This runs only when the AI Normalizer fails, preserving the extracted rows.
    """
    print("FALLBACK RAW:", [(r.raw_label, r.section_context) for r in raw_charges])
    normalized: List[NormalizedCharge] = []
    context_payload = dict(shipment_context or {})
    missing_components = context_payload.get("missing_components") or []
    
    def _is_freight_charge(label: str) -> bool:
        lbl = label.lower()
        return any(kw in lbl for kw in ["freight", "airfreight", "af", "a/f", "frt"])

    default_bucket: SpotChargeBucket = "ORIGIN"
    if missing_components:
        missing_set = {str(item).upper() for item in missing_components}
        if "DESTINATION_LOCAL" in missing_set and "ORIGIN_LOCAL" not in missing_set:
            default_bucket = "DESTINATION"
        elif "ORIGIN_LOCAL" in missing_set:
            default_bucket = "ORIGIN"

    for raw in raw_charges:
        # Determine bucket contextually:
        # Default EXPORT/export-side sections to ORIGIN unless shipment context clearly says otherwise.
        # Classify Airfreight AKL - POM via PX(BNE) as FREIGHT.
        # Do not classify Customs Clearance and EDI Fee as PNG destination charges just because of their names;
        # in this sample they are under EXPORT and should be origin/export-side (ORIGIN) or ambiguous.
        if _is_freight_charge(raw.raw_label):
            bucket: SpotChargeBucket = "FREIGHT"
        else:
            sec = (raw.section_context or "").upper()
            if "EXPORT" in sec or "ORIGIN" in sec:
                bucket = "ORIGIN"
            elif "IMPORT" in sec or "DESTINATION" in sec:
                bucket = "DESTINATION"
            else:
                bucket = default_bucket
            
        currency = raw.currency_hint or quote_currency_hint or "USD"
        if not currency or len(currency.strip()) != 3:
            currency_match = re.search(r"\b[A-Z]{3}\b", raw.raw_amount_string.upper())
            currency = currency_match.group(0) if currency_match else "USD"

        # Helper to parse decimal safely
        def to_decimal(val_str: Optional[str]) -> Optional[Decimal]:
            if not val_str:
                return None
            val_str = val_str.replace(",", "").strip()
            if "poa" in val_str.lower():
                return Decimal("0.00")
            num_match = re.search(r"[0-9]+(?:\.[0-9]+)?", val_str)
            if num_match:
                try:
                    return Decimal(num_match.group(0))
                except Exception:
                    return Decimal("0.00")
            return None

        raw_rate_dec = to_decimal(raw.raw_rate)
        raw_min_dec = to_decimal(raw.raw_minimum)
        raw_percentage_dec = to_decimal(raw.raw_percentage)

        # Percentage check
        if raw_percentage_dec is not None or "%" in raw.raw_amount_string:
            unit_basis: UnitBasis = "PERCENTAGE"
            amount_val = raw_percentage_dec or to_decimal(raw.raw_amount_string) or Decimal("0.00")
            percentage = amount_val
            rate_per_unit = None
            minimum_amount = None
            percent_applies_to = "FREIGHT"
        # MIN_OR_PER_KG check (if raw_rate and raw_minimum exist and unit is KG/per KG)
        elif raw_rate_dec is not None and raw_min_dec is not None and raw.raw_unit and any(uk in raw.raw_unit.lower() for uk in ["kg", "per kg"]):
            unit_basis = "MIN_OR_PER_KG"
            amount_val = raw_rate_dec
            rate_per_unit = raw_rate_dec
            minimum_amount = raw_min_dec
            percentage = None
            percent_applies_to = None
        else:
            # If only raw_minimum exists or POA (default to PER_SHIPMENT)
            if raw_rate_dec is not None:
                unit_basis = "PER_KG"
                amount_val = raw_rate_dec
                rate_per_unit = raw_rate_dec
                minimum_amount = None
            else:
                raw_amt_lower = raw.raw_amount_string.lower()
                if any(x in raw_amt_lower for x in ["/kg", "per kg", "per-kg", "/ kg"]):
                    unit_basis = "PER_KG"
                    amount_val = to_decimal(raw.raw_amount_string) or Decimal("0.00")
                    rate_per_unit = amount_val
                    minimum_amount = None
                else:
                    unit_basis = "PER_SHIPMENT"
                    amount_val = raw_min_dec or to_decimal(raw.raw_amount_string) or Decimal("0.00")
                    rate_per_unit = None
                    minimum_amount = None
            percentage = None
            percent_applies_to = None
            
        norm = NormalizedCharge(
            original_raw_label=raw.raw_label,
            v4_product_code="UNMAPPED",
            friendly_description=raw.raw_label,
            v4_bucket=bucket,
            unit_basis=unit_basis,
            amount=amount_val,
            rate_per_unit=rate_per_unit,
            minimum_amount=minimum_amount,
            percentage=percentage,
            percent_applies_to=percent_applies_to,
            currency=currency,
            confidence="LOW",
        )
        normalized.append(norm)
        
    return normalized


def _deduplicate_normalized_charges(charges: List[NormalizedCharge]) -> List[NormalizedCharge]:
    if not charges:
        return []
        
    groups: dict[str, List[NormalizedCharge]] = {}
    for c in charges:
        key = _normalize_label_tolerant(c.original_raw_label)
        groups.setdefault(key, []).append(c)
        
    deduplicated: List[NormalizedCharge] = []
    for key, group in groups.items():
        if len(group) == 1:
            deduplicated.append(group[0])
            continue
            
        rate_charge = None
        flat_charge = None
        percentage_charge = None
        
        for c in group:
            if c.unit_basis in ("PER_KG", "MIN_OR_PER_KG"):
                if rate_charge is None or (rate_charge.unit_basis == "PER_KG" and c.unit_basis == "MIN_OR_PER_KG"):
                    rate_charge = c
            elif c.unit_basis == "PERCENTAGE":
                percentage_charge = c
            elif c.unit_basis == "PER_SHIPMENT":
                if flat_charge is None:
                    flat_charge = c
                else:
                    existing_amt = flat_charge.amount or flat_charge.minimum_amount or Decimal("0.00")
                    new_amt = c.amount or c.minimum_amount or Decimal("0.00")
                    if existing_amt == Decimal("0.00") and new_amt > Decimal("0.00"):
                        flat_charge = c
                        
        if rate_charge and flat_charge:
            merged_charge = rate_charge.model_copy()
            merged_charge.unit_basis = "MIN_OR_PER_KG"
            merged_charge.rate_per_unit = rate_charge.rate_per_unit or rate_charge.amount
            merged_charge.minimum_amount = flat_charge.minimum_amount or flat_charge.amount
            merged_charge.amount = merged_charge.rate_per_unit
            if flat_charge.confidence == "LOW":
                merged_charge.confidence = "LOW"
            deduplicated.append(merged_charge)
        elif rate_charge:
            deduplicated.append(rate_charge)
        elif percentage_charge:
            deduplicated.append(percentage_charge)
        elif flat_charge:
            deduplicated.append(flat_charge)
        else:
            deduplicated.append(group[0])
            
    return deduplicated


def parse_rate_quote_text(
    text: str,
    source_type: str = "TEXT",
    context: Optional[dict] = None
) -> AIRateIntakePipelineResult:
    """Parse unstructured rate quote text using a 3-step LLM pipeline."""

    if not text or len(text.strip()) < 10:
        return AIRateIntakePipelineResult(
            success=False,
            error="Input text is too short to parse",
            raw_text_length=len(text) if text else 0,
            source_type=source_type,
            model_used=GEMINI_MODEL,
        )

    genai = get_gemini_client()
    if not genai:
        return AIRateIntakePipelineResult(
            success=False,
            error=(
                "Gemini API not configured. Set GEMINI_API_KEY and install `google-genai`."
            ),
            raw_text_length=len(text),
            source_type=source_type,
            model_used=GEMINI_MODEL,
        )

    quote_currency = _infer_quote_currency_from_text(text)
    warnings: List[str] = []
    raw_charges = []
    normalized_charges = []
    audit_result = None
    normalization_failed = False

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)

        # Stage 1: Extractor
        try:
            ai_charges = _extract_raw_charges(model, text, shipment_context=context)
        except Exception as e:
            logger.warning("AI Intake Extractor failed, using pattern extraction only: %s", e)
            ai_charges = []
            
        diag_charges = _extract_diagnostic_table_candidates(text)
        tabular_charges = _extract_tabular_charge_candidates(text)
        pattern_charges = _extract_pattern_charge_candidates(text)
        
        raw_charges = _merge_all_charge_candidates(
            ai_charges=ai_charges,
            tabular_charges=tabular_charges,
            pattern_charges=pattern_charges,
            diag_charges=diag_charges,
        )

        # Stage 2: Normalizer
        try:
            normalized_charges = _normalize_charges(
                model,
                raw_charges,
                shipment_context=context,
                quote_currency_hint=quote_currency,
            )
        except Exception as e:
            logger.warning("AI Normalizer failed. Recovering raw charges as unmapped lines: %s", e, exc_info=True)
            warnings.append("AI normalization failed; raw charge extraction preserved for manual review.")
            normalization_failed = True
            normalized_charges = _generate_fallback_normalized_charges(
                raw_charges=raw_charges,
                shipment_context=context,
                quote_currency_hint=quote_currency,
            )

        normalized_charges = _deduplicate_normalized_charges(normalized_charges)

        # Stage 3: Critic/Audit
        if not normalization_failed:
            try:
                audit_result = _audit_extraction(model, text, normalized_charges)
            except Exception as e:
                logger.warning("AI Critic/Audit failed. Proceeding with normalized charges: %s", e, exc_info=True)
                warnings.append(f"AI Critic/Audit failed: {str(e)}")
                audit_result = ExtractionAuditResult(
                    is_safe_to_proceed=False,
                    missed_charges=[],
                    hallucinations_detected=[],
                )
        else:
            audit_result = ExtractionAuditResult(
                is_safe_to_proceed=False,
                missed_charges=[],
                hallucinations_detected=[],
            )

        charge_lines, line_warnings = _build_final_spot_charge_lines(
            normalized_charges=normalized_charges,
            raw_charges=raw_charges,
            quote_currency_hint=quote_currency,
        )
        warnings.extend(line_warnings)


        if audit_result.missed_charges:
            warnings.append("Audit flagged possible missed charges: " + "; ".join(audit_result.missed_charges))
        if audit_result.hallucinations_detected:
            warnings.append(
                "Audit flagged possible hallucinations: "
                + "; ".join(audit_result.hallucinations_detected)
            )
        if not raw_charges:
            warnings.append("No raw charges extracted from input")
        if raw_charges and not normalized_charges:
            warnings.append("Raw charges were extracted but none were normalized")

        success = audit_result.is_safe_to_proceed and not normalization_failed

        return AIRateIntakePipelineResult(
            success=success,
            quote_input=QuoteInputPayload(
                quote_currency=quote_currency,
                charge_lines=charge_lines,
            ),
            warnings=warnings,
            error=None if success else "Extraction audit marked result unsafe to proceed or normalization failed",
            raw_text_length=len(text),
            source_type=source_type,
            model_used=GEMINI_MODEL,
            analysis_text=_build_pipeline_analysis_text(raw_charges, normalized_charges, audit_result),
            quote_currency=quote_currency,
            raw_extracted_charges=raw_charges,
            normalized_charges=normalized_charges,
            extraction_audit=audit_result,
        )
    except Exception as e:
        logger.exception("Multi-agent parse pipeline failed")
        return AIRateIntakePipelineResult(
            success=False,
            error=f"Gemini multi-agent pipeline error: {str(e)}",
            warnings=warnings,
            raw_text_length=len(text),
            source_type=source_type,
            model_used=GEMINI_MODEL,
            quote_currency=quote_currency,
            raw_extracted_charges=raw_charges,
            normalized_charges=normalized_charges,
        )


def _call_gemini_structured(model, prompt: str, response_schema: type[BaseModel], stage_name: str) -> BaseModel:
    """Call Gemini with structured outputs and validate into a Pydantic model."""
    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                },
            )
            if response.parsed is not None:
                return response_schema.model_validate(response.parsed)

            json_text = (response.text or "").strip()
            if not json_text:
                raise ValueError(f"{stage_name}: empty Gemini response")
                
            sanitized = _sanitize_json_text(json_text)
            logger.info(
                "%s attempt %s/%s parsing: raw_len=%s, sanitized_len=%s",
                stage_name,
                attempt + 1,
                MAX_RETRIES + 1,
                len(json_text),
                len(sanitized),
            )
            return response_schema.model_validate(json.loads(sanitized))
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = e
            logger.warning(
                "%s attempt %s/%s structured parse error: %s",
                stage_name,
                attempt + 1,
                MAX_RETRIES + 1,
                e,
            )
        except Exception as e:
            last_error = e
            logger.exception("%s attempt %s/%s Gemini error", stage_name, attempt + 1, MAX_RETRIES + 1)

    raise RuntimeError(f"{stage_name} failed after {MAX_RETRIES + 1} attempts: {last_error}")


def _extract_pdf_text_with_gemini(pdf_content: bytes, context: Optional[dict] = None) -> str:
    """Use Gemini multimodal input to transcribe a PDF when text extraction is insufficient."""
    from django.conf import settings
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured in settings")

    try:
        from google import genai as genai_sdk
    except ImportError as exc:
        raise RuntimeError("google-genai is required for multimodal PDF extraction") from exc

    prompt = (
        "Read this freight rate quote PDF and extract the visible commercial content as plain text.\n"
        "Preserve table rows, charge labels, rates, currencies, units, min charges, validity, and notes.\n"
        "Do not summarize. Do not explain. Do not invent values.\n"
        "Return only the extracted quote content.\n"
    )
    if context:
        prompt += f"\nShipment context for disambiguation only:\n{_dump_json(context)}\n"

    client = genai_sdk.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            prompt,
            genai_sdk.types.Part.from_bytes(data=pdf_content, mime_type="application/pdf"),
        ],
        config={"temperature": 0.1},
    )
    text = _GenAIResponseAdapter(response).text.strip()
    if not text:
        raise RuntimeError("Gemini multimodal PDF extraction returned empty text")
    return text


def _extract_pdf_text_from_page_images_with_gemini(pdf_content: bytes, context: Optional[dict] = None) -> str:
    """Render PDF pages to images and use Gemini to transcribe layout-heavy or scanned documents."""
    from django.conf import settings
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured in settings")

    try:
        from google import genai as genai_sdk
    except ImportError as exc:
        raise RuntimeError("google-genai is required for image-based PDF extraction") from exc

    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for image-based PDF extraction") from exc

    doc = fitz.open(stream=pdf_content, filetype="pdf")
    try:
        page_parts = []
        for page_index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            page_parts.append(
                genai_sdk.types.Part.from_bytes(data=pix.tobytes("png"), mime_type="image/png")
            )
    finally:
        doc.close()

    if not page_parts:
        raise RuntimeError("PDF contains no renderable pages")

    prompt = (
        "You are transcribing a freight quote PDF from page images.\n"
        "Extract the visible commercial content as plain text in reading order.\n"
        "Preserve table rows, line items, currencies, units, validity, surcharges, minimums, notes, and section headers.\n"
        "Do not summarize. Do not infer. Do not omit repeated charge rows.\n"
        "Return only the extracted quote content.\n"
    )
    if context:
        prompt += f"\nShipment context for disambiguation only:\n{_dump_json(context)}\n"

    client = genai_sdk.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, *page_parts],
        config={"temperature": 0.1},
    )
    text = _GenAIResponseAdapter(response).text.strip()
    if not text:
        raise RuntimeError("Gemini page-image PDF extraction returned empty text")
    return text


def extract_rate_quote_text_from_pdf(
    pdf_content: bytes,
    context: Optional[dict] = None,
) -> PDFRateQuoteTextResult:
    """Extract quote text from a PDF using text extraction first, then OCR/document-understanding fallbacks."""
    from .pdf_extraction import extract_text_from_pdf, MIN_EXPECTED_CHARS

    extraction_result = extract_text_from_pdf(pdf_content)
    warnings = list(extraction_result.warnings or [])
    extracted_text = (extraction_result.text or "").strip()
    text_marked_insufficient = any("This may be a scanned PDF" in str(w) for w in warnings)

    if extraction_result.success and len(extracted_text) >= MIN_EXPECTED_CHARS and not text_marked_insufficient:
        return PDFRateQuoteTextResult(
            success=True,
            text=extracted_text,
            warnings=warnings,
            extraction_method=extraction_result.method_used or "PDF_TEXT",
        )

    try:
        ocr_layout_text = _extract_pdf_text_from_page_images_with_gemini(pdf_content, context=context).strip()
        if len(ocr_layout_text) < MIN_EXPECTED_CHARS:
            warnings.append("Gemini OCR/layout PDF extraction returned limited text; review carefully.")
        else:
            warnings = [
                w for w in warnings
                if "This may be a scanned PDF" not in w
            ]
        warnings.append("Used Gemini OCR/layout PDF extraction fallback.")
        return PDFRateQuoteTextResult(
            success=True,
            text=ocr_layout_text,
            warnings=warnings,
            extraction_method="GEMINI_OCR_LAYOUT",
        )
    except Exception as ocr_layout_error:
        warnings.append(f"Gemini OCR/layout fallback unavailable: {ocr_layout_error}")

    try:
        multimodal_text = _extract_pdf_text_with_gemini(pdf_content, context=context).strip()
        if len(multimodal_text) < MIN_EXPECTED_CHARS:
            warnings.append("Gemini multimodal PDF extraction returned limited text; review carefully.")
        else:
            warnings = [
                w for w in warnings
                if "This may be a scanned PDF" not in w
            ]
        warnings.append("Used Gemini multimodal PDF extraction fallback.")
        return PDFRateQuoteTextResult(
            success=True,
            text=multimodal_text,
            warnings=warnings,
            extraction_method="GEMINI_MULTIMODAL",
        )
    except Exception as multimodal_error:
        if extraction_result.success and extracted_text:
            warnings.append(f"Gemini multimodal fallback unavailable: {multimodal_error}")
            return PDFRateQuoteTextResult(
                success=True,
                text=extracted_text,
                warnings=warnings,
                extraction_method=extraction_result.method_used or "PDF_TEXT",
            )
        return PDFRateQuoteTextResult(
            success=False,
            text="",
            warnings=warnings,
            error=extraction_result.error or str(multimodal_error),
            extraction_method="PDF_TEXT",
        )


def _extract_raw_charges(model, text: str, shipment_context: Optional[dict] = None) -> List[RawExtractedCharge]:
    """Agent 1 (Extractor): prompt Gemini to extract verbatim raw charge candidates."""
    prompt = _build_extractor_prompt(text=text, shipment_context=shipment_context)
    envelope = _call_gemini_structured(model, prompt, _RawExtractedChargesEnvelope, "Extractor")
    return envelope.charges


def _normalize_charges(
    model,
    raw_charges: List[RawExtractedCharge],
    shipment_context: Optional[dict] = None,
    quote_currency_hint: Optional[str] = None,
) -> List[NormalizedCharge]:
    """Agent 2 (Normalizer): map raw charges to canonical V4 codes."""
    prompt = _build_normalizer_prompt(
        raw_charges=raw_charges,
        shipment_context=shipment_context,
        quote_currency_hint=quote_currency_hint,
    )
    envelope = _call_gemini_structured(model, prompt, _NormalizedChargesEnvelope, "Normalizer")
    return envelope.charges


def _audit_extraction(
    model,
    original_text: str,
    normalized_charges: List[NormalizedCharge],
) -> ExtractionAuditResult:
    """Agent 3 (Critic): detect missed charges and hallucinations."""
    prompt = _build_audit_prompt(original_text=original_text, normalized_charges=normalized_charges)
    return _call_gemini_structured(model, prompt, ExtractionAuditResult, "Critic")


def _build_extractor_prompt(text: str, shipment_context: Optional[dict] = None) -> str:
    context_json = _dump_json(shipment_context or {})
    return f"""You are Agent 1 (Extractor) in a multi-agent rate extraction pipeline.

Rules:
- ONLY extract data explicitly present in the email/text.
- Preserve raw_label and raw_amount_string verbatim.
- Preserve source evidence: source_excerpt should be the shortest exact source snippet supporting the charge; source_line_number is one-based when available; source_line_identity should be a stable visible row/key when available.
- Do NOT normalize labels, map codes, infer buckets, or infer unit basis.
- MUST extract every charge-like line matching "<label>:<currency><amount>", including short labels such as "DOC", "CUS", "A/F", and "Handle".
- MUST extract colon-rated charges even when the unit is missing. Preserve the visible amount; the normalizer will default missing units to PER_SHIPMENT.
- MUST NOT drop a charge because it contains parenthetical text, e.g. "(for small cargo)". Preserve that text in raw_amount_string.
- Set is_conditional=true only when the text indicates optional/conditional wording (e.g., if applicable, subject to, optional).
- Descriptive qualifiers like "for small cargo" or "dangerous goods" are NOT conditional — they are notes about applicability.
- currency_hint is optional and should only be included if directly visible in the same charge text.

Freight rate notation guide (preserve these verbatim in raw_amount_string):
- "USD6.8/kg(+45kgs)" → raw_amount_string="USD6.8/kg(+45kgs)", currency_hint="USD"
- "USD 3.50/kg +100kg" → raw_amount_string="USD 3.50/kg +100kg", currency_hint="USD"
- "AUD 2.80 per kg min 50kg" → raw_amount_string="AUD 2.80 per kg min 50kg", currency_hint="AUD"
- "Handle:USD50(for small cargo)" → raw_label="Handle", raw_amount_string="USD50(for small cargo)", currency_hint="USD"
- "DOC:USD30" → raw_label="DOC", raw_amount_string="USD30", currency_hint="USD"
- "Pick Up+Gate In:USD200" → raw_label="Pick Up+Gate In", raw_amount_string="USD200", currency_hint="USD"
- The primary numeric value before /kg is the RATE. Do NOT split or recalculate it.

Shipment context (reference only; do not infer values from it):
{context_json}

Return structured JSON matching the schema: {{ \"charges\": [RawExtractedCharge, ...] }}.

Source text:
---
{text}
---
"""


def _build_normalizer_prompt(
    raw_charges: List[RawExtractedCharge],
    shipment_context: Optional[dict] = None,
    quote_currency_hint: Optional[str] = None,
) -> str:
    context_payload = dict(shipment_context or {})
    if quote_currency_hint:
        context_payload["quote_currency_hint"] = quote_currency_hint
    return f"""You are Agent 2 (Normalizer) in a multi-agent rate extraction pipeline.

Task:
- Convert each RawExtractedCharge into a NormalizedCharge.
- Map to canonical v4 product codes and buckets.
- Parse amount and currency from raw_amount_string.
- Preserve row order and emit one normalized row per raw row.

Critical confidence rule:
- If you are not at least 90% confident in the v4 product mapping, set v4_product_code to UNMAPPED and confidence to LOW.
- Prefer UNMAPPED over guessing.

Freight rate parsing (CRITICAL — read carefully):
- Expressions like "USD6.8/kg", "USD 3.50/kg", "AUD2.80 per kg" are PER_KG rates.
  The numeric value BEFORE /kg IS the rate. Example: "USD6.8/kg" → amount=6.80, rate_per_unit=6.80, unit_basis=PER_KG.
- Weight-break annotations like "(+45kgs)", "+100kg", "min 50kg" after a /kg rate indicate the
  minimum chargeable weight threshold or rating break (e.g., "for shipments over 50kg"), NOT a minimum charge amount.
  They should be IGNORED for amount/rate parsing — they are operational notes, not pricing values.
- Do NOT confuse weight-break thresholds with minimum charge amounts.
  "USD6.8/kg(+45kgs)" means rate=6.80 per kg with a 45kg weight break. It does NOT mean min_amount=6.80.
- Only use MIN_OR_PER_KG when the text explicitly states BOTH a flat minimum charge AND a per-kg rate
  (e.g., "min USD 50 or 2.10/kg"). If only one number is present (e.g., "6.8/kg"), it is ALWAYS PER_KG.
- NEVER invent or hallucinate rate values from these examples. Only use numbers found in the source text.

Additional rules:
- EXACTLY categorise percentage fees (e.g. "10% of freight") as PERCENTAGE.
- currency must be a 3-letter code. Use quote_currency_hint only when the charge text lacks an explicit currency.
- amount must be numeric and non-negative.
- If raw_amount_string has a currency and amount but no explicit unit (e.g. "USD50"), set unit_basis to PER_SHIPMENT.
- Parenthetical descriptive text in raw_amount_string is note/context, not a reason to drop the charge.
- Non-charge business rules (e.g. "Import GST to be 9% of Commercial Invoice" or payment terms), terms/conditions, signatures, or section headers are NOT standard cargo charges. You MUST map them with `v4_product_code = "UNMAPPED"` and set `confidence = LOW` so they remain reviewable and are not processed as regular flat/percentage charges. Do NOT invent a standard amount for them.
- For PERCENTAGE, set unit_basis to PERCENTAGE, populate `percentage` and `percent_applies_to` (and set `amount` to the same numeric percentage value).
- For MIN_OR_PER_KG, set unit_basis to MIN_OR_PER_KG, populate both `rate_per_unit` and `minimum_amount` (and set `amount` equal to `rate_per_unit`).
- confidence must be HIGH or LOW only.
- friendly_description: Create a clean, professional display name for the charge. Map common abbreviations to full names:
  * A/F, FRT, FREIGHT -> Air Freight
  * CUS, CLEARANCE, CLEANING -> Customs Clearance
  * DOC, DOCUMENTATION -> Documentation Fee
  * THC, TERMINAL -> Terminal Handling Charge
  * HANDLE, HANDLING -> Handling Fee
  * PICKUP, PICK UP, TRUCKING -> Pickup Charge
  * GATE IN -> Gate In Fee
  If the raw label is already professional, preserve it.
- CONTEXTUAL MAPPING: If `missing_components` is provided in the Context, you MUST prefer mapping charges to those buckets (e.g. DESTINATION_LOCAL -> DESTINATION, ORIGIN_LOCAL -> ORIGIN, FREIGHT -> FREIGHT). If only one component is present in `missing_components` (e.g. just DESTINATION_LOCAL), you MUST map ALL charges in the email to that single bucket, because we know the agent is strictly pricing that leg.

Shipment context:
{_dump_json(context_payload)}

Raw charges:
{_dump_json([c.model_dump(mode="json") for c in raw_charges])}

Return structured JSON matching the schema: {{ \"charges\": [NormalizedCharge, ...] }}.
"""


def _build_audit_prompt(original_text: str, normalized_charges: List[NormalizedCharge]) -> str:
    return f"""You are Agent 3 (Critic) in a multi-agent rate extraction pipeline.

Compare the original text against the normalized charges and audit for quality issues.

Tasks:
- List missed charges that appear in the text but are not represented.
- List hallucinations_detected where normalized output is unsupported by the text.
- Set is_safe_to_proceed=false if hallucinations are present or important charges are missing.
- Be conservative and concise.

Original text:
---
{original_text}
---

Normalized charges:
{_dump_json([c.model_dump(mode="json") for c in normalized_charges])}

Return structured JSON matching ExtractionAuditResult only.
"""


def _build_final_spot_charge_lines(
    normalized_charges: List[NormalizedCharge],
    raw_charges: List[RawExtractedCharge],
    quote_currency_hint: Optional[str] = None,
) -> tuple[List[SpotChargeLine], List[str]]:
    """Convert normalized charges into final validated SpotChargeLine objects."""
    warnings: List[str] = []
    lines: List[SpotChargeLine] = []

    raw_by_label: dict[str, List[RawExtractedCharge]] = {}
    for raw in raw_charges:
        raw_by_label.setdefault(raw.raw_label, []).append(raw)

    for i, normalized in enumerate(normalized_charges, start=1):
        candidates = raw_by_label.get(normalized.original_raw_label, [])
        raw_match = candidates.pop(0) if candidates else None

        payload = {
            "bucket": normalized.v4_bucket,
            "description": normalized.friendly_description or normalized.original_raw_label,
            "original_raw_label": normalized.original_raw_label,
            "v4_product_code": normalized.v4_product_code,
            "v4_bucket": normalized.v4_bucket,
            "unit_basis": normalized.unit_basis,
            "currency": _normalize_currency_value(normalized.currency) or quote_currency_hint,
            "conditional": raw_match.is_conditional if raw_match else False,
            "normalization_confidence": normalized.confidence,
            "confidence": 0.95 if normalized.confidence == "HIGH" else 0.35,
        }
        if raw_match:
            payload["source_excerpt"] = raw_match.source_excerpt or (
                f"{raw_match.raw_label}: {raw_match.raw_amount_string}".strip()
            )
            payload["source_line_number"] = raw_match.source_line_number
            payload["source_line_identity"] = raw_match.source_line_identity
            
            raw_notes = _extract_parenthetical_notes(raw_match.raw_amount_string)
            notes_parts = []
            if raw_notes:
                notes_parts.append(raw_notes)
            if getattr(raw_match, "raw_notes", None):
                notes_parts.append(raw_match.raw_notes)
            
            # Check for POA in raw minimum or raw amount string to mark review warning
            raw_amt_lower = (raw_match.raw_amount_string or "").lower()
            raw_min_lower = (raw_match.raw_minimum or "").lower()
            if "poa" in raw_amt_lower or "poa" in raw_min_lower:
                notes_parts.append("POA - manual review required")
                
            if notes_parts:
                payload["notes"] = "; ".join(notes_parts)[:500]

        if normalized.unit_basis == "PER_SHIPMENT":
            payload["amount"] = normalized.amount
        elif normalized.unit_basis == "PER_KG":
            payload["rate_per_unit"] = normalized.rate_per_unit or normalized.amount
        elif normalized.unit_basis == "PERCENTAGE":
            payload["percentage"] = normalized.percentage if normalized.percentage is not None else normalized.amount
            payload["percent_applies_to"] = normalized.percent_applies_to or normalized.v4_bucket
            if normalized.percent_applies_to is None:
                warnings.append(
                    f"Line {i}: percent_applies_to missing for '{normalized.original_raw_label}', defaulted to bucket"
                )
        elif normalized.unit_basis == "MIN_OR_PER_KG":
            payload["rate_per_unit"] = normalized.rate_per_unit or normalized.amount
            if normalized.minimum_amount is not None:
                payload["minimum"] = normalized.minimum_amount
            else:
                warnings.append(
                    f"Line {i}: minimum_amount missing for MIN_OR_PER_KG '{normalized.original_raw_label}'"
                )

        if normalized.v4_product_code == "UNMAPPED":
            warnings.append(f"Line {i}: Unmapped charge '{normalized.original_raw_label}'")
        if normalized.confidence == "LOW":
            warnings.append(f"Line {i}: Low-confidence normalization for '{normalized.original_raw_label}'")

        try:
            line = SpotChargeLine(**payload)
            lines.append(line)
            warnings.extend(line.get_warnings())
        except Exception as e:
            warnings.append(f"Line {i} validation failed after normalization: {str(e)}")
            logger.warning("Final SpotChargeLine validation failed on line %s: %s", i, e)

    return lines, warnings


def _build_pipeline_analysis_text(
    raw_charges: List[RawExtractedCharge],
    normalized_charges: List[NormalizedCharge],
    audit_result: ExtractionAuditResult,
) -> str:
    return (
        f"Extractor={len(raw_charges)} raw charges. "
        f"Normalizer={len(normalized_charges)} normalized charges. "
        f"Critic safe_to_proceed={audit_result.is_safe_to_proceed}. "
        f"Missed={len(audit_result.missed_charges)}. "
        f"Hallucinations={len(audit_result.hallucinations_detected)}."
    )


def _dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, default=str)


def parse_pdf_rate_quote(pdf_content: bytes, context: Optional[dict] = None) -> AIRateIntakePipelineResult:
    """
    Extract text from PDF and parse into charge lines.
    
    Combines PDF extraction with AI parsing in one call.
    """
    extraction_result = extract_rate_quote_text_from_pdf(pdf_content, context=context)

    if not extraction_result.success:
        return AIRateIntakePipelineResult(
            success=False,
            error=extraction_result.error or "PDF extraction failed",
            raw_text_length=0,
            source_type="PDF",
            model_used=GEMINI_MODEL,
        )
    
    # Step 2: Parse extracted text with AI
    result = parse_rate_quote_text(extraction_result.text, source_type="PDF", context=context)
    
    # Add any PDF extraction warnings
    if extraction_result.warnings:
        result.warnings = extraction_result.warnings + result.warnings
    
    return result
