"""Caregiver mode: schedules from Indian prescriptions, doses, refills, the care circle and the emergency summary."""
from datetime import date, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import care
from fhg.api import Settings, create_app
from fhg.models import FamilyMember, Medication, Relationship

ADMIN = {"X-Admin-Key": "admin-secret"}


@pytest.mark.parametrize("text,slots,days,food", [
    ("1-0-1, after food, 30 days", {"morning": 1, "night": 1}, 30, "after food"),
    ("0-0-1 x 2 weeks", {"night": 1}, 14, None),
    ("½-0-½ before food", {"morning": 0.5, "night": 0.5}, None, "before food"),
    ("1-1-1-1", {"morning": 1, "afternoon": 1, "night": 2}, None, None),
    ("BD for 1 month", {"morning": 1, "night": 1}, 30, None),
    ("TDS", {"morning": 1, "afternoon": 1, "night": 1}, None, None),
    ("once daily, empty stomach", {"morning": 1}, None, "empty stomach"),
    ("HS", {"night": 1}, None, None),
    ("twice daily", {"morning": 1, "night": 1}, None, None),
])
def test_schedule_from_prescription(text, slots, days, food):
    s = care.parse_schedule(text)
    assert (s.slots, s.days, s.food, s.understood) == (slots, days, food, True)


def test_schedule_edge_cases():
    assert care.parse_schedule("SOS for pain").as_needed and care.parse_schedule("SOS").slots == {}
    assert not care.parse_schedule("as directed").understood
    assert care.parse_schedule("500 mg").slots == {}                      # a strength isn't a schedule
    med = Medication(name="Telma 40", dosage="1-0-1", schedule={"morning": 1})
    assert care.schedule_for(med).slots == {"morning": 1}                 # the caregiver's correction wins


def test_refill():
    today = date(2026, 12, 10)
    course = Medication(name="Glycomet 500", dosage="1-0-1 x 30 days", prescribed_on=date(2026, 11, 14))
    assert care.refill(course, today) == {"days_left": 4, "runs_out_on": "2026-12-14", "basis": "course", "due": True}
    stock = Medication(name="Telma 40", dosage="1-0-0", stock=20, stock_on=date(2026, 12, 1))
    assert care.refill(stock, today)["days_left"] == 11 and not care.refill(stock, today)["due"]
    assert care.refill(Medication(name="Crocin", dosage="SOS"), today) is None
    assert care.refill(Medication(name="X", dosage="1-0-1"), today) is None      # nothing to go on


def mum():
    return FamilyMember(relationship=Relationship.MOTHER, name="Asha", medications=[
        Medication(id="m1", name="Glycomet 500", dosage="1-0-1 after food", reminders=True),
        Medication(id="m2", name="Telma 40", dosage="1-0-0", reminders=True),
        Medication(id="m3", name="Old one", dosage="1-0-1", reminders=False)])


def test_doses_and_alerts():
    day = date(2026, 12, 10)
    at = lambda h, m=0: datetime(2026, 12, 10, h, m, tzinfo=care.IST)  # noqa: E731
    doses = care.doses_for_day(mum(), day, [], now=at(9))
    assert [(d["name"], d["slot"], d["status"]) for d in doses] == [
        ("Glycomet 500", "morning", "due"), ("Telma 40", "morning", "due"), ("Glycomet 500", "night", "upcoming")]
    log = [{"med_id": "m1", "day": "2026-12-10", "slot": "morning", "status": "taken", "by_name": "Rahul"}]
    assert care.doses_for_day(mum(), day, log, now=at(11))[0]["status"] == "taken"
    assert care.doses_for_day(mum(), day, log, now=at(11))[1]["status"] == "missed"
    alerts = care.due_care_alerts(at(8, 5), "Asha", mum(), [])
    assert [m for _, m in alerts] == ["Time for Asha's morning medicines: Glycomet 500, Telma 40."]
    assert alerts[0][0].endswith(":2026-12-10:morning")
    missed = care.due_care_alerts(at(11, 5), "Asha", mum(), log)
    assert [m for _, m in missed] == ["Asha's morning medicines haven't been marked as taken: Glycomet 500, Telma 40."]
    all_taken = log + [{"med_id": "m2", "day": "2026-12-10", "slot": "morning", "status": "taken"}]
    assert care.due_care_alerts(at(11, 5), "Asha", mum(), all_taken) == []
    assert care.due_care_alerts(at(12), "Asha", mum(), []) == []          # nothing due at noon
    started = mum()
    started.medications[1].prescribed_on = date(2026, 12, 11)
    assert [d["name"] for d in care.doses_for_day(started, day, [], now=at(9))] == ["Glycomet 500", "Glycomet 500"]


