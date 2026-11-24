"""Phase 2: forwarding documents by email and WhatsApp, and results over time."""
import base64
import hashlib
import hmac
import json
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from test_documents import FIX, text_pdf  # noqa: E402

from fhg.api import Settings, create_app  # noqa: E402
from fhg.inbound import token_for_domain  # noqa: E402

APP_SECRET = "meta-app-secret"


class FakeWhatsApp:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.media: dict[str, bytes] = {}

    def download(self, media_id):
        return self.media[media_id]

    def send_text(self, to, body):
        self.sent.append((to, body))

    def send_template(self, to, name, lang, params):
        self.templates = getattr(self, "templates", [])
        self.templates.append((to, name, lang, params))


@pytest.fixture
def wa():
    return FakeWhatsApp()


@pytest.fixture
def api(tmp_path, wa):
    return TestClient(create_app(Settings(
        db_path=str(tmp_path / "f.db"), encryption_key=Fernet.generate_key().decode(),
        inbound_email_domain="in.example.org", inbound_email_secret="mail-secret",
        whatsapp_number="+91 80000 00000", whatsapp_verify_token="verify-me", whatsapp_app_secret=APP_SECRET,
    ), whatsapp_client=wa))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def postmark(to: str, *files: tuple[str, str, bytes]) -> dict:
    return {"From": "lab@example.com", "To": to, "Subject": "Your report",
            "ToFull": [{"Email": to}], "TextBody": "Please find attached.",
            "Attachments": [{"Name": n, "ContentType": t, "Content": base64.b64encode(d).decode(),
                             "ContentLength": len(d)} for n, t, d in files]}


def wa_payload(sender: str, message: dict) -> bytes:
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "messaging_product": "whatsapp", "messages": [{"from": sender, "id": "wamid.1", **message}]}}]}]}).encode()


def wa_post(api, body: bytes, secret=APP_SECRET):
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api.post("/inbound/whatsapp", content=body,
                    headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})


# --- email ------------------------------------------------------------------------------------

def test_forwarded_email_attachments_wait_for_review(api):
    h = account(api)
    info = api.get("/v1/inbound", headers=h).json()
    address = info["email"]["address"]
    assert info["email"]["available"] and address.endswith("@in.example.org")
    assert api.get("/v1/inbound", headers=h).json()["email"]["address"] == address        # stable

    lab = text_pdf((FIX / "lab_report.txt").read_text().splitlines())
    r = api.post("/inbound/email?secret=mail-secret", json=postmark(
        f"Priya <{address}>", ("report.pdf", "application/pdf", lab), ("photo.jpg", "image/jpeg",
                                                                        (FIX / "prescription.jpg").read_bytes()),
        ("notes.txt", "text/plain", b"ignored")))
    assert r.json() == {"accepted": 2}
    docs = api.get("/v1/documents", headers=h).json()
    assert {d["source"] for d in docs} == {"email"} and {d["status"] for d in docs} == {"review"}
    assert {d["doc_type"] for d in docs} == {"lab_report", "prescription"}
    notes = api.get("/v1/notifications", headers=h).json()
    assert notes[0]["kind"] == "documents_received" and "2 documents arrived by email and are waiting for your review" in notes[0]["message"]
    # Nothing is in the record until the user reviews and saves.
    assert api.get("/v1/profile", headers=h).json()["observations"] == []


def test_email_webhook_rejects_bad_secret_and_unknown_addresses(api):
    h = account(api)
    address = api.get("/v1/inbound", headers=h).json()["email"]["address"]
    pdf = text_pdf(["Diagnosis: Hypertension"])
    assert api.post("/inbound/email?secret=wrong", json=postmark(address, ("a.pdf", "application/pdf", pdf))).status_code == 404
    assert api.post("/inbound/email?secret=mail-secret",
                    json=postmark("nobody1234567@in.example.org", ("a.pdf", "application/pdf", pdf))).json() == {"accepted": 0}
    assert api.post("/inbound/email?secret=mail-secret",
                    json=postmark(address.replace("in.example.org", "evil.org"), ("a.pdf", "application/pdf", pdf))
                    ).json() == {"accepted": 0}
    # Rotating the address retires the old one.
    new = api.post("/v1/inbound/email/rotate", headers=h).json()["email"]["address"]
    assert new != address
    assert api.post("/inbound/email?secret=mail-secret", json=postmark(address, ("a.pdf", "application/pdf", pdf))
                    ).json() == {"accepted": 0}
    assert api.post("/inbound/email?secret=mail-secret", json=postmark(new, ("a.pdf", "application/pdf", pdf))
                    ).json() == {"accepted": 1}


