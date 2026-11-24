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
    "documents_received": "Your forwarded documents are ready to review.",
    "booking": "There's an update on your test booking.",
    "reminder": "A health check is still due. Open the app to book it.",
    "care": "An update about someone you care for.",
    "risk": "Your genetic counselor shared your results.",
    "privacy": "There's an answer to your privacy question.",
    "security": "Important security notice about your account.",
}
# Where tapping the notification opens. Pushes never carry health details (they show on lock screens).
PUSH_URL = {"booking": "/", "reminder": "/", "documents_received": "/", "care": "/", "risk": "/",
            "privacy": "/privacy", "security": "/"}
DEFAULT_TEXT = "You have a new update."
# Lock-screen texts in the person's language (set in the app). Still no health details.
PUSH_TEXT_I18N = {
    "hi": {
        "family_cascade": "एक रिश्तेदार ने स्वास्थ्य से जुड़ी ऐसी जानकारी साझा की है जो आप पर असर डाल सकती है।",
        "invitation_accepted": "एक रिश्तेदार ने आपका आमंत्रण स्वीकार कर लिया।",
        "referral": "आपकी देखभाल टीम ने आपके रेफ़रल में बदलाव किया है।",
        "documents_received": "आपके फ़ॉरवर्ड किए दस्तावेज़ जाँच के लिए तैयार हैं।",
        "booking": "आपकी टेस्ट बुकिंग के बारे में नई जानकारी है।",
        "reminder": "एक स्वास्थ्य जाँच अभी बाकी है। बुक करने के लिए ऐप खोलें।",
        "care": "जिनकी आप देखभाल करते हैं, उनके बारे में नई जानकारी है।",
        "risk": "आपके जेनेटिक काउंसलर ने आपके नतीजे साझा किए हैं।",
        "privacy": "आपके गोपनीयता सवाल का जवाब आ गया है।",
        "security": "आपके खाते के बारे में ज़रूरी सुरक्षा सूचना।",
        "_default": "आपके लिए नई जानकारी है।",
    },
    "mr": {
        "family_cascade": "एका नातेवाइकाने तुमच्यावर परिणाम करू शकेल अशी आरोग्याशी संबंधित माहिती शेअर केली आहे.",
        "invitation_accepted": "एका नातेवाइकाने तुमचे आमंत्रण स्वीकारले.",
        "referral": "तुमच्या काळजी टीमने तुमच्या रेफरलमध्ये बदल केला आहे.",
        "documents_received": "तुम्ही फॉरवर्ड केलेली कागदपत्रे तपासणीसाठी तयार आहेत.",
        "booking": "तुमच्या चाचणी बुकिंगबद्दल नवीन माहिती आहे.",
        "reminder": "एक आरोग्य तपासणी अजून बाकी आहे. बुक करण्यासाठी अ‍ॅप उघडा.",
        "care": "तुम्ही ज्यांची काळजी घेता, त्यांच्याबद्दल नवीन माहिती आहे.",
        "risk": "तुमच्या जेनेटिक काउन्सेलरने तुमचे निकाल शेअर केले आहेत.",
        "privacy": "तुमच्या गोपनीयतेच्या प्रश्नाचे उत्तर आले आहे.",
        "security": "तुमच्या खात्याबद्दल महत्त्वाची सुरक्षा सूचना.",
        "_default": "तुमच्यासाठी नवीन माहिती आहे.",
    },
}


def push_text(kind: str, lang: str = "en") -> str:
    table = PUSH_TEXT_I18N.get(lang)
    if table:
        return table.get(kind, table["_default"])
    return PUSH_TEXT.get(kind, DEFAULT_TEXT)


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

    def notify(self, user_id: str, kind: str, message: str, url: Optional[str] = None) -> None:
        self.store.notify(user_id, kind, message)
        tokens = self.store.push_tokens_for(user_id)
        if not tokens:
            return
        target = url or PUSH_URL.get(kind, "/")
        lang = self.store.user_lang(user_id) if hasattr(self.store, "user_lang") else "en"
        if self._pool:
            self._pool.submit(self._push, tokens, kind, target, lang)  # don't make the request wait on Expo
        else:
            self._push(tokens, kind, target, lang)

    def _push(self, tokens: list[str], kind: str, url: str = "/", lang: str = "en") -> None:
        body = push_text(kind, lang)
        messages = [PushMessage(t, TITLE, body, {"kind": kind, "url": url}) for t in tokens]
        try:
            invalid = self.sender.send(messages)
            if invalid:
                self.store.remove_push_tokens(invalid)
        except Exception:
            log.exception("sending push notifications failed")
