import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import partners
from fhg.api import Settings, create_app

SAMPLES = Path(__file__).parent.parent / "fhg" / "sample_data"
HBOC = "hboc_family_pattern"
ADMIN = {"X-Admin-Key": "admin-secret"}


class FakeWebhooks:
    def __init__(self):
        self.calls = []
        self.fail = False

    def send(self, url, body, headers):
        if self.fail:
            raise ConnectionError("partner down")
        self.calls.append((url, body, headers))


@pytest.fixture
def hooks():
    return FakeWebhooks()


@pytest.fixture
def client(tmp_path, hooks):
    settings = Settings(db_path=str(tmp_path / "p.db"), encryption_key=Fernet.generate_key().decode(),
                        admin_key="admin-secret")
    return TestClient(create_app(settings, webhook_sender=hooks, webhooks_in_background=False,
                                 push_in_background=False))


def account(client):
    return {"Authorization": f"Bearer {client.post('/v1/users').json()['token']}"}


@pytest.fixture
def world(client):
    """A clinic, a connected high-risk patient, and a genetic-counseling partner."""
    admin = account(client)
    org = client.post("/v1/orgs", json={"name": "Riverside Family Practice"}, headers=admin).json()
    patient = account(client)
    client.post("/v1/ingest/fhir", json=json.loads((SAMPLES / "fhir_bundle.json").read_text()), headers=patient)
    client.post("/v1/clinics", json={"code": org["patient_code"], "display_name": "Priya Shah"}, headers=patient)
    created = client.post("/admin/partners", headers=ADMIN, json={
        "name": "GenomeCo Genetic Counseling", "kind": "genetic_counseling",
        "webhook_url": "https://partner.example/hooks/fhg"}).json()
    pref = client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()["patients"][0]["patient_ref"]
    return {"admin": admin, "org": org, "patient": patient, "pref": pref,
            "partner": created["partner"], "key": {"X-API-Key": created["api_key"]},
            "secret": created["webhook_secret"]}


def refer(client, w, **body):
    return client.post(f"/v1/orgs/{w['org']['id']}/patients/{w['pref']}/referrals", headers=w["admin"],
                       json={"rule_id": HBOC, "status": "referred", **body})


def test_admin_partner_management(client):
    assert client.post("/admin/partners", json={"name": "X Co"}).status_code == 403
    assert client.post("/admin/partners", headers={"X-Admin-Key": "nope"}, json={"name": "X Co"}).status_code == 403
    r = client.post("/admin/partners", headers=ADMIN, json={"name": "LabCo", "kind": "lab"})
    assert r.status_code == 201 and r.json()["api_key"].startswith("fhgp_")
    assert client.post("/admin/partners", headers=ADMIN, json={"name": "Bad", "webhook_url": "ftp://x"}).status_code == 422
    assert [p["name"] for p in client.get("/admin/partners", headers=ADMIN).json()] == ["LabCo"]


def test_directory_is_staff_only(client, world):
    names = [p["name"] for p in client.get("/v1/referral-partners", headers=world["admin"]).json()]
    assert names == ["GenomeCo Genetic Counseling"]
    assert client.get("/v1/referral-partners", headers=world["patient"]).status_code == 403


