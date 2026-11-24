"""The pilot report: outcomes across all families, small counts hidden, and the optional surveys."""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import pilot
from fhg.api import Settings, create_app

ADMIN = {"X-Admin-Key": "admin-secret"}


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "p.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret"), webhooks_in_background=False,
                                 webhook_sender=type("S", (), {"send": lambda *a: None})()))


def family(api, text="My mother had breast cancer at 44. My maternal grandmother had ovarian cancer."):
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.put("/v1/profile/demographics", headers=h, json={"sex": "female", "birth_date": "1985-01-01"})
    api.post("/v1/ingest/text", headers=h, json={"text": text})
    return h


def test_surveys_baseline_then_followup():
    t0 = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert pilot.due_questions(t0.isoformat(), set(), t0) == ["baseline_knowledge", "baseline_discussed"]
    assert pilot.due_questions(t0.isoformat(), {"baseline_knowledge"}, t0) == ["baseline_discussed"]
    later = t0 + timedelta(days=pilot.FOLLOWUP_DAYS)
    assert pilot.due_questions(t0.isoformat(), {"baseline_knowledge", "baseline_discussed"}, later) == [
        "followup_action", "followup_useful"]


def test_survey_endpoints(api):
    h = family(api)
    due = api.get("/v1/surveys", headers=h).json()
    assert [q["id"] for q in due] == ["baseline_knowledge", "baseline_discussed"] and due[0]["options"] == ["most", "some", "very_little"]
    assert api.post("/v1/surveys/baseline_knowledge", headers=h, json={"answer": "lots"}).status_code == 422
    assert api.post("/v1/surveys/nope", headers=h, json={"answer": "yes"}).status_code == 404
    assert api.post("/v1/surveys/baseline_knowledge", headers=h, json={"answer": "some"}).status_code == 204
    assert api.post("/v1/surveys/baseline_discussed", headers=h, json={"answer": "skipped"}).status_code == 204
    assert api.get("/v1/surveys", headers=h).json() == []
    assert {a["question"] for a in api.get("/v1/privacy/export", headers=h).json()["survey_answers"]} == {
        "baseline_knowledge", "baseline_discussed"}


def test_report_numbers(api):
    hs = [family(api) for _ in range(6)]
    family(api, text="Nothing known.")
    for h in hs[:5]:
        api.post("/v1/surveys/baseline_knowledge", headers=h, json={"answer": "very_little"})
    api.post("/v1/surveys/baseline_knowledge", headers=hs[5], json={"answer": "skipped"})
    lab = api.post("/admin/partners", headers=ADMIN, json={"name": "Thyro Labs", "kind": "lab"}).json()
    api.put(f"/admin/partners/{lab['partner']['id']}/catalog", headers=ADMIN, json=[{"test": "hba1c", "price_inr": 450}])
    b = api.post("/v1/bookings", headers=hs[0], json={"partner_id": lab["partner"]["id"], "tests": ["hba1c"],
                                                       "contact": {"name": "P", "phone": "+91 98123 45678"}}).json()
    api.post(f"/v1/bookings/{b['id']}/done-elsewhere", headers=hs[0])
    api.post("/v1/bookings", headers=hs[1], json={"partner_id": lab["partner"]["id"], "tests": ["hba1c"],
                                                   "contact": {"name": "Q", "phone": "+91 98123 45679"}})

    assert api.get("/admin/pilot-report").status_code in (401, 403)
    r = api.get("/admin/pilot-report", headers=ADMIN).json()
    f = r["families"]
    assert (f["total"], f["with_relatives"], f["with_three_generations"], f["active_last_7_days"]) == (7, 6, 6, 7)
    assert r["findings"]["families_with_an_item"] == 6 and r["findings"]["families_with_an_item_to_discuss_soon"] == 0
    assert r["findings"]["by_item"]["Family pattern worth a hereditary cancer risk assessment"] == 6
    assert (r["tests"]["booked"], r["tests"]["completed"], r["tests"]["completion_rate_percent"]) == (2, 1, 50.0)
    assert r["survey"]["baseline_knowledge"] == {"question": pilot.QUESTIONS["baseline_knowledge"]["text"],
                                                 "answers": {"very_little": 5}, "responses": 5}   # "skipped" not counted

    csv = api.get("/admin/pilot-report?format=csv", headers=ADMIN)
    assert csv.headers["content-type"].startswith("text/csv") and "attachment" in csv.headers["content-disposition"]
    rows = {line.split(",")[1]: line.split(",")[-1] for line in csv.text.strip().splitlines()[1:]}
    assert rows["Families taking part"] == "7" and rows["Tests booked"] == "<5"           # small counts hidden
    assert rows["Completion rate (%)"] == "50.0"


def test_caregiver_adherence(api, monkeypatch):
    h = family(api)
    api.post("/v1/family", headers=h, json={"relationship": "father", "name": "Ravi"})
    uid = api.get("/v1/auth/me", headers=h).json()["user_id"]
    member = next(m for m in api.get("/v1/profile", headers=h).json()["family"] if m["relationship"] == "father")
    cid = f"{uid}.{member['id']}"
    med = api.post(f"/v1/care/{cid}/medications", headers=h, json={"name": "Telma 40", "dosage": "1-0-0"}).json()["medications"][0]
    # The medicine started 3 days ago; two of those days' doses were taken.
    store = api.app.state.store
    p = store.get_profile(uid)
    start = (datetime.now(timezone.utc) - timedelta(days=3)).date()
    next(m for m in p.family if m.id == member["id"]).medications[0].prescribed_on = start
    store.save_profile(p)
    for back in (1, 2):
        day = (datetime.now(timezone.utc) - timedelta(days=back)).date().isoformat()
        store.log_dose(uid, member["id"], med["id"], day, "morning", "taken", uid)
    c = api.get("/admin/pilot-report", headers=ADMIN).json()["caregiving"]
    assert (c["people_with_reminders"], c["doses_scheduled_28d"], c["doses_taken_28d"]) == (1, 3, 2)
    assert c["adherence_percent"] == 66.7
