"""The trust layer: direct ABHA link via the ABDM Wrapper, DPDP Act rights, breach notices, and hardening."""
import json

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app
from fhg.connectors import abdm

ADMIN = {"X-Admin-Key": "admin-secret"}
WRAPPER = "http://wrapper.local:8082"

LAB_BUNDLE = {"resourceType": "Bundle", "type": "collection", "entry": [
    {"resource": {"resourceType": "Condition", "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006",
                                                                     "display": "Type 2 diabetes"}]}}},
    {"resource": {"resourceType": "Observation", "effectiveDateTime": "2026-10-02",
                  "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                  "valueQuantity": {"value": 7.2, "unit": "%"}}}]}


class FakeWrapper:
    """Answers like the ABDM Wrapper's v3 HIU facade (docs/wrapperV3.yaml in NHA-ABDM/ABDM-wrapper)."""

    def __init__(self):
        self.calls, self.consent = [], "REQUESTED"
        self.records_ready = False

    def request_json(self, method, url, body=None):
        path = url.removeprefix(WRAPPER)
        self.calls.append((method, path, body))
        if path == "/v3/consent-init":
            if body["consent"]["patient"]["id"] == "nobody@sbx":
                return 400, {"message": "Initiation of consent failed", "errors": [{"error": {"code": 1000, "message": "Invalid patient"}}]}
            return 202, {"clientRequestId": "creq-1", "httpStatusCode": "ACCEPTED"}
        if path.startswith("/v3/consent-status/"):
            if self.consent == "GRANTED":
                return 200, {"status": "CONSENT_ON_NOTIFY_RESPONSE_RECEIVED", "consentDetails": {
                    "grantedOn": "2026-11-24", "hiTypes": ["DiagnosticReport"],
                    "consent": [{"status": "GRANTED", "consentArtefacts": [{"id": "art-1", "hipId": "RUBY_HALL"}]}]}}
            return 200, {"status": self.consent if self.consent != "REQUESTED" else "CONSENT_INIT_ACCEPTED"}
        if path == "/v3/health-information/fetch-records":
            return 202, {"clientRequestId": "hreq-1"}
        if path.startswith("/v3/health-information/status/"):
            if not self.records_ready:
                return 200, {"status": "HEALTH_INFORMATION_REQUEST_SUCCESS", "decryptedHealthInformationEntries": []}
            return 200, {"status": "ENCRYPTED_HEALTH_INFORMATION_RECEIVED", "decryptedHealthInformationEntries": [
                {"careContextReference": "visit-1", "bundleContent": json.dumps(LAB_BUNDLE)}]}
        return 404, {}


class Hooks:
    def __init__(self):
        self.sent = []

    def send(self, url, body, headers):
        self.sent.append(json.loads(body))


@pytest.fixture
def wrapper():
    return FakeWrapper()


@pytest.fixture
def hooks():
    return Hooks()


@pytest.fixture
def api(tmp_path, wrapper, hooks):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "t.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret", abdm_wrapper_url=WRAPPER, abdm_hiu_id="FHG_HIU",
                                          grievance_officer_name="Privacy Officer", grievance_officer_email="privacy@fhg.example",
                                          grievance_days=30),
                                 abdm_http=wrapper, webhook_sender=hooks, webhooks_in_background=False,
                                 push_in_background=False))


def account(api, birth="1985-06-01"):
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.put("/v1/profile/demographics", headers=h, json={"sex": "female", "birth_date": birth})
    return h


# --- ABHA ------------------------------------------------------------------------------------------

def test_abha_address_format():
    assert abdm.valid_abha_address("priya.shah@abdm") and abdm.valid_abha_address("priya_85@sbx")
    assert not abdm.valid_abha_address("priya@gmail.com") and not abdm.valid_abha_address("@abdm")