def test_plus_addressing_and_token_parsing():
    assert token_for_domain(["abcd2345efgh+lab@in.example.org"], "in.example.org") == "abcd2345efgh"
    assert token_for_domain(["x@in.example.org"], "in.example.org") is None


def test_forwarding_off_when_not_configured(tmp_path):
    api = TestClient(create_app(Settings(db_path=str(tmp_path / "n.db"), encryption_key=Fernet.generate_key().decode())))
    h = account(api)
    assert api.get("/v1/inbound", headers=h).json() == {
        "email": {"available": False, "address": None},
        "whatsapp": {"available": False, "number": None, "linked": False}}
    assert api.post("/inbound/email?secret=", json={}).status_code == 404
    assert api.post("/inbound/whatsapp", content=b"{}").status_code == 404
    assert api.post("/v1/inbound/whatsapp/code", headers=h).status_code == 404


# --- WhatsApp ---------------------------------------------------------------------------------

def test_whatsapp_verification_handshake(api):
    ok = api.get("/inbound/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                              "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    assert api.get("/inbound/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "nope",
                                                "hub.challenge": "x"}).status_code == 403


def test_whatsapp_link_then_send_a_photo(api, wa):
    h = account(api)
    phone = "919812345678"
    # An unknown number is told how to connect; nothing is stored.
    wa.media["m0"] = (FIX / "prescription.jpg").read_bytes()
    wa_post(api, wa_payload(phone, {"type": "image", "image": {"id": "m0", "mime_type": "image/jpeg"}}))
    assert "isn't connected" in wa.sent[-1][1] and api.get("/v1/documents", headers=h).json() == []

    code = api.post("/v1/inbound/whatsapp/code", headers=h).json()
    assert code["message"] == f"LINK {code['code']}" and code["number"] == "+91 80000 00000"
    wa_post(api, wa_payload(phone, {"type": "text", "text": {"body": f"LINK {code['code']}"}}))
    assert "now connected" in wa.sent[-1][1] and api.get("/v1/inbound", headers=h).json()["whatsapp"]["linked"]
    # The code works once.
    other = account(api)
    wa_post(api, wa_payload("919800000001", {"type": "text", "text": {"body": f"LINK {code['code']}"}}))
    assert api.get("/v1/inbound", headers=other).json()["whatsapp"]["linked"] is False

    wa.media["m1"] = (FIX / "lab_report.jpg").read_bytes()
    r = wa_post(api, wa_payload(phone, {"type": "image", "image": {"id": "m1", "mime_type": "image/jpeg"}}))
    assert r.json() == {"received": 1}
    docs = api.get("/v1/documents", headers=h).json()
    assert len(docs) == 1 and docs[0]["source"] == "whatsapp" and docs[0]["doc_type"] == "lab_report"
    assert wa.sent[-1] == (phone, "Got it. Open Family Health Graph to check what we read before it's added to your record.")
    # Replies never carry health information.
    assert not any("HbA1c" in body or "Sunita" in body for _, body in wa.sent)

    wa_post(api, wa_payload(phone, {"type": "audio", "audio": {"id": "a1"}}))
    assert "Voice notes" in wa.sent[-1][1]
    wa_post(api, wa_payload(phone, {"type": "sticker", "sticker": {"id": "s1"}}))
    assert "photo or a PDF" in wa.sent[-1][1]

    assert api.delete("/v1/inbound/whatsapp", headers=h).status_code == 204
    wa_post(api, wa_payload(phone, {"type": "image", "image": {"id": "m1", "mime_type": "image/jpeg"}}))
    assert len(api.get("/v1/documents", headers=h).json()) == 1


