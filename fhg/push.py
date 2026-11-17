"""Push notifications for in-app notifications (family alerts, accepted invites).

Every in-app notification goes through :class:`Notifier`, which stores it and
pushes a short alert to the user's registered phones.

Privacy: push text appears on lock screens and passes through Apple/Google and
Expo, so it never contains health information, names or relationships, only
a generic nudge. The details are shown inside the app after it is unlocked.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

log = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_TOKEN_RE = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-]{10,}\]$")

TITLE = "Family Health Graph"
PUSH_TEXT = {
    "family_cascade": "A relative shared a health update that may affect you.",
    "invitation_accepted": "A relative accepted your invitation.",
    "referral": "Your care team updated a referral for you.",
}
DEFAULT_TEXT = "You have a new update."


@dataclass
class PushMessage:
    to: str
    title: str
    body: str
    data: dict = field(default_factory=dict)


class PushSender(Protocol):
    def send(self, messages: list[PushMessage]) -> list[str]:
        """Send messages; return the tokens that are no longer valid."""
        ...


class ConsolePushSender:
    """Development: log pushes instead of sending them."""

    def send(self, messages: list[PushMessage]) -> list[str]:
        for m in messages:
            log.warning("DEV PUSH to %s | %s: %s", m.to, m.title, m.body)
        return []


Post = Callable[[str, bytes, dict], dict]


def _urllib_post(url: str, body: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https URL)
        return json.loads(resp.read())


class ExpoPushSender:
    """Sends through Expo's push service, which relays to APNs and FCM."""

    CHUNK = 100  # Expo's per-request limit

    def __init__(self, access_token: Optional[str] = None, post: Optional[Post] = None):
        self.access_token = access_token
        self.post = post or _urllib_post

    def send(self, messages: list[PushMessage]) -> list[str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        invalid: list[str] = []
        for i in range(0, len(messages), self.CHUNK):
            chunk = messages[i:i + self.CHUNK]
            payload = [{"to": m.to, "title": m.title, "body": m.body, "data": m.data,
                        "sound": "default", "priority": "high"} for m in chunk]
            result = self.post(EXPO_PUSH_URL, json.dumps(payload).encode(), headers)
            for message, ticket in zip(chunk, result.get("data", [])):
                if ticket.get("status") == "error":
                    if (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                        invalid.append(message.to)
                    else:
                        log.warning("push to a device failed: %s", ticket.get("message"))
        return invalid


def push_sender_from_env() -> PushSender:
    if os.environ.get("FHG_PUSH_BACKEND", "console") == "expo":
        return ExpoPushSender(os.environ.get("FHG_EXPO_ACCESS_TOKEN"))
    return ConsolePushSender()


class Notifier:
    """Store an in-app notification and push a generic alert to the user's phones."""

    def __init__(self, store, sender: PushSender, background: bool = True):
        self.store = store
        self.sender = sender
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push") if background else None

    def notify(self, user_id: str, kind: str, message: str) -> None:
        self.store.notify(user_id, kind, message)
        tokens = self.store.push_tokens_for(user_id)
        if not tokens:
            return
        if self._pool:
            self._pool.submit(self._push, tokens, kind)  # don't make the request wait on Expo
        else:
            self._push(tokens, kind)

    def _push(self, tokens: list[str], kind: str) -> None:
        body = PUSH_TEXT.get(kind, DEFAULT_TEXT)
        messages = [PushMessage(t, TITLE, body, {"kind": kind, "url": "/"}) for t in tokens]
        try:
            invalid = self.sender.send(messages)
            if invalid:
                self.store.remove_push_tokens(invalid)
        except Exception:
            log.exception("sending push notifications failed")
