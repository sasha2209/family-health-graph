"""Phase 3: connecting patient portals (SMART on FHIR) and importing ABDM / FHIR record files."""
import base64
import hashlib
import json
import sqlite3
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from test_documents import FIX, text_pdf  # noqa: E402

from fhg.api import Settings, create_app  # noqa: E402
from fhg.connectors.smart import SmartError  # noqa: E402

ISS = "https://ehr.example.org/fhir"


class FakeEHR:
    """A SMART on FHIR server: discovery, PKCE token endpoint, and patient-scoped FHIR reads."""

    def __init__(self):
        self.codes: dict[str, str] = {}   # code -> PKCE challenge
        self.tokens = {"tok-1", "tok-2"}
        self.reads: list[str] = []
        self.refreshes = 0

    def get_json(self, url, token=None):
        if url == f"{ISS}/.well-known/smart-configuration":
            return {"authorization_endpoint": "https://ehr.example.org/authorize", "token_endpoint": "https://ehr.example.org/token"}
        if token not in self.tokens:
            raise SmartError("401")
        self.reads.append(url.removeprefix(ISS))
        path = url.removeprefix(ISS)
        if path == "/Patient/p123":
            return {"resourceType": "Patient", "id": "p123", "gender": "female", "birthDate": "1985-02-01"}
        if path.startswith("/Condition"):
            if "page=2" in path:
                return {"resourceType": "Bundle", "entry": [{"resource": {
                    "resourceType": "Condition", "code": {"text": "High blood pressure"}}}]}
            return {"resourceType": "Bundle", "link": [{"relation": "next", "url": f"{ISS}/Condition?patient=p123&page=2"}],
                    "entry": [{"resource": {"resourceType": "Condition", "code": {"coding": [
                        {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9"}], "text": "Type 2 diabetes"}}}]}
        if path.startswith("/Observation") and "laboratory" in path:
            return {"resourceType": "Bundle", "link": [{"relation": "next", "url": "https://evil.example.com/steal"}],
                    "entry": [{"resource": {"resourceType": "Observation", "effectiveDateTime": "2026-02-01",
                        "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                        "valueQuantity": {"value": 6.8, "unit": "%"}}}]}
        if path.startswith("/FamilyMemberHistory"):
            return {"resourceType": "Bundle", "entry": [{"resource": {
                "resourceType": "FamilyMemberHistory", "relationship": {"coding": [{"code": "MTH"}]},
                "condition": [{"code": {"text": "Breast cancer"}, "onsetAge": {"value": 44}}]}}]}
        if path.startswith("/MedicationStatement"):
            raise SmartError("403 not granted")
        return {"resourceType": "Bundle", "entry": []}

    def post_form(self, url, data):
        assert url == "https://ehr.example.org/token"
        if data["grant_type"] == "authorization_code":
            challenge = self.codes.pop(data["code"], None)
            expected = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).rstrip(b"=").decode()
            if challenge != expected:
                raise SmartError("invalid_grant")
            return {"access_token": "tok-1", "refresh_token": "ref-1", "expires_in": 3600, "patient": "p123",
                    "token_type": "Bearer"}
        if data["grant_type"] == "refresh_token" and data["refresh_token"] == "ref-1":
            self.refreshes += 1
            return {"access_token": "tok-2", "expires_in": 3600}
        raise SmartError("invalid_grant")

    def approve(self, authorize_url: str) -> str:
        """What the patient's browser does at the EHR: returns the redirect back to us."""
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(authorize_url).query))
        assert q["code_challenge_method"] == "S256" and q["aud"] == ISS and "patient/Condition.read" in q["scope"]
        self.codes["code-xyz"] = q["code_challenge"]
        return f"{urllib.parse.urlsplit(q['redirect_uri']).path}?code=code-xyz&state={q['state']}"


@pytest.fixture
def ehr():
    return FakeEHR()


@pytest.fixture
def api(tmp_path, ehr):
    providers = json.dumps([{"id": "riverside", "name": "Riverside Health (Epic)", "iss": ISS, "client_id": "fhg-app"}])
    return TestClient(create_app(Settings(db_path=str(tmp_path / "c.db"), encryption_key=Fernet.generate_key().decode(),
                                          public_url="https://app.example.org", smart_providers=providers), smart_http=ehr))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def connect(api, ehr, h, **extra):
    start = api.post("/v1/connect/smart", headers=h, json={"provider": "riverside", **extra})
    assert start.status_code == 200, start.text
    url = start.json()["authorize_url"]
    assert url.startswith("https://ehr.example.org/authorize?")
    assert dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))["redirect_uri"] == \
        "https://app.example.org/connect/smart/callback"
    return api.get(ehr.approve(url))


def test_connect_portal_and_import_records(api, ehr, tmp_path):
    h = account(api)
    assert api.get("/v1/connections", headers=h).json() == {
        "connections": [], "available": [{"id": "riverside", "name": "Riverside Health (Epic)", "kind": "smart"}]}
    page = connect(api, ehr, h)
    assert page.status_code == 200 and "Connected to Riverside Health (Epic)" in page.text
    assert 'href="/app/connections"' in page.text

    p = api.get("/v1/profile", headers=h).json()
    assert {c["category"] for c in p["conditions"]} == {"type_2_diabetes", "hypertension"}   # both pages read
    assert p["sex"] == "female" and p["birth_date"] == "1985-02-01"
    assert p["observations"][0]["code"] == "hba1c" and p["observations"][0]["value"] == 6.8
    mother = next(m for m in p["family"] if m["relationship"] == "mother")
    assert mother["conditions"][0]["category"] == "breast_cancer" and mother["conditions"][0]["onset_age"] == 44
    conn = api.get("/v1/connections", headers=h).json()["connections"][0]
    assert conn["status"] == "active" and conn["last_sync_summary"]["read"]["Condition"] == 2
    assert p["conditions"][0]["source"] == f"smart:{conn['id']}"
    # Paging never follows a link to another host; a resource type the portal refuses is skipped.
    assert not any("evil" in r for r in ehr.reads)
    # Tokens are encrypted at rest.
    raw = (tmp_path / "c.db").read_bytes()
    assert b"ref-1" not in raw and b"tok-1" not in raw


def test_state_is_single_use_and_cancel_imports_nothing(api, ehr):
    h = account(api)
    start = api.post("/v1/connect/smart", headers=h, json={"provider": "riverside"}).json()
    back = ehr.approve(start["authorize_url"])
    assert "Connected" in api.get(back).text
    assert api.get(back).status_code == 400                                 # replay
    assert api.get("/connect/smart/callback?state=forged&code=x").status_code == 400

    start = api.post("/v1/connect/smart", headers=h, json={"provider": "riverside"}).json()
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(start["authorize_url"]).query))["state"]
    r = api.get(f"/connect/smart/callback?state={state}&error=access_denied")
    assert "cancelled" in r.text and len(api.get("/v1/connections", headers=h).json()["connections"]) == 1
    assert api.post("/v1/connect/smart", headers=h, json={"provider": "nope"}).status_code == 404


def test_wrong_pkce_verifier_is_refused(api, ehr):
    h = account(api)
    start = api.post("/v1/connect/smart", headers=h, json={"provider": "riverside"}).json()
    back = ehr.approve(start["authorize_url"])
    ehr.codes["code-xyz"] = "not-the-challenge"
    r = api.get(back)
    assert r.status_code == 502 and api.get("/v1/connections", headers=h).json()["connections"] == []


def test_sync_refreshes_an_expired_token(api, ehr):
    from unittest import mock
    h = account(api)
    connect(api, ehr, h)
    conn_id = api.get("/v1/connections", headers=h).json()["connections"][0]["id"]
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    with mock.patch("fhg.api.datetime") as dt:      # two hours on: the 1-hour access token has expired
        dt.now.return_value = later
        dt.fromisoformat = datetime.fromisoformat
        r = api.post(f"/v1/connections/{conn_id}/sync", headers=h)
    assert r.status_code == 200, r.text
    assert ehr.refreshes == 1
    assert r.json()["merged"]["conditions"] == 0          # the same records again: nothing duplicated


def test_disconnect_deletes_tokens(api, ehr, tmp_path):
    h, other = account(api), account(api)
    connect(api, ehr, h)
    conn_id = api.get("/v1/connections", headers=h).json()["connections"][0]["id"]
    assert api.post(f"/v1/connections/{conn_id}/sync", headers=other).status_code == 404
    assert api.delete(f"/v1/connections/{conn_id}", headers=other).status_code == 404
    assert api.delete(f"/v1/connections/{conn_id}", headers=h).status_code == 204
    assert api.get("/v1/connections", headers=h).json()["connections"] == []
    (secret,) = sqlite3.connect(tmp_path / "c.db").execute("SELECT secret FROM connections").fetchone()
    assert secret is None
    # Imported records stay.
    assert api.get("/v1/profile", headers=h).json()["conditions"]


def test_return_to_cannot_redirect_off_site(api, ehr):
    h = account(api)
    page = connect(api, ehr, h, return_to="//evil.example.com/")
    assert "evil" not in page.text and 'href="/app/connections"' in page.text
    page = connect(api, ehr, h, return_to="/app/settings")
    assert 'href="/app/settings"' in page.text


# --- ABDM / FHIR record files -----------------------------------------------------------------

def abdm_bundle(with_structured=True, pdf: bytes | None = None) -> dict:
    entries = [
        {"resource": {"resourceType": "Composition", "status": "final", "date": "2026-03-14",
                      "title": "Prescription record", "type": {"coding": [{"system": "http://snomed.info/sct",
                                                                           "code": "440545006", "display": "Prescription record"}]}}},
        {"resource": {"resourceType": "Patient", "name": [{"text": "Sunita Shah"}], "gender": "female"}},
        {"resource": {"resourceType": "Practitioner", "name": [{"text": "Dr. Anil Mehta"}]}},
        {"resource": {"resourceType": "Organization", "name": "City Care Clinic"}},
    ]
    if with_structured:
        entries += [
            {"resource": {"resourceType": "Condition", "code": {"coding": [{"system": "http://snomed.info/sct",
                                                                             "code": "44054006"}], "text": "Diabetes mellitus type 2"}}},
            {"resource": {"resourceType": "MedicationRequest", "status": "active",
                          "medicationCodeableConcept": {"text": "Metformin 500 mg"}}},
        ]
    if pdf:
        entries.append({"resource": {"resourceType": "DocumentReference", "status": "current", "content": [
            {"attachment": {"contentType": "application/pdf", "data": base64.b64encode(pdf).decode()}}]}})
    return {"resourceType": "Bundle", "type": "document", "entry": entries}


def upload(api, h, data: bytes):
    return api.post("/v1/documents", headers=h, json={"data_base64": base64.b64encode(data).decode(),
                                                      "filename": "record.json"})


def test_abdm_record_file_goes_through_review(api):
    h = account(api)
    r = upload(api, h, json.dumps(abdm_bundle()).encode())
    assert r.status_code == 201, r.text
    doc = r.json()
    e = doc["extraction"]
    assert doc["method"] == "fhir" and doc["media_type"] == "application/fhir+json"
    assert (e["doc_type"], e["doc_date"], e["doctor"], e["facility"]) == ("prescription", "2026-03-14",
                                                                         "Dr. Anil Mehta", "City Care Clinic")
    assert e["patient"]["name"] == "Sunita Shah" and e["conditions"][0]["category"] == "type_2_diabetes"
    assert e["medications"][0]["name"] == "Metformin 500 mg"
    assert api.get("/v1/profile", headers=h).json()["conditions"] == []     # waits for review
    assert "Composition" in doc["text_preview"]


def test_pdf_only_abdm_record_is_read_by_ocr(api):
    h = account(api)
    pdf = text_pdf((FIX / "lab_report.txt").read_text().splitlines())
    doc = upload(api, h, json.dumps(abdm_bundle(with_structured=False, pdf=pdf)).encode()).json()
    obs = {o["code"]: o["value"] for o in doc["extraction"]["observations"]}
    assert obs["hba1c"] == 7.8 and doc["extraction"]["doc_date"] == "2026-03-14"
    assert "Attached report" in doc["text_preview"]
