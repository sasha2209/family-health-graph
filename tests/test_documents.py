import base64
import io
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image

from fhg.api import Settings, create_app
from fhg.documents import read_document, tesseract_available
from fhg.documents.parse import expand_shorthand, find_date, parse_document

FIX = Path(__file__).parent / "fixtures" / "documents"
needs_ocr = pytest.mark.skipif(not tesseract_available(), reason="tesseract not installed")


def text_pdf(lines: list[str]) -> bytes:
    """A minimal PDF with a real text layer (what lab portals export)."""
    stream = "BT /F1 11 Tf 40 800 Td 14 TL " + " ".join(
        "(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for line in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class FakeClaude:
    """Stands in for anthropic.Anthropic(); records what would have been sent."""

    def __init__(self, result: dict):
        self.calls: list[dict] = []
        self.result = result
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self.result))],
                               stop_reason="end_turn", model=kwargs["model"],
                               usage=SimpleNamespace(input_tokens=1800, output_tokens=210))


AI_RESULT = {"doc_type": "prescription", "doc_date": "2026-05-09", "doctor": "Dr. K. Rao", "facility": None,
             "conditions": [{"name": "Hypertension", "category": "hypertension"}],
             "medications": [{"name": "Amlodipine 5 mg", "dosage": "1-0-0"}],
             "observations": [], "family": []}


# --- rules -----------------------------------------------------------------------------------

def test_lab_report_rules():
    e = parse_document((FIX / "lab_report.txt").read_text())
    assert e.doc_type == "lab_report" and e.doc_date == date(2026, 3, 14)
    assert e.facility.startswith("SUNRISE DIAGNOSTICS") and e.doctor == "Dr. Anil Mehta"
    assert (e.patient.name, e.patient.age, e.patient.sex) == ("Sunita Shah", 62, "female")
    obs = {o.code: (o.value, o.unit, o.flag) for o in e.observations}
    assert obs["hba1c"] == (7.8, "%", "h")
    assert obs["fasting_glucose"] == (142, "mg/dL", "h")
    assert obs["ldl_cholesterol"] == (162, "mg/dL", "h")      # not VLDL (38) and not the LDL/HDL ratio
    assert obs["hdl_cholesterol"] == (38, "mg/dL", "l")
    assert obs["tsh"][0] == 3.2 and obs["vitamin_d"] == (14.2, "ng/mL", "l")
    # Interpretation tables mention "Diabetes >= 6.5"; that is not a diagnosis.
    assert e.conditions == [] and e.medications == []


def test_prescription_rules():
    e = parse_document((FIX / "prescription.txt").read_text())
    assert e.doc_type == "prescription" and e.doc_date == date(2026, 4, 2) and e.doctor == "Dr. Ramesh Iyer"
    assert {c.category for c in e.conditions} == {"hypertension", "type_2_diabetes", "hyperlipidemia"}
    meds = {m.name: m.dosage for m in e.medications}
    assert meds["Metformin 500 mg"] == "1-0-1, after food, 30 days"
    assert "Telma 40 (Telmisartan 40mg)" in meds and "Vitamin D3 60000 IU" in meds
    obs = {o.code: o.value for o in e.observations}
    assert obs == {"systolic_bp": 148, "diastolic_bp": 94, "bmi": 28.4}
    fam = {r.relationship: [(c.category, c.onset_age) for c in r.conditions] for r in e.family}
    assert fam == {"mother": [("type_2_diabetes", None)], "father": [("coronary_artery_disease", 52)]}


def test_shorthand_negation_and_dates():
    assert "type 2 diabetes" in expand_shorthand("K/C/O T2DM")
    assert "breast cancer" in expand_shorthand("Ca. breast")
    e = parse_document("Rx\nNo h/o DM or HTN\nDiagnosis: Acute gastritis\nTab. Pan 40 1-0-0 before food x 5 days")
    assert [c.name for c in e.conditions] == ["Acute gastritis"]          # negated history is skipped
    assert e.medications[0].name == "Pan 40" and "before food" in e.medications[0].dosage
    assert find_date(["DOB: 01/02/1980", "Date: 05/06/2026"]) == date(2026, 6, 5)   # day-first, birth dates ignored


# --- OCR ---------------------------------------------------------------------------------------

@needs_ocr
def test_photo_of_lab_report_is_read_locally():
    r = read_document((FIX / "lab_report.jpg").read_bytes(), allow_ai=False)
    assert r.text.method == "ocr" and r.text.confidence > 60 and r.ai is None and r.ai_reason is None
    obs = {o.code: o.value for o in r.extraction.observations}
    assert obs["hba1c"] == 7.8 and obs["ldl_cholesterol"] == 162 and obs["hdl_cholesterol"] == 38


@needs_ocr
def test_photo_of_prescription_is_read_locally():
    r = read_document((FIX / "prescription.jpg").read_bytes(), allow_ai=False)
    assert r.extraction.doc_type == "prescription"
    assert any(m.name.startswith("Metformin") for m in r.extraction.medications)


