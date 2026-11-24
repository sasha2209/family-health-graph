"""The person's language: stored on the server, used for lock-screen pushes and caregiver reminders."""
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import care
from fhg.api import Settings, create_app
from fhg.push import push_text

ADMIN = {"X-Admin-Key": "admin-secret"}


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "l.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret"), push_in_background=False))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def test_language_setting(api):
    h = account(api)
    assert api.get("/v1/auth/me", headers=h).json()["lang"] == "en"
    assert api.put("/v1/profile/language", headers=h, json={"lang": "hi"}).json() == {"lang": "hi"}
    assert api.get("/v1/auth/me", headers=h).json()["lang"] == "hi"
    assert api.put("/v1/profile/language", headers=h, json={"lang": "fr"}).status_code == 422


def test_push_texts_follow_language_and_stay_generic():
    assert push_text("care", "hi") == "जिनकी आप देखभाल करते हैं, उनके बारे में नई जानकारी है।"
    assert push_text("care", "en") == "An update about someone you care for."
    assert push_text("unknown_kind", "hi") == "आपके लिए नई जानकारी है।"
    assert push_text("care", "ta") == "An update about someone you care for."     # no table yet: English


def test_caregiver_reminders_in_each_persons_language(api, monkeypatch):
    me, sib = account(api), account(api)
    api.put("/v1/profile/language", headers=sib, json={"lang": "hi"})
    api.post("/v1/family", headers=me, json={"relationship": "mother", "name": "Asha"})
    uid = api.get("/v1/auth/me", headers=me).json()["user_id"]
    cid = f"{uid}.{api.get('/v1/profile', headers=me).json()['family'][0]['id']}"
    api.post(f"/v1/care/{cid}/medications", headers=me, json={"name": "Telma 40", "dosage": "1-0-0"})
    api.post(f"/v1/care/join/{api.post(f'/v1/care/{cid}/invite', headers=me).json()['token']}", headers=sib, json={"name": "Rahul"})
    fixed = datetime(2026, 12, 10, 8, 10, tzinfo=care.IST)

    class FakeNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed
    monkeypatch.setattr("fhg.api.datetime", FakeNow)
    assert api.post("/admin/tasks/care", headers=ADMIN).json()["sent"] == 2
    msgs = lambda h: [n["message"] for n in api.get("/v1/notifications", headers=h).json() if "Telma" in n["message"]]  # noqa: E731
    assert msgs(me) == ["Time for Asha's morning medicines: Telma 40."]
    assert msgs(sib) == ["Asha की सुबह की दवाइयों का समय: Telma 40।"]
