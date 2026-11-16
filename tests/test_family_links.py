import json
import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app
from fhg.family_links import compose, inverse_relationship
from fhg.models import Relationship as R

SAMPLES = Path(__file__).parent.parent / "fhg" / "sample_data"


# --- relationship algebra ----------------------------------------------------------

@pytest.mark.parametrize("rel,sex,expected", [
    (R.MOTHER, "female", R.DAUGHTER),
    (R.MOTHER, "male", R.SON),
    (R.MOTHER, None, R.CHILD),
    (R.SON, "female", R.MOTHER),
    (R.SISTER, None, R.SIBLING),
    (R.PATERNAL_GRANDFATHER, "male", R.GRANDSON),
    (R.MATERNAL_AUNT, "female", R.NIECE),
    (R.NEPHEW, "male", R.UNCLE),
    (R.PATERNAL_COUSIN, "female", R.COUSIN),
])
def test_inverse_relationship(rel, sex, expected):
    assert inverse_relationship(rel, sex) == expected


@pytest.mark.parametrize("link,theirs,expected", [
    (R.MOTHER, R.SISTER, R.MATERNAL_AUNT),
    (R.MOTHER, R.MOTHER, R.MATERNAL_GRANDMOTHER),
    (R.FATHER, R.BROTHER, R.PATERNAL_UNCLE),
    (R.SISTER, R.MATERNAL_AUNT, R.MATERNAL_AUNT),
    (R.PATERNAL_UNCLE, R.FATHER, R.PATERNAL_GRANDFATHER),
    (R.MOTHER, R.DAUGHTER, None),  # could be me: never guessed
    (R.SON, R.MOTHER, None),
])
def test_compose(link, theirs, expected):
    assert compose(link, theirs) == expected


# --- API ---------------------------------------------------------------------------------

@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "t.db"), encryption_key=Fernet.generate_key().decode())


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def new_user(client):
    return auth(client.post("/v1/users").json()["token"])


@pytest.fixture
def inviter(client):
    """A woman whose record (sample FHIR) already lists her mother."""
    h = new_user(client)
    client.post("/v1/ingest/fhir", json=json.loads((SAMPLES / "fhir_bundle.json").read_text()), headers=h)
    return h


