"""SMART on FHIR standalone patient launch: connect a patient portal (Epic, Oracle Health, any SMART EHR)
and import the patient's own records.

Flow (OAuth 2.0 authorization code with PKCE, public client):
  app ──POST /v1/connect/smart {provider}──▶ authorize URL ──▶ patient signs in at their EHR and approves
  EHR ──redirect──▶ /connect/smart/callback?code&state ──▶ token exchange ──▶ FHIR reads ──▶ merged into the record
Refresh tokens (when the EHR grants offline_access) let "Sync now" re-import later without signing in again.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, Protocol

# SMART v1 scopes are still the most widely accepted; servers that support v2 accept these too.
SCOPES = ("launch/patient openid fhirUser offline_access patient/Patient.read patient/Condition.read "
          "patient/Observation.read patient/MedicationRequest.read patient/MedicationStatement.read "
          "patient/FamilyMemberHistory.read")
# What we read for one patient. Observations are limited to labs and vitals.
QUERIES = ("Condition?patient={pid}", "Observation?patient={pid}&category=laboratory",
           "Observation?patient={pid}&category=vital-signs", "MedicationRequest?patient={pid}",
           "MedicationStatement?patient={pid}", "FamilyMemberHistory?patient={pid}")
MAX_PAGES = 10


class SmartError(Exception):
    pass


class Http(Protocol):
    def get_json(self, url: str, token: Optional[str] = None) -> dict: ...
    def post_form(self, url: str, data: dict) -> dict: ...


class UrllibHttp:
    def get_json(self, url: str, token: Optional[str] = None) -> dict:
        headers = {"Accept": "application/fhir+json, application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:  # noqa: S310
                return json.loads(r.read())
        except (urllib.error.URLError, ValueError) as exc:
            raise SmartError(f"Couldn't read {urllib.parse.urlsplit(url).path}: {exc}") from exc

    def post_form(self, url: str, data: dict) -> dict:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            raise SmartError(f"The health system refused the sign-in ({exc.code}).") from exc
        except (urllib.error.URLError, ValueError) as exc:
            raise SmartError(f"Couldn't reach the health system: {exc}") from exc


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    iss: str          # FHIR base URL
    client_id: str
    client_secret: Optional[str] = None   # confidential clients only; most patient apps are public clients


def providers_from_env(raw: Optional[str]) -> dict[str, Provider]:
    """FHG_SMART_PROVIDERS: JSON list of {id, name, iss, client_id[, client_secret]}."""
    if not raw:
        return {}
    return {p["id"]: Provider(p["id"], p["name"], p["iss"].rstrip("/"), p["client_id"], p.get("client_secret"))
            for p in json.loads(raw)}


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def discover(http: Http, iss: str) -> dict:
    """The EHR's authorize and token endpoints, from .well-known/smart-configuration."""
    conf = http.get_json(f"{iss}/.well-known/smart-configuration")
    if not conf.get("authorization_endpoint") or not conf.get("token_endpoint"):
        raise SmartError("This health system doesn't publish SMART sign-in details.")
    return conf


def authorize_url(conf: dict, provider: Provider, redirect_uri: str, state: str, challenge: str) -> str:
    return conf["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": provider.client_id, "redirect_uri": redirect_uri, "scope": SCOPES,
        "state": state, "aud": provider.iss, "code_challenge": challenge, "code_challenge_method": "S256"})


def _token_request(http: Http, conf: dict, provider: Provider, data: dict) -> dict:
    data = {**data, "client_id": provider.client_id}
    if provider.client_secret:
        data["client_secret"] = provider.client_secret
    tok = http.post_form(conf["token_endpoint"], data)
    if not tok.get("access_token"):
        raise SmartError("The health system didn't grant access.")
    return tok


def exchange_code(http: Http, conf: dict, provider: Provider, code: str, redirect_uri: str, verifier: str) -> dict:
    tok = _token_request(http, conf, provider, {"grant_type": "authorization_code", "code": code,
                                                "redirect_uri": redirect_uri, "code_verifier": verifier})
    if not tok.get("patient"):
        raise SmartError("The health system didn't say which patient record to read.")
    return tok


def refresh(http: Http, conf: dict, provider: Provider, refresh_token: str) -> dict:
    return _token_request(http, conf, provider, {"grant_type": "refresh_token", "refresh_token": refresh_token})


@dataclass
class Pull:
    bundle: dict
    counts: dict[str, int] = field(default_factory=dict)


def fetch_patient_bundle(http: Http, iss: str, token: str, patient_id: str) -> Pull:
    """Read the patient and their records into one collection Bundle, following paging links."""
    entries = [{"resource": http.get_json(f"{iss}/Patient/{urllib.parse.quote(patient_id)}", token)}]
    counts: dict[str, int] = {}
    for query in QUERIES:
        url: Optional[str] = f"{iss}/{query.format(pid=urllib.parse.quote(patient_id))}"
        pages = 0
        while url and pages < MAX_PAGES:
            try:
                page = http.get_json(url, token)
            except SmartError:
                break  # a server may not support every resource type or scope; keep what we can read
            pages += 1
            for e in page.get("entry") or []:
                res = e.get("resource") or {}
                if res.get("resourceType") in ("Condition", "Observation", "MedicationRequest",
                                               "MedicationStatement", "FamilyMemberHistory"):
                    entries.append({"resource": res})
                    counts[res["resourceType"]] = counts.get(res["resourceType"], 0) + 1
            url = next((link.get("url") for link in page.get("link") or [] if link.get("relation") == "next"), None)
            if url and not url.startswith(iss):
                break  # never follow paging links to another host with the patient's token
    return Pull({"resourceType": "Bundle", "type": "collection", "entry": entries}, counts)
