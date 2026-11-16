import hashlib
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app
from fhg.security import hash_token
from fhg.storage import Store
from fhg.security import FieldCipher


class Outbox:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))

    def last_code(self) -> str:
        return re.search(r"\b(\d{6})\b", self.sent[-1][2]).group(1)


PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def id_token(iss="https://appleid.apple.com", aud="com.example.familyhealthgraph", sub="apple-user-1",
             email="relay@privaterelay.appleid.com", nonce=None, exp_in=600, key=PRIVATE_KEY):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + exp_in,
              "email": email, "email_verified": "true"}
    if nonce:
        claims["nonce"] = nonce
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def outbox():
    return Outbox()


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "a.db"), encryption_key=Fernet.generate_key().decode(),
                    auth_secret="test-secret", apple_audiences=("com.example.familyhealthgraph",))


@pytest.fixture
def client(settings, outbox):
    return TestClient(create_app(settings, email_sender=outbox,
                                 oidc_key_resolver=lambda provider, token: PRIVATE_KEY.public_key()))


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def email_sign_in(client, outbox, email="Priya@Example.com", headers=None, device="iPhone"):
    assert client.post("/v1/auth/email/start", json={"email": email}).status_code == 200
    r = client.post("/v1/auth/email/verify", headers=headers or {},
                    json={"email": email, "code": outbox.last_code(), "device": device})
    assert r.status_code == 200, r.text
    return r.json()


def test_config(client):
    assert client.get("/v1/auth/config").json() == {"email": True, "apple": True, "google": False}


def test_email_sign_up_then_sign_in_on_another_device(client, outbox):
    first = email_sign_in(client, outbox)
    assert first["new_account"] is True and first["email"] == "priya@example.com"
    assert outbox.sent[-1][0] == "priya@example.com"
    client.post("/v1/ingest/text", json={"text": "My mother had breast cancer at 44."}, headers=bearer(first["token"]))

    # Second phone, same email (different case and spacing) -> same account and data.
    second = email_sign_in(client, outbox, email="  priya@EXAMPLE.com ", device="Pixel")
    assert second["new_account"] is False and second["user_id"] == first["user_id"]
    assert second["token"] != first["token"]
    fam = client.get("/v1/profile", headers=bearer(second["token"])).json()["family"]
    assert fam[0]["relationship"] == "mother"

    sessions = client.get("/v1/auth/sessions", headers=bearer(second["token"])).json()
    assert {s["device"] for s in sessions} == {"iPhone", "Pixel"}
    assert [s["current"] for s in sessions if s["device"] == "Pixel"] == [True]

    # Revoke the lost iPhone from the Pixel.
    iphone = next(s for s in sessions if s["device"] == "iPhone")
    assert client.delete(f"/v1/auth/sessions/{iphone['id']}", headers=bearer(second["token"])).status_code == 204
    assert client.get("/v1/profile", headers=bearer(first["token"])).status_code == 401

    me = client.get("/v1/auth/me", headers=bearer(second["token"])).json()
    assert me["secured"] is True and me["identities"][0] == {**me["identities"][0], "provider": "email",
                                                            "email": "priya@example.com"}


def test_secure_an_anonymous_account(client, outbox):
    anon = client.post("/v1/users", json={"device": "iPhone"}).json()
    h = bearer(anon["token"])
    client.post("/v1/ingest/text", json={"text": "My dad had a heart attack at 50."}, headers=h)
    assert client.get("/v1/auth/me", headers=h).json()["secured"] is False

    linked = email_sign_in(client, outbox, email="sam@example.com", headers=h)
    assert linked == {**linked, "linked": True, "user_id": anon["user_id"]} and "token" not in linked
    assert client.get("/v1/auth/me", headers=h).json()["secured"] is True

    # Signing in on a new device with that email reaches the same data.
    other = email_sign_in(client, outbox, email="sam@example.com")
    assert other["user_id"] == anon["user_id"]


def test_cannot_attach_an_email_owned_by_another_account(client, outbox):
    email_sign_in(client, outbox, email="taken@example.com")
    anon = client.post("/v1/users").json()
    client.post("/v1/auth/email/start", json={"email": "taken@example.com"})
    r = client.post("/v1/auth/email/verify", headers=bearer(anon["token"]),
                    json={"email": "taken@example.com", "code": outbox.last_code()})
    assert r.status_code == 409


def test_code_rules(client, outbox):
    assert client.post("/v1/auth/email/start", json={"email": "not-an-email"}).status_code == 422
    client.post("/v1/auth/email/start", json={"email": "a@example.com"})
    code = outbox.last_code()
    wrong = "000000" if code != "000000" else "111111"

    r = client.post("/v1/auth/email/verify", json={"email": "a@example.com", "code": wrong})
    assert r.status_code == 400 and "4 attempts left" in r.json()["detail"]
    ok = client.post("/v1/auth/email/verify", json={"email": "a@example.com", "code": code})
    assert ok.status_code == 200
    # Single use.
    again = client.post("/v1/auth/email/verify", json={"email": "a@example.com", "code": code})
    assert again.status_code == 400

    # Five wrong attempts lock the code, even if the right one comes next.
    client.post("/v1/auth/email/start", json={"email": "b@example.com"})
    code = outbox.last_code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        client.post("/v1/auth/email/verify", json={"email": "b@example.com", "code": wrong})
    assert client.post("/v1/auth/email/verify", json={"email": "b@example.com", "code": code}).status_code == 400

    # A newer code replaces the older one.
    client.post("/v1/auth/email/start", json={"email": "c@example.com"})
    old = outbox.last_code()
    client.post("/v1/auth/email/start", json={"email": "c@example.com"})
    new = outbox.last_code()
    if old != new:
        assert client.post("/v1/auth/email/verify", json={"email": "c@example.com", "code": old}).status_code == 400
    assert client.post("/v1/auth/email/verify", json={"email": "c@example.com", "code": new}).status_code == 200