def invite(client, h, **body):
    r = client.post("/v1/invitations", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def rule_ids(client, h):
    return {i["rule_id"]: i for i in client.get("/v1/insights", headers=h).json()["insights"]}


def test_invite_preview_accept_and_share(client, inviter):
    mother_id = next(m["id"] for m in client.get("/v1/profile", headers=inviter).json()["family"]
                     if m["relationship"] == "mother")
    inv = invite(client, inviter, member_id=mother_id, inviter_name="Priya",
                 message="Mom, can you add your side?")
    assert inv["invite_url"].endswith("/invite/" + inv["token"])
    assert inv["invitation"]["relationship"] == "mother"

    preview = client.get(f"/v1/invites/{inv['token']}").json()
    assert preview == {**preview, "inviter_name": "Priya", "you_are_their": "mother",
                       "they_are_your": "daughter", "they_will_share": "conditions"}

    # Mother accepts as a brand-new user and shares her history plus family tree.
    r = client.post(f"/v1/invites/{inv['token']}/accept", json={"share_level": "conditions_and_tree"})
    assert r.status_code == 200 and r.json()["they_are_your"] == "daughter"
    mom = auth(r.json()["token"])

    # Link is single-use.
    assert client.post(f"/v1/invites/{inv['token']}/accept", json={}).status_code == 410
    assert client.get(f"/v1/invites/{inv['token']}").status_code == 410

    # Mother records her own history: a BRCA1 variant, and her sister's colon cancer at 45.
    r = client.post("/v1/ingest/text", headers=mom, json={"text": (
        "I have a BRCA1 mutation. My sister had colon cancer at 45. "
        "My daughter had nothing serious.")})
    assert r.json()["relatives_notified"] == 1

    notes = client.get("/v1/notifications", headers=inviter).json()
    kinds = [n["kind"] for n in notes]
    assert "invitation_accepted" in kinds and "family_cascade" in kinds
    cascade = next(n for n in notes if n["kind"] == "family_cascade")
    assert "Your mother shared" in cascade["message"] and "BRCA1/BRCA2" in cascade["message"]

    # Daughter's insights now reflect the variant (HIGH) and the composed maternal aunt.
    ids = rule_ids(client, inviter)
    assert ids["hboc_family_pattern"]["level"] == "high"
    assert any("Maternal aunt: Colorectal cancer" in e for e in ids["colorectal_family_history"]["evidence"])

    # Merged into the existing "mother" entry, not duplicated.
    fam = client.get("/v1/profile?include_linked=true", headers=inviter).json()["family"]
    mothers = [m for m in fam if m["relationship"] == "mother"]
    assert len(mothers) == 1 and mothers[0]["linked"] is True
    # The stored record is untouched: sharing is computed live.
    stored = client.get("/v1/profile", headers=inviter).json()["family"]
    assert not any(m["linked"] for m in stored)

    # Mother sees her daughter as a linked relative (daughter shares conditions by default).
    links = client.get("/v1/links", headers=mom).json()
    assert links[0]["relationship"] == "daughter" and links[0]["they_share"] == "conditions"

    # Mother narrows sharing to her own conditions: the aunt disappears, the variant stays.
    client.put(f"/v1/links/{links[0]['link_id']}", json={"share_level": "conditions"}, headers=mom)
    ids = rule_ids(client, inviter)
    assert "colorectal_family_history" not in ids and ids["hboc_family_pattern"]["level"] == "high"

    # Mother stops sharing entirely: back to the daughter's own data.
    client.put(f"/v1/links/{links[0]['link_id']}", json={"share_level": "none"}, headers=mom)
    assert rule_ids(client, inviter)["hboc_family_pattern"]["level"] == "moderate"


def test_shared_data_never_leaves_to_partners_or_exports(client, inviter):
    inv = invite(client, inviter, relationship="sister")
    sis = auth(client.post(f"/v1/invites/{inv['token']}/accept", json={}).json()["token"])
    client.post("/v1/ingest/text", json={"text": "I have Lynch syndrome."}, headers=sis)
    assert "colorectal_family_history" in rule_ids(client, inviter)

    export = json.dumps(client.get("/v1/export/fhir", headers=inviter).json()).lower()
    assert "lynch" not in export
    client.post("/v1/consents", json={"scope": "share:primary-care", "granted": True}, headers=inviter)
    payload = client.post("/v1/partners/primary-care/share", headers=inviter).json()["payload"]
    assert "lynch" not in json.dumps(payload["fhir_bundle"]).lower()


def test_existing_user_accepts_and_existing_results_cascade(client, inviter):
    brother = new_user(client)
    client.post("/v1/ingest/text", json={"text": "I had malignant hyperthermia during surgery."}, headers=brother)
    inv = invite(client, inviter, relationship="brother", share_level="none")
    r = client.post(f"/v1/invites/{inv['token']}/accept", json={}, headers=brother)
    assert r.status_code == 200 and "token" not in r.json()
    assert r.json()["they_are_your"] == "sister"
    # The brother's result already on file reaches the inviter immediately.
    assert any(n["kind"] == "family_cascade" for n in client.get("/v1/notifications", headers=inviter).json())
    assert "malignant_hyperthermia" in rule_ids(client, inviter)
    # The inviter shares nothing, so the brother sees no data from her.
    assert client.get("/v1/links", headers=brother).json()[0]["they_share"] == "none"

    # Already linked; can't link twice.
    inv2 = invite(client, inviter, relationship="brother")
    assert client.post(f"/v1/invites/{inv2['token']}/accept", json={}, headers=brother).status_code == 409


def test_relationship_override_on_accept(client, inviter):
    inv = invite(client, inviter, relationship="niece")
    r = client.post(f"/v1/invites/{inv['token']}/accept", json={"relationship": "paternal_aunt"})
    assert r.json()["they_are_your"] == "paternal_aunt"


def test_invitation_guards(client, inviter, settings):
    inv = invite(client, inviter, relationship="father")
    assert client.post(f"/v1/invites/{inv['token']}/accept", json={}, headers=inviter).status_code == 400
    assert client.get("/v1/invites/not-a-token").status_code == 404
    assert client.post("/v1/invitations", json={}, headers=inviter).status_code == 422
    assert client.post("/v1/invitations", json={"member_id": "nope"}, headers=inviter).status_code == 404
    assert client.post("/v1/invitations", json={"relationship": "father", "share_level": "all"},
                       headers=inviter).status_code == 422

    # Revoke, then the link is dead.
    assert client.delete(f"/v1/invitations/{inv['invitation']['id']}", headers=inviter).status_code == 204
    assert client.post(f"/v1/invites/{inv['token']}/accept", json={}).status_code == 410
    listed = client.get("/v1/invitations", headers=inviter).json()
    assert listed[0]["status"] == "revoked" and "token" not in listed[0]

    # Declining works and is final.
    inv = invite(client, inviter, relationship="sister")
    assert client.post(f"/v1/invites/{inv['token']}/decline").status_code == 204
    assert client.get(f"/v1/invites/{inv['token']}").status_code == 410

    # Tokens and messages aren't stored in plaintext.
    inv = invite(client, inviter, relationship="sister", message="secret-note")
    db = sqlite3.connect(settings.db_path)
    dump = "\n".join(db.iterdump())
    assert inv["token"] not in dump and "secret-note" not in dump


def test_expired_invitation(client, inviter, settings):
    inv = invite(client, inviter, relationship="sister")
    db = sqlite3.connect(settings.db_path)
    with db:
        db.execute("UPDATE invitations SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert client.get(f"/v1/invites/{inv['token']}").status_code == 410


def test_unlink_and_account_deletion_remove_access(client, inviter):
    inv = invite(client, inviter, relationship="sister")
    sis = auth(client.post(f"/v1/invites/{inv['token']}/accept", json={}).json()["token"])
    client.post("/v1/ingest/text", json={"text": "I have familial hypercholesterolemia."}, headers=sis)
    assert "familial_hypercholesterolemia" in rule_ids(client, inviter)

    link_id = client.get("/v1/links", headers=inviter).json()[0]["link_id"]
    assert client.delete(f"/v1/links/{link_id}", headers=inviter).status_code == 204
    assert client.get("/v1/links", headers=sis).json() == []
    assert "familial_hypercholesterolemia" not in rule_ids(client, inviter)

    # Re-link, then the sister deletes her account: her data disappears for the inviter.
    inv = invite(client, inviter, relationship="sister")
    client.post(f"/v1/invites/{inv['token']}/accept", json={}, headers=sis)
    assert "familial_hypercholesterolemia" in rule_ids(client, inviter)
    client.delete("/v1/me", headers=sis)
    assert client.get("/v1/links", headers=inviter).json() == []
    assert "familial_hypercholesterolemia" not in rule_ids(client, inviter)


def test_record_gaps_suggests_inviting_until_linked(client, inviter):
    gaps = rule_ids(client, inviter)["record_gaps"]["evidence"]
    assert gaps[0].startswith("Invite a parent or sibling")
    inv = invite(client, inviter, relationship="sister")
    client.post(f"/v1/invites/{inv['token']}/accept", json={})
    gaps = rule_ids(client, inviter).get("record_gaps", {"evidence": []})["evidence"]
    assert not any(g.startswith("Invite") for g in gaps)
