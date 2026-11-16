"""Persistence: SQLite with encrypted health data, provenance, consent and audit.

Health data (profiles and raw ingested documents) is encrypted before it is
written. Metadata needed to operate the service (user IDs, consent scopes,
audit events) is stored in the clear so it can be queried and reviewed.
Swap SQLite for Postgres in production; the interface stays the same.
"""
from __future__ import annotations

import json
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
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
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
    def __init__(self, path: str | Path, cipher: FieldCipher):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._cipher = cipher
        self._lock = threading.RLock()

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        # One connection is shared across worker threads, so reads take the lock too.
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # --- users -------------------------------------------------------------
    def create_user(self) -> tuple[str, str]:
        user_id, token = uuid.uuid4().hex, new_token()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO users (id, token_hash, created_at) VALUES (?, ?, ?)",
                (user_id, hash_token(token), _now()),
            )
        self.save_profile(HealthProfile(user_id=user_id))
        self.audit(user_id, "user", "account.created")
        return user_id, token

    def user_for_token(self, token: str) -> Optional[str]:
        rows = self._query("SELECT id FROM users WHERE token_hash = ?", (hash_token(token),))
        return rows[0]["id"] if rows else None

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