def test_code_rate_limit_and_expiry(client, outbox, settings):
    for _ in range(5):
        assert client.post("/v1/auth/email/start", json={"email": "d@example.com"}).status_code == 200
    assert client.post("/v1/auth/email/start", json={"email": "d@example.com"}).status_code == 429

    client.post("/v1/auth/email/start", json={"email": "e@example.com"})
    db = sqlite3.connect(settings.db_path)
    with db:
        db.execute("UPDATE login_codes SET expires_at = '2000-01-01T00:00:00+00:00'")
    r = client.post("/v1/auth/email/verify", json={"email": "e@example.com", "code": outbox.last_code()})
    assert r.status_code == 400


def test_no_plaintext_email_or_tokens_at_rest(client, outbox, settings):
    result = email_sign_in(client, outbox, email="private.person@example.com")
    dump = "\n".join(sqlite3.connect(settings.db_path).iterdump())
    assert "private.person" not in dump
    assert result["token"] not in dump and hash_token(result["token"]) in dump
    assert outbox.last_code() not in dump


def test_logout_and_session_expiry(client, outbox, settings):
    token = email_sign_in(client, outbox)["token"]
    assert client.post("/v1/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/v1/profile", headers=bearer(token)).status_code == 401

    token = email_sign_in(client, outbox)["token"]
    db = sqlite3.connect(settings.db_path)
    with db:
        db.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    r = client.get("/v1/profile", headers=bearer(token))
    assert r.status_code == 401 and "expired" in r.json()["detail"]


def test_deleting_account_frees_the_email(client, outbox):
    first = email_sign_in(client, outbox, email="z@example.com")
    client.delete("/v1/me", headers=bearer(first["token"]))
    again = email_sign_in(client, outbox, email="z@example.com")
    assert again["new_account"] is True and again["user_id"] != first["user_id"]


# --- Sign in with Apple / Google -----------------------------------------------------------

def test_apple_sign_in(client):
    r = client.post("/v1/auth/oidc/apple", json={"id_token": id_token(), "device": "iPhone"})
    assert r.status_code == 200 and r.json()["new_account"] is True
    again = client.post("/v1/auth/oidc/apple", json={"id_token": id_token()})
    assert again.json()["user_id"] == r.json()["user_id"]
    me = client.get("/v1/auth/me", headers=bearer(again.json()["token"])).json()
    assert me["identities"][0]["provider"] == "apple"


def test_apple_nonce_accepts_raw_or_sha256(client):
    raw = "n0nce-value"
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    assert client.post("/v1/auth/oidc/apple", json={"id_token": id_token(nonce=hashed), "nonce": raw}).status_code == 200
    assert client.post("/v1/auth/oidc/apple", json={"id_token": id_token(nonce=raw), "nonce": raw}).status_code == 200
    assert client.post("/v1/auth/oidc/apple", json={"id_token": id_token(nonce="other"), "nonce": raw}).status_code == 401


@pytest.mark.parametrize("token", [
    id_token(aud="someone-elses-app"),
    id_token(iss="https://evil.example.com"),
    id_token(exp_in=-3600),
    id_token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
    "not-a-jwt",
])
def test_apple_rejects_bad_tokens(client, token):
    assert client.post("/v1/auth/oidc/apple", json={"id_token": token}).status_code == 401


def test_unconfigured_or_unknown_provider(client):
    tok = id_token(iss="https://accounts.google.com", aud="client-id")
    assert client.post("/v1/auth/oidc/google", json={"id_token": tok}).status_code == 404
    assert client.post("/v1/auth/oidc/myspace", json={"id_token": tok}).status_code == 404


def test_link_apple_to_email_account(client, outbox):
    acct = email_sign_in(client, outbox, email="both@example.com")
    r = client.post("/v1/auth/oidc/apple", headers=bearer(acct["token"]), json={"id_token": id_token(sub="apple-9")})
    assert r.json()["linked"] is True
    via_apple = client.post("/v1/auth/oidc/apple", json={"id_token": id_token(sub="apple-9")}).json()
    assert via_apple["user_id"] == acct["user_id"]
    providers = {i["provider"] for i in client.get("/v1/auth/me", headers=bearer(acct["token"])).json()["identities"]}
    assert providers == {"email", "apple"}


# --- migration ------------------------------------------------------------------------------

def test_legacy_database_tokens_keep_working(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE users (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);")
    db.execute("INSERT INTO users VALUES ('u1', ?, '2026-01-01T00:00:00+00:00')", (hash_token("old-token"),))
    db.commit()
    db.close()

    store = Store(path, FieldCipher(Fernet.generate_key()))
    assert store.user_for_token("old-token") == "u1"
    user_id, token = store.create_user()  # still works with the old NOT NULL column
    assert store.user_for_token(token) == user_id
    Store(path, FieldCipher(Fernet.generate_key()))  # migration is idempotent
    assert len(store.sessions_for("u1")) == 1