# --- API -------------------------------------------------------------------------------------------

@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "c.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret", public_url="https://fhg.example"),
                                 push_in_background=False))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def with_mother(api, h):
    api.post("/v1/family", headers=h, json={"relationship": "mother", "name": "Asha", "conditions": [{"name": "type 2 diabetes"}]})
    member = api.get("/v1/profile", headers=h).json()["family"][0]
    uid = api.get("/v1/auth/me", headers=h).json()["user_id"]
    return f"{uid}.{member['id']}"


def test_care_flow_with_a_sibling(api):
    me, sib, stranger = account(api), account(api), account(api)
    cid = with_mother(api, me)
    c = api.post(f"/v1/care/{cid}/medications", headers=me, json={"name": "Glycomet 500", "dosage": "1-0-1 after food",
                                                                   "stock": 30}).json()
    med = c["medications"][0]
    assert (med["generic"], med["schedule"], med["reminders"], med["refill"]["days_left"]) == ("metformin", {"morning": 1, "night": 1}, True, 15)
    assert [x["slot"] for x in c["today"]] == ["morning", "night"]
    assert api.get("/v1/care", headers=me).json()[0]["name"] == "Asha"

    # Invite a sibling; a stranger can't see anything.
    assert api.get(f"/v1/care/{cid}", headers=stranger).status_code == 404
    inv = api.post(f"/v1/care/{cid}/invite", headers=me).json()
    assert inv["url"].startswith("https://fhg.example/app/care-join/") and "Asha" in inv["message"]
    joined = api.post(f"/v1/care/join/{inv['token']}", headers=sib, json={"name": "Rahul"}).json()
    assert joined["role"] == "caregiver" and joined["caregivers"] == []          # only the owner sees the circle
    assert api.post(f"/v1/care/join/{inv['token']}", headers=stranger).status_code == 404   # one use only
    assert any("Rahul joined the care circle for Asha" in n["message"] for n in api.get("/v1/notifications", headers=me).json())
    assert api.post(f"/v1/care/{cid}/invite", headers=sib).status_code == 403

    # The sibling marks a dose; the owner sees who did.
    r = api.post(f"/v1/care/{cid}/doses", headers=sib, json={"med_id": med["id"], "slot": "night", "status": "taken"})
    assert r.status_code == 200
    night = next(d for d in api.get(f"/v1/care/{cid}", headers=me).json()["today"] if d["slot"] == "night")
    assert night["status"] == "taken" and night["by"] == "Rahul"
    assert api.post(f"/v1/care/{cid}/doses", headers=sib, json={"med_id": med["id"], "slot": "afternoon",
                                                               "status": "taken"}).status_code == 404
    future = (date.today() + timedelta(days=3)).isoformat()
    assert api.post(f"/v1/care/{cid}/doses", headers=sib, json={"med_id": med["id"], "slot": "night", "day": future,
                                                               "status": "taken"}).status_code == 422

    # Corrections: schedule and stock.
    c = api.patch(f"/v1/care/{cid}/medications/{med['id']}", headers=sib, json={"schedule": {"night": 1}, "stock": 10}).json()
    assert c["medications"][0]["schedule"] == {"night": 1} and c["medications"][0]["refill"]["days_left"] == 10
    assert api.patch(f"/v1/care/{cid}/medications/{med['id']}", headers=sib,
                     json={"schedule": {"lunch": 1}}).status_code == 422

    # Owner removes the sibling.
    sib_id = api.get("/v1/auth/me", headers=sib).json()["user_id"]
    assert api.get(f"/v1/care/{cid}", headers=me).json()["caregivers"][0]["name"] == "Rahul"
    assert api.delete(f"/v1/care/{cid}/caregivers/{sib_id}", headers=me).status_code == 204
    assert api.get(f"/v1/care/{cid}", headers=sib).status_code == 404


