"""Referral partners: organisations such as genetic-counseling services or
testing labs that receive referrals from clinics and report outcomes back.

Security model
* Partners are created by the platform operator (admin key), the point at
  which a contract (BAA/DPA) would be signed. Each gets an API key, stored only
  as a hash, and an optional webhook URL plus signing secret.
* Webhooks are "thin": they carry only an event type and a referral ID, never
  health data. The partner fetches details with its API key. A leaked or
  misrouted webhook therefore exposes nothing.
* Webhook bodies are signed like Stripe's: header
  ``X-FHG-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, f"{t}.{body}")>``.
* A partner can only see referrals routed to it, and loses access when the
  patient disconnects from the referring clinic.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

log = logging.getLogger(__name__)

PARTNER_KINDS = ("genetic_counseling", "genetic_testing", "lab", "specialist", "prevention_program", "other")
# What a partner may report back.
PARTNER_STATUSES = ("scheduled", "completed", "declined")
FHIR_STATUS = {"referred": "active", "scheduled": "active", "completed": "completed", "declined": "revoked"}


def sign(secret: str, body: bytes, timestamp: Optional[int] = None) -> str:
    t = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify(secret: str, body: bytes, header: str, tolerance_s: int = 300, now: Optional[int] = None) -> bool:
    """Reference verifier for partners (also used in tests)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs((int(time.time()) if now is None else now) - t) > tolerance_s:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))


def event(kind: str, referral_id: str) -> dict:
    return {"id": "evt_" + uuid.uuid4().hex[:16], "type": kind,
            "created": datetime.now(timezone.utc).isoformat(), "data": {"referral_id": referral_id}}


class WebhookSender(Protocol):
    def send(self, url: str, body: bytes, headers: dict) -> None: ...


class HttpWebhookSender:
    def send(self, url: str, body: bytes, headers: dict) -> None:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10):  # noqa: S310 (operator-configured partner URL)
            pass


class PartnerNotifier:
    """Delivers signed webhooks in the background so clinic requests never wait on a partner."""

    def __init__(self, store, sender: WebhookSender, background: bool = True):
        self.store, self.sender = store, sender
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="webhook") if background else None

    def notify_event(self, partner_id: str, kind: str, data: dict) -> None:
        """A health-data-free event with arbitrary ids (e.g. {"booking_id": ...})."""
        partner = self.store.partner(partner_id)
        secret = self.store.partner_webhook_secret(partner_id)
        if not partner or not partner["webhook_url"] or not secret:
            return
        body = json.dumps({"id": "evt_" + uuid.uuid4().hex[:16], "type": kind,
                           "created": datetime.now(timezone.utc).isoformat(), "data": data}).encode()
        headers = {"Content-Type": "application/json", "X-FHG-Signature": sign(secret, body),
                   "User-Agent": "FamilyHealthGraph-Webhooks/1"}
        job: Callable[[], None] = lambda: self._deliver(partner["webhook_url"], body, headers)
        self._pool.submit(job) if self._pool else job()

    def notify(self, partner_id: str, kind: str, referral_id: str) -> None:
        partner = self.store.partner(partner_id)
        secret = self.store.partner_webhook_secret(partner_id)
        if not partner or not partner["webhook_url"] or not secret:
            return
        body = json.dumps(event(kind, referral_id)).encode()
        headers = {"Content-Type": "application/json", "X-FHG-Signature": sign(secret, body),
                   "User-Agent": "FamilyHealthGraph-Webhooks/1"}
        job: Callable[[], None] = lambda: self._deliver(partner["webhook_url"], body, headers)
        self._pool.submit(job) if self._pool else job()

    def _deliver(self, url: str, body: bytes, headers: dict) -> None:
        try:
            self.sender.send(url, body, headers)
        except Exception:
            # Partners can always pull GET /v1/partner/referrals, so a failed push loses nothing.
            log.exception("webhook delivery to partner failed")


def service_request(referral: dict, program: str, clinic_name: str, partner_name: str,
                    patient_display: str, reason: Optional[str], evidence: list[str]) -> dict:
    """The referral as a FHIR R4 ServiceRequest (what EHRs and partner systems ingest)."""
    resource = {
        "resourceType": "ServiceRequest",
        "id": referral["id"],
        "status": FHIR_STATUS.get(referral["status"], "active"),
        "intent": "order",
        "code": {"text": program},
        "subject": {"display": patient_display},
        "requester": {"display": clinic_name},
        "performer": [{"display": partner_name}],
        "authoredOn": referral["created_at"],
    }
    if reason:
        resource["reasonCode"] = [{"text": reason}]
    if evidence:
        resource["note"] = [{"text": "Family history (patient-reported): " + "; ".join(evidence)}]
    return resource