def test_abha_link_consent_then_records(api, wrapper):
    h = account(api)
    assert {"id": "abdm", "name": "ABHA (hospitals and labs across India)", "kind": "abdm"} in \
        api.get("/v1/connections", headers=h).json()["available"]
    assert api.post("/v1/connect/abha", headers=h, json={"abha_address": "priya@gmail.com"}).status_code == 422
    assert api.post("/v1/connect/abha", headers=h, json={"abha_address": "nobody@sbx"}).status_code == 502
    r = api.post("/v1/connect/abha", headers=h, json={"abha_address": "Priya.Shah@sbx"})
    assert r.status_code == 201 and "approve the request" in r.json()["message"]
    cid = r.json()["id"]
    init = next(b for m, p, b in wrapper.calls if p == "/v3/consent-init" and b["consent"]["patient"]["id"] == "priya.shah@sbx")
    c = init["consent"]
    assert (c["hiu"], c["purpose"]["code"], c["permission"]["accessMode"]) == ({"id": "FHG_HIU"}, "CAREMGT", "STORE")
    assert "DiagnosticReport" in c["hiTypes"] and c["permission"]["dateRange"]["to"].endswith("Z")

    # Not approved yet.
    assert api.post(f"/v1/connections/{cid}/sync", headers=h).json()["status"] == "pending"
    # Approved; the HIP hasn't sent the records yet.
    wrapper.consent = "GRANTED"
    out = api.post(f"/v1/connections/{cid}/sync", headers=h).json()
    assert out["status"] == "pending" and "Still fetching from 1 source" in out["message"]
    # Records arrive and go through the FHIR import.
    wrapper.records_ready = True
    out = api.post(f"/v1/connections/{cid}/sync", headers=h).json()
    assert out["status"] == "active" and out["merged"]["observations"] == 1 and out["merged"]["conditions"] == 1
    p = api.get("/v1/profile", headers=h).json()
    assert p["observations"][0]["source"] == "abdm:RUBY_HALL" and p["conditions"][0]["category"] == "type_2_diabetes"
    fetches = [c for c in wrapper.calls if c[1] == "/v3/health-information/fetch-records"]
    assert len(fetches) == 1 and fetches[0][2]["consentId"] == "art-1"          # requested once, not on every sync
    # Syncing again doesn't import twice.
    assert api.post(f"/v1/connections/{cid}/sync", headers=h).json()["merged"]["observations"] == 0
    conn = api.get("/v1/connections", headers=h).json()["connections"][0]
    assert conn["display_name"] == "ABHA · priya.shah@sbx" and conn["status"] == "active"


def test_abha_denied(api, wrapper):
    h = account(api)
    cid = api.post("/v1/connect/abha", headers=h, json={"abha_address": "priya@sbx"}).json()["id"]
    wrapper.consent = "DENIED"
    r = api.post(f"/v1/connections/{cid}/sync", headers=h)
    assert r.status_code == 409 and "declined" in r.json()["detail"]


def test_abha_needs_configuration(tmp_path):
    plain = TestClient(create_app(Settings(db_path=str(tmp_path / "p.db"), encryption_key=Fernet.generate_key().decode())))
    h = {"Authorization": f"Bearer {plain.post('/v1/users').json()['token']}"}
    assert plain.post("/v1/connect/abha", headers=h, json={"abha_address": "a.b@sbx"}).status_code == 404
    assert all(a["kind"] != "abdm" for a in plain.get("/v1/connections", headers=h).json()["available"])


# --- DPDP rights -----------------------------------------------------------------------------------

def test_notice_in_english_and_hindi(api):
    en = api.get("/v1/privacy/notice").json()
    assert en["title"] == "How we use your information" and en["contact"]["email"] == "privacy@fhg.example"
    assert any("Data Protection Board" in i["title"] for s in en["sections"] for i in s["items"])
    hi = api.get("/v1/privacy/notice?lang=hi").json()
    assert hi["lang"] == "hi" and "आपकी जानकारी" in hi["title"] and len(hi["sections"]) == len(en["sections"])
    assert api.get("/v1/privacy/notice?lang=fr").json()["lang"] == "en"


