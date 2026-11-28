"""The practice clinic for staff training: full of made-up families, and walled off from the real pilot."""
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import clinic, practice
from fhg.api import Settings, create_app
from fhg.insights import generate_insights

ADMIN = {"X-Admin-Key": "k"}


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "p.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="k"), webhooks_in_background=False,
                                 webhook_sender=type("S", (), {"send": lambda *a: None})()))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def test_families_cover_every_program_and_status():
    found, statuses = set(), set()
    for f in practice.FAMILIES:
        ids = {i.rule_id for i in generate_insights(practice.profile(f, "u")).insights}
        assert set(f.referrals) <= ids, f.name                 # each referral matches what the history shows
        found |= ids
        statuses |= set(f.referrals.values())
    assert set(clinic.PROGRAMS) <= found
    assert statuses == set(clinic.STATUSES)


def test_staff_practise_on_it_and_it_stays_out_of_the_pilot(api):
    real = account(api)
    api.post("/v1/ingest/text", headers=real, json={"text": "My mother had breast cancer at 44."})
    staff = account(api)
    before = api.get("/admin/pilot-report", headers=ADMIN).json()

    made = api.post("/admin/practice-clinics", headers=ADMIN, json={"name": "Kothrud practice", "lang": "mr"}).json()
    assert made["patients"] == len(practice.FAMILIES)
    org = api.post("/v1/orgs/join", headers=staff, json={"code": made["staff_code"]}).json()
    assert org["practice"] is True and org["lang"] == "mr"

    work = api.get(f"/v1/orgs/{org['id']}/patients", headers=staff).json()
    assert len(work["patients"]) == len(practice.FAMILIES) and work["org"]["practice"] is True
    assert work["impact"]["referrals_made"] > 0 and work["impact"]["referrals_completed"] > 0
    ref = work["patients"][0]["patient_ref"]
    assert api.post(f"/v1/orgs/{org['id']}/patients/{ref}/referrals", headers=staff,
                    json={"rule_id": work["patients"][0]["flags"][0]["rule_id"], "status": "referred"}).status_code == 200

    # Kept out of the pilot's numbers, and real patients can't join it.
    assert api.get("/admin/pilot-report", headers=ADMIN).json()["families"] == before["families"]
    assert api.get("/admin/pilot-report", headers=ADMIN).json()["referrals"] == before["referrals"]
    counts = api.get("/admin/overview", headers=ADMIN).json()["counts"]
    assert counts["practice_clinics"] == 1 and counts["clinics"] == 0
    code = api.get("/v1/orgs", headers=staff).json()[0]["patient_code"]
    assert api.get(f"/v1/public/clinics/{code}").status_code == 404
    assert api.post("/v1/clinics", headers=real, json={"code": code, "display_name": "Real"}).status_code == 404

    # Its referrals never reach a partner.
    lab = api.post("/admin/partners", headers=ADMIN, json={"name": "Counsel Co", "kind": "genetic_counseling"}).json()
    assert api.post(f"/v1/orgs/{org['id']}/patients/{ref}/referrals", headers=staff,
                    json={"rule_id": work["patients"][0]["flags"][0]["rule_id"], "status": "referred",
                          "partner_id": lab["partner"]["id"]}).status_code == 422

    listed = api.get("/admin/practice-clinics", headers=ADMIN).json()
    assert [(c["name"], c["patients"], c["staff"]) for c in listed] == [("Kothrud practice", len(practice.FAMILIES), 1)]


def test_deleting_removes_only_made_up_patients(api):
    real = account(api)
    made = api.post("/admin/practice-clinics", headers=ADMIN, json={}).json()
    staff = account(api)
    api.post("/v1/orgs/join", headers=staff, json={"code": made["staff_code"]})
    real_org = api.post("/v1/orgs", headers=real, json={"name": "Real clinic"}).json()
    assert api.delete(f"/admin/practice-clinics/{real_org['id']}", headers=ADMIN).status_code == 404
    out = api.delete(f"/admin/practice-clinics/{made['id']}", headers=ADMIN).json()
    assert out == {"deleted": True, "patients": len(practice.FAMILIES)}
    assert api.get("/admin/practice-clinics", headers=ADMIN).json() == []
    assert api.get("/v1/orgs", headers=staff).json() == []                     # trainees keep their accounts
    assert api.get("/v1/profile", headers=staff).status_code == 200
    assert api.get("/v1/orgs", headers=real).json()[0]["name"] == "Real clinic"


def test_needs_attention(api):
    made = api.post("/admin/practice-clinics", headers=ADMIN, json={}).json()
    staff = account(api)
    org = api.post("/v1/orgs/join", headers=staff, json={"code": made["staff_code"]}).json()
    work = api.get(f"/v1/orgs/{org['id']}/patients", headers=staff).json()
    items = {(a["display_name"], a["status"]) for a in work["attention"]}
    assert ("Sunita Kulkarni", "referred") in items                     # referred 20 days ago, no news
    assert ("Rajesh Deshpande", "scheduled") in items                   # scheduled 40 days ago
    assert ("Lata Wagh", "identified") in items                         # discuss soon, 12 days, no decision
    assert not any(name == "Anil Patil" for name, _ in items)           # referred 3 days ago: fine
    assert [a["days"] for a in work["attention"]] == sorted((a["days"] for a in work["attention"]), reverse=True)

    # Acting on it clears it.
    lata = next(p for p in work["patients"] if p["display_name"] == "Lata Wagh")
    for f in lata["flags"]:
        api.post(f"/v1/orgs/{org['id']}/patients/{lata['patient_ref']}/referrals", headers=staff,
                 json={"rule_id": f["rule_id"], "status": "referred"})
    work = api.get(f"/v1/orgs/{org['id']}/patients", headers=staff).json()
    assert not any(a["display_name"] == "Lata Wagh" for a in work["attention"])


def test_stuck_referral_counts():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    ago = lambda d: (now - timedelta(days=d)).isoformat()  # noqa: E731
    refs = [{"status": "referred", "updated_at": ago(15)}, {"status": "referred", "updated_at": ago(5)},
            {"status": "scheduled", "updated_at": ago(31)}, {"status": "completed", "updated_at": ago(90)}]
    assert clinic.stuck_referrals(refs, now) == {"referred_no_update_14_days": 1, "scheduled_not_done_30_days": 1}
