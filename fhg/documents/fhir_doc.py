"""Read a FHIR record file (exported from the ABHA app, a hospital or a lab) like any other document.

ABDM health records are FHIR R4 document Bundles: a Composition saying what kind of record it is
(prescription, diagnostic report, discharge summary, OP consultation…), the structured resources, and often
the original report as a PDF in a DocumentReference, Binary or DiagnosticReport.presentedForm. We map the
structured part to the same Extraction the review screen uses, and pull out the attachments so a PDF-only record
is still read (by OCR). Nothing here depends on a specific ABDM profile version.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Optional

from ..ingest.fhir import _iter_resources, parse_fhir
from ..terminology import OBSERVATION_TO_LOINC
from .models import (Extraction, ExtractedCondition, ExtractedMedication, ExtractedObservation,
                     ExtractedRelative, PatientInfo)

MEDIA_FHIR = "application/fhir+json"
_ATTACHMENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}


def looks_like_fhir(data: bytes) -> Optional[dict]:
    head = data[:2048].lstrip()
    if not head.startswith(b"{") or b"resourceType" not in data[:65536]:
        return None
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    return doc if isinstance(doc, dict) and "resourceType" in doc else None


def _doc_type(resources: list[dict]) -> str:
    """From the Composition (or DiagnosticReport) title and type."""
    texts = []
    for r in resources:
        if r.get("resourceType") == "Composition":
            texts += [r.get("title", ""), (r.get("type") or {}).get("text", "")]
            texts += [c.get("display", "") for c in (r.get("type") or {}).get("coding", [])]
    if any(r.get("resourceType") == "DiagnosticReport" for r in resources):
        texts.append("diagnostic report")
    blob = " ".join(texts).lower()
    if re.search(r"discharge", blob):
        return "discharge_summary"
    if re.search(r"prescription", blob):
        return "prescription"
    if re.search(r"diagnostic|lab|laboratory|pathology", blob):
        return "lab_report"
    return "other"


def _date(resources: list[dict]) -> Optional[date]:
    for r in resources:
        if r.get("resourceType") in ("Composition", "DiagnosticReport", "DocumentReference"):
            raw = r.get("date") or r.get("effectiveDateTime") or r.get("issued")
            if raw:
                try:
                    return date.fromisoformat(raw[:10])
                except ValueError:
                    pass
    return None


def attachments(doc: dict) -> list[tuple[str, bytes]]:
    """(content type, bytes) of embedded PDFs and images."""
    out = []

    def take(att: dict) -> None:
        ctype = (att.get("contentType") or "").split(";")[0].strip().lower()
        if ctype in _ATTACHMENT_TYPES and att.get("data"):
            try:
                out.append((ctype, base64.b64decode(att["data"])))
            except ValueError:
                pass

    for r in _iter_resources(doc):
        t = r.get("resourceType")
        if t == "DocumentReference":
            for c in r.get("content") or []:
                take(c.get("attachment") or {})
        elif t == "DiagnosticReport":
            for att in r.get("presentedForm") or []:
                take(att)
        elif t == "Binary":
            take({"contentType": r.get("contentType"), "data": r.get("data")})
    return out


def extraction_from_fhir(doc: dict) -> tuple[Extraction, str]:
    """(Extraction for review, a short text summary of what the file contains)."""
    resources = list(_iter_resources(doc))
    fragment = parse_fhir(doc, source="fhir")
    doc_date = _date(resources)
    patient = PatientInfo(sex=fragment.sex.value if fragment.sex else None)
    for r in resources:
        if r.get("resourceType") == "Patient" and r.get("name"):
            n = r["name"][0]
            patient.name = n.get("text") or " ".join([*n.get("given", []), n.get("family", "")]).strip() or None
    facility = next((r.get("name") for r in resources if r.get("resourceType") == "Organization" and r.get("name")), None)
    doctor = next((((r.get("name") or [{}])[0].get("text")) for r in resources
                   if r.get("resourceType") == "Practitioner" and r.get("name")), None)
    extraction = Extraction(
        doc_type=_doc_type(resources), doc_date=doc_date, facility=facility, doctor=doctor, patient=patient,
        conditions=[ExtractedCondition(name=c.display_name, category=c.category, onset_age=c.onset_age,
                                       evidence="From the record file") for c in fragment.conditions],
        medications=[ExtractedMedication(name=m.name, dosage=m.dosage, evidence="From the record file")
                     for m in fragment.medications],
        observations=[ExtractedObservation(code=o.code, display=OBSERVATION_TO_LOINC.get(o.code, ("", o.code))[1],
                                           value=o.value, unit=o.unit, evidence="From the record file")
                      for o in fragment.observations],
        family=[ExtractedRelative(relationship=m.relationship.value, conditions=[
            ExtractedCondition(name=c.display_name, category=c.category, onset_age=c.onset_age,
                               evidence="From the record file") for c in m.conditions])
                for m in fragment.family if m.conditions],
        read_by="rules",
    )
    kinds: dict[str, int] = {}
    for r in resources:
        kinds[r.get("resourceType", "?")] = kinds.get(r.get("resourceType", "?"), 0) + 1
    summary = "FHIR record file: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
    return extraction, summary
