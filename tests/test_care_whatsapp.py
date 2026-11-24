"""Medicine reminders on the cared-for person's own WhatsApp: opt-in, reminders, "1" to mark taken, STOP."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_forwarding import FakeWhatsApp, account, wa_payload, wa_post  # noqa: E402

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from fhg import care  # noqa: E402
from fhg.api import Settings, create_app  # noqa: E402

APP_SECRET = "app-secret"
ADMIN = {"X-Admin-Key": "admin-secret"}
PARENT = "919800011122"


@pytest.fixture
def wa():
    return FakeWhatsApp()


@pytest.fixture
def api(tmp_path, wa):
    return TestClient(create_app(Settings(
        db_path=str(tmp_path / "w.db"), encryption_key=Fernet.generate_key().decode(), admin_key="admin-secret",
        whatsapp_number="+91 80000 00000", whatsapp_verify_token="v", whatsapp_app_secret=APP_SECRET),
        whatsapp_client=wa, push_in_background=False))


def at(monkeypatch, hour, minute=5):
    fixed = datetime(2026, 12, 10, hour, minute, tzinfo=care.IST)

    class FakeNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed
    monkeypatch.setattr("fhg.api.datetime", FakeNow)


def say(api, text, sender=PARENT):
    wa_post(api, wa_payload(sender, {"type": "text", "text": {"body": text}}), secret=APP_SECRET)


def setup_mother(api):
    h = account(api)
    api.post("/v1/family", headers=h, json={"relationship": "mother", "name": "Asha"})
    uid = api.get("/v1/auth/me", headers=h).json()["user_id"]
    cid = f"{uid}.{api.get('/v1/profile', headers=h).json()['family'][0]['id']}"
    api.post(f"/v1/care/{cid}/medications", headers=h, json={"name": "Telma 40", "dosage": "1-0-0"})
    api.post(f"/v1/care/{cid}/medications", headers=h, json={"name": "Glycomet 500", "dosage": "1-0-1"})
    return h, cid


def test_phone_numbers():
    assert care.normalize_phone("98000 11122") == "919800011122"
    assert care.normalize_phone("+91 98000-11122") == "919800011122"
    assert care.normalize_phone("098000 11122") == "919800011122"
    with pytest.raises(ValueError):
        care.normalize_phone("12345")


def test_invite_opt_in_remind_mark_taken_and_stop(api, wa, monkeypatch):
    h, cid = setup_mother(api)
    assert api.put(f"/v1/care/{cid}/whatsapp", headers=h, json={"phone": "98000 11122", "lang": "hi", "agreed": False}).status_code == 422
    assert api.put(f"/v1/care/{cid}/whatsapp", headers=h, json={"phone": "123", "lang": "hi", "agreed": True}).status_code == 422
    out = api.put(f"/v1/care/{cid}/whatsapp", headers=h, json={"phone": "98000 11122", "lang": "hi", "agreed": True}).json()
    assert out["whatsapp"] == {"phone": "•••• 1122", "lang": "hi", "status": "invited", "updated_at": out["whatsapp"]["updated_at"]}
    assert wa.templates[-1] == (PARENT, "care_optin", "hi", [])

    # No reminders until they reply YES.
    at(monkeypatch, 8)
    api.post("/admin/tasks/care", headers=ADMIN)
    assert len(wa.templates) == 1
    say(api, "हाँ")
    assert wa.sent[-1] == (PARENT, care.wa_text("hi", "active"))
    assert api.get(f"/v1/care/{cid}", headers=h).json()["whatsapp"]["status"] == "active"

    # At 8 am: one reminder template, once.
    api.post("/admin/tasks/care", headers=ADMIN)
    api.post("/admin/tasks/care", headers=ADMIN)
    reminders = [t for t in wa.templates if t[1] == "medicine_reminder"]
    assert reminders == [(PARENT, "medicine_reminder", "hi", ["सुबह", "Glycomet 500, Telma 40"])]

    # They reply 1: the morning doses are marked taken, and the family sees who marked them.
    say(api, "1")
    assert wa.sent[-1] == (PARENT, care.wa_text("hi", "taken", names="Glycomet 500, Telma 40"))
    today = api.get(f"/v1/care/{cid}", headers=h).json()["today"]
    morning = [d for d in today if d["slot"] == "morning"]
    assert {d["status"] for d in morning} == {"taken"} and morning[0]["by"] == "Asha (WhatsApp)"
    say(api, "1")
    assert wa.sent[-1] == (PARENT, care.wa_text("hi", "nothing_due"))
    say(api, "kya haal hai")
    assert wa.sent[-1] == (PARENT, care.wa_text("hi", "help"))

    # STOP ends them; the family sees it.
    say(api, "STOP")
    assert wa.sent[-1] == (PARENT, care.wa_text("hi", "stopped"))
    assert api.get(f"/v1/care/{cid}", headers=h).json()["whatsapp"]["status"] == "stopped"
    at(monkeypatch, 21)
    api.post("/admin/tasks/care", headers=ADMIN)
    assert len([t for t in wa.templates if t[1] == "medicine_reminder"]) == 1


def test_family_can_turn_it_off_and_others_cannot(api, wa):
    h, cid = setup_mother(api)
    stranger = account(api)
    assert api.put(f"/v1/care/{cid}/whatsapp", headers=stranger, json={"phone": "9800011122", "agreed": True}).status_code == 404
    assert api.delete(f"/v1/care/{cid}/whatsapp", headers=h).status_code == 404
    api.put(f"/v1/care/{cid}/whatsapp", headers=h, json={"phone": "9800011122", "lang": "en", "agreed": True})
    assert api.delete(f"/v1/care/{cid}/whatsapp", headers=h).json()["whatsapp"]["status"] == "stopped"


def test_unknown_numbers_still_get_the_normal_reply(api, wa):
    say(api, "hello", sender="919811111111")
    assert "isn't connected" in wa.sent[-1][1]


def test_marathi_reminders(api, wa, monkeypatch):
    h, cid = setup_mother(api)
    api.put(f"/v1/care/{cid}/whatsapp", headers=h, json={"phone": "98000 11122", "lang": "mr", "agreed": True})
    assert wa.templates[-1] == (PARENT, "care_optin", "mr", [])
    say(api, "होय")
    assert wa.sent[-1] == (PARENT, care.wa_text("mr", "active"))
    at(monkeypatch, 8)
    api.post("/admin/tasks/care", headers=ADMIN)
    assert wa.templates[-1] == (PARENT, "medicine_reminder", "mr", ["सकाळ", "Glycomet 500, Telma 40"])
    say(api, "घेतली")
    assert wa.sent[-1] == (PARENT, care.wa_text("mr", "taken", names="Glycomet 500, Telma 40"))
    say(api, "नको")
    assert wa.sent[-1] == (PARENT, care.wa_text("mr", "stopped"))
