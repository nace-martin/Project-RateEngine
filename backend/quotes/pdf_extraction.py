"""
PDF Text Extraction Service

Extracts text from PDF documents for AI rate intake.
Uses pdfplumber as primary extractor with pymupdf as fallback.

Architecture Principles:
- Deterministic text extraction (no AI in this step)
- AI receives only extracted text, never raw PDFs
- Warn user if extraction quality is low
"""

import io
import logging
from typing import Optional
import re

from .ai_intake_schemas import PDFExtractionResult

logger = logging.getLogger(__name__)

# Minimum characters expected from a rate quote PDF
MIN_EXPECTED_CHARS = 50

# If text extraction yields less than this ratio of expected content, try OCR
LOW_TEXT_THRESHOLD = 0.3

_CURRENCY_OR_RATE_PATTERN = re.compile(
    r"\b(?:USD|AUD|PGK|SGD|NZD|EUR|GBP|HKD|JPY|CNY|PHP|IDR|MYR|THB|INR)\b|\b\d+(?:\.\d+)?\s*(?:/kg|kg|%|\bflat\b)",
    re.IGNORECASE,
)


def extract_text_from_pdf(pdf_content: bytes) -> PDFExtractionResult:
    """
    Extract text from PDF bytes.
    
    Strategy:
    1. Try pdfplumber (best for digital PDFs)
    2. Fallback to pymupdf (alternative extraction)
    3. If both yield minimal text, warn about possible scanned PDF
    
    Args:
        pdf_content: Raw PDF bytes
        
    Returns:
        PDFExtractionResult with extracted text and metadata
    """
    
    result = _extract_with_pdfplumber(pdf_content)
    if result.success and _is_text_sufficient(result.text):
        return result

    logger.info("pdfplumber extraction insufficient, trying pymupdf")
    result_pymupdf = _extract_with_pymupdf(pdf_content)

    result = _choose_better_result(result, result_pymupdf)

    if not _is_text_sufficient(result.text):
        result.warnings.append(
            "Very little text extracted. This may be a scanned PDF. "
            "Consider using OCR or manually entering the rates."
        )

    return result


def _normalize_extracted_text(text: str) -> str:
    lines = [line.rstrip() for line in (text or "").splitlines()]
    collapsed: list[str] = []
    blank_streak = 0
    for line in lines:
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if not cleaned:
            blank_streak += 1
            if blank_streak <= 1:
                collapsed.append("")
            continue
        blank_streak = 0
        collapsed.append(cleaned)
    return "\n".join(collapsed).strip()


def _text_quality_score(text: str) -> float:
    normalized = _normalize_extracted_text(text)
    if not normalized:
        return 0.0
    char_score = min(len(normalized) / max(MIN_EXPECTED_CHARS, 1), 2.0)
    line_count = len([line for line in normalized.splitlines() if line.strip()])
    line_score = min(line_count / 8.0, 1.5)
    signal_matches = len(_CURRENCY_OR_RATE_PATTERN.findall(normalized))
    signal_score = min(signal_matches / 4.0, 2.0)
    return char_score + line_score + signal_score


def _is_text_sufficient(text: str) -> bool:
    normalized = _normalize_extracted_text(text)
    return len(normalized) >= MIN_EXPECTED_CHARS and _text_quality_score(normalized) >= 2.2


def _choose_better_result(primary: PDFExtractionResult, candidate: PDFExtractionResult) -> PDFExtractionResult:
    if not candidate.success:
        if primary.success:
            primary.text = _normalize_extracted_text(primary.text)
        return primary
    if not primary.success:
        candidate.text = _normalize_extracted_text(candidate.text)
        return candidate

    primary.text = _normalize_extracted_text(primary.text)
    candidate.text = _normalize_extracted_text(candidate.text)
    if _text_quality_score(candidate.text) > _text_quality_score(primary.text):
        return candidate
    return primary


