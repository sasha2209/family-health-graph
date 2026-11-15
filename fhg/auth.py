"""Sign-in: one-time email codes and Sign in with Apple / Google.

Accounts can start anonymous (a device token only) so people can try the app
with zero friction, then add an email or Apple/Google identity to secure the
account and sign in on other devices. Every sign-in creates a separate,
revocable, expiring session (see storage.py).

Design notes
* Email addresses are never stored in the clear: lookups use a keyed HMAC of
  the normalised address and the address itself is stored encrypted.
* Codes are 6 digits, expire after 10 minutes, are single use, allow 5 wrong
  attempts, and each address can request at most 5 per hour.
* "Send me a code" always responds the same way, so it doesn't reveal whether
  an address has an account.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable, Optional, Protocol

import jwt

log = logging.getLogger(__name__)

CODE_TTL_MINUTES = 10
MAX_CODES_PER_HOUR = 5
MAX_CODE_ATTEMPTS = 5

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise AuthError(422, "Enter a valid email address")
    return email


def email_key(secret: str, email: str) -> str:
    return hmac.new(secret.encode(), b"email:" + email.encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def code_hash(secret: str, key: str, code: str) -> str:
    return hmac.new(secret.encode(), f"code:{key}:{code}".encode(), hashlib.sha256).hexdigest()


# --- email delivery -------------------------------------------------------------------

class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleEmailSender:
    """Development: print the email to the server log instead of sending it."""

    def send(self, to: str, subject: str, body: str) -> None:
        log.warning("DEV EMAIL to %s | %s\n%s", to, subject, body)


@dataclass
class SmtpEmailSender:
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    sender: str

    @classmethod
    def from_env(cls) -> "SmtpEmailSender":
        return cls(
            host=os.environ["FHG_SMTP_HOST"],
            port=int(os.environ.get("FHG_SMTP_PORT", "587")),
            username=os.environ.get("FHG_SMTP_USERNAME"),
            password=os.environ.get("FHG_SMTP_PASSWORD"),
            sender=os.environ["FHG_EMAIL_FROM"],
        )

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password or "")
            smtp.send_message(msg)


def email_sender_from_env() -> EmailSender:
    if os.environ.get("FHG_EMAIL_BACKEND", "console") == "smtp":
        return SmtpEmailSender.from_env()
    return ConsoleEmailSender()


def code_email(code: str) -> tuple[str, str]:
    # Deliberately generic: no health information, nothing about the account.
    return (
        f"Your Family Health Graph sign-in code: {code}",
        f"Your sign-in code is {code}\n\n"
        f"It expires in {CODE_TTL_MINUTES} minutes. If you didn't ask for it, you can ignore this email.\n",
    )


# --- Sign in with Apple / Google --------------------------------------------------------

@dataclass(frozen=True)
class OidcProvider:
    name: str
    issuers: frozenset[str]
    jwks_url: str


PROVIDERS = {
    "apple": OidcProvider("apple", frozenset({"https://appleid.apple.com"}),
                          "https://appleid.apple.com/auth/keys"),
    "google": OidcProvider("google", frozenset({"https://accounts.google.com", "accounts.google.com"}),
                           "https://www.googleapis.com/oauth2/v3/certs"),
}

# (provider, raw token) -> verification key. Injected in tests; defaults to the
# provider's published JWKS (cached by PyJWKClient).
KeyResolver = Callable[[OidcProvider, str], object]
_jwk_clients: dict[str, jwt.PyJWKClient] = {}


def _default_key_resolver(provider: OidcProvider, token: str) -> object:
    client = _jwk_clients.setdefault(provider.name, jwt.PyJWKClient(provider.jwks_url, cache_keys=True))
    return client.get_signing_key_from_jwt(token).key


def verify_id_token(provider_name: str, token: str, audiences: tuple[str, ...],
                    nonce: Optional[str] = None,
                    key_resolver: Optional[KeyResolver] = None) -> tuple[str, Optional[str]]:
    """Verify an OpenID Connect ID token; returns (subject, verified email or None)."""
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise AuthError(404, "Unknown sign-in provider")
    if not audiences:
        raise AuthError(404, f"Sign in with {provider_name.capitalize()} is not configured on this server")
    try:
        key = (key_resolver or _default_key_resolver)(provider, token)
        claims = jwt.decode(token, key=key, algorithms=["RS256", "ES256"], audience=list(audiences),
                            options={"require": ["exp", "iat", "iss", "sub", "aud"]}, leeway=60)
    except jwt.PyJWTError as exc:
        raise AuthError(401, f"Invalid sign-in token ({exc.__class__.__name__})") from exc
    if claims.get("iss") not in provider.issuers:
        raise AuthError(401, "Invalid sign-in token (issuer)")
    if nonce is not None:
        # Apple puts the SHA-256 of the client's nonce in the token; accept either form.
        hashed = hashlib.sha256(nonce.encode()).hexdigest()
        if claims.get("nonce") not in (nonce, hashed):
            raise AuthError(401, "Invalid sign-in token (nonce)")
    email = claims.get("email")
    verified = claims.get("email_verified") in (True, "true")
    return str(claims["sub"]), (email if email and verified else None)
