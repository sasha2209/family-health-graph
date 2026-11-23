"""Book a test from an action item, the lab reports back with results, and reminders follow up."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import bookings
from fhg.api import Settings, create_app

ADMIN = {"X-Admin-Key": "admin-secret"}


class Hooks:
    def __init__(self):
        self.sent = []

    def send(self, url, body, headers):
        self.sent.append((url, json.loads(body)))


@pytest.fixture
def hooks():
    return Hooks()


@pytest.fixture
def api(tmp_path, hooks):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "b.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret"), webhook_sender=hooks, webhooks_in_background=False))


def lab(api, name, catalog):
    r = api.post("/admin/partners", headers=ADMIN, json={"name": name, "kind": "lab",
                                                          "webhook_url": f"https://{name.split()[0].lower()}.example.com/hooks"}).json()
    assert api.put(f"/admin/partners/{r['partner']['id']}/catalog", headers=ADMIN, json=catalog).status_code == 200
    return r["partner"]["id"], {"X-API-Key": r["api_key"]}


def at_risk_user(api):
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.put("/v1/profile/demographics", headers=h, json={"sex": "female", "birth_date": "1980-01-01"})
    api.post("/v1/ingest/text", headers=h, json={"text": "My mother had type 2 diabetes."})
    api.post("/v1/ingest/fhir", headers=h, json={"resourceType": "Observation", "effectiveDateTime": "2025-06-01",
                                                  "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]},
                                                  "valueQuantity": {"value": 6.0, "unit": "%"}})
    return h


CONTACT = {"name": "Priya Shah", "phone": "+91 98123 45678", "address": "12 MG Road, Pune", "pincode": "411001"}


def book(api, h, partner_id, tests=("hba1c",), rule="diabetes_risk"):
    r = api.post("/v1/bookings", headers=h, json={"partner_id": partner_id, "tests": list(tests), "rule_id": rule,
                                                   "preferred_date": "2026-12-01", "slot": "morning", "contact": CONTACT})
    assert r.status_code == 201, r.text
    return r.json()


def test_book_from_insight_then_results_come_back(api, hooks, tmp_path):
    thyro, thyro_key = lab(api, "Thyro Labs", [{"test": "hba1c", "price_inr": 450, "home_collection": True},
                                               {"test": "fasting_glucose", "price_inr": 150, "home_collection": True}])
    lab(api, "Cheaper Diagnostics", [{"test": "hba1c", "price_inr": 299}])
    h = at_risk_user(api)

    offer = api.get("/v1/insights/diabetes_risk/tests", headers=h).json()
    hba1c = next(t for t in offer["tests"] if t["test"] == "hba1c")
    assert [o["partner_name"] for o in hba1c["offers"]] == ["Cheaper Diagnostics", "Thyro Labs"]    # cheapest first
    assert hba1c["prep"] == "No fasting needed." and offer["bookings"] == []

    b = book(api, h, thyro, tests=("hba1c", "fasting_glucose"))
    assert b["status"] == "requested" and b["price_inr"] == 600 and "contact" not in b
    url, event = hooks.sent[-1]
    assert url == "https://thyro.example.com/hooks" and event["type"] == "booking.created"
    assert event["data"] == {"booking_id": b["id"]}                         # no health data in webhooks
    assert b"Priya" not in (tmp_path / "b.db").read_bytes()                  # contact encrypted at rest

    listed = api.get("/v1/partner/bookings?status=requested", headers=thyro_key).json()
    assert listed[0]["contact"]["phone"] == "+91 98123 45678" and [t["code"] for t in listed[0]["tests"]] == ["hba1c", "fasting_glucose"]

    r = api.post(f"/v1/partner/bookings/{b['id']}/status", headers=thyro_key,
                 json={"status": "scheduled", "scheduled_for": "2026-12-01T08:00:00+05:30"})
    assert r.status_code == 200
    assert "Thyro Labs confirmed your HbA1c, Fasting blood sugar for 1 Dec 2026." in [
        n["message"] for n in api.get("/v1/notifications", headers=h).json()]

    results = {"resourceType": "Bundle", "type": "collection", "entry": [
        {"resource": {"resourceType": "Observation", "effectiveDateTime": "2026-12-01",
                      "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4"}]}, "valueQuantity": {"value": 6.6, "unit": "%"}}},
        {"resource": {"resourceType": "Observation", "effectiveDateTime": "2026-12-01",
                      "code": {"coding": [{"system": "http://loinc.org", "code": "1558-6"}]}, "valueQuantity": {"value": 131, "unit": "mg/dL"}}},
        {"resource": {"resourceType": "Observation", "effectiveDateTime": "2026-12-01",   # not booked: ignored
                      "code": {"coding": [{"system": "http://loinc.org", "code": "13457-7"}]}, "valueQuantity": {"value": 140, "unit": "mg/dL"}}},
        {"resource": {"resourceType": "Condition", "code": {"text": "Diabetes"}}},          # never accepted from a lab
    ]}
    r = api.post(f"/v1/partner/bookings/{b['id']}/results", headers=thyro_key, json=results).json()
    assert r["accepted"] == 2 and r["ignored"] == 1
    p = api.get("/v1/profile", headers=h).json()
    latest = max((o for o in p["observations"] if o["code"] == "hba1c"), key=lambda o: o["effective_date"])
    assert latest["value"] == 6.6 and latest["source"] == f"partner:{thyro}:booking:{b['id']}"
    assert p["conditions"] == []
    assert api.get("/v1/bookings", headers=h).json()[0]["status"] == "completed"
    dm = next(i for i in api.get("/v1/insights", headers=h).json()["insights"] if i["rule_id"] == "diabetes_risk")
    assert dm["level"] == "high"                                          # the new result changes the advice
    assert any("results from Thyro Labs are in" in n["message"] for n in api.get("/v1/notifications", headers=h).json())


def test_validation_and_isolation(api):
    thyro, thyro_key = lab(api, "Thyro Labs", [{"test": "hba1c", "price_inr": 450}])
    other, other_key = lab(api, "Other Labs", [{"test": "lipid_profile", "price_inr": 600}])
    h, h2 = at_risk_user(api), at_risk_user(api)
    assert api.post("/v1/bookings", headers=h, json={"partner_id": thyro, "tests": ["lipid_profile"],
                                                      "contact": CONTACT}).status_code == 422
    assert api.post("/v1/bookings", headers=h, json={"partner_id": "nope", "tests": ["hba1c"], "contact": CONTACT}).status_code == 404
    assert api.post("/v1/bookings", headers=h, json={"partner_id": thyro, "tests": ["hba1c"],
                                                      "contact": {**CONTACT, "phone": "call me"}}).status_code == 422
    assert api.put(f"/admin/partners/{thyro}/catalog", headers=ADMIN, json=[{"test": "mri"}]).status_code == 422
    b = book(api, h, thyro)
    assert api.get(f"/v1/partner/bookings/{b['id']}", headers=other_key).status_code == 404
    assert api.post(f"/v1/bookings/{b['id']}/cancel", headers=h2).status_code == 404
    bad = api.post(f"/v1/partner/bookings/{b['id']}/results", headers=thyro_key, json={
        "resourceType": "Observation", "code": {"coding": [{"system": "http://loinc.org", "code": "13457-7"}]},
        "valueQuantity": {"value": 140, "unit": "mg/dL"}})
    assert bad.status_code == 422                                          # LDL wasn't booked
    assert api.post(f"/v1/bookings/{b['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert api.post(f"/v1/partner/bookings/{b['id']}/status", headers=thyro_key, json={"status": "scheduled"}).status_code == 409
    b2 = book(api, h, thyro)
    assert api.post(f"/v1/bookings/{b2['id']}/done-elsewhere", headers=h).json()["status"] == "completed_elsewhere"
    metrics = api.get("/admin/bookings/metrics", headers=ADMIN).json()
    assert {(m["status"], m["n"]) for m in metrics if m["partner"] == "Thyro Labs"} == {("cancelled", 1), ("completed_elsewhere", 1)}


# --- follow-through ---------------------------------------------------------------------------------

class I:
    def __init__(self, rule_id, title="Type 2 diabetes risk"):
        self.rule_id, self.title = rule_id, title


T0 = datetime(2026, 12, 1, 9, tzinfo=timezone.utc)


def test_reminders_until_booked_and_done():
    insights = [I("diabetes_risk"), I("blood_pressure", "Blood pressure")]
    due = bookings.due_reminders(T0, insights, [], [])
    assert [(k, kind) for k, kind, _ in due] == [("insight:diabetes_risk", "reminder")]   # only items a test answers
    assert "HbA1c and Fasting blood sugar test" in due[0][2]
    sent = [{"key": "insight:diabetes_risk", "sent_at": T0.isoformat()}]
    assert bookings.due_reminders(T0 + timedelta(days=3), insights, [], sent) == []           # not every day
    assert bookings.due_reminders(T0 + timedelta(days=7), insights, [], sent)                 # weekly
    three = [{"key": "insight:diabetes_risk", "sent_at": (T0 + timedelta(days=7 * i)).isoformat()} for i in range(3)]
    assert bookings.due_reminders(T0 + timedelta(days=60), insights, [], three) == []          # at most 3

    requested = {"id": "b1", "status": "requested", "rule_id": "diabetes_risk", "partner_name": "Thyro Labs",
                 "created_at": T0.isoformat(), "scheduled_for": None}
    assert bookings.due_reminders(T0 + timedelta(days=1), insights, [requested], []) == []      # booked: no insight nudge
    late = bookings.due_reminders(T0 + timedelta(days=2), insights, [requested], [])
    assert late[0][0] == "booking:b1" and "hasn't confirmed" in late[0][2]
    scheduled = {**requested, "status": "scheduled", "scheduled_for": "2026-12-05T08:00:00+05:30"}
    assert bookings.due_reminders(datetime(2026, 12, 6, tzinfo=timezone.utc), insights, [scheduled], []) == []
    assert "aren't in yet" in bookings.due_reminders(datetime(2026, 12, 7, tzinfo=timezone.utc), insights, [scheduled], [])[0][2]
    for status in ("completed", "completed_elsewhere"):
        assert bookings.due_reminders(T0 + timedelta(days=30), insights, [{**requested, "status": status}], []) == []
    assert bookings.due_reminders(T0, insights, [{**requested, "status": "cancelled"}], [])      # cancelled: nudge again


def test_reminder_job_endpoint(api):
    h = at_risk_user(api)
    assert api.post("/admin/tasks/reminders").status_code in (401, 403)
    assert api.post("/admin/tasks/reminders", headers=ADMIN).json()["sent"] >= 1
    assert any(n["kind"] == "reminder" for n in api.get("/v1/notifications", headers=h).json())
    assert api.post("/admin/tasks/reminders", headers=ADMIN).json()["sent"] == 0                  # not twice in a week
