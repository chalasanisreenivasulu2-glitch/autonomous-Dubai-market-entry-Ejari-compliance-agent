import os
import re
from typing import Optional, Tuple
try:
    import pymupdf  # PyMuPDF >=1.24.3
except ImportError:
    import fitz as pymupdf  # Legacy alias
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI


class ExtractedDocumentFields(BaseModel):
    trade_name_en: Optional[str] = None
    trade_name_ar: Optional[str] = None
    lease_tenant_name: Optional[str] = None
    lease_landlord_name: Optional[str] = None
    current_rent_aed: Optional[float] = None
    proposed_rent_aed: Optional[float] = None
    notice_days_given: Optional[int] = None
    makani_number: Optional[str] = None
    district: Optional[str] = None


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extracts UTF-8 text across all pages of a PDF using PyMuPDF (fitz)."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages_text = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"--- Page {page_num} ---\n{text.strip()}")
    doc.close()
    return "\n\n".join(pages_text)


def split_bilingual_text(raw_text: str) -> Tuple[str, str]:
    """Separates English and Arabic lines from a bilingual Dubai tenancy contract."""
    arabic_pattern = re.compile(r"[\u0600-\u06FF]")
    en_lines, ar_lines = [], []
    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("--- Page "):
            continue
        arabic_chars = len(arabic_pattern.findall(cleaned))
        if arabic_chars > 0 and (arabic_chars / max(len(cleaned), 1)) >= 0.25:
            ar_lines.append(cleaned)
        else:
            en_lines.append(cleaned)
    return "\n".join(en_lines), "\n".join(ar_lines)


def parse_uploaded_pdfs(
    lease_pdf_bytes: Optional[bytes] = None,
    trade_cert_pdf_bytes: Optional[bytes] = None,
) -> dict:
    """Extracts text via PyMuPDF and uses Gemini structured output to populate fields."""
    lease_raw = extract_text_from_pdf_bytes(lease_pdf_bytes) if lease_pdf_bytes else ""
    cert_raw = extract_text_from_pdf_bytes(trade_cert_pdf_bytes) if trade_cert_pdf_bytes else ""
    lease_en, lease_ar = split_bilingual_text(lease_raw)

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY in .env to parse uploaded PDFs.")

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-pro-preview", api_key=api_key, temperature=0.0,
    ).with_structured_output(ExtractedDocumentFields, method="json_schema")

    prompt = f"""
    Extract structured Dubai company registration and tenancy contract metadata from the PDF text below.
    Leave any field null if not explicitly present.

    TRADE NAME CERTIFICATE TEXT:
    {cert_raw[:8000]}

    DRAFT COMMERCIAL LEASE TEXT:
    {lease_raw[:12000]}
    """

    extracted: ExtractedDocumentFields = llm.invoke(prompt)

    lease_doc = pymupdf.open(stream=lease_pdf_bytes, filetype="pdf") if lease_pdf_bytes else None
    cert_doc = pymupdf.open(stream=trade_cert_pdf_bytes, filetype="pdf") if trade_cert_pdf_bytes else None
    lease_pages = len(lease_doc) if lease_doc else 0
    cert_pages = len(cert_doc) if cert_doc else 0
    if lease_doc: lease_doc.close()
    if cert_doc: cert_doc.close()

    return {
        "extracted_fields": extracted.model_dump(),
        "raw_lease_en": lease_en or lease_raw,
        "raw_lease_ar": lease_ar,
        "cert_page_count": cert_pages,
        "lease_page_count": lease_pages,
    }