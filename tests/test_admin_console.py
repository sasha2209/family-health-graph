"""The pilot operations console and the admin endpoints behind it."""
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app

ADMIN = {"X-Admin-Key": "admin-secret"}


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "a.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret")))


def test_console_page(api):
    r = api.get("/admin")
    assert r.status_code == 200 and "Pilot operations" in r.text
    assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"
    assert "admin-secret" not in r.text


def test_overview(api):
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.post("/v1/privacy/grievances", headers=h, json={"category": "access", "message": "Who saw my data?"})
    out = api.get("/admin/overview", headers=ADMIN).json()
    assert out["counts"]["users"] == 1 and out["counts"]["grievances_open"] == 1 and out["counts"]["grievances_overdue"] == 0
    assert "hba1c" in out["tests"] and "lab" in out["partner_kinds"]


def test_partner_lifecycle_with_price_list(api):
    p = api.post("/admin/partners", headers=ADMIN, json={"name": "Thyro Labs", "kind": "lab"}).json()["partner"]
    api.put(f"/admin/partners/{p['id']}/catalog", headers=ADMIN, json=[{"test": "hba1c", "price_inr": 450}])
    listed = {x["id"]: x for x in api.get("/admin/partners", headers=ADMIN).json()}
    assert listed[p["id"]]["catalog"] == [{"test": "hba1c", "price_inr": 450.0, "home_collection": False, "turnaround_days": None}]
    assert api.post(f"/admin/partners/{p['id']}/deactivate", headers=ADMIN).json()["active"] in (0, False)
    assert api.post(f"/admin/partners/{p['id']}/activate", headers=ADMIN).json()["active"] in (1, True)
    assert api.post("/admin/partners/nope/activate", headers=ADMIN).status_code == 404


def test_wrong_keys_lock_out(api):
    for _ in range(10):
        assert api.get("/admin/overview", headers={"X-Admin-Key": "guess"}).status_code == 403
    assert api.get("/admin/overview", headers={"X-Admin-Key": "guess"}).status_code == 429
    assert api.get("/admin/overview", headers=ADMIN).status_code == 429          # even the right key, for now


def test_run_a_job_from_the_console(api):
    assert api.post("/admin/jobs/housekeeping/run").status_code in (401, 403)
    assert "deleted" in api.post("/admin/jobs/housekeeping/run", headers=ADMIN).json()
    assert api.post("/admin/jobs/nope/run", headers=ADMIN).status_code == 404
    jobs = {j["name"]: j["status"] for j in api.get("/admin/jobs", headers=ADMIN).json()["jobs"]}
    assert jobs == {"housekeeping": "ok"}