def test_text_pdf_needs_no_ocr():
    r = read_document(text_pdf((FIX / "lab_report.txt").read_text().splitlines()), allow_ai=False)
    assert r.text.method == "pdf_text" and r.extraction.doc_type == "lab_report"
    assert {o.code for o in r.extraction.observations} >= {"hba1c", "ldl_cholesterol"}


# --- AI fallback -----------------------------------------------------------------------------

def _blank_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), "white").save(buf, "PNG")
    return buf.getvalue()


def test_ai_not_used_when_rules_succeed():
    fake = FakeClaude(AI_RESULT)
    read_document(text_pdf((FIX / "prescription.txt").read_text().splitlines()), allow_ai=True, client=fake)
    assert fake.calls == []


def test_ai_gets_text_not_image_when_rules_find_nothing():
    fake = FakeClaude(AI_RESULT)
    r = read_document(text_pdf(["Some clinic", "Pt seen today, complains of headache for two weeks.",
                                "Plan discussed in detail with the patient and family members."]),
                      allow_ai=True, client=fake)
    assert r.ai_reason == "nothing_recognised" and r.ai.mode == "text"
    sent = fake.calls[0]
    assert isinstance(sent["messages"][0]["content"], str) and "headache" in sent["messages"][0]["content"]
    assert sent["output_config"]["effort"] == "low" and sent["output_config"]["format"]["type"] == "json_schema"
    assert r.extraction.read_by == "rules+ai" and r.extraction.medications[0].name == "Amlodipine 5 mg"


def test_ai_gets_one_small_image_only_when_there_is_no_text():
    fake = FakeClaude(AI_RESULT)
    r = read_document(_blank_png(), allow_ai=True, client=fake)
    assert r.ai_reason == "no_text" and r.ai.mode == "image"
    block = fake.calls[0]["messages"][0]["content"][0]
    img = Image.open(io.BytesIO(base64.b64decode(block["source"]["data"])))
    assert block["source"]["media_type"] == "image/jpeg" and max(img.size) <= 1400 and img.mode == "L"


def test_no_ai_without_consent():
    fake = FakeClaude(AI_RESULT)
    r = read_document(_blank_png(), allow_ai=False, client=fake)
    assert fake.calls == [] and r.extraction.is_empty() and "handwritten" in r.warnings[0]


# --- API -------------------------------------------------------------------------------------

@pytest.fixture
def fake_ai():
    return FakeClaude(AI_RESULT)


@pytest.fixture
def api(tmp_path, fake_ai):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "d.db"), encryption_key=Fernet.generate_key().decode()),
                                 document_ai_client=fake_ai))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def upload(api, h, data: bytes, filename="doc.pdf"):
    return api.post("/v1/documents", json={"data_base64": base64.b64encode(data).decode(), "filename": filename}, headers=h)


def test_upload_review_and_save_own_lab_report(api, tmp_path):
    h = account(api)
    r = upload(api, h, text_pdf((FIX / "lab_report.txt").read_text().splitlines()))
    assert r.status_code == 201
    doc = r.json()
    assert doc["status"] == "review" and doc["method"] == "pdf_text" and doc["ai_used"] is False
    assert "HbA1c" in doc["text_preview"]
    # Nothing is in the record until the user saves the reviewed items.
    assert api.get("/v1/profile", headers=h).json()["observations"] == []

    kept = [o for o in doc["extraction"]["observations"] if o["code"] != "tsh"]   # user unticked TSH
    saved = api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={
        "doc_type": "lab_report", "doc_date": doc["extraction"]["doc_date"], "observations": kept}).json()
    assert saved["merged"]["observations"] == len(kept) and saved["document"]["status"] == "saved"
    obs = api.get("/v1/profile", headers=h).json()["observations"]
    hba1c = next(o for o in obs if o["code"] == "hba1c")
    assert hba1c["value"] == 7.8 and hba1c["effective_date"] == "2026-03-14" and hba1c["source"] == f"document:{doc['id']}"
    assert not any(o["code"] == "tsh" for o in obs)
    assert api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={}).status_code == 409

    listed = api.get("/v1/documents", headers=h).json()
    assert [d["id"] for d in listed] == [doc["id"]] and listed[0]["doc_type"] == "lab_report"
    f = api.get(f"/v1/documents/{doc['id']}/file", headers=h)
    assert f.headers["content-type"] == "application/pdf" and f.content.startswith(b"%PDF")
    # The original and the text are encrypted at rest.
    raw = (tmp_path / "d.db").read_bytes()
    assert b"Sunita" not in raw and b"HbA1c" not in raw


