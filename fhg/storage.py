"""Persistence: SQLite with encrypted health data, provenance, consent and audit.

Health data (profiles and raw ingested documents) is encrypted before it is
written. Metadata needed to operate the service (user IDs, consent scopes,
audit events) is stored in the clear so it can be queried and reviewed.
Swap SQLite for Postgres in production; the interface stays the same.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import HealthProfile
from .security import FieldCipher, hash_token, new_token

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
-- One row per signed-in device. Only a hash of the bearer token is stored.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device TEXT,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
-- Ways to sign in to an account. For email, `subject` is a keyed hash of the
-- address (so it can be looked up) and `email` holds it encrypted for display.
CREATE TABLE IF NOT EXISTS identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email BLOB,
    created_at TEXT NOT NULL,
    PRIMARY KEY (provider, subject)
);
CREATE INDEX IF NOT EXISTS idx_identities_user ON identities(user_id);
-- Push tokens belong to a session, so signing a device out stops its pushes.
CREATE TABLE IF NOT EXISTS push_devices (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    platform TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_user ON push_devices(user_id);
-- Clinics and other care organisations (B2B). Patients connect with a code and
-- can disconnect at any time; staff see only connected patients.
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    patient_code TEXT NOT NULL UNIQUE,
    staff_code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS org_staff (
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (org_id, user_id)
);
CREATE TABLE IF NOT EXISTS org_patients (
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display BLOB NOT NULL,          -- encrypted name the patient chose to show the clinic
    connected_at TEXT NOT NULL,
    PRIMARY KEY (org_id, user_id)
);
CREATE TABLE IF NOT EXISTS login_codes (
    id TEXT PRIMARY KEY,
    email_key TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_codes_email ON login_codes(email_key);
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingest_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    raw BLOB NOT NULL,
    summary TEXT NOT NULL,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consents (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope TEXT NOT NULL,
    granted_at TEXT,
    revoked_at TEXT,
    PRIMARY KEY (user_id, scope)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
CREATE TABLE IF NOT EXISTS invitations (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    inviter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,       -- what the invitee is to the inviter
    member_id TEXT,                   -- inviter's existing record for this relative
    inviter_share TEXT NOT NULL,      -- what the inviter will share once linked
    details BLOB NOT NULL,            -- encrypted {inviter_name, message}
    status TEXT NOT NULL,             -- pending | accepted | declined | revoked
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    responded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_inviter ON invitations(inviter_id);
-- One row per direction: owner sees relative as `relationship` and shares
-- `share_level` of their own data with them.
CREATE TABLE IF NOT EXISTS family_links (
    link_id TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    relative_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL,
    member_id TEXT,
    share_level TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (link_id, owner_id)
);
CREATE INDEX IF NOT EXISTS idx_links_owner ON family_links(owner_id);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    message BLOB NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    SESSION_DAYS = 90  # sliding: extended whenever the session is used

    def __init__(self, path: str | Path, cipher: FieldCipher):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._cipher = cipher
        self._lock = threading.RLock()
        self._migrate_legacy_tokens()

    def _migrate_legacy_tokens(self) -> None:
        """Databases from before sessions existed kept one token per user on the
        users table. Move those tokens into sessions so existing devices stay
        signed in, and remember to fill the old NOT NULL column on insert."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(users)")}
        self._legacy_users = "token_hash" in cols
        if not self._legacy_users:
            return
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(days=self.SESSION_DAYS)).isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions (id, token_hash, user_id, device, created_at, last_used_at, expires_at) "
                "SELECT 'legacy-' || id, token_hash, id, 'migrated', created_at, ?, ? FROM users "
                "WHERE token_hash NOT LIKE 'unused-%'", (now.isoformat(), expires))

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        # One connection is shared across worker threads, so reads take the lock too.
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # --- users -------------------------------------------------------------
    def create_user(self, device: Optional[str] = None) -> tuple[str, str]:
        """Create an account and a first session; returns (user_id, token)."""
        user_id = uuid.uuid4().hex
        with self._lock, self._conn:
            if self._legacy_users:
                self._conn.execute("INSERT INTO users (id, token_hash, created_at) VALUES (?, ?, ?)",
                                   (user_id, f"unused-{uuid.uuid4().hex}", _now()))
            else:
                self._conn.execute("INSERT INTO users (id, created_at) VALUES (?, ?)", (user_id, _now()))
        self.save_profile(HealthProfile(user_id=user_id))
        self.audit(user_id, "user", "account.created")
        _, token = self.create_session(user_id, device)
        return user_id, token

    # --- sessions ------------------------------------------------------------
    def create_session(self, user_id: str, device: Optional[str] = None) -> tuple[str, str]:
        session_id, token = uuid.uuid4().hex[:16], new_token()
        now = datetime.now(timezone.utc)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, token_hash, user_id, device, created_at, last_used_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, hash_token(token), user_id, (device or "")[:80] or None, now.isoformat(),
                 now.isoformat(), (now + timedelta(days=self.SESSION_DAYS)).isoformat()))
        self.audit(user_id, "user", "session.created", {"session_id": session_id, "device": device})
        return session_id, token

    def session_for_token(self, token: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM sessions WHERE token_hash = ?", (hash_token(token),))
        if not rows:
            return None
        row = rows[0]
        now = datetime.now(timezone.utc)
        if datetime.fromisoformat(row["expires_at"]) < now:
            return None
        # Slide the expiry, at most once an hour to avoid a write per request.
        if now - datetime.fromisoformat(row["last_used_at"]) > timedelta(hours=1):
            with self._lock, self._conn:
                self._conn.execute("UPDATE sessions SET last_used_at = ?, expires_at = ? WHERE id = ?",
                                   (now.isoformat(), (now + timedelta(days=self.SESSION_DAYS)).isoformat(),
                                    row["id"]))
        return {"id": row["id"], "user_id": row["user_id"]}

    def user_for_token(self, token: str) -> Optional[str]:
        session = self.session_for_token(token)
        return session["user_id"] if session else None

    def sessions_for(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT id, device, created_at, last_used_at, expires_at FROM sessions "
                           "WHERE user_id = ? AND expires_at > ? ORDER BY last_used_at DESC",
                           (user_id, _now()))
        return [dict(r) for r in rows]

    def revoke_session(self, user_id: str, session_id: str) -> bool:
        with self._lock, self._conn:
            n = self._conn.execute("DELETE FROM sessions WHERE id = ? AND user_id = ?",
                                   (session_id, user_id)).rowcount
        if n:
            self.audit(user_id, "user", "session.revoked", {"session_id": session_id})
        return n == 1

    # --- organisations (clinic portal) --------------------------------------------------
    @staticmethod
    def _join_code() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
        raw = "".join(secrets.choice(alphabet) for _ in range(8))
        return f"{raw[:4]}-{raw[4:]}"

    def create_org(self, name: str, admin_user_id: str) -> dict:
        org_id, now = uuid.uuid4().hex[:12], _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO organizations (id, name, patient_code, staff_code, created_at) VALUES (?, ?, ?, ?, ?)",
                (org_id, name, self._join_code(), self._join_code(), now))
            self._conn.execute("INSERT INTO org_staff (org_id, user_id, role, created_at) VALUES (?, ?, 'admin', ?)",
                               (org_id, admin_user_id, now))
        self.audit(admin_user_id, "user", "org.created", {"org_id": org_id})
        return self.org(org_id)

    def org(self, org_id: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM organizations WHERE id = ?", (org_id,))
        return dict(rows[0]) if rows else None

    def org_by_code(self, kind: str, code: str) -> Optional[dict]:
        column = {"patient": "patient_code", "staff": "staff_code"}[kind]
        rows = self._query(f"SELECT * FROM organizations WHERE {column} = ?", (code.strip().upper(),))
        return dict(rows[0]) if rows else None

    def add_staff(self, org_id: str, user_id: str, role: str = "clinician") -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO org_staff (org_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
                               (org_id, user_id, role, _now()))

    def staff_role(self, org_id: str, user_id: str) -> Optional[str]:
        rows = self._query("SELECT role FROM org_staff WHERE org_id = ? AND user_id = ?", (org_id, user_id))
        return rows[0]["role"] if rows else None

    def orgs_for_staff(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT o.*, s.role FROM organizations o JOIN org_staff s ON s.org_id = o.id "
                           "WHERE s.user_id = ? ORDER BY o.created_at", (user_id,))
        return [dict(r) for r in rows]

    def connect_patient(self, org_id: str, user_id: str, display: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO org_patients (org_id, user_id, display, connected_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(org_id, user_id) DO UPDATE SET display = excluded.display",
                (org_id, user_id, self._cipher.encrypt(display), _now()))

    def disconnect_patient(self, org_id: str, user_id: str) -> bool:
        with self._lock, self._conn:
            return self._conn.execute("DELETE FROM org_patients WHERE org_id = ? AND user_id = ?",
                                      (org_id, user_id)).rowcount == 1

    def org_patients(self, org_id: str) -> list[dict]:
        rows = self._query("SELECT user_id, display, connected_at FROM org_patients WHERE org_id = ? "
                           "ORDER BY connected_at", (org_id,))
        return [{"user_id": r["user_id"], "display": self._cipher.decrypt(r["display"]),
                 "connected_at": r["connected_at"]} for r in rows]

    def orgs_for_patient(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT o.id, o.name, p.connected_at FROM org_patients p JOIN organizations o "
                           "ON o.id = p.org_id WHERE p.user_id = ? ORDER BY p.connected_at", (user_id,))
        return [dict(r) for r in rows]

    # --- push devices --------------------------------------------------------------
    def register_push_token(self, token: str, user_id: str, session_id: str, platform: Optional[str]) -> None:
        """A token identifies one app install; if another account registered it
        before (e.g. someone else signed in on this phone), it moves here."""
        now = _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO push_devices (token, user_id, session_id, platform, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(token) DO UPDATE SET user_id = excluded.user_id, "
                "session_id = excluded.session_id, platform = excluded.platform, updated_at = excluded.updated_at",
                (token, user_id, session_id, platform, now, now))

    def push_tokens_for(self, user_id: str) -> list[str]:
        return [r["token"] for r in self._query("SELECT token FROM push_devices WHERE user_id = ?", (user_id,))]

    def push_registered(self, session_id: str) -> bool:
        return bool(self._query("SELECT 1 FROM push_devices WHERE session_id = ?", (session_id,)))

    def unregister_push_for_session(self, session_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM push_devices WHERE session_id = ?", (session_id,))

    def remove_push_tokens(self, tokens: list[str]) -> None:
        with self._lock, self._conn:
            self._conn.executemany("DELETE FROM push_devices WHERE token = ?", [(t,) for t in tokens])

    # --- sign-in identities ----------------------------------------------------
    def user_for_identity(self, provider: str, subject: str) -> Optional[str]:
        rows = self._query("SELECT user_id FROM identities WHERE provider = ? AND subject = ?",
                           (provider, subject))
        return rows[0]["user_id"] if rows else None

    def add_identity(self, user_id: str, provider: str, subject: str, email: Optional[str]) -> bool:
        """Attach a sign-in method; False if it already belongs to an account."""
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT INTO identities (provider, subject, user_id, email, created_at) VALUES (?, ?, ?, ?, ?)",
                    (provider, subject, user_id, self._cipher.encrypt(email) if email else None, _now()))
        except sqlite3.IntegrityError:
            return False
        self.audit(user_id, "user", "identity.added", {"provider": provider})
        return True

    def identities_for(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT provider, email, created_at FROM identities WHERE user_id = ? "
                           "ORDER BY created_at", (user_id,))
        return [{"provider": r["provider"],
                 "email": self._cipher.decrypt(r["email"]) if r["email"] else None,
                 "created_at": r["created_at"]} for r in rows]

    # --- one-time email codes ---------------------------------------------------
    def create_login_code(self, email_key: str, code_hash: str, ttl_minutes: int) -> None:
        now = datetime.now(timezone.utc)
        with self._lock, self._conn:
            # A new code replaces any earlier unused one.
            self._conn.execute("UPDATE login_codes SET consumed_at = ? WHERE email_key = ? AND consumed_at IS NULL",
                               (now.isoformat(), email_key))
            self._conn.execute(
                "INSERT INTO login_codes (id, email_key, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, email_key, code_hash, now.isoformat(),
                 (now + timedelta(minutes=ttl_minutes)).isoformat()))

    def login_codes_since(self, email_key: str, since: datetime) -> int:
        rows = self._query("SELECT COUNT(*) AS n FROM login_codes WHERE email_key = ? AND created_at > ?",
                           (email_key, since.isoformat()))
        return rows[0]["n"]

    def active_login_code(self, email_key: str) -> Optional[dict]:
        rows = self._query("SELECT id, code_hash, attempts, expires_at FROM login_codes "
                           "WHERE email_key = ? AND consumed_at IS NULL ORDER BY created_at DESC LIMIT 1",
                           (email_key,))
        if not rows or datetime.fromisoformat(rows[0]["expires_at"]) < datetime.now(timezone.utc):
            return None
        return dict(rows[0])

    def record_code_attempt(self, code_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?", (code_id,))

    def consume_login_code(self, code_id: str) -> bool:
        """Single use: only one concurrent request can consume a code."""
        with self._lock, self._conn:
            return self._conn.execute(
                "UPDATE login_codes SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL",
                (_now(), code_id)).rowcount == 1

    @property
    def write_lock(self) -> threading.RLock:
        """Hold while doing read-modify-write on a profile so concurrent
        requests can't overwrite each other's changes (single-process only;
        use row versioning / SELECT ... FOR UPDATE with Postgres)."""
        return self._lock

    # --- profiles ----------------------------------------------------------
    def get_profile(self, user_id: str) -> HealthProfile:
        row = next(iter(self._query("SELECT data FROM profiles WHERE user_id = ?", (user_id,))), None)
        if not row:
            return HealthProfile(user_id=user_id)
        return HealthProfile.model_validate_json(self._cipher.decrypt(row["data"]))

    def save_profile(self, profile: HealthProfile) -> None:
        blob = self._cipher.encrypt(profile.model_dump_json())
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO profiles (user_id, data, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                (profile.user_id, blob, _now()),
            )

    # --- provenance --------------------------------------------------------
    def record_ingest(self, user_id: str, source_type: str, raw: str, summary: dict) -> str:
        event_id = uuid.uuid4().hex
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ingest_events (id, user_id, source_type, raw, summary, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, user_id, source_type, self._cipher.encrypt(raw), json.dumps(summary), _now()),
            )
        return event_id

    def list_ingests(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT id, source_type, summary, received_at FROM ingest_events "
            "WHERE user_id = ? ORDER BY received_at", (user_id,))
        return [{"id": r["id"], "source_type": r["source_type"],
                 "summary": json.loads(r["summary"]), "received_at": r["received_at"]} for r in rows]

    # --- consent -----------------------------------------------------------
    def set_consent(self, user_id: str, scope: str, granted: bool) -> None:
        now = _now()
        with self._lock, self._conn:
            if granted:
                self._conn.execute(
                    "INSERT INTO consents (user_id, scope, granted_at, revoked_at) VALUES (?, ?, ?, NULL) "
                    "ON CONFLICT(user_id, scope) DO UPDATE SET granted_at = excluded.granted_at, revoked_at = NULL",
                    (user_id, scope, now),
                )
            else:
                self._conn.execute(
                    "UPDATE consents SET revoked_at = ? WHERE user_id = ? AND scope = ?",
                    (now, user_id, scope),
                )

    def consents(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT scope, granted_at, revoked_at FROM consents WHERE user_id = ? ORDER BY scope", (user_id,))
        return [dict(r) | {"active": r["revoked_at"] is None} for r in rows]

    def has_consent(self, user_id: str, scope: str) -> bool:
        row = next(iter(self._query("SELECT 1 FROM consents WHERE user_id = ? AND scope = ? AND revoked_at IS NULL", (user_id, scope))), None)
        return row is not None

    def users_with_consent(self, scope: str) -> list[str]:
        rows = self._query("SELECT user_id FROM consents WHERE scope = ? AND revoked_at IS NULL", (scope,))
        return [r["user_id"] for r in rows]

    # --- audit -------------------------------------------------------------
    def audit(self, user_id: str, actor: str, action: str, detail: Optional[dict] = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO audit_log (user_id, actor, action, detail, ts) VALUES (?, ?, ?, ?, ?)",
                (user_id, actor, action, json.dumps(detail or {}), _now()),
            )

    def audit_log(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT actor, action, detail, ts FROM audit_log WHERE user_id = ? ORDER BY id", (user_id,))
        return [{"actor": r["actor"], "action": r["action"],
                 "detail": json.loads(r["detail"] or "{}"), "ts": r["ts"]} for r in rows]

    # --- invitations --------------------------------------------------------
    def create_invitation(self, inviter_id: str, relationship: str, member_id: Optional[str],
                          inviter_share: str, inviter_name: Optional[str],
                          message: Optional[str], ttl_days: int = 14) -> tuple[dict, str]:
        inv_id, token = uuid.uuid4().hex[:16], new_token()
        now = datetime.now(timezone.utc)
        details = self._cipher.encrypt(json.dumps({"inviter_name": inviter_name, "message": message}))
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO invitations (id, token_hash, inviter_id, relationship, member_id, "
                "inviter_share, details, status, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                (inv_id, hash_token(token), inviter_id, relationship, member_id, inviter_share,
                 details, now.isoformat(), (now + timedelta(days=ttl_days)).isoformat()),
            )
        return self._invitation(inv_id), token

    def _row_to_invitation(self, r: sqlite3.Row) -> dict:
        details = json.loads(self._cipher.decrypt(r["details"]))
        status = r["status"]
        if status == "pending" and datetime.fromisoformat(r["expires_at"]) < datetime.now(timezone.utc):
            status = "expired"
        return {"id": r["id"], "inviter_id": r["inviter_id"], "relationship": r["relationship"],
                "member_id": r["member_id"], "inviter_share": r["inviter_share"],
                "inviter_name": details.get("inviter_name"), "message": details.get("message"),
                "status": status, "created_at": r["created_at"], "expires_at": r["expires_at"],
                "responded_at": r["responded_at"]}

    def _invitation(self, inv_id: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM invitations WHERE id = ?", (inv_id,))
        return self._row_to_invitation(rows[0]) if rows else None

    def invitation_by_token(self, token: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM invitations WHERE token_hash = ?", (hash_token(token),))
        return self._row_to_invitation(rows[0]) if rows else None

    def invitations_for(self, inviter_id: str) -> list[dict]:
        rows = self._query("SELECT * FROM invitations WHERE inviter_id = ? ORDER BY created_at DESC",
                           (inviter_id,))
        return [self._row_to_invitation(r) for r in rows]

    def set_invitation_status(self, inv_id: str, status: str, only_if_pending: bool = True) -> bool:
        sql = "UPDATE invitations SET status = ?, responded_at = ? WHERE id = ?"
        if only_if_pending:
            sql += " AND status = 'pending'"
        with self._lock, self._conn:
            return self._conn.execute(sql, (status, _now(), inv_id)).rowcount == 1

    # --- family links -------------------------------------------------------------
    def create_link(self, a: str, b: str, *, b_to_a: str, a_member_id: Optional[str], a_share: str,
                    a_to_b: str, b_member_id: Optional[str], b_share: str) -> str:
        """Link users a and b. ``b_to_a`` is what b is to a (as a sees it)."""
        link_id, now = uuid.uuid4().hex[:16], _now()
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT INTO family_links (link_id, owner_id, relative_id, relationship, member_id, "
                "share_level, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(link_id, a, b, b_to_a, a_member_id, a_share, now),
                 (link_id, b, a, a_to_b, b_member_id, b_share, now)],
            )
        return link_id

    def links_for(self, owner_id: str) -> list[dict]:
        """Each link as seen by ``owner_id``, including what the other side shares."""
        rows = self._query(
            "SELECT mine.link_id, mine.relative_id, mine.relationship, mine.member_id, "
            "mine.share_level AS i_share, theirs.share_level AS they_share, "
            "theirs.relationship AS i_am, mine.created_at "
            "FROM family_links mine JOIN family_links theirs "
            "ON theirs.link_id = mine.link_id AND theirs.owner_id = mine.relative_id "
            "WHERE mine.owner_id = ? ORDER BY mine.created_at", (owner_id,))
        return [dict(r) for r in rows]

    def are_linked(self, a: str, b: str) -> bool:
        return bool(self._query("SELECT 1 FROM family_links WHERE owner_id = ? AND relative_id = ?", (a, b)))

    def set_share_level(self, link_id: str, owner_id: str, level: str) -> bool:
        with self._lock, self._conn:
            return self._conn.execute(
                "UPDATE family_links SET share_level = ? WHERE link_id = ? AND owner_id = ?",
                (level, link_id, owner_id)).rowcount == 1

    def delete_link(self, link_id: str, owner_id: str) -> bool:
        with self._lock, self._conn:
            if not self._conn.execute("SELECT 1 FROM family_links WHERE link_id = ? AND owner_id = ?",
                                      (link_id, owner_id)).fetchone():
                return False
            self._conn.execute("DELETE FROM family_links WHERE link_id = ?", (link_id,))
        return True

    # --- notifications ------------------------------------------------------------
    def notify(self, user_id: str, kind: str, message: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO notifications (user_id, kind, message, created_at) VALUES (?, ?, ?, ?)",
                (user_id, kind, self._cipher.encrypt(message), _now()))

    def notifications(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT id, kind, message, created_at, read_at FROM notifications "
                           "WHERE user_id = ? ORDER BY id DESC", (user_id,))
        return [{"id": r["id"], "kind": r["kind"], "message": self._cipher.decrypt(r["message"]),
                 "created_at": r["created_at"], "read": r["read_at"] is not None} for r in rows]

    def mark_notifications_read(self, user_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                               (_now(), user_id))

    # --- deletion ----------------------------------------------------------
    def delete_user(self, user_id: str) -> None:
        """Erase all health data and credentials. The audit trail is retained
        (it contains no health data) as evidence the deletion happened."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.audit(user_id, "user", "account.deleted")