def test_summary_export_nominee_and_grievance(api):
    h = account(api)
    api.post("/v1/ingest/text", headers=h, json={"text": "My mother had breast cancer at 45."})
    api.post("/v1/clinics", headers=h, json={"code": api.post("/v1/orgs", headers=account(api), json={"name": "Riverside"})
                                             .json()["patient_code"], "display_name": "Priya"})
    s = api.get("/v1/privacy", headers=h).json()
    assert s["held"][1]["count"] == 1 and s["minor"] is False
    assert {"with": "Riverside (clinic)", "what": "Your record and insights"}.items() <= s["shared_with"][0].items()

    assert api.put("/v1/privacy/nominee", headers=h, json={"name": "Rahul", "relationship": "brother",
                                                           "phone": "+91 98123 00000"}).json()["name"] == "Rahul"
    g = api.post("/v1/privacy/grievances", headers=h, json={"category": "sharing", "message": "Who saw my record?"}).json()
    assert g["status"] == "open" and "30 days" in g["message"]
    assert api.post("/v1/privacy/grievances", headers=h, json={"category": "spam", "message": "hello there"}).status_code == 422

    assert api.get("/admin/grievances").status_code in (401, 403)
    open_ = api.get("/admin/grievances", headers=ADMIN).json()
    assert open_[0]["message"] == "Who saw my record?" and open_[0]["overdue"] is False
    api.post(f"/admin/grievances/{g['id']}/answer", headers=ADMIN, json={"response": "Only Riverside, on 24 Nov."})
    assert api.get("/v1/privacy", headers=h).json()["grievances"][0]["status"] == "resolved"
    assert any("Only Riverside" in n["message"] for n in api.get("/v1/notifications", headers=h).json())

    e = api.get("/v1/privacy/export", headers=h)
    data = e.json()
    assert "attachment" in e.headers["content-disposition"] and data["nominee"]["name"] == "Rahul"
    assert data["profile"]["family"][0]["relationship"] == "mother" and any(
        a["action"] == "privacy.export" for a in api.get("/v1/audit", headers=h).json())


def test_minors_cannot_switch_on_sharing(api):
    teen = account(api, birth="2012-01-01")
    r = api.post("/v1/consents", headers=teen, json={"scope": "research_deidentified", "granted": True})
    assert r.status_code == 403 and "under 18" in r.json()["detail"]
    assert api.post("/v1/consents", headers=teen, json={"scope": "research_deidentified", "granted": False}).status_code == 200
    assert api.get("/v1/privacy", headers=teen).json()["minor"] is True
    adult = account(api)
    assert api.post("/v1/consents", headers=adult, json={"scope": "research_deidentified", "granted": True}).status_code == 200


def test_erasure_tells_partners(api, hooks):
    h = account(api)
    lab = api.post("/admin/partners", headers=ADMIN, json={"name": "Thyro Labs", "kind": "lab",
                                                          "webhook_url": "https://thyro.example/hooks"}).json()
    api.put(f"/admin/partners/{lab['partner']['id']}/catalog", headers=ADMIN, json=[{"test": "hba1c", "price_inr": 450}])
    b = api.post("/v1/bookings", headers=h, json={"partner_id": lab["partner"]["id"], "tests": ["hba1c"], "contact": {
        "name": "Priya", "phone": "+91 98123 45678"}}).json()
    assert api.delete("/v1/me", headers=h).status_code == 204
    assert {"type": "booking.erasure_requested", "data": {"booking_id": b["id"]}}.items() <= hooks.sent[-1].items()


# --- breaches, hardening, housekeeping ------------------------------------------------------------

def test_breach_register_notifies_affected_people(api):
    a, b = account(api), account(api)
    uid = api.get("/v1/auth/me", headers=a).json()["user_id"]
    body = {"nature": "A misconfigured backup was publicly readable for 2 hours.", "data_affected": ["email addresses"],
            "detected_at": "2026-11-24T08:00:00Z", "likely_consequences": "Your email could be used for phishing.",
            "measures_taken": "The backup was locked down and access logs reviewed.",
            "what_you_can_do": "Be careful with emails asking for your sign-in code."}
    assert api.post("/admin/breaches", headers=ADMIN, json=body).status_code == 422          # who is affected?
    r = api.post("/admin/breaches", headers=ADMIN, json={**body, "affected_user_ids": [uid, "unknown"]}).json()
    assert r["notified"] == 1
    note = api.get("/v1/notifications", headers=a).json()[0]
    assert note["kind"] == "security" and "publicly readable" in note["message"] and "privacy@fhg.example" in note["message"]
    assert api.get("/v1/notifications", headers=b).json() == []
    assert api.post(f"/admin/breaches/{r['id']}/board/intimation", headers=ADMIN).json()["board_intimated_at"]
    assert api.post(f"/admin/breaches/{r['id']}/board/later", headers=ADMIN).status_code == 404
    assert api.get("/admin/breaches", headers=ADMIN).json()[0]["affected"] == 1


def test_security_headers_and_housekeeping(api):
    r = api.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "strict-transport-security" not in r.headers                    # only over https
    assert api.post("/admin/tasks/housekeeping", headers=ADMIN).json()["deleted"].keys() >= {"login_codes", "care_invites"}
