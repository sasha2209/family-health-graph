import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app

SAMPLES = Path(__file__).parent.parent / "fhg" / "sample_data"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "c.db"),
                                          encryption_key=Fernet.generate_key().decode())))


def account(client):
    return {"Authorization": f"Bearer {client.post('/v1/users').json()['token']}"}


@pytest.fixture
def clinic(client):
    admin = account(client)
    org = client.post("/v1/orgs", json={"name": "Riverside Family Practice"}, headers=admin).json()
    return admin, org


def connect(client, org, name, text=None, fhir=False):
    h = account(client)
    if fhir:
        client.post("/v1/ingest/fhir", json=json.loads((SAMPLES / "fhir_bundle.json").read_text()), headers=h)
    if text:
        client.post("/v1/ingest/text", json={"text": text}, headers=h)
    r = client.post("/v1/clinics", json={"code": org["patient_code"].lower(), "display_name": name}, headers=h)
    assert r.status_code == 201 and r.json()["name"] == "Riverside Family Practice"
    return h


def test_create_org_and_codes(client, clinic):
    admin, org = clinic
    assert org["role"] == "admin" and len(org["patient_code"]) == 9 and org["staff_code"] != org["patient_code"]
    assert client.get("/v1/orgs", headers=admin).json()[0]["id"] == org["id"]


def test_worklist_sorted_by_priority_with_programs_and_impact(client, clinic):
    admin, org = clinic
    connect(client, org, "Low Risk Lee", text="My dad has high blood pressure.")
    connect(client, org, "Priya Shah", fhir=True)
    connect(client, org, "Sam Ortiz", text="My father had colon cancer at 44.")

    data = client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()
    names = [p["display_name"] for p in data["patients"]]
    assert names[-1] == "Low Risk Lee"                       # nothing actionable, sorts last
    assert set(names[:2]) == {"Priya Shah", "Sam Ortiz"}      # both have high-priority items

    priya = next(p for p in data["patients"] if p["display_name"] == "Priya Shah")
    programs = {f["program"] for f in priya["flags"]}
    assert "Genetic counseling: hereditary breast/ovarian cancer" in programs
    assert priya["age"] is not None and priya["sex"] == "female" and priya["completeness"] >= 60

    impact = data["impact"]
    assert impact["patients_connected"] == 3 and impact["patients_with_high_priority"] == 2
    progs = {p["program"]: p["patients"] for p in impact["programs"]}
    assert progs["Earlier colorectal screening / Lynch evaluation"] == 1


def test_report_and_audit_trail(client, clinic):
    admin, org = clinic
    patient = connect(client, org, "Priya Shah", fhir=True)
    ref = client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()["patients"][0]["patient_ref"]
    r = client.get(f"/v1/orgs/{org['id']}/patients/{ref}/report", headers=admin)
    assert r.status_code == 200 and "Family health history summary" in r.text
    actions = [(a["actor"], a["action"]) for a in client.get("/v1/audit", headers=patient).json()]
    assert (f"org:{org['id']}", "clinic.viewed_report") in actions
    assert ("user", "clinic.connected") in actions


def test_access_control(client, clinic):
    admin, org = clinic
    outsider = account(client)
    connect(client, org, "Priya Shah", fhir=True)
    assert client.get(f"/v1/orgs/{org['id']}/patients", headers=outsider).status_code == 404
    assert client.get(f"/v1/orgs/{org['id']}/patients/abc/report", headers=admin).status_code == 404

    # A colleague joins with the staff code (and doesn't get to see it, only admins do).
    colleague = account(client)
    joined = client.post("/v1/orgs/join", json={"code": org["staff_code"]}, headers=colleague).json()
    assert joined["role"] == "clinician" and "staff_code" not in joined
    assert len(client.get(f"/v1/orgs/{org['id']}/patients", headers=colleague).json()["patients"]) == 1

    # The patient code can't be used to join as staff, and vice versa.
    assert client.post("/v1/orgs/join", json={"code": org["patient_code"]}, headers=outsider).status_code == 404
    bad = client.post("/v1/clinics", json={"code": org["staff_code"], "display_name": "x y"}, headers=outsider)
    assert bad.status_code == 404


def test_patient_can_disconnect_and_ids_differ_between_clinics(client, clinic):
    admin, org = clinic
    patient = connect(client, org, "Priya Shah", fhir=True)
    other_admin = account(client)
    other = client.post("/v1/orgs", json={"name": "Lakeside Cardiology"}, headers=other_admin).json()
    client.post("/v1/clinics", json={"code": other["patient_code"], "display_name": "P. Shah"}, headers=patient)

    ref_a = client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()["patients"][0]["patient_ref"]
    ref_b = client.get(f"/v1/orgs/{other['id']}/patients", headers=other_admin).json()["patients"][0]["patient_ref"]
    assert ref_a != ref_b
    assert {c["name"] for c in client.get("/v1/clinics", headers=patient).json()} == {
        "Riverside Family Practice", "Lakeside Cardiology"}

    assert client.delete(f"/v1/clinics/{org['id']}", headers=patient).status_code == 204
    assert client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()["patients"] == []
    assert client.get(f"/v1/orgs/{org['id']}/patients/{ref_a}/report", headers=admin).status_code == 404


def test_lookup_and_portal_page(client, clinic):
    _, org = clinic
    h = account(client)
    assert client.get(f"/v1/clinics/lookup/{org['patient_code']}", headers=h).json()["name"] == "Riverside Family Practice"
    assert client.get("/v1/clinics/lookup/NOPE-NOPE", headers=h).status_code == 404
    assert "Clinic portal" in client.get("/portal").text
