"""
AI Rate Intake Service

Uses Google Gemini (configurable model; defaults to Gemini 2.5 Flash Lite)
to parse unstructured rate quotes into structured charge lines.

Architecture Principles:
- AI is input accelerator only — does NOT make pricing decisions
- AI output MUST pass Pydantic validation
- AI never writes directly to database
- All output requires human acceptance
"""

import json
import logging
import os
import re
from collections import Counter
from typing import Optional, List

from pydantic import BaseModel, Field, ValidationError

from .ai_intake_schemas import (
    ExtractionAuditResult,
    NormalizedCharge,
    RawExtractedCharge,
    SpotChargeLine,
    VALID_CURRENCIES,
)

logger = logging.getLogger(__name__)
_LEGACY_SDK_WARNING_EMITTED = False

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


class _RawExtractedChargesEnvelope(BaseModel):
    charges: List[RawExtractedCharge] = Field(default_factory=list)


class _NormalizedChargesEnvelope(BaseModel):
    charges: List[NormalizedCharge] = Field(default_factory=list)


class AIRateIntakePipelineResult(BaseModel):
    """Service return shape kept compatible with existing API formatters."""

    success: bool
    lines: List[SpotChargeLine] = Field(default_factory=list)
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
    codes = re.findall(r"\b[A-Z]{3}\b", upper)
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


def get_gemini_client():
    """Get configured Gemini client. Returns None if not configured."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set")
        return None

    try:
        from google import genai as genai_sdk
        return _GenAIClientAdapter(genai_sdk, api_key)
    except ImportError as genai_import_error:
        # Backward-compatibility fallback for environments that still have
        # `google-generativeai` installed instead of `google-genai`.
        try:
            import google.generativeai as legacy_genai_sdk
        except ImportError as legacy_import_error:
            logger.error(
                "Gemini SDK import failed (google-genai: %s, google-generativeai: %s)",
                genai_import_error,
                legacy_import_error,
            )
            return None

        try:
            legacy_genai_sdk.configure(api_key=api_key)
        except Exception as config_error:
            logger.error("Failed configuring google-generativeai client: %s", config_error)
            return None

        global _LEGACY_SDK_WARNING_EMITTED
        if not _LEGACY_SDK_WARNING_EMITTED:
            logger.warning(
                "Using deprecated google-generativeai fallback. "
                "Install `google-genai` for the preferred Gemini client."
            )
            _LEGACY_SDK_WARNING_EMITTED = True

        return legacy_genai_sdk


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
                "Gemini API not configured. Set GEMINI_API_KEY and install "
                "`google-genai` (or `google-generativeai` as legacy fallback)."
            ),
            raw_text_length=len(text),
            source_type=source_type,
            model_used=GEMINI_MODEL,
        )

    quote_currency = _infer_quote_currency_from_text(text)
    warnings: List[str] = []

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)

        raw_charges = _extract_raw_charges(model, text, shipment_context=context)
        normalized_charges = _normalize_charges(
            model,
            raw_charges,
            shipment_context=context,
            quote_currency_hint=quote_currency,
        )
        audit_result = _audit_extraction(model, text, normalized_charges)

        lines, line_warnings = _build_final_spot_charge_lines(
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

        return AIRateIntakePipelineResult(
            success=audit_result.is_safe_to_proceed,
            lines=lines,
            warnings=warnings,
            error=None if audit_result.is_safe_to_proceed else "Extraction audit marked result unsafe to proceed",
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
            return response_schema.model_validate(json.loads(json_text))
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
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")

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


def extract_rate_quote_text_from_pdf(
    pdf_content: bytes,
    context: Optional[dict] = None,
) -> PDFRateQuoteTextResult:
    """Extract quote text from a PDF using text extraction first, then Gemini multimodal fallback."""
    from .pdf_extraction import extract_text_from_pdf, MIN_EXPECTED_CHARS

    extraction_result = extract_text_from_pdf(pdf_content)
    warnings = list(extraction_result.warnings or [])
    extracted_text = (extraction_result.text or "").strip()

    if extraction_result.success and len(extracted_text) >= MIN_EXPECTED_CHARS:
        return PDFRateQuoteTextResult(
            success=True,
            text=extracted_text,
            warnings=warnings,
            extraction_method=extraction_result.method_used or "PDF_TEXT",
        )

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
- Do NOT normalize labels, map codes, infer buckets, or infer unit basis.
- Set is_conditional=true only when the text indicates optional/conditional wording (e.g., if applicable, subject to, optional).
- currency_hint is optional and should only be included if directly visible in the same charge text.

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

Additional rules:
- EXACTLY categorise dual pricing (e.g. "min X or Y/kg", "35 min / 0.25 pkg") as MIN_OR_PER_KG.
- EXACTLY categorise percentage fees (e.g. "10% of freight") as PERCENTAGE.
- currency must be a 3-letter code. Use quote_currency_hint only when the charge text lacks an explicit currency.
- amount must be numeric and non-negative.
- For PERCENTAGE, set unit_basis to PERCENTAGE, populate `percentage` and `percent_applies_to` (and set `amount` to the same numeric percentage value).
- For MIN_OR_PER_KG, set unit_basis to MIN_OR_PER_KG, populate both `rate_per_unit` and `minimum_amount` (and set `amount` equal to `rate_per_unit`).
- confidence must be HIGH or LOW only.
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
            "description": normalized.original_raw_label,
            "original_raw_label": normalized.original_raw_label,
            "v4_product_code": normalized.v4_product_code,
            "v4_bucket": normalized.v4_bucket,
            "unit_basis": normalized.unit_basis,
            "currency": _normalize_currency_value(normalized.currency) or quote_currency_hint,
            "conditional": raw_match.is_conditional if raw_match else False,
            "normalization_confidence": normalized.confidence,
            "confidence": 0.95 if normalized.confidence == "HIGH" else 0.35,
        }

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
