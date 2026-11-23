"""Phase 4: Connect with Family Health Graph (OAuth + FHIR family history for partners, with consent)."""
import base64
import hashlib
import secrets
import urllib.parse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app

REDIRECT = "https://partner.example.com/callback"
ADMIN = {"X-Admin-Key": "admin-secret"}


@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "o.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret", public_url="https://fhg.example.org")),
                      follow_redirects=False)


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def partner(api, name="GenomeCo Genetic Counseling", confidential=False, redirect=REDIRECT):
    p = api.post("/admin/partners", headers=ADMIN, json={"name": name, "kind": "genetic_counseling"}).json()["partner"]
    reg = api.put(f"/admin/partners/{p['id']}/oauth", headers=ADMIN,
                  json={"redirect_uris": [redirect], "confidential": confidential})
    assert reg.status_code == 200, reg.text
    return p["id"], reg.json()["client_secret"]


def pkce():
    verifier = secrets.token_urlsafe(48)
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def user_with_history(api):
    h = account(api)
    api.put("/v1/profile/demographics", headers=h, json={"sex": "female", "birth_date": "1985-06-15"})
    api.post("/v1/family", headers=h, json={"relationship": "mother", "name": "Sunita", "conditions": [
        {"name": "breast cancer", "onset_age": 46}]})
    api.post("/v1/family", headers=h, json={"relationship": "maternal_aunt", "name": "Kavita", "conditions": [
        {"name": "ovarian cancer", "onset_age": 58}]})
    assert api.post("/v1/ingest/fhir", headers=h, json={"resourceType": "Condition", "code": {"text": "Hypertension"}}
                    ).status_code == 200
    return h


def authorize(api, h, client_id, scopes="family_history.read risk.read patient.read", state="xyz"):
    verifier, challenge = pkce()
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": scopes,
         "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    r = api.get("/oauth/authorize", params=q)
    assert r.status_code == 302 and r.headers["location"].startswith("/app/authorize?"), r.text
    info = api.get("/v1/oauth/request", headers=h, params={"client_id": client_id, "redirect_uri": REDIRECT, "scope": scopes})
    assert info.status_code == 200
    ok = api.post("/v1/oauth/approve", headers=h, json={
        "client_id": client_id, "redirect_uri": REDIRECT, "scopes": scopes.split(), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"}).json()
    back = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(ok["redirect_to"]).query))
    assert ok["redirect_to"].startswith(REDIRECT) and back["state"] == state
    return back["code"], verifier, info.json()


def token(api, client_id, code, verifier, **extra):
    return api.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
                                          "client_id": client_id, "code_verifier": verifier, **extra})


def connected(api, h, client_id, scopes="family_history.read risk.read patient.read"):
    code, verifier, _ = authorize(api, h, client_id, scopes)
    t = token(api, client_id, code, verifier)
    assert t.status_code == 200, t.text
    return t.json()


def fhir(api, tok, path):
    return api.get(f"/fhir/r4/{path}", headers={"Authorization": f"Bearer {tok['access_token']}"})


