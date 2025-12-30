"""
AI Rate Intake Service

Uses Google Gemini 2.0 Flash to parse unstructured rate quotes into structured charge lines.

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
from decimal import Decimal, InvalidOperation
from typing import Optional, List

from .ai_intake_schemas import (
    SpotChargeLine,
    AIRateIntakeResponse,
    VALID_CURRENCIES,
)

logger = logging.getLogger(__name__)

# Gemini model configuration
GEMINI_MODEL = "gemini-2.0-flash-lite"
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
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai not installed")
        return None
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set")
        return None
    
    genai.configure(api_key=api_key)
    return genai


def parse_rate_quote_text(
    text: str,
    source_type: str = "TEXT",
    context: Optional[dict] = None
) -> AIRateIntakeResponse:
    """
    Parse unstructured rate quote text into structured charge lines and provide analysis.
    
    Args:
        text: Extracted text from agent quote (email, PDF, etc.)
        source_type: Source document type (TEXT, PDF, EMAIL)
        context: Optional dictionary with quote details (origin, dest, weight, etc.)
        
    Returns:
        AIRateIntakeResponse with validated charge lines and pricing analysis
    """
    
    if not text or len(text.strip()) < 10:
        return AIRateIntakeResponse(
            success=False,
            error="Input text is too short to parse",
            raw_text_length=len(text) if text else 0,
            source_type=source_type
        )
    
    genai = get_gemini_client()
    if not genai:
        return AIRateIntakeResponse(
            success=False,
            error="Gemini API not configured. Set GEMINI_API_KEY environment variable.",
            raw_text_length=len(text),
            source_type=source_type
        )
    
    # Build the extraction prompt
    prompt = _build_extraction_prompt(text, context)
    
    # Try extraction with retries
    for attempt in range(MAX_RETRIES + 1):
        try:
            model = genai.GenerativeModel(GEMINI_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,  # Low temperature for consistent output
                    "response_mime_type": "application/json",
                }
            )
            
            # Parse JSON response
            json_text = response.text.strip()
            parsed = json.loads(json_text)
            
            # Validate and convert to Pydantic models
            return _validate_ai_response(parsed, text, source_type)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Attempt {attempt + 1}: JSON decode error: {e}")
            if attempt == MAX_RETRIES:
                return AIRateIntakeResponse(
                    success=False,
                    error=f"Failed to parse AI response as JSON after {MAX_RETRIES + 1} attempts",
                    raw_text_length=len(text),
                    source_type=source_type,
                    model_used=GEMINI_MODEL
                )
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: Gemini API error")
            if attempt == MAX_RETRIES:
                return AIRateIntakeResponse(
                    success=False,
                    error=f"Gemini API error: {str(e)}",
                    raw_text_length=len(text),
                    source_type=source_type,
                    model_used=GEMINI_MODEL
                )
    
    # Should not reach here
    return AIRateIntakeResponse(
        success=False,
        error="Unexpected error in rate parsing",
        raw_text_length=len(text),
        source_type=source_type
    )


def _build_extraction_prompt(text: str, context: Optional[dict] = None) -> str:
    """Build the prompt for Gemini to act as an Assistive Reviewer for agent rate replies."""
    
    context_str = ""
    if context:
        context_str = f"""