def test_prescription_saved_with_medicines_and_family_history(api):
    h = account(api)
    doc = upload(api, h, text_pdf((FIX / "prescription.txt").read_text().splitlines())).json()
    e = doc["extraction"]
    api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={
        "doc_type": e["doc_type"], "doc_date": e["doc_date"], "conditions": e["conditions"],
        "medications": e["medications"], "observations": e["observations"], "family": e["family"]})
    p = api.get("/v1/profile", headers=h).json()
    met = next(m for m in p["medications"] if m["name"].startswith("Metformin"))
    assert met["dosage"].startswith("1-0-1") and met["prescribed_on"] == "2026-04-02"
    assert {c["category"] for c in p["conditions"]} >= {"type_2_diabetes", "hypertension"}
    father = next(m for m in p["family"] if m["relationship"] == "father")
    assert father["conditions"][0]["category"] == "coronary_artery_disease" and father["conditions"][0]["onset_age"] == 52
    fhir = api.get("/v1/export/fhir", headers=h).json()
    med = next(x["resource"] for x in fhir["entry"] if x["resource"]["resourceType"] == "MedicationStatement")
    assert med["dosage"][0]["text"].startswith("1-0-1")


def test_relatives_document_feeds_family_history(api):
    """A daughter uploads her mother's report: diagnoses go to 'mother', and the mother's own
    family history becomes the user's grandparents' history."""
    h = account(api)
    doc = upload(api, h, text_pdf(["Discharge Summary", "Diagnosis: Ca breast, T2DM",
                                   "Family history: Mother - ovarian cancer at 60"])).json()
    e = doc["extraction"]
    assert {c["category"] for c in e["conditions"]} == {"breast_cancer", "type_2_diabetes"}
    r = api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={
        "subject": "mother", "doc_type": e["doc_type"], "relative_age": 62, "conditions": e["conditions"],
        "family": e["family"], "medications": [{"name": "Tab. Letrozole 2.5 mg"}]}).json()
    assert r["document"]["subject"] == "mother" and r["document"]["subject_member_id"]
    fam = {m["relationship"]: m for m in api.get("/v1/profile", headers=h).json()["family"]}
    assert {c["category"] for c in fam["mother"]["conditions"]} == {"breast_cancer", "type_2_diabetes"}
    assert fam["mother"]["age"] == 62
    assert fam["maternal_grandmother"]["conditions"][0]["category"] == "ovarian_cancer"
    # A managed profile: the mother's medicine is on her record, not the user's.
    assert [m["name"] for m in fam["mother"]["medications"]] == ["Tab. Letrozole 2.5 mg"]
    assert api.get("/v1/profile", headers=h).json()["medications"] == []
    # The family history now drives insights.
    rules = {i["rule_id"] for i in api.get("/v1/insights", headers=h).json()["insights"]}
    assert any("hboc" in rid or "breast" in rid for rid in rules)


def test_ai_only_with_consent_and_tokens_recorded(api, fake_ai):
    h = account(api)
    blank = _blank_png()
    doc = upload(api, h, blank, "scan.png").json()
    assert doc["ai_used"] is False and fake_ai.calls == [] and doc["warnings"]

    api.post("/v1/consents", headers=h, json={"scope": "ai_document_reading", "granted": True})
    doc = upload(api, h, blank, "scan.png").json()
    assert doc["ai_used"] is True and doc["ai_mode"] == "image" and len(fake_ai.calls) == 1
    assert (doc["input_tokens"], doc["output_tokens"]) == (1800, 210)
    assert doc["extraction"]["medications"][0]["name"] == "Amlodipine 5 mg"
    audit = api.get("/v1/audit", headers=h).json()
    assert any(a["action"] == "document.uploaded" and a["detail"]["tokens"] == 2010 for a in audit)


def test_rejects_bad_files_and_other_users(api):
    h, other = account(api), account(api)
    assert upload(api, h, b"hello world", "x.txt").status_code == 415
    assert api.post("/v1/documents", json={"data_base64": ""}, headers=h).status_code == 422
    doc = upload(api, h, text_pdf(["Diagnosis: Hypertension"])).json()
    assert api.get(f"/v1/documents/{doc['id']}", headers=other).status_code == 404
    assert api.get(f"/v1/documents/{doc['id']}/file", headers=other).status_code == 404
    assert api.post(f"/v1/documents/{doc['id']}/save", headers=h,
                    json={"observations": [{"code": "made_up", "value": 1}]}).status_code == 422
    assert api.delete(f"/v1/documents/{doc['id']}", headers=other).status_code == 404
    assert api.delete(f"/v1/documents/{doc['id']}", headers=h).status_code == 204
    assert api.get("/v1/documents", headers=h).json() == []


def test_account_deletion_removes_documents(api, tmp_path):
    h = account(api)
    upload(api, h, text_pdf(["Diagnosis: Hypertension"]))
    api.delete("/v1/me", headers=h)
    import sqlite3
    assert sqlite3.connect(tmp_path / "d.db").execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_saved_document_keeps_header_fields(api):
    h = account(api)
    doc = upload(api, h, text_pdf((FIX / "lab_report.txt").read_text().splitlines())).json()
    api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={"doc_type": "lab_report", "observations": []})
    saved = api.get(f"/v1/documents/{doc['id']}", headers=h).json()["extraction"]
    assert saved["patient"]["name"] == "Sunita Shah" and saved["facility"].startswith("SUNRISE") and saved["observations"] == []
