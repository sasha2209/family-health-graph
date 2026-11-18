"""AI reading, used only when local OCR + rules come up short.

Kept cheap on purpose:
- It is a fallback. Most typed lab reports and printed prescriptions never reach it.
- It receives the OCR *text* (trimmed to MAX_TEXT_CHARS), not the image. Only when there is
  no usable text (a handwritten prescription, a blurry photo) is one downscaled grayscale
  image sent instead.
- A short system prompt, a strict JSON schema (no prose to pay for), low effort and a small
  output cap.

The model is configurable with FHG_DOC_MODEL. Token use is recorded on every document.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..terminology import CONCEPTS, OBSERVATION_TO_LOINC
from .models import DOC_TYPES, Extraction

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TEXT_CHARS = 6000
MAX_IMAGE_SIDE = 1400  # ~2k image tokens; enough for most handwriting

SYSTEM = (
    "Extract structured data from one medical document (prescription, lab report or discharge summary; "
    "often Indian, often OCR text with errors). Only include what the document states; never infer a diagnosis "
    "from a medicine or a lab value. Conditions: diagnoses of the patient (skip negated or 'rule out' ones). "
    "Family history goes in family, not conditions. Medicine names as written, with strength; dosage like "
    "'1-0-1 after food, 5 days'. Lab values only for the listed codes. Dates as YYYY-MM-DD (Indian dates are day-first)."
)

_COND = {"type": "object", "additionalProperties": False, "required": ["name", "category"],
         "properties": {"name": {"type": "string"},
                        "category": {"type": ["string", "null"], "enum": [c.category for c in CONCEPTS] + [None]}}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["doc_type", "doc_date", "doctor", "facility", "conditions", "medications", "observations", "family"],
    "properties": {
        "doc_type": {"type": "string", "enum": list(DOC_TYPES)},
        "doc_date": {"type": ["string", "null"]},
        "doctor": {"type": ["string", "null"]},
        "facility": {"type": ["string", "null"]},
        "conditions": {"type": "array", "items": _COND},
        "medications": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "dosage"],
            "properties": {"name": {"type": "string"}, "dosage": {"type": ["string", "null"]}}}},
        "observations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["code", "value", "unit"],
            "properties": {"code": {"type": "string", "enum": sorted(OBSERVATION_TO_LOINC)},
                           "value": {"type": "number"}, "unit": {"type": "string"}}}},
        "family": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["relationship", "conditions"],
            "properties": {"relationship": {"type": "string"}, "conditions": {"type": "array", "items": _COND}}}},
    },
}


@dataclass
class AiResult:
    extraction: Extraction
    model: str
    input_tokens: int
    output_tokens: int
    mode: str  # "text" | "image"


def shrink_image(png: bytes) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("L")
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=75)
        return out.getvalue()


def default_client() -> Optional[object]:
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic()


def ai_extract(client: object, text: str = "", image_png: Optional[bytes] = None) -> Optional[AiResult]:
    """Ask the model for an Extraction from OCR text, or (no text) from one small image."""
    model = os.environ.get("FHG_DOC_MODEL", DEFAULT_MODEL)
    if image_png is not None and len(text.strip()) < 40:
        mode = "image"
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.standard_b64encode(shrink_image(image_png)).decode()}},
                   {"type": "text", "text": "Extract this document."}]
    else:
        mode = "text"
        content = "Document text:\n" + text[:MAX_TEXT_CHARS]
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=3000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except Exception:
        log.exception("AI document reading failed")
        return None
    if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
        log.warning("AI document reading stopped: %s", response.stop_reason)
        return None
    raw = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
    try:
        data = json.loads(raw)
        try:
            data["doc_date"] = date.fromisoformat(data.get("doc_date") or "").isoformat()
        except ValueError:
            data["doc_date"] = None
        extraction = Extraction.model_validate({**data, "read_by": "rules+ai"})
    except (ValueError, TypeError):
        log.warning("AI document reading returned unusable JSON")
        return None
    usage = getattr(response, "usage", None)
    return AiResult(extraction, getattr(response, "model", model),
                    getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0, mode)