SHIPMENT CONTEXT:
- From: {context.get('origin', 'Unknown')} ({context.get('origin_code', 'Unknown')})
- To: {context.get('destination', 'Unknown')} ({context.get('destination_code', 'Unknown')})
- Weight: {context.get('weight', 'Unknown')} kg
- Shipment Type: {context.get('shipment_type', 'Unknown')}
- Incoterm: {context.get('incoterm', 'Unknown')}
- Payment: {context.get('payment_term', 'Unknown')}
- TARGET COMPONENTS (MISSING IN DB): {", ".join(context.get('missing_components', []))}
"""

    return f'''You are an expert Air Freight Assistive Reviewer. Your job is to interpret an agent's rate reply and identify the specific charges we are missing for this shipment.

{context_str}

TASKS:
1. **Identify Missing Charges**: We already have standard rates for some parts of this shipment. We are SPECIFICALLY looking for the "TARGET COMPONENTS" listed above.
2. **Determine Applicability**: Based on the context, decide if the agent's charges apply to the ORIGIN or DESTINATION. 
   - Example: If the agent is in Singapore (SIN) and SIN is the Destination, their local charges (Delivery, Clearance, Terminal) are DESTINATION charges.
3. **Interpret Meaning**: Read the email/text to understand what is explicitly confirmed and what is conditional.
4. **Structured Checklist**: Provide a 3-4 sentence "Analyst Review" that says exactly what was found and what is still missing.

EXTRACTION RULES:
1. Extract individual charges into the `lines` array.
2. Categorize into ORIGIN, FREIGHT, or DESTINATION.
3. Identify unit_basis using these options:
   - **PER_KG**: Simple per-kg rate. Use `rate_per_unit` for the per-kg rate.
   - **PER_SHIPMENT**: Flat fee per shipment. Use `amount` for the flat amount.
   - **PERCENTAGE**: Percentage of another charge. Use `percentage` and `percent_applies_to`.
   - **MIN_OR_PER_KG**: Dual pricing like "35.00 min or 0.25 per kg". Use BOTH `minimum` (the floor) AND `rate_per_unit` (the per-kg rate). The final charge is MAX(minimum, rate_per_unit * weight).
4. For PERCENTAGE, specify what it applies to (e.g., "Commercial Invoice", "FREIGHT").

OUTPUT FORMAT (JSON):
{{
  "analysis_text": "✅ Confirmed: ... \\n⚠️ Conditional: ... \\n❌ Missing: ...",
  "quote_currency": "Default currency code (e.g. SGD) if stated globally",
  "lines": [
    {{
      "bucket": "ORIGIN" | "FREIGHT" | "DESTINATION",
      "description": "string (charge name)",
      "amount": number | null (for PER_SHIPMENT flat fees),
      "rate_per_unit": number | null (for PER_KG or MIN_OR_PER_KG per-kg rate),
      "currency": "3-letter code (optional if quote_currency is set)",
      "unit_basis": "PER_KG" | "PER_SHIPMENT" | "PERCENTAGE" | "MIN_OR_PER_KG",
      "percentage": number | null (for PERCENTAGE only),
      "minimum": number | null (floor amount for MIN_OR_PER_KG),
      "maximum": number | null (ceiling if applicable),
      "percent_applies_to": "string" | null (for PERCENTAGE only),
      "conditional": boolean (true if charge is 'if applicable' or option)
    }}
  ]
}}

EXAMPLES:
- "Terminal Fee: 35.00 min or 0.25 per KGS" → unit_basis="MIN_OR_PER_KG", minimum=35.00, rate_per_unit=0.25
- "Handling: 50.00 per shpt" → unit_basis="PER_SHIPMENT", amount=50.00
- "Airfreight: 6.80/kg" → unit_basis="PER_KG", rate_per_unit=6.80
- "GST: 9% of Commercial Invoice" → unit_basis="PERCENTAGE", percentage=9, percent_applies_to="Commercial Invoice"

AGENT RATE REPLY TEXT:
---
{text}
---

Return ONLY valid JSON. Focus on accuracy and risk prevention. If the email is vague, flag it clearly in the analysis_text.'''


def _validate_ai_response(
    parsed: dict,
    original_text: str,
    source_type: str
) -> AIRateIntakeResponse:
    """Validate AI response and convert to Pydantic models."""
    
    warnings: List[str] = []
    validated_lines: List[SpotChargeLine] = []
    
    lines_data = parsed.get("lines", [])
    analysis_text = parsed.get("analysis_text", "")
    quote_currency = _normalize_currency_value(parsed.get("quote_currency"))
    if not quote_currency:
        quote_currency = _infer_quote_currency_from_text(original_text)
    
    if not isinstance(lines_data, list):
        return AIRateIntakeResponse(
            success=False,
            error="AI response 'lines' is not an array",
            raw_text_length=len(original_text),
            source_type=source_type,
            model_used=GEMINI_MODEL
        )
    
    for i, line_data in enumerate(lines_data):
        try:
            if line_data.get("currency"):
                line_data["currency"] = _normalize_currency_value(line_data.get("currency"))

            # Convert string decimals or numbers to Decimal
            for field in ["amount", "rate_per_unit", "percentage", "minimum", "maximum"]:
                if line_data.get(field) is not None:
                    try:
                        line_data[field] = Decimal(str(line_data[field]))
                    except (InvalidOperation, ValueError):
                        line_data[field] = None
                        warnings.append(f"Line {i+1}: Invalid {field} format")
            
            # Validate with Pydantic
            validated_line = SpotChargeLine(**line_data)
            validated_lines.append(validated_line)
            
            # Collect any warnings from the line
            line_warnings = validated_line.get_warnings()
            warnings.extend(line_warnings)
            
        except Exception as e:
            warnings.append(f"Line {i+1} validation failed: {str(e)}")
            logger.warning(f"Failed to validate line {i+1}: {e}")
    
    return AIRateIntakeResponse(
        success=True,
        lines=validated_lines,
        analysis_text=analysis_text,
        warnings=warnings,
        quote_currency=quote_currency,
        raw_text_length=len(original_text),
        source_type=source_type,
        model_used=GEMINI_MODEL
    )


def parse_pdf_rate_quote(pdf_content: bytes, context: Optional[dict] = None) -> AIRateIntakeResponse:
    """
    Extract text from PDF and parse into charge lines.
    
    Combines PDF extraction with AI parsing in one call.
    """
    from .pdf_extraction import extract_text_from_pdf
    
    # Step 1: Extract text from PDF
    extraction_result = extract_text_from_pdf(pdf_content)
    
    if not extraction_result.success:
        return AIRateIntakeResponse(
            success=False,
            error=extraction_result.error or "PDF extraction failed",
            raw_text_length=0,
            source_type="PDF"
        )
    
    # Step 2: Parse extracted text with AI
    result = parse_rate_quote_text(extraction_result.text, source_type="PDF", context=context)
    
    # Add any PDF extraction warnings
    if extraction_result.warnings:
        result.warnings = extraction_result.warnings + result.warnings
    
    return result