def _table_rows_to_text(table) -> list[str]:
    rows: list[str] = []
    if not isinstance(table, list):
        return rows
    for row in table:
        if not isinstance(row, list):
            continue
        cleaned = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
        cleaned = [cell for cell in cleaned if cell]
        if cleaned:
            rows.append(" | ".join(cleaned))
    return rows


def _extract_with_pdfplumber(pdf_content: bytes) -> PDFExtractionResult:
    """Extract text using pdfplumber library."""
    try:
        import pdfplumber
    except ImportError:
        return PDFExtractionResult(
            success=False,
            error="pdfplumber not installed. Run: pip install pdfplumber",
            method_used="PDFPLUMBER"
        )
    
    try:
        pdf_file = io.BytesIO(pdf_content)
        extracted_text = []
        page_count = 0
        
        with pdfplumber.open(pdf_file) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_lines: list[str] = []
                text = page.extract_text(layout=True, x_tolerance=1, y_tolerance=3)
                if text:
                    page_lines.append(text)

                try:
                    tables = page.extract_tables() or []
                    for table in tables:
                        page_lines.extend(_table_rows_to_text(table))
                except Exception:
                    logger.debug("pdfplumber table extraction failed for a page", exc_info=True)

                page_text = _normalize_extracted_text("\n".join(page_lines))
                if page_text:
                    extracted_text.append(page_text)

        full_text = _normalize_extracted_text("\n\n".join(extracted_text))
        
        return PDFExtractionResult(
            success=True,
            text=full_text,
            page_count=page_count,
            method_used="PDFPLUMBER",
            ocr_used=False
        )
        
    except Exception as e:
        logger.exception("pdfplumber extraction failed")
        return PDFExtractionResult(
            success=False,
            error=f"pdfplumber extraction failed: {str(e)}",
            method_used="PDFPLUMBER"
        )


def _extract_with_pymupdf(pdf_content: bytes) -> PDFExtractionResult:
    """Extract text using pymupdf (fitz) library."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return PDFExtractionResult(
            success=False,
            error="pymupdf not installed. Run: pip install pymupdf",
            method_used="PYMUPDF"
        )
    
    try:
        pdf_file = io.BytesIO(pdf_content)
        doc = fitz.open(stream=pdf_file, filetype="pdf")
        
        extracted_text = []
        page_count = len(doc)
        
        for page in doc:
            page_lines: list[str] = []
            try:
                blocks = page.get_text("blocks", sort=True) or []
                for block in blocks:
                    text = str(block[4] or "").strip()
                    if text:
                        page_lines.append(text)
            except Exception:
                logger.debug("pymupdf block extraction failed for a page", exc_info=True)

            if not page_lines:
                text = page.get_text()
                if text:
                    page_lines.append(text)

            page_text = _normalize_extracted_text("\n".join(page_lines))
            if page_text:
                extracted_text.append(page_text)
        
        doc.close()
        full_text = _normalize_extracted_text("\n\n".join(extracted_text))
        
        return PDFExtractionResult(
            success=True,
            text=full_text,
            page_count=page_count,
            method_used="PYMUPDF",
            ocr_used=False
        )
        
    except Exception as e:
        logger.exception("pymupdf extraction failed")
        return PDFExtractionResult(
            success=False,
            error=f"pymupdf extraction failed: {str(e)}",
            method_used="PYMUPDF"
        )


def extract_text_from_file(file_obj) -> PDFExtractionResult:
    """
    Extract text from a Django UploadedFile or file-like object.
    
    Args:
        file_obj: Django UploadedFile or any file-like object with read()
        
    Returns:
        PDFExtractionResult
    """
    try:
        content = file_obj.read()
        if isinstance(content, str):
            content = content.encode('utf-8')
        return extract_text_from_pdf(content)
    except Exception as e:
        logger.exception("Failed to read file for PDF extraction")
        return PDFExtractionResult(
            success=False,
            error=f"Failed to read file: {str(e)}"
        )
