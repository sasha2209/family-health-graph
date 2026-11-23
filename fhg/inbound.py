"""Forward documents in by email or WhatsApp, straight into the review queue.

Email: every user gets a private address (``<token>@<FHG_INBOUND_EMAIL_DOMAIN>``). An inbound-mail provider
(Postmark's inbound webhook format; SendGrid/Mailgun can be adapted) POSTs each message to
``/inbound/email?secret=...``. PDF and image attachments become documents waiting for review.

WhatsApp (Business Cloud API): the user links their number once by sending a short code shown in the app.
After that, any photo or PDF they send to the business number becomes a document. Replies never contain
health information.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol

log = logging.getLogger(__name__)

ACCEPTED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/jpg", "image/webp"}
GRAPH = "https://graph.facebook.com/v21.0"


def new_email_token() -> str:
    # Lowercase letters and digits only (email local parts are case-insensitive in practice). ~62 bits.
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def new_link_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def phone_key(secret: str, phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return hmac.new(secret.encode(), b"whatsapp:" + digits.encode(), hashlib.sha256).hexdigest()


# --- email ------------------------------------------------------------------------------------

@dataclass
class EmailAttachment:
    filename: str
    content_type: str
    content_b64: str


def email_recipients(payload: dict) -> list[str]:
    """Addresses a Postmark-style inbound payload was sent to."""
    out = []
    for key in ("OriginalRecipient", "To", "Cc", "Bcc"):
        value = payload.get(key)
        if isinstance(value, str):
            out += re.findall(r"[\w.+-]+@[\w.-]+", value)
    for key in ("ToFull", "CcFull", "BccFull"):
        for item in payload.get(key) or []:
            if isinstance(item, dict) and item.get("Email"):
                out.append(item["Email"])
    return [a.lower() for a in out]


def token_for_domain(addresses: list[str], domain: str) -> Optional[str]:
    domain = domain.lower().lstrip("@")
    for address in addresses:
        local, _, host = address.partition("@")
        if host == domain and re.fullmatch(r"[a-z0-9]{8,32}", local.split("+")[0]):
            return local.split("+")[0]
    return None


def email_attachments(payload: dict) -> list[EmailAttachment]:
    out = []
    for a in payload.get("Attachments") or []:
        if not isinstance(a, dict):
            continue
        ctype = (a.get("ContentType") or "").split(";")[0].strip().lower()
        if ctype in ACCEPTED_TYPES and a.get("Content"):
            out.append(EmailAttachment(a.get("Name") or "attachment", ctype, a["Content"]))
    return out


# --- WhatsApp ---------------------------------------------------------------------------------

class WhatsAppClient(Protocol):
    def download(self, media_id: str) -> bytes: ...
    def send_text(self, to: str, body: str) -> None: ...


class GraphWhatsAppClient:
    def __init__(self, access_token: str, phone_number_id: str):
        self.token, self.phone_number_id = access_token, phone_number_id

    def _request(self, url: str, data: Optional[bytes] = None) -> bytes:
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (Meta's Graph API)
            return resp.read()

    def download(self, media_id: str) -> bytes:
        meta = json.loads(self._request(f"{GRAPH}/{media_id}"))
        return self._request(meta["url"])

    def send_text(self, to: str, body: str) -> None:
        self._request(f"{GRAPH}/{self.phone_number_id}/messages", json.dumps({
            "messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}).encode())


def verify_meta_signature(app_secret: str, raw_body: bytes, header: Optional[str]) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass
class WhatsAppMessage:
    sender: str          # the sender's phone number, digits only
    kind: str            # text | image | document | audio | other
    text: str = ""
    media_id: Optional[str] = None
    mime_type: Optional[str] = None
    filename: Optional[str] = None


def whatsapp_messages(payload: dict) -> list[WhatsAppMessage]:
    out = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            for m in (change.get("value") or {}).get("messages") or []:
                kind = m.get("type")
                msg = WhatsAppMessage(sender=re.sub(r"\D", "", m.get("from", "")), kind=kind if kind in (
                    "text", "image", "document", "audio") else "other")
                if kind == "text":
                    msg.text = (m.get("text") or {}).get("body", "")
                elif kind in ("image", "document"):
                    media = m.get(kind) or {}
                    msg.media_id, msg.mime_type = media.get("id"), (media.get("mime_type") or "").split(";")[0]
                    msg.filename = media.get("filename") or ("photo.jpg" if kind == "image" else "document.pdf")
                if msg.sender:
                    out.append(msg)
    return out

# Reply texts, in six languages, live in fhg/i18n.py.
