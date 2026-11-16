import json
import re

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app
from fhg.push import ExpoPushSender, PushMessage

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbb]"


class FakeSender:
    def __init__(self):
        self.sent: list[PushMessage] = []
        self.invalid: set[str] = set()
        self.fail = False

    def send(self, messages):
        if self.fail:
            raise RuntimeError("push service down")
        self.sent.extend(messages)
        return [m.to for m in messages if m.to in self.invalid]


@pytest.fixture
def sender():
    return FakeSender()


@pytest.fixture
def client(tmp_path, sender):
    settings = Settings(db_path=str(tmp_path / "p.db"), encryption_key=Fernet.generate_key().decode())
    return TestClient(create_app(settings, push_sender=sender, push_in_background=False))


def account(client):
    return {"Authorization": f"Bearer {client.post('/v1/users').json()['token']}"}


def linked_pair(client, share="conditions"):
    me, relative = account(client), account(client)
    inv = client.post("/v1/invitations", json={"relationship": "mother"}, headers=me).json()
    client.post(f"/v1/invites/{inv['token']}/accept", json={"share_level": share}, headers=relative)
    return me, relative


def test_register_status_and_unregister(client):
    h = account(client)
    assert client.get("/v1/devices/push", headers=h).json() == {"registered": False}
    assert client.put("/v1/devices/push", json={"token": TOKEN_A, "platform": "ios"}, headers=h).status_code == 200
    assert client.get("/v1/devices/push", headers=h).json() == {"registered": True}
    assert client.delete("/v1/devices/push", headers=h).status_code == 204
    assert client.get("/v1/devices/push", headers=h).json() == {"registered": False}
    assert client.put("/v1/devices/push", json={"token": "not-a-token"}, headers=h).status_code == 422


def test_family_alert_pushes_without_health_details(client, sender):
    me, mom = linked_pair(client)
    client.put("/v1/devices/push", json={"token": TOKEN_A, "platform": "ios"}, headers=me)
    sender.sent.clear()
    client.post("/v1/ingest/text", json={"text": "I have a BRCA1 mutation."}, headers=mom)

    assert len(sender.sent) == 1
    msg = sender.sent[0]
    assert msg.to == TOKEN_A and msg.data == {"kind": "family_cascade", "url": "/"}
    text = (msg.title + " " + msg.body).lower()
    for leaked in ("brca", "cancer", "mother", "variant"):
        assert leaked not in text
    # The full detail is still available inside the app.
    assert "BRCA1/BRCA2" in client.get("/v1/notifications", headers=me).json()[0]["message"]


def test_invitation_accepted_pushes_inviter(client, sender):
    me = account(client)
    client.put("/v1/devices/push", json={"token": TOKEN_A}, headers=me)
    inv = client.post("/v1/invitations", json={"relationship": "sister"}, headers=me).json()
    client.post(f"/v1/invites/{inv['token']}/accept", json={})
    assert [m.data["kind"] for m in sender.sent] == ["invitation_accepted"]


def test_signing_out_or_revoking_stops_pushes(client, sender):
    me, mom = linked_pair(client)
    client.put("/v1/devices/push", json={"token": TOKEN_A}, headers=me)
    client.post("/v1/auth/logout", headers=me)
    sender.sent.clear()
    client.post("/v1/ingest/text", json={"text": "I have Lynch syndrome."}, headers=mom)
    assert sender.sent == []


def test_token_moves_to_whoever_signs_in_on_the_phone(client, sender):
    first, second = account(client), account(client)
    client.put("/v1/devices/push", json={"token": TOKEN_A}, headers=first)
    client.put("/v1/devices/push", json={"token": TOKEN_A}, headers=second)
    assert client.get("/v1/devices/push", headers=first).json()["registered"] is False
    assert client.get("/v1/devices/push", headers=second).json()["registered"] is True


def test_dead_tokens_are_pruned_and_failures_dont_break_requests(client, sender):
    me, mom = linked_pair(client)
    client.put("/v1/devices/push", json={"token": TOKEN_A}, headers=me)
    sender.invalid.add(TOKEN_A)
    client.post("/v1/ingest/text", json={"text": "I have a BRCA2 mutation."}, headers=mom)
    assert client.get("/v1/devices/push", headers=me).json()["registered"] is False

    client.put("/v1/devices/push", json={"token": TOKEN_B}, headers=me)
    sender.fail = True
    r = client.post("/v1/ingest/text", json={"text": "I have familial hypercholesterolemia."}, headers=mom)
    assert r.status_code == 200 and r.json()["relatives_notified"] == 1


def test_expo_sender_chunks_and_reports_unregistered_devices():
    calls = []

    def fake_post(url, body, headers):
        payload = json.loads(body)
        calls.append((url, payload, headers))
        return {"data": [
            {"status": "error", "details": {"error": "DeviceNotRegistered"}} if m["to"].endswith("7]")
            else {"status": "ok", "id": "x"} for m in payload]}

    tokens = [f"ExponentPushToken[device{i:014d}]" for i in range(150)]
    invalid = ExpoPushSender(access_token="secret", post=fake_post).send(
        [PushMessage(t, "T", "B", {"url": "/"}) for t in tokens])
    assert [len(c[1]) for c in calls] == [100, 50]
    assert calls[0][0] == "https://exp.host/--/api/v2/push/send"
    assert calls[0][2]["Authorization"] == "Bearer secret"
    assert invalid == [t for t in tokens if re.search(r"7\]$", t)]