def test_whatsapp_rejects_unsigned_requests(api, wa):
    body = wa_payload("919812345678", {"type": "text", "text": {"body": "hi"}})
    assert api.post("/inbound/whatsapp", content=body).status_code == 401
    assert wa_post(api, body, secret="wrong").status_code == 401
    assert wa.sent == []


def test_phone_numbers_are_not_stored_in_plain_text(api, wa, tmp_path):
    h = account(api)
    code = api.post("/v1/inbound/whatsapp/code", headers=h).json()["code"]
    wa_post(api, wa_payload("919812345678", {"type": "text", "text": {"body": code}}))
    assert b"919812345678" not in (tmp_path / "f.db").read_bytes()


# --- trends -----------------------------------------------------------------------------------

def _save_lab(api, h, a1c: str, ldl: str, date: str, subject="self", **extra):
    lines = [f"Date: {date}", "Test Name Result Unit Biological Ref. Interval",
             f"HbA1c {a1c} % 4.0 - 5.6", f"LDL Cholesterol {ldl} mg/dL < 100", "Reference range", "Pathology lab"]
    doc = api.post("/v1/documents", headers=h, json={"data_base64": base64.b64encode(text_pdf(lines)).decode()}).json()
    e = doc["extraction"]
    r = api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={
        "subject": subject, "doc_type": e["doc_type"], "doc_date": e["doc_date"], "observations": e["observations"], **extra})
    assert r.status_code == 200, r.text
    return doc


def test_trends_and_rising_hba1c_insight(api):
    h = account(api)
    first = _save_lab(api, h, "5.6", "120", "10/01/2025")
    _save_lab(api, h, "5.9", "118", "12/07/2025")
    _save_lab(api, h, "6.2", "131", "15/01/2026")
    tests = {t["code"]: t for t in api.get("/v1/trends", headers=h).json()["tests"]}
    a1c = tests["hba1c"]
    assert [p["value"] for p in a1c["points"]] == [5.6, 5.9, 6.2]
    assert [p["date"] for p in a1c["points"]] == ["2025-01-10", "2025-07-12", "2026-01-15"]
    assert a1c["change"] == 0.3 and a1c["latest_band"] == {"label": "Prediabetes range", "tone": "watch"}
    assert a1c["points"][0]["source"] == "document" and a1c["points"][0]["document_id"] == first["id"]
    assert a1c["bands"][0] == {"from": None, "to": 5.7, "label": "Normal", "tone": "good"}
    assert tests["ldl_cholesterol"]["latest_band"]["label"] == "Borderline high"
    assert list(tests)[:2] == ["hba1c", "ldl_cholesterol"]      # clinically ordered

    dm = next(i for i in api.get("/v1/insights", headers=h).json()["insights"] if i["rule_id"] == "diabetes_risk")
    assert "Your HbA1c rose from 5.6% (Jan 2025) to 6.2% (Jan 2026)" in dm["evidence"]


def test_trends_for_a_relative_and_unit_normalisation(api):
    h = account(api)
    _save_lab(api, h, "7.1", "4.9", "01/03/2026", subject="father")   # LDL in mmol/L style value
    dad = next(m for m in api.get("/v1/profile", headers=h).json()["family"] if m["relationship"] == "father")
    tests = {t["code"]: t for t in api.get(f"/v1/trends?member_id={dad['id']}", headers=h).json()["tests"]}
    assert tests["hba1c"]["latest_band"]["label"] == "Diabetes range"
    assert api.get("/v1/trends", headers=h).json() == {"tests": []}
    assert api.get("/v1/trends?member_id=nope", headers=h).status_code == 404

    from fhg.trends import normalise
    assert normalise("ldl_cholesterol", 4.9, "mmol/L") == (189.5, "mg/dL")
    assert normalise("fasting_glucose", 7.0, "mmol/l") == (126.0, "mg/dL")
