import json
import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app
from fhg.clinician_report import pedigree_svg
from fhg.ingest import parse_fhir

SAMPLES = Path(__file__).parent.parent / "fhg" / "sample_data"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "r.db"),
                                          encryption_key=Fernet.generate_key().decode())))


def account(client):
    return {"Authorization": f"Bearer {client.post('/v1/users').json()['token']}"}


def test_report_sections_and_content(client):
    h = account(client)
    client.post("/v1/ingest/fhir", json=json.loads((SAMPLES / "fhir_bundle.json").read_text()), headers=h)
    r = client.get("/v1/report/clinician", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"
    html = r.text
    for heading in ("Items to consider", "Pedigree", "Family history", "Patient's own history",
                    "Information still missing"):
        assert heading in html
    assert "Family pattern worth a hereditary cancer risk assessment" in html
    assert "USPSTF" in html                      # guideline cited
    assert "1984-05-02" in html and "Female" in html
    assert "LDL cholesterol 172 mg/dL (2026-03-10)" in html
    assert "BP 134/86 mmHg" in html
    assert "Levothyroxine" in html
    assert "Patient-reported" in html
    assert "report.clinician" in [a["action"] for a in client.get("/v1/audit", headers=h).json()]


def test_report_escapes_user_text(client):
    h = account(client)
    client.post("/v1/family", headers=h, json={"relationship": "sister", "name": "<img src=x onerror=alert(1)>",
                                               "conditions": [{"name": "<script>alert(1)</script>"}]})
    html = client.get("/v1/report/clinician", headers=h).text
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_shared_history_can_be_left_out(client):
    me, mom = account(client), account(client)
    inv = client.post("/v1/invitations", json={"relationship": "mother"}, headers=me).json()
    client.post(f"/v1/invites/{inv['token']}/accept", json={}, headers=mom)
    client.post("/v1/ingest/text", json={"text": "I have Lynch syndrome."}, headers=mom)
    assert "Lynch" in client.get("/v1/report/clinician", headers=me).text
    assert "Shared by relative" in client.get("/v1/report/clinician", headers=me).text
    assert "Lynch" not in client.get("/v1/report/clinician?include_shared=false", headers=me).text


def test_requires_auth(client):
    assert client.get("/v1/report/clinician").status_code == 401


def test_pedigree_draws_every_placed_relative():
    profile = parse_fhir(json.loads((SAMPLES / "fhir_bundle.json").read_text()))
    svg = pedigree_svg(profile)
    # Sample: father, mother, maternal aunt, paternal grandfather (+ paternal GM placeholder),
    # maternal grandmother (+ maternal GF placeholder), sister, and the patient = 9 symbols.
    symbols = len(re.findall(r"<(rect|circle|polygon points=\"[\d.]+,[\d.]+ [\d.]+,[\d.]+ [\d.]+,[\d.]+ [\d.]+,[\d.]+\")", svg))
    assert symbols == 9
    assert svg.count('stroke-dasharray') == 2          # the two unrecorded grandparents
    assert "Patient" in svg and "Breast ca 46" in svg and "CAD/MI 51" in svg