def test_full_flow_shares_family_history_without_names(api):
    client_id, _ = partner(api)
    h = user_with_history(api)
    code, verifier, info = authorize(api, h, client_id)
    assert info["partner"]["name"] == "GenomeCo Genetic Counseling"
    assert [s["scope"] for s in info["scopes"]] == ["family_history.read", "risk.read", "patient.read"]
    t = token(api, client_id, code, verifier)
    assert t.status_code == 200 and t.headers["cache-control"] == "no-store"
    tok = t.json()
    assert tok["token_type"] == "Bearer" and tok["scope"] == "family_history.read risk.read patient.read"

    fmh = fhir(api, tok, "FamilyMemberHistory")
    assert fmh.headers["content-type"].startswith("application/fhir+json")
    bundle = fmh.json()
    assert bundle["type"] == "searchset" and bundle["total"] == 2
    mother = next(e["resource"] for e in bundle["entry"] if e["resource"]["relationship"]["coding"][0]["code"] == "MTH")
    assert mother["patient"] == {"reference": f"Patient/{tok['patient']}"}
    assert mother["condition"][0]["onsetAge"]["value"] == 46
    assert "Sunita" not in fmh.text and "Kavita" not in fmh.text            # never names

    risks = fhir(api, tok, "RiskAssessment").json()
    titles = [e["resource"]["prediction"][0]["outcome"]["text"] for e in risks["entry"]]
    assert any("breast" in t.lower() or "ovarian" in t.lower() or "hereditary" in t.lower() for t in titles)
    first = risks["entry"][0]["resource"]
    assert fhir(api, tok, f"RiskAssessment/{first['id']}").json()["id"] == first["id"]

    patient = fhir(api, tok, "Patient").json()["entry"][0]["resource"]
    assert patient == {"resourceType": "Patient", "id": tok["patient"], "gender": "female", "birthDate": "1985"}

    # Not granted: own conditions.
    denied = fhir(api, tok, "Condition")
    assert denied.status_code == 403 and denied.json()["resourceType"] == "OperationOutcome"
    assert fhir(api, tok, "Encounter").status_code == 404

    grants = api.get("/v1/grants", headers=h).json()
    assert len(grants) == 1 and grants[0]["partner"]["name"] == "GenomeCo Genetic Counseling" and grants[0]["last_used_at"]
    audit = [a["action"] for a in api.get("/v1/audit", headers=h).json()]
    assert {"partner.consent_granted", "partner.token_issued", "partner.read"} <= set(audit)


def test_authorize_validation(api):
    client_id, _ = partner(api)
    _, challenge = pkce()
    base = {"response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "scope": "family_history.read",
            "state": "s1", "code_challenge": challenge, "code_challenge_method": "S256"}
    assert api.get("/oauth/authorize", params={**base, "client_id": "nope"}).status_code == 400
    bad_redirect = api.get("/oauth/authorize", params={**base, "redirect_uri": "https://evil.example.com/cb"})
    assert bad_redirect.status_code == 400 and "evil" not in bad_redirect.headers.get("location", "")
    for params, error in (({"scope": "family_history.read everything.write"}, "invalid_scope"),
                          ({"code_challenge_method": "plain"}, "invalid_request"),
                          ({"response_type": "token"}, "unsupported_response_type")):
        r = api.get("/oauth/authorize", params={**base, **params})
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
        assert r.status_code == 302 and q["error"] == error and q["state"] == "s1"


def test_token_endpoint_checks_code_pkce_redirect_and_client(api):
    client_id, _ = partner(api)
    other_id, _ = partner(api, name="Other Labs")
    h = user_with_history(api)
    code, verifier, _ = authorize(api, h, client_id)
    assert token(api, client_id, code, "wrong-verifier").json() == {"error": "invalid_grant"}
    code, verifier, _ = authorize(api, h, client_id)
    assert token(api, other_id, code, verifier).json() == {"error": "invalid_grant"}
    code, verifier, _ = authorize(api, h, client_id)
    assert api.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                          "redirect_uri": REDIRECT + "x", "code_verifier": verifier}).status_code == 400
    code, verifier, _ = authorize(api, h, client_id)
    assert token(api, client_id, code, verifier).status_code == 200
    assert token(api, client_id, code, verifier).json() == {"error": "invalid_grant"}     # single use
    assert api.post("/oauth/token", data={"grant_type": "password", "client_id": client_id}).json() == {
        "error": "unsupported_grant_type"}


def test_confidential_client_needs_its_secret(api):
    client_id, secret = partner(api, confidential=True)
    assert secret.startswith("fhgcs_")
    h = user_with_history(api)
    code, verifier, _ = authorize(api, h, client_id)
    assert token(api, client_id, code, verifier).status_code == 401
    assert token(api, client_id, code, verifier, client_secret="wrong").status_code == 401
    code, verifier, _ = authorize(api, h, client_id)
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    r = api.post("/oauth/token", headers={"Authorization": f"Basic {basic}"}, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier})
    assert r.status_code == 200, r.text