def test_emergency_summary_and_link(api):
    me = account(api)
    cid = with_mother(api, me)
    api.post(f"/v1/care/{cid}/medications", headers=me, json={"name": "Telma 40", "dosage": "1-0-0"})
    info = {"blood_group": "B+", "allergies": ["Penicillin"], "emergency_contact_name": "Priya",
            "emergency_contact_phone": "+91 98123 45678", "doctor_name": "Dr Mehta <script>", "hospital": "Ruby Hall"}
    assert api.put(f"/v1/care/{cid}/info", headers=me, json={**info, "blood_group": "Z"}).status_code == 422
    assert api.put(f"/v1/care/{cid}/info", headers=me, json=info).json()["info"]["blood_group"] == "B+"
    page = api.get(f"/v1/care/{cid}/summary", headers=me).text
    assert "Blood group: B+" in page and "Penicillin" in page and "telmisartan" in page and "1-0-0" in page
    assert "Type 2 diabetes" in page and "&lt;script&gt;" in page and "<script>" not in page

    link = api.post(f"/v1/care/{cid}/emergency-links", headers=me, json={"hours": 2}).json()
    assert link["url"].startswith("https://fhg.example/e/")
    public = TestClient(api.app)                                            # no sign-in
    r = public.get("/e/" + link["url"].rsplit("/", 1)[1])
    assert r.status_code == 200 and "Penicillin" in r.text and r.headers["cache-control"] == "no-store"
    assert r.headers["x-robots-tag"] == "noindex"
    assert any("emergency summary was just opened" in n["message"] for n in api.get("/v1/notifications", headers=me).json())
    assert api.get(f"/v1/care/{cid}", headers=me).json()["emergency_links"][0]["views"] == 1
    assert api.delete(f"/v1/care/{cid}/emergency-links/{link['id']}", headers=me).status_code == 204
    assert public.get("/e/" + link["url"].rsplit("/", 1)[1]).status_code == 404
    assert public.get("/e/not-a-token").status_code == 404
    assert api.post(f"/v1/care/{cid}/emergency-links", headers=me, json={"hours": 500}).status_code == 422


def test_hourly_job_notifies_the_circle_once(api, monkeypatch):
    me, sib = account(api), account(api)
    cid = with_mother(api, me)
    api.post(f"/v1/care/{cid}/medications", headers=me, json={"name": "Telma 40", "dosage": "1-0-0"})
    inv = api.post(f"/v1/care/{cid}/invite", headers=me).json()
    api.post(f"/v1/care/join/{inv['token']}", headers=sib, json={"name": "Rahul"})
    fixed = datetime(2026, 12, 10, 8, 10, tzinfo=care.IST)

    class FakeNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr("fhg.api.datetime", FakeNow)
    assert api.post("/admin/tasks/care").status_code in (401, 403)
    assert api.post("/admin/tasks/care", headers=ADMIN).json()["sent"] == 2                 # owner and sibling
    assert api.post("/admin/tasks/care", headers=ADMIN).json()["sent"] == 0                 # not twice
    for h in (me, sib):
        assert any(n["message"] == "Time for Asha's morning medicines: Telma 40." for n in api.get("/v1/notifications", headers=h).json())


def test_deleting_the_relative_ends_the_circle(api):
    me, sib = account(api), account(api)
    cid = with_mother(api, me)
    inv = api.post(f"/v1/care/{cid}/invite", headers=me).json()
    api.post(f"/v1/care/join/{inv['token']}", headers=sib)
    assert api.delete(f"/v1/family/{cid.split('.')[1]}", headers=me).status_code == 204
    assert api.get("/v1/care", headers=sib).json() == []
