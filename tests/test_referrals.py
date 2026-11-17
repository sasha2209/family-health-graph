import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app

SAMPLES = Path(__file__).parent.parent / "fhg" / "sample_data"
HBOC = "hboc_family_pattern"
CRC = "colorectal_family_history"


class FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, messages):
        self.sent.extend(messages)
        return []


@pytest.fixture
def sender():
    return FakeSender()


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "ref.db"), encryption_key=Fernet.generate_key().decode())


@pytest.fixture
def client(settings, sender):
    return TestClient(create_app(settings, push_sender=sender, push_in_background=False))


def account(client):
    return {"Authorization": f"Bearer {client.post('/v1/users').json()['token']}"}


@pytest.fixture
def setup(client):
    admin = account(client)
    org = client.post("/v1/orgs", json={"name": "Riverside Family Practice"}, headers=admin).json()

    def connect(name, *, fhir=False, text=None):
        h = account(client)
        if fhir:
            client.post("/v1/ingest/fhir", json=json.loads((SAMPLES / "fhir_bundle.json").read_text()), headers=h)
        if text:
            client.post("/v1/ingest/text", json={"text": text}, headers=h)
        client.post("/v1/clinics", json={"code": org["patient_code"], "display_name": name}, headers=h)
        return h

    return admin, org, connect


def worklist(client, admin, org):
    return client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()


def ref_of(data, name):
    return next(p["patient_ref"] for p in data["patients"] if p["display_name"] == name)


def refer(client, admin, org, pref, rule, status, note=None):
    return client.post(f"/v1/orgs/{org['id']}/patients/{pref}/referrals", headers=admin,
                       json={"rule_id": rule, "status": status, "note": note})


def test_referral_pipeline_and_funnel(client, setup, sender):
    admin, org, connect = setup
    priya = connect("Priya Shah", fhir=True)
    connect("Ana Ruiz", text="My mother had ovarian cancer at 50.")
    connect("Sam Ortiz", text="My father had colon cancer at 44.")
    data = worklist(client, admin, org)
    priya_ref, ana_ref = ref_of(data, "Priya Shah"), ref_of(data, "Ana Ruiz")

    # Every flag starts as "identified".
    assert {f["referral"] for p in data["patients"] for f in p["flags"]} == {"identified"}

    r = refer(client, admin, org, priya_ref, HBOC, "referred", note="Genome counseling clinic, Dr Lee")
    assert r.status_code == 200 and r.json()["status"] == "referred"
    assert r.json()["history"][0] == {**r.json()["history"][0], "status": "referred", "by_you": True,
                                      "note": "Genome counseling clinic, Dr Lee"}
    refer(client, admin, org, priya_ref, HBOC, "scheduled")
    final = refer(client, admin, org, priya_ref, HBOC, "completed").json()
    assert [e["status"] for e in final["history"]] == ["referred", "scheduled", "completed"]
    refer(client, admin, org, ana_ref, HBOC, "declined", note="Prefers to wait")

    data = worklist(client, admin, org)
    priya_flags = {f["rule_id"]: f["referral"] for p in data["patients"] if p["display_name"] == "Priya Shah"
                   for f in p["flags"]}
    assert priya_flags[HBOC] == "completed"

    funnel = {f["rule_id"]: f for f in data["impact"]["funnel"]}
    hboc = funnel[HBOC]
    assert (hboc["identified"], hboc["referred"], hboc["scheduled"], hboc["completed"], hboc["declined"]) == (2, 1, 1, 1, 1)
    assert hboc["completion_rate"] == 50 and hboc["median_days_to_complete"] is not None
    assert funnel[CRC]["identified"] == 1 and funnel[CRC]["referred"] == 0
    assert data["impact"]["referrals_completed"] == 1 and data["impact"]["referrals_made"] == 1

    # The patient sees it, is notified with a generic push, and the audit log records it.
    mine = client.get("/v1/referrals", headers=priya).json()
    assert mine[0]["status"] == "completed" and mine[0]["org_name"] == "Riverside Family Practice"
    assert mine[0]["program"].startswith("Genetic counseling")
    notes = [n["message"] for n in client.get("/v1/notifications", headers=priya).json() if n["kind"] == "referral"]
    assert len(notes) == 2 and "referred you for" in notes[-1] and "scheduled your" in notes[0]
    assert all("Genetic" not in (m.title + m.body) for m in sender.sent)
    assert any(a["action"] == "clinic.referral" for a in client.get("/v1/audit", headers=priya).json())


def test_referral_validation_and_access(client, setup):
    admin, org, connect = setup
    connect("Priya Shah", fhir=True)
    pref = ref_of(worklist(client, admin, org), "Priya Shah")
    assert refer(client, admin, org, pref, "made_up_rule", "referred").status_code == 422
    assert refer(client, admin, org, pref, HBOC, "lost").status_code == 422
    assert refer(client, admin, org, "nobody", HBOC, "referred").status_code == 404
    outsider = account(client)
    assert refer(client, outsider, org, pref, HBOC, "referred").status_code == 404


def test_disconnect_deletes_referrals_and_notes_are_encrypted(client, setup, settings):
    admin, org, connect = setup
    priya = connect("Priya Shah", fhir=True)
    pref = ref_of(worklist(client, admin, org), "Priya Shah")
    refer(client, admin, org, pref, HBOC, "referred", note="secret-referral-note")
    assert "secret-referral-note" not in "\n".join(sqlite3.connect(settings.db_path).iterdump())

    client.delete(f"/v1/clinics/{org['id']}", headers=priya)
    assert client.get("/v1/referrals", headers=priya).json() == []
    assert worklist(client, admin, org)["impact"]["funnel"] == []