def test_refresh_rotation_and_revocation(api):
    client_id, _ = partner(api)
    h = user_with_history(api)
    tok = connected(api, h, client_id)
    r = api.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                       "client_id": client_id})
    new = r.json()
    assert r.status_code == 200 and new["access_token"] != tok["access_token"]
    assert api.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                          "client_id": client_id}).json() == {"error": "invalid_grant"}   # rotated
    assert fhir(api, new, "FamilyMemberHistory").status_code == 200

    grant_id = api.get("/v1/grants", headers=h).json()[0]["id"]
    other = account(api)
    assert api.delete(f"/v1/grants/{grant_id}", headers=other).status_code == 404
    assert api.delete(f"/v1/grants/{grant_id}", headers=h).status_code == 204
    assert fhir(api, new, "FamilyMemberHistory").status_code == 401
    assert fhir(api, tok, "FamilyMemberHistory").status_code == 401
    assert api.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": new["refresh_token"],
                                          "client_id": client_id}).json() == {"error": "invalid_grant"}
    assert api.get("/v1/grants", headers=h).json() == []
    # A deactivated partner loses access too.
    tok = connected(api, h, client_id)
    api.post(f"/admin/partners/{client_id}/deactivate", headers=ADMIN)
    assert fhir(api, tok, "FamilyMemberHistory").status_code == 401


def test_linked_relatives_shared_data_is_never_passed_on(api):
    client_id, _ = partner(api)
    other_id, _ = partner(api, name="Second Partner")
    h = user_with_history(api)
    inv = api.post("/v1/invitations", headers=h, json={"relationship": "sister", "share_level": "conditions"}).json()
    sis = {"Authorization": "Bearer " + api.post(f"/v1/invites/{inv['token']}/accept",
                                                 json={"share_level": "conditions_and_tree"}).json()["token"]}
    api.post("/v1/ingest/fhir", headers=sis, json={"resourceType": "Condition", "code": {"text": "Melanoma"}})
    # The user sees the sister's shared melanoma in their own view...
    assert any(c["category"] == "melanoma" for m in api.get("/v1/profile?include_linked=true", headers=h).json()["family"]
               for c in m["conditions"])
    tok = connected(api, h, client_id)
    assert "melanoma" not in fhir(api, tok, "FamilyMemberHistory").text.lower()      # ...partners never do
    # Each partner sees a different patient id, so partners can't link a user between them.
    assert connected(api, h, other_id)["patient"] != tok["patient"]


def test_deny_and_admin_validation_and_metadata(api):
    client_id, _ = partner(api)
    h = user_with_history(api)
    r = api.post("/v1/oauth/deny", headers=h, json={"client_id": client_id, "redirect_uri": REDIRECT, "state": "s"}).json()
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r["redirect_to"]).query))
    assert q == {"error": "access_denied", "state": "s"} and api.get("/v1/grants", headers=h).json() == []
    p = api.post("/admin/partners", headers=ADMIN, json={"name": "Plain HTTP", "kind": "lab"}).json()["partner"]
    assert api.put(f"/admin/partners/{p['id']}/oauth", headers=ADMIN, json={"redirect_uris": ["http://partner.example.com/cb"]}
                   ).status_code == 422
    assert api.put(f"/admin/partners/{p['id']}/oauth", headers=ADMIN, json={"redirect_uris": ["http://localhost:3000/cb"]}
                   ).status_code == 200
    assert api.put(f"/admin/partners/{p['id']}/oauth", json={"redirect_uris": [REDIRECT]}).status_code in (401, 403)

    meta = api.get("/.well-known/oauth-authorization-server").json()
    assert meta["authorization_endpoint"] == "https://fhg.example.org/oauth/authorize"
    assert meta["code_challenge_methods_supported"] == ["S256"] and "family_history.read" in meta["scopes_supported"]
    assert api.get("/fhir/r4/.well-known/smart-configuration").json()["token_endpoint"] == "https://fhg.example.org/oauth/token"
    cap = api.get("/fhir/r4/metadata").json()
    assert cap["resourceType"] == "CapabilityStatement" and {"FamilyMemberHistory", "RiskAssessment"} <= {
        r["type"] for r in cap["rest"][0]["resource"]}
    assert api.get("/fhir/r4/FamilyMemberHistory").status_code == 401