def test_end_to_end_referral_to_partner_and_back(client, world, hooks):
    assert refer(client, world, partner_id=world["partner"]["id"], note="Please see within 4 weeks").status_code == 200

    # Thin, signed webhook: no health data, verifiable with the secret.
    url, body, headers = hooks.calls[-1]
    assert url == "https://partner.example/hooks/fhg"
    evt = json.loads(body)
    assert evt["type"] == "referral.created" and set(evt["data"]) == {"referral_id"}
    assert partners.verify(world["secret"], body, headers["X-FHG-Signature"])
    assert not partners.verify(world["secret"], body + b"x", headers["X-FHG-Signature"])
    assert b"Priya" not in body and b"cancer" not in body.lower()

    # Partner pulls the referral with its API key.
    listing = client.get("/v1/partner/referrals", headers=world["key"]).json()
    ref = listing["referrals"][0]
    assert ref["referral_id"] == evt["data"]["referral_id"] and ref["patient"]["display_name"] == "Priya Shah"
    assert ref["clinic"]["name"] == "Riverside Family Practice" and ref["program"].startswith("Genetic counseling")
    sr = ref["service_request"]
    assert sr["resourceType"] == "ServiceRequest" and sr["status"] == "active" and sr["intent"] == "order"
    assert sr["performer"][0]["display"] == "GenomeCo Genetic Counseling"
    assert "Mother: Breast cancer" in sr["note"][0]["text"]
    assert ref["history"][0] == {**ref["history"][0], "by": "clinic", "note": "Please see within 4 weeks"}
    summary = client.get(f"/v1/partner/referrals/{ref['referral_id']}/summary", headers=world["key"])
    assert "Family health history summary" in summary.text

    # Partner reports back; the clinic funnel, patient app and audit trail all reflect it.
    rid = ref["referral_id"]
    assert client.post(f"/v1/partner/referrals/{rid}/status", headers=world["key"],
                       json={"status": "scheduled", "note": "Telehealth 3 Dec"}).json()["status"] == "scheduled"
    done = client.post(f"/v1/partner/referrals/{rid}/status", headers=world["key"], json={"status": "completed"}).json()
    assert done["service_request"]["status"] == "completed"
    assert [h["by"] for h in done["history"]] == ["clinic", "partner", "partner"]

    funnel = {f["rule_id"]: f for f in client.get(f"/v1/orgs/{world['org']['id']}/patients",
                                                  headers=world["admin"]).json()["impact"]["funnel"]}
    assert funnel[HBOC]["completed"] == 1
    flags = client.get(f"/v1/orgs/{world['org']['id']}/patients", headers=world["admin"]).json()["patients"][0]["flags"]
    assert next(f for f in flags if f["rule_id"] == HBOC)["partner"] == "GenomeCo Genetic Counseling"

    mine = client.get("/v1/referrals", headers=world["patient"]).json()[0]
    assert mine["status"] == "completed" and mine["partner_name"] == "GenomeCo Genetic Counseling"
    messages = [n["message"] for n in client.get("/v1/notifications", headers=world["patient"]).json()]
    assert any("with GenomeCo" in m for m in messages) and any("GenomeCo Genetic Counseling scheduled" in m for m in messages)
    actions = {a["action"] for a in client.get("/v1/audit", headers=world["patient"]).json()}
    assert {"clinic.referral_sent_to_partner", "partner.viewed_referral", "partner.viewed_summary",
            "partner.updated_referral"} <= actions


def test_partner_isolation_and_auth(client, world):
    refer(client, world, partner_id=world["partner"]["id"])
    other = client.post("/admin/partners", headers=ADMIN, json={"name": "OtherLab", "kind": "lab"}).json()
    other_key = {"X-API-Key": other["api_key"]}
    assert client.get("/v1/partner/referrals", headers=other_key).json()["referrals"] == []
    rid = client.get("/v1/partner/referrals", headers=world["key"]).json()["referrals"][0]["referral_id"]
    assert client.get(f"/v1/partner/referrals/{rid}", headers=other_key).status_code == 404
    assert client.post(f"/v1/partner/referrals/{rid}/status", headers=other_key, json={"status": "completed"}).status_code == 404
    assert client.get("/v1/partner/referrals").status_code == 401
    assert client.get("/v1/partner/referrals", headers={"X-API-Key": "fhgp_wrong"}).status_code == 401
    # Partners can't set clinic-only statuses.
    assert client.post(f"/v1/partner/referrals/{rid}/status", headers=world["key"], json={"status": "referred"}).status_code == 422

    # Deactivated partners lose access immediately.
    client.post(f"/admin/partners/{world['partner']['id']}/deactivate", headers=ADMIN)
    assert client.get("/v1/partner/referrals", headers=world["key"]).status_code == 401


def test_patient_disconnect_ends_partner_access(client, world):
    refer(client, world, partner_id=world["partner"]["id"])
    client.delete(f"/v1/clinics/{world['org']['id']}", headers=world["patient"])
    assert client.get("/v1/partner/referrals", headers=world["key"]).json()["referrals"] == []


def test_routing_rules_and_webhook_failures(client, world, hooks):
    assert refer(client, world, partner_id="nope").status_code == 422
    hooks.fail = True
    assert refer(client, world, partner_id=world["partner"]["id"]).status_code == 200   # push failure is non-fatal
    hooks.fail = False
    # Updating status without partner_id keeps the routing and sends referral.updated.
    client.post(f"/v1/orgs/{world['org']['id']}/patients/{world['pref']}/referrals", headers=world["admin"],
                json={"rule_id": HBOC, "status": "scheduled"})
    assert json.loads(hooks.calls[-1][1])["type"] == "referral.updated"
    # Explicit null routes it back in-house; the partner no longer sees it.
    refer(client, world, partner_id=None)
    assert client.get("/v1/partner/referrals", headers=world["key"]).json()["referrals"] == []


def test_signature_rejects_stale_timestamps():
    body = b'{"x":1}'
    header = partners.sign("s3cret", body, timestamp=1_000)
    assert partners.verify("s3cret", body, header, now=1_100)
    assert not partners.verify("s3cret", body, header, now=1_000 + 3600)
    assert not partners.verify("s3cret", body, "garbage")
