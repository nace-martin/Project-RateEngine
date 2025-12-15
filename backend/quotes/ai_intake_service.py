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
from decimal import Decimal, InvalidOperation
from typing import Optional, List

from .ai_intake_schemas import (
    SpotChargeLine,
    AIRateIntakeResponse,
    VALID_CURRENCIES,
)

logger = logging.getLogger(__name__)

# Gemini model configuration
GEMINI_MODEL = "gemini-2.0-flash-exp"
MAX_RETRIES = 2


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
    source_type: str = "TEXT"
) -> AIRateIntakeResponse:
    """
    Parse unstructured rate quote text into structured charge lines.
    
    Args:
        text: Extracted text from agent quote (email, PDF, etc.)
        source_type: Source document type (TEXT, PDF, EMAIL)
        
    Returns:
        AIRateIntakeResponse with validated charge lines
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
    prompt = _build_extraction_prompt(text)
    
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


def _build_extraction_prompt(text: str) -> str:
    """Build the prompt for Gemini to extract charge lines."""
    
    return f'''You are an air freight rate extraction assistant. Extract charge lines from the following rate quote text.

IMPORTANT RULES:
1. Extract ONLY charges that appear in the text
2. Do NOT invent or assume charges that aren't explicitly mentioned
3. Categorize each charge into one of these buckets:
   - ORIGIN: Pickup, collection, export clearance, export agency, export documentation
   - FREIGHT: Air freight, fuel surcharge on freight, security surcharge
   - DESTINATION: Delivery, import clearance, import agency, import documentation, handling
4. Identify the unit basis:
   - PER_KG: Charged per kilogram (e.g., "$2.50/kg")
   - PER_SHIPMENT: Flat fee per shipment (e.g., "$150.00")
   - PERCENTAGE: Percentage of another charge (e.g., "10% of freight")
5. For PERCENTAGE charges, you MUST specify what it applies to in percent_applies_to
6. Extract currency codes (AUD, USD, PGK, etc.)
7. Extract minimum and maximum charges if mentioned

OUTPUT FORMAT (JSON array):
{{
  "lines": [
    {{
      "bucket": "ORIGIN" | "FREIGHT" | "DESTINATION",
      "description": "string - the charge name",
      "amount": "decimal or null for percentages",
      "currency": "3-letter code or null for percentages",
      "unit_basis": "PER_KG" | "PER_SHIPMENT" | "PERCENTAGE",
      "percentage": "decimal (0-100) if percentage-based, else null",
      "minimum": "decimal or null",
      "maximum": "decimal or null",
      "percent_applies_to": "what this percentage is based on, required for PERCENTAGE"
    }}
  ]
}}

RATE QUOTE TEXT:
---
{text}
---

Extract all charges and return ONLY valid JSON. If no charges found, return {{"lines": []}}'''


def _validate_ai_response(
    parsed: dict,
    original_text: str,
    source_type: str
) -> AIRateIntakeResponse:
    """Validate AI response and convert to Pydantic models."""
    
    warnings: List[str] = []
    validated_lines: List[SpotChargeLine] = []
    
    lines_data = parsed.get("lines", [])
    
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
            # Convert string decimals to Decimal
            if line_data.get("amount"):
                try:
                    line_data["amount"] = Decimal(str(line_data["amount"]))
                except (InvalidOperation, ValueError):
                    line_data["amount"] = None
                    warnings.append(f"Line {i+1}: Invalid amount format")
            
            if line_data.get("percentage"):
                try:
                    line_data["percentage"] = Decimal(str(line_data["percentage"]))
                except (InvalidOperation, ValueError):
                    line_data["percentage"] = None
                    warnings.append(f"Line {i+1}: Invalid percentage format")
            
            if line_data.get("minimum"):
                try:
                    line_data["minimum"] = Decimal(str(line_data["minimum"]))
                except (InvalidOperation, ValueError):
                    line_data["minimum"] = None
            
            if line_data.get("maximum"):
                try:
                    line_data["maximum"] = Decimal(str(line_data["maximum"]))
                except (InvalidOperation, ValueError):
                    line_data["maximum"] = None
            
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
        warnings=warnings,
        raw_text_length=len(original_text),
        source_type=source_type,
        model_used=GEMINI_MODEL
    )


def parse_pdf_rate_quote(pdf_content: bytes) -> AIRateIntakeResponse:
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
    result = parse_rate_quote_text(extraction_result.text, source_type="PDF")
    
    # Add any PDF extraction warnings
    if extraction_result.warnings:
        result.warnings = extraction_result.warnings + result.warnings
    
    return result
