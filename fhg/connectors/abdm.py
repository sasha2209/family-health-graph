"""Direct ABHA link: pull a person's records from ABDM-linked hospitals and labs, with their consent.

Family Health Graph acts as an ABDM **Health Information User (HIU)**. Rather than implementing the gateway protocol
(sessions, callbacks, Fidelius ECDH encryption) ourselves, we call NHA's open-source **ABDM Wrapper**
(github.com/NHA-ABDM/ABDM-wrapper), deployed next to this server, through its v3 HIU facade (docs/wrapperV3.yaml in
that repository):

1. ``POST {wrapper}/v3/consent-init``: ask for consent to the person's ABHA address. They approve it in their
   ABHA/PHR app.
2. ``GET {wrapper}/v3/consent-status/{requestId}``: GRANTED, with one consent artefact per hospital/lab (HIP), or
   DENIED / EXPIRED / REVOKED.
3. ``POST {wrapper}/v3/health-information/fetch-records``: request the records for an artefact.
4. ``GET {wrapper}/v3/health-information/status/{requestId}``: the decrypted FHIR bundles, which go through the same
   FHIR import as every other source.

The wrapper's latest release predates this code; check its API against the current sandbox before go-live.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

HI_TYPES = ("OPConsultation", "Prescription", "DischargeSummary", "DiagnosticReport", "ImmunizationRecord",
            "HealthDocumentRecord", "WellnessRecord")
ABHA_ADDRESS = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._]{2,31}@(sbx|abdm)$")


class AbdmError(Exception):
    pass


class JsonHttp(Protocol):
    def request_json(self, method: str, url: str, body: Optional[dict] = None) -> tuple[int, dict]: ...


class UrllibJsonHttp:
    def request_json(self, method: str, url: str, body: Optional[dict] = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (our own wrapper deployment)
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read() or b"{}")
            except ValueError:
                return exc.code, {}
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AbdmError(f"The ABDM connection service isn't reachable ({exc}).") from exc


@dataclass
class ConsentState:
    status: str                                    # REQUESTED | GRANTED | DENIED | EXPIRED | REVOKED | ERROR
    artefacts: list[dict] = field(default_factory=list)   # [{"id": consent id, "hip_id": ...}]
    message: Optional[str] = None


@dataclass
class Records:
    done: bool
    bundles: list[dict] = field(default_factory=list)
    message: Optional[str] = None


def _errors(body: dict) -> str:
    errs = body.get("errors") or []
    msgs = [((e.get("error") or e) or {}).get("message") for e in errs if isinstance(e, dict)]
    return "; ".join(m for m in msgs if m) or body.get("message") or "the request was rejected"


class WrapperClient:
    def __init__(self, base_url: str, hiu_id: str, requester_name: str, http: JsonHttp,
                 purpose_code: str = "CAREMGT", purpose_text: str = "Care Management"):
        self.base = base_url.rstrip("/")
        self.hiu_id, self.requester_name, self.http = hiu_id, requester_name, http
        self.purpose_code, self.purpose_text = purpose_code, purpose_text

    def consent_init(self, abha_address: str, years: int = 10, keep_days: int = 365,
                     hi_types: tuple[str, ...] = HI_TYPES) -> str:
        """Ask for consent; returns the request id to poll. The person approves in their ABHA app."""
        now = datetime.now(timezone.utc)
        request_id = str(uuid.uuid4())
        fmt = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"  # noqa: E731
        body = {"requestId": request_id, "timestamp": fmt(now), "consent": {
            "purpose": {"text": self.purpose_text, "code": self.purpose_code, "refUri": "http://terminology.hl7.org"},
            "patient": {"id": abha_address},
            "hiu": {"id": self.hiu_id},
            "requester": {"name": self.requester_name},
            "hiTypes": list(hi_types),
            "permission": {"accessMode": "STORE",
                           "dateRange": {"from": fmt(now - timedelta(days=365 * years)), "to": fmt(now)},
                           "dataEraseAt": fmt(now + timedelta(days=keep_days)),
                           "frequency": {"unit": "HOUR", "value": 1, "repeats": 0}},
        }}
        status, out = self.http.request_json("POST", f"{self.base}/v3/consent-init", body)
        if status >= 400:
            raise AbdmError(f"ABDM didn't accept the consent request: {_errors(out)}")
        return out.get("clientRequestId") or request_id

    def consent_status(self, request_id: str) -> ConsentState:
        status, out = self.http.request_json("GET", f"{self.base}/v3/consent-status/{request_id}")
        if status >= 400:
            return ConsentState("ERROR", message=_errors(out))
        details = out.get("consentDetails") or {}
        text = json.dumps(out.get("status") or "") + json.dumps([c.get("status") for c in details.get("consent") or []])
        for word in ("DENIED", "REVOKED", "EXPIRED"):
            if word in text:
                return ConsentState(word)
        artefacts = [{"id": a["id"], "hip_id": a.get("hipId")}
                     for c in details.get("consent") or [] for a in c.get("consentArtefacts") or [] if a.get("id")]
        if "GRANTED" in text or artefacts:
            return ConsentState("GRANTED", artefacts)
        return ConsentState("REQUESTED")

    def fetch_records(self, consent_id: str) -> str:
        request_id = str(uuid.uuid4())
        status, out = self.http.request_json("POST", f"{self.base}/v3/health-information/fetch-records",
                                             {"requestId": request_id, "consentId": consent_id,
                                              "requesterId": self.hiu_id})
        if status >= 400:
            raise AbdmError(f"Couldn't request the records: {_errors(out)}")
        return out.get("clientRequestId") or request_id

    def records_status(self, request_id: str) -> Records:
        status, out = self.http.request_json("GET", f"{self.base}/v3/health-information/status/{request_id}")
        if status >= 400:
            return Records(done=True, message=_errors(out))
        entries = out.get("decryptedHealthInformationEntries") or []
        bundles = []
        for e in entries:
            content = e.get("bundleContent")
            try:
                bundles.append(json.loads(content) if isinstance(content, str) else content)
            except ValueError:
                continue
        return Records(done=bool(entries) or "ERROR" in str(out.get("status", "")).upper(), bundles=bundles,
                       message=None if entries else out.get("error"))


def valid_abha_address(value: str) -> bool:
    """name@abdm (production) or name@sbx (sandbox)."""
    return bool(ABHA_ADDRESS.match(value.strip()))


