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

from .ai_intake_schemas import PDFExtractionResult

logger = logging.getLogger(__name__)

# Minimum characters expected from a rate quote PDF
MIN_EXPECTED_CHARS = 50

# If text extraction yields less than this ratio of expected content, try OCR
LOW_TEXT_THRESHOLD = 0.3


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
    
    # Try pdfplumber first (most reliable for digital PDFs)
    result = _extract_with_pdfplumber(pdf_content)
    if result.success and len(result.text.strip()) > MIN_EXPECTED_CHARS:
        return result
    
    # Fallback to pymupdf
    logger.info("pdfplumber extraction insufficient, trying pymupdf")
    result_pymupdf = _extract_with_pymupdf(pdf_content)
    
    # Use whichever result has more text
    if result_pymupdf.success:
        if len(result_pymupdf.text.strip()) > len(result.text.strip()):
            result = result_pymupdf
    
    # If still minimal text, add warning about possible scanned PDF
    if len(result.text.strip()) < MIN_EXPECTED_CHARS:
        result.warnings.append(
            "Very little text extracted. This may be a scanned PDF. "
            "Consider using OCR or manually entering the rates."
        )
    
    return result


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
                text = page.extract_text()
                if text:
                    extracted_text.append(text)
        
        full_text = "\n\n".join(extracted_text)
        
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
            text = page.get_text()
            if text:
                extracted_text.append(text)
        
        doc.close()
        full_text = "\n\n".join(extracted_text)
        
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
