import pytest

from quotes.ai_intake_schemas import PDFExtractionResult
from quotes.ai_intake_service import extract_rate_quote_text_from_pdf


def _pdf_extraction_result(**overrides):
    payload = {
        "success": True,
        "text": "Digitally extracted quote text with enough content to skip multimodal fallback.",
        "page_count": 1,
        "method_used": "PDFPLUMBER",
        "ocr_used": False,
        "ocr_confidence": None,
        "error": None,
        "warnings": [],
    }
    payload.update(overrides)
    return PDFExtractionResult(**payload)


@pytest.mark.django_db
def test_extract_rate_quote_text_from_pdf_uses_multimodal_fallback_for_scanned_pdf(monkeypatch):
    monkeypatch.setattr(
        "quotes.pdf_extraction.extract_text_from_pdf",
        lambda _content: _pdf_extraction_result(
            text="too short",
            warnings=["Very little text extracted. This may be a scanned PDF."],
        ),
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_pdf_text_with_gemini",
        lambda _content, context=None: "Carrier quote\nFreight: USD 5.00/kg\nDestination charges: USD 75.00 flat",
    )

    result = extract_rate_quote_text_from_pdf(b"%PDF-1.4 fake", context={"origin": "POM"})

    assert result.success is True
    assert result.extraction_method == "GEMINI_MULTIMODAL"
    assert "USD 5.00/kg" in result.text
    assert any("multimodal PDF extraction fallback" in warning for warning in result.warnings)
    assert all("scanned PDF" not in warning for warning in result.warnings)


@pytest.mark.django_db
def test_extract_rate_quote_text_from_pdf_keeps_digital_text_when_sufficient(monkeypatch):
    monkeypatch.setattr(
        "quotes.pdf_extraction.extract_text_from_pdf",
        lambda _content: _pdf_extraction_result(),
    )

    result = extract_rate_quote_text_from_pdf(b"%PDF-1.4 fake")

    assert result.success is True
    assert result.extraction_method == "PDFPLUMBER"
    assert "Digitally extracted quote text" in result.text
