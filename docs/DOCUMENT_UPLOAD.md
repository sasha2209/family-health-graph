# Document upload: prescriptions, lab reports and discharge summaries

People snap a photo or upload a PDF; we read it, they tick what's right, and only that goes into the record —
theirs, or a relative's (the "family health manager" uploading a parent's report).

```
photo / PDF ──▶ text ──────────────▶ rules ─────────────▶ AI reader (fallback only) ──▶ review ──▶ record
               PDF text layer, or     fhg/documents/      fhg/documents/ai.py            app      yours or a
               Tesseract OCR          parse.py                                                    relative's
               (on our server, free)  (free)
```

## Keeping AI tokens low

| Step | Cost | Handles |
|---|---|---|
| PDF text layer (`pypdf`) | free | Most lab-portal and hospital PDFs |
| Tesseract OCR (`tesseract-ocr`, `poppler-utils`) | free, ~1 s per page | Photos of printed prescriptions and reports |
| Rules (`parse.py`) | free | Dates (day-first), patient/doctor/lab names, 15 common tests with units and H/L flags, `Tab./Cap.` medicines with `1-0-1` dosing, diagnoses including shorthand (`K/C/O T2DM, HTN`, `Ca breast`), family history (`F/H: Mother - DM`), negations (`No h/o DM`) |
| **AI reader** — only if the rules found nothing, a prescription had no medicines, or there's no usable text | ~1–3k tokens | Handwriting, unusual layouts |

When the AI reader runs it gets **the OCR text, trimmed to 6,000 characters**, not the image. Only when there's no
usable text (handwriting OCR can't read) does it get **one grayscale image, at most 1,400 px** (~2k tokens).
It answers in a strict JSON schema (no prose), at low effort, with a 3,000-token cap. Rules win where both found
something; the AI only fills gaps.

- **Consent:** off by default. Users turn on *AI reading for hard-to-read documents* in Settings
  (consent scope `ai_document_reading`). Without it, unreadable documents get a "type it in" prompt.
- **Model:** `FHG_DOC_MODEL` (default `claude-opus-5-5`). Setting a smaller model, such as `claude-haiku-5-5`,
  cuts the cost of each fallback call further. Server-side refusal fallback is enabled.
- **Measurement:** every document stores `input_tokens` / `output_tokens`, and the audit log records them, so you
  can see the real cost per document and what share of documents needed AI.
- **Key:** set `ANTHROPIC_API_KEY`. Without it everything still works; there's just no fallback.

## API

| | |
|---|---|
| `POST /v1/documents` `{"data_base64", "filename"}` | Read a PDF/JPEG/PNG (≤ 12 MB, 30 per hour). Returns a draft: `extraction` (doc type, date, facility, doctor, patient, conditions, medications, observations, family), `method`, `ai_used`, tokens, `warnings`. **Nothing is added to the record yet.** |
| `POST /v1/documents/{id}/save` | The items the user kept, and `subject`: `"self"` or a relationship (`"mother"`). For a relative, diagnoses go to that relative, and *their* family history is mapped onto yours (their mother → your maternal grandmother). Medicines and lab values are kept only for yourself. |
| `GET /v1/documents`, `GET /v1/documents/{id}`, `GET /v1/documents/{id}/file` | List, detail (with the text we read), original file |
| `DELETE /v1/documents/{id}` | Deletes the file and what was read; items already saved stay in the record |

The original file, the OCR text and the extraction are encrypted at rest, like the rest of the record, and are
deleted with the account. Saved items carry `source: "document:<id>"` for provenance.

## Managed family profiles

The person who manages the family's paperwork can keep a record for each relative:
- A document filed under a relative adds their **diagnoses, medicines and test results** to that relative
  (`subject` + optional `member_id` to pick between, say, two sisters). Later documents merge into the same
  record; a newer prescription for the same medicine updates the dosing.
- `GET /v1/family/{id}` returns the relative's record plus the documents filed under them; `PATCH` edits name,
  sex, age and deceased; `DELETE /v1/family/{id}/items/{item_id}` removes a diagnosis, medicine or result.
- **Insights use it:** a parent's, sibling's or child's LDL of 190 mg/dL or more (from their own report) flags
  possible familial hypercholesterolemia for you.
- **Privacy:** a relative's medicines and results stay on your record only. Linked relatives who see your family
  tree get diagnoses only, as before; partners and research exports never get them.

## Next

- WhatsApp / email forwarding into the same pipeline (phase 2).
- Lab trends over time from repeated reports; Hindi OCR (`tesseract-ocr-hin`) for bilingual reports.
- Hand a managed profile over to the relative when they join (today their own account starts fresh and links).
