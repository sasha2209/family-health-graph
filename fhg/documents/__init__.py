"""Document upload: photos and PDFs of prescriptions, lab reports and discharge summaries.

    file ──▶ text (PDF text layer, else Tesseract OCR; local, free)
         ──▶ rules (parse.py; free)
         ──▶ AI reader, only if the rules come up short and the user allowed it (ai.py)
         ──▶ draft for the user to review ──▶ confirmed items merged into the profile
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .ai import AiResult, ai_extract, default_client
from .models import DOC_TYPES, Extraction
from .ocr import TextResult, UnsupportedDocument, extract_text, tesseract_available
from .parse import parse_document

LOW_OCR_CONFIDENCE = 50  # below this Tesseract is usually reading handwriting badly

__all__ = ["DOC_TYPES", "Extraction", "ReadResult", "UnsupportedDocument", "read_document", "tesseract_available"]


@dataclass
class ReadResult:
    media_type: str
    text: TextResult
    extraction: Extraction
    ai: Optional[AiResult] = None
    ai_reason: Optional[str] = None  # why the AI reader was (or would have been) used
    warnings: list[str] = field(default_factory=list)


def _needs_ai(text: TextResult, rules: Extraction) -> tuple[Optional[str], bool]:
    """(reason, send the image instead of text)."""
    if len(text.text.strip()) < 40:
        return "no_text", True
    if text.method == "ocr" and text.confidence is not None and text.confidence < LOW_OCR_CONFIDENCE:
        return "low_ocr_confidence", True
    if rules.is_empty():
        return "nothing_recognised", False
    if rules.doc_type == "prescription" and not rules.medications:
        return "no_medicines_found", False
    return None, False


def _merge(rules: Extraction, ai: Extraction) -> Extraction:
    """Rules win where both found something; the AI fills gaps."""
    out = rules.model_copy(deep=True)
    out.read_by = "rules+ai"
    if out.doc_type == "other":
        out.doc_type = ai.doc_type
    out.doc_date = out.doc_date or ai.doc_date
    out.doctor = out.doctor or ai.doctor
    out.facility = out.facility or ai.facility
    have = {c.category or c.name.lower() for c in out.conditions}
    out.conditions += [c for c in ai.conditions if (c.category or c.name.lower()) not in have]
    have = {m.name.split()[0].lower() for m in out.medications if m.name.split()}
    out.medications += [m for m in ai.medications if m.name.split() and m.name.split()[0].lower() not in have]
    have = {o.code for o in out.observations}
    out.observations += [o for o in ai.observations if o.code not in have]
    have = {r.relationship for r in out.family}
    out.family += [r for r in ai.family if r.relationship not in have]
    return out


def read_document(data: bytes, allow_ai: bool, client: Optional[object] = None) -> ReadResult:
    media_type, text = extract_text(data)
    rules = parse_document(text.text) if text.text else Extraction()
    result = ReadResult(media_type, text, rules)
    reason, use_image = _needs_ai(text, rules)
    result.ai_reason = reason
    if reason is None:
        return result
    if not allow_ai:
        if reason in ("no_text", "low_ocr_confidence"):
            result.warnings.append("This looks handwritten or hard to read. Turn on AI reading in Settings to read it, "
                                   "or type what it says.")
        return result
    client = client or default_client()
    if client is None or (use_image and not text.images):
        return result
    ai = ai_extract(client, text="" if use_image else text.text,
                    image_png=text.images[0] if (use_image and text.images) else None)
    if ai is not None:
        result.ai = ai
        result.extraction = _merge(rules, ai.extraction)
    return result
