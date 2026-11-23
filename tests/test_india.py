"""India-specific: the Indian Diabetes Risk Score and the brand → generic medicine list."""
import base64
import sys
from datetime import date
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from test_documents import text_pdf  # noqa: E402

from fhg.api import Settings, create_app  # noqa: E402
from fhg.insights.rules import idrs  # noqa: E402
from fhg.medicines import lookup, size  # noqa: E402
from fhg.models import Condition, FamilyMember, HealthProfile, Observation, Relationship, Sex  # noqa: E402


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "i.db"), encryption_key=Fernet.generate_key().decode())))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def born(age: int) -> str:
    return date(date.today().year - age, 1, 1).isoformat()   # 1 January: exactly `age` today


# --- IDRS ---------------------------------------------------------------------------------------

def profile(age, sex, waist=None, activity=None, parents=()):
    p = HealthProfile(sex=Sex(sex), birth_date=date.fromisoformat(born(age)), activity=activity)
    if waist is not None:
        p.observations.append(Observation(code="waist_circumference", value=waist, unit="cm", effective_date=date.today()))
    for rel in parents:
        p.family.append(FamilyMember(relationship=Relationship(rel), conditions=[
            Condition(name="Type 2 diabetes", category="type_2_diabetes")]))
    return p


@pytest.mark.parametrize("args,score", [
    ((30, "female", 75, "exercise_and_active_work", ()), 0),                 # all lowest bands
    ((34, "male", 89, "exercise_and_active_work", ()), 0),
    ((35, "male", 90, "exercise_or_active_work", ("mother",)), 20 + 10 + 20 + 10),
    ((49, "female", 80, "exercise_or_active_work", ()), 20 + 10 + 20),
    ((50, "female", 90, "sedentary", ("mother", "father")), 30 + 20 + 30 + 20),   # maximum = 100
    ((62, "male", 99, "sedentary", ("father",)), 30 + 10 + 30 + 10),
    ((62, "male", 100, "sedentary", ()), 30 + 20 + 30),
])
def test_idrs_scoring_matches_the_published_bands(args, score):
    r = idrs(profile(*args))
    assert r["score"] == score and r["missing"] == []


def test_idrs_missing_answers_are_listed_not_guessed():
    r = idrs(profile(55, "female"))
    assert r["score"] == 30 and set(r["missing"]) == {"waist size", "physical activity"}
    assert idrs(HealthProfile()) is None


def test_idrs_insight_through_the_api(api):
    h = account(api)
    api.put("/v1/profile/demographics", headers=h, json={"sex": "male", "birth_date": born(52)})
    api.post("/v1/ingest/text", headers=h, json={"text": "My mother had diabetes."})
    rules = {i["rule_id"] for i in api.get("/v1/insights", headers=h).json()["insights"]}
    assert "indian_diabetes_risk" not in rules                       # 40 with two answers missing: wait
    r = api.put("/v1/profile/lifestyle", headers=h, json={"activity": "sedentary", "waist_cm": 96})
    assert r.status_code == 200 and r.json()["activity"] == "sedentary"
    ins = next(i for i in api.get("/v1/insights", headers=h).json()["insights"] if i["rule_id"] == "indian_diabetes_risk")
    assert ins["title"] == "Indian Diabetes Risk Score: 80 of 100" and ins["level"] == "moderate"
    assert "Waist 96 cm: 10 points" in ins["evidence"] and "Parents with diabetes: mother: 10 points" in ins["evidence"]
    assert "Mohan" in ins["references"][0]["title"]
    trends = {t["code"] for t in api.get("/v1/trends", headers=h).json()["tests"]}
    assert "waist_circumference" in trends
    assert api.put("/v1/profile/lifestyle", headers=h, json={"activity": "couch"}).status_code == 422
    # Someone already diagnosed doesn't get a screening score.
    api.post("/v1/ingest/fhir", headers=h, json={"resourceType": "Condition", "code": {"text": "Type 2 diabetes"}})
    assert "indian_diabetes_risk" not in {i["rule_id"] for i in api.get("/v1/insights", headers=h).json()["insights"]}


# --- medicines ----------------------------------------------------------------------------------

def test_brand_lookup():
    assert size() >= 100
    assert lookup("Tab. Telma-H 40").generic == "telmisartan + hydrochlorothiazide"
    assert lookup("Glycomet GP 1").generic == "glimepiride + metformin"
    assert lookup("Glycomet 500 SR").generic == "metformin"
    assert lookup("Metformin 500 mg").drug_class.startswith("Biguanide")
    assert lookup("Ecosprin AV 75").generic == "aspirin + atorvastatin"
    assert lookup("Crocin Advance") .generic == "paracetamol"
    assert lookup("Unknownbrand 5") is None


def test_prescription_shows_generics_and_brands_merge(api):
    h = account(api)
    doc = api.post("/v1/documents", headers=h, json={"data_base64": base64.b64encode(text_pdf([
        "Date: 01/04/2026", "Rx", "Tab. Glycomet 500 1-0-1 after food", "Tab. Telma 40 1-0-0"])).decode()}).json()
    meds = {m["name"]: m for m in doc["extraction"]["medications"]}
    assert meds["Glycomet 500"]["generic"] == "metformin" and meds["Telma 40"]["drug_class"].startswith("Angiotensin")
    api.post(f"/v1/documents/{doc['id']}/save", headers=h, json={"doc_type": "prescription", "doc_date": "2026-04-01",
                                                                 "medications": doc["extraction"]["medications"]})
    # A later prescription of the same medicine under another brand updates it instead of adding a second one.
    doc2 = api.post("/v1/documents", headers=h, json={"data_base64": base64.b64encode(text_pdf([
        "Date: 01/06/2026", "Rx", "Tab. Glyciphage 500 1-1-1 after food"])).decode()}).json()
    api.post(f"/v1/documents/{doc2['id']}/save", headers=h, json={"doc_type": "prescription", "doc_date": "2026-06-01",
                                                                  "medications": doc2["extraction"]["medications"]})
    p = api.get("/v1/profile", headers=h).json()
    metformin = [m for m in p["medications"] if m["generic"] == "metformin"]
    assert len(metformin) == 1 and metformin[0]["dosage"].startswith("1-1-1") and metformin[0]["prescribed_on"] == "2026-06-01"
    fhir = api.get("/v1/export/fhir", headers=h).json()
    texts = [e["resource"]["medicationCodeableConcept"]["text"] for e in fhir["entry"]
             if e["resource"]["resourceType"] == "MedicationStatement"]
    assert "Telma 40 (telmisartan)" in texts
