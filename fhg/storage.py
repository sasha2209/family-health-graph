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
    source TEXT,                    -- how they joined: 'code' (typed in the app) or 'link' (intake link/QR)
    PRIMARY KEY (org_id, user_id)
);
-- Referral partners (e.g. genetic counseling, testing labs) vetted by the platform.
-- They authenticate with an API key (hash stored) and get signed, PHI-free webhooks.
CREATE TABLE IF NOT EXISTS partners (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE,
    webhook_url TEXT,
    webhook_secret BLOB,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
-- One referral per (clinic, patient, care program); every status change is an event.
CREATE TABLE IF NOT EXISTS referrals (
    id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (org_id, user_id, rule_id)
);
CREATE TABLE IF NOT EXISTS referral_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_id TEXT NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    note BLOB,                       -- encrypted free text
    by_user TEXT NOT NULL,
    at TEXT NOT NULL
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
-- Uploaded medical documents. The file, OCR text and extraction are encrypted.
-- subject: "self", or the relationship of a relative whose document this is.
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,             -- review | saved | discarded
    doc_type TEXT NOT NULL,
    doc_date TEXT,
    subject TEXT NOT NULL DEFAULT 'self',
    subject_member_id TEXT,           -- the relative's FamilyMember id when subject isn't "self"
    filename TEXT,
    media_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    file BLOB,
    text BLOB NOT NULL,
    extraction BLOB NOT NULL,
    method TEXT NOT NULL,             -- pdf_text | ocr | none
    ocr_confidence REAL,
    ai_model TEXT,
    ai_mode TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    saved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id, created_at);
-- Tests booked from an action item. Contact details are encrypted and shared only with the chosen partner.
CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    partner_id TEXT NOT NULL REFERENCES partners(id),
    rule_id TEXT,
    tests TEXT NOT NULL,              -- JSON list of test codes
    status TEXT NOT NULL,             -- requested | scheduled | sample_collected | completed | cancelled | completed_elsewhere
    preferred_date TEXT,
    slot TEXT,
    scheduled_for TEXT,
    contact BLOB NOT NULL,            -- encrypted JSON {name, phone, address, pincode}
    price_inr REAL,
    note BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_partner ON bookings(partner_id, status);
-- Risk figures a genetic counseling partner calculated (e.g. in CanRisk) and posted back. Encrypted.
CREATE TABLE IF NOT EXISTS risk_results (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    partner_id TEXT NOT NULL REFERENCES partners(id),
    referral_id TEXT,
    data BLOB NOT NULL,               -- encrypted JSON {model, predictions[], note}
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_results_user ON risk_results(user_id, created_at);
-- Caregiver mode. A care circle lets others (siblings) help look after a relative on the owner's record.
CREATE TABLE IF NOT EXISTS care_circle (
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    caregiver_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name BLOB,                        -- encrypted: what the caregiver is called ("Rahul")
    joined_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, member_id, caregiver_id)
);
CREATE INDEX IF NOT EXISTS idx_care_circle_caregiver ON care_circle(caregiver_id);
CREATE TABLE IF NOT EXISTS care_invites (
    token_hash TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS dose_log (
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    med_id TEXT NOT NULL,
    day TEXT NOT NULL,
    slot TEXT NOT NULL,
    status TEXT NOT NULL,             -- taken | skipped
    by_user TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (owner_id, member_id, med_id, day, slot)
);
-- Time-limited, revocable links to a relative's emergency summary (e.g. for a hospital or an ambulance crew).
CREATE TABLE IF NOT EXISTS emergency_links (
    token_hash TEXT PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    views INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
-- DPDP Act: a nominee to exercise the person's rights on death or incapacity (s.14), grievances (s.13), and the
-- register of personal data breaches with the notices sent (s.8(6)). Personal details are encrypted.
CREATE TABLE IF NOT EXISTS nominees (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grievances (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    message BLOB NOT NULL,
    status TEXT NOT NULL,             -- open | resolved
    response BLOB,
    created_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_grievances_status ON grievances(status, due_at);
CREATE TABLE IF NOT EXISTS breaches (
    id TEXT PRIMARY KEY,
    data BLOB NOT NULL,               -- encrypted JSON: what happened, data affected, measures, contact
    occurred_at TEXT,
    detected_at TEXT NOT NULL,
    affected INTEGER NOT NULL,
    board_intimated_at TEXT,
    board_report_at TEXT,
    created_at TEXT NOT NULL
);
-- Background jobs (fhg/scheduler.py): when each last ran, and how it went.
CREATE TABLE IF NOT EXISTS job_runs (
    name TEXT PRIMARY KEY,
    last_run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT
);
-- Optional pilot survey answers (fhg/pilot.py). Only reported in aggregate.
CREATE TABLE IF NOT EXISTS survey_answers (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    PRIMARY KEY (user_id, question)
);
-- Medicine reminders sent to the cared-for person's own WhatsApp (they opt in by replying YES).
CREATE TABLE IF NOT EXISTS care_whatsapp (
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL,
    phone_key TEXT NOT NULL,          -- keyed hash of the number, for routing replies
    phone BLOB NOT NULL,              -- encrypted
    lang TEXT NOT NULL,
    status TEXT NOT NULL,             -- invited | active | stopped
    set_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, member_id)
);
CREATE INDEX IF NOT EXISTS idx_care_whatsapp_key ON care_whatsapp(phone_key);
CREATE TABLE IF NOT EXISTS nudges (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nudges_user ON nudges(user_id);
-- Connect with Family Health Graph: OAuth for partners. A grant is the user's consent artefact.
CREATE TABLE IF NOT EXISTS oauth_grants (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    partner_id TEXT NOT NULL REFERENCES partners(id),
    scopes TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_grants_user ON oauth_grants(user_id);
CREATE TABLE IF NOT EXISTS oauth_codes (
    code_hash TEXT PRIMARY KEY,
    grant_id TEXT NOT NULL REFERENCES oauth_grants(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    code_challenge TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_tokens (
    token_hash TEXT PRIMARY KEY,
    grant_id TEXT NOT NULL REFERENCES oauth_grants(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,               -- access | refresh
    expires_at TEXT NOT NULL
);
-- Connected record sources (SMART on FHIR portals, ABDM). Tokens are encrypted.
CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,               -- smart | abdm
    provider TEXT NOT NULL,           -- provider id (smart) or HIP name (abdm)
    display_name TEXT NOT NULL,
    secret BLOB,                      -- encrypted JSON: tokens, patient id, consent ids
    status TEXT NOT NULL,             -- active | pending | revoked | error
    last_sync_at TEXT,
    last_sync_summary TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_connections_user ON connections(user_id);
-- Short-lived state for an OAuth sign-in or consent request in progress.
CREATE TABLE IF NOT EXISTS connect_states (
    state_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    data BLOB NOT NULL,
    expires_at TEXT NOT NULL
);
-- Forwarding channels: a private email address, and a linked WhatsApp number (stored as an HMAC for lookup
-- and encrypted for replies).
CREATE TABLE IF NOT EXISTS inbound_channels (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email_token TEXT UNIQUE,
    whatsapp_key TEXT UNIQUE,
    whatsapp_phone BLOB,
    link_code_hash TEXT,
    link_code_expires TEXT,
    lang TEXT,                        -- WhatsApp reply language (en, hi, bn, ta, te, mr)
    pending BLOB,                     -- encrypted: what a "1/2/3" reply would save
    updated_at TEXT NOT NULL
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
        self._add_column_if_missing("org_patients", "source", "TEXT")
        self._add_column_if_missing("referrals", "partner_id", "TEXT REFERENCES partners(id)")
        self._add_column_if_missing("documents", "subject_member_id", "TEXT")
        self._add_column_if_missing("documents", "source", "TEXT NOT NULL DEFAULT 'upload'")
        self._add_column_if_missing("partners", "redirect_uris", "TEXT")
        self._add_column_if_missing("inbound_channels", "lang", "TEXT")
        self._add_column_if_missing("inbound_channels", "pending", "BLOB")
        self._add_column_if_missing("partners", "client_secret_hash", "TEXT")
        self._add_column_if_missing("partners", "catalog", "TEXT")
        self._add_column_if_missing("users", "lang", "TEXT")
        self._add_column_if_missing("organizations", "lang", "TEXT")
        self._add_column_if_missing("organizations", "practice", "INTEGER NOT NULL DEFAULT 0")
        self._add_column_if_missing("users", "practice", "INTEGER NOT NULL DEFAULT 0")
        self._add_column_if_missing("consents", "version", "TEXT")   # which wording was agreed to (pilot study)

    def _add_column_if_missing(self, table: str, column: str, decl: str) -> None:
        cols = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            with self._conn:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

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

    # --- practice clinics (staff training; made-up patients) ---------------------------------
    def mark_practice(self, org_id: str, user_ids: list[str]) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE organizations SET practice = 1 WHERE id = ?", (org_id,))
            self._conn.executemany("UPDATE users SET practice = 1 WHERE id = ?", [(u,) for u in user_ids])

    def practice_orgs(self) -> list[dict]:
        rows = self._query("SELECT o.*, (SELECT COUNT(*) FROM org_patients p WHERE p.org_id = o.id) AS patients, "
                           "(SELECT COUNT(*) FROM org_staff s WHERE s.org_id = o.id) AS staff "
                           "FROM organizations o WHERE o.practice = 1 ORDER BY o.created_at")
        return [dict(r) for r in rows]

    def backdate_practice(self, org_id: str, user_id: str, days: int) -> None:
        """Make a practice patient look as if they connected, and their referrals last changed, ``days`` ago."""
        at = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock, self._conn:
            if not self._conn.execute("SELECT practice FROM organizations WHERE id = ?", (org_id,)).fetchone()["practice"]:
                raise ValueError("Only a practice clinic's patients can be backdated")
            self._conn.execute("UPDATE org_patients SET connected_at = ? WHERE org_id = ? AND user_id = ?",
                               (at, org_id, user_id))
            self._conn.execute("UPDATE referral_events SET at = ? WHERE referral_id IN "
                               "(SELECT id FROM referrals WHERE org_id = ? AND user_id = ?)", (at, org_id, user_id))
            self._conn.execute("UPDATE referrals SET created_at = ?, updated_at = ? WHERE org_id = ? AND user_id = ?",
                               (at, at, org_id, user_id))

    def delete_practice_org(self, org_id: str) -> int:
        """Deletes a practice clinic and its made-up patients (never a real account). Returns patients deleted."""
        with self._lock, self._conn:
            org = self._conn.execute("SELECT practice FROM organizations WHERE id = ?", (org_id,)).fetchone()
            if org is None or not org["practice"]:
                return -1
            users = [r["user_id"] for r in self._conn.execute(
                "SELECT p.user_id FROM org_patients p JOIN users u ON u.id = p.user_id "
                "WHERE p.org_id = ? AND u.practice = 1", (org_id,))]
            self._conn.executemany("DELETE FROM users WHERE id = ? AND practice = 1", [(u,) for u in users])
            self._conn.execute("DELETE FROM organizations WHERE id = ? AND practice = 1", (org_id,))
        return len(users)

    def set_org_lang(self, org_id: str, lang: str) -> None:
        """The second language (after English) on the clinic's poster, staff guide and intake page."""
        with self._lock, self._conn:
            self._conn.execute("UPDATE organizations SET lang = ? WHERE id = ?", (lang, org_id))

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

    def connect_patient(self, org_id: str, user_id: str, display: str, source: str = "code") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO org_patients (org_id, user_id, display, connected_at, source) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(org_id, user_id) DO UPDATE SET display = excluded.display",
                (org_id, user_id, self._cipher.encrypt(display), _now(), source))

    def disconnect_patient(self, org_id: str, user_id: str) -> bool:
        """Removes the clinic's access, and its referrals for this patient."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM referrals WHERE org_id = ? AND user_id = ?", (org_id, user_id))
            return self._conn.execute("DELETE FROM org_patients WHERE org_id = ? AND user_id = ?",
                                      (org_id, user_id)).rowcount == 1

    # --- referrals --------------------------------------------------------------------
    _KEEP = object()

    def set_referral_status(self, org_id: str, user_id: str, rule_id: str, status: str,
                            by_user: str, note: Optional[str], partner_id=_KEEP) -> dict:
        """Create or update a referral. ``partner_id`` routes it to a referral
        partner (None = handled in-house); leave it out to keep the current one."""
        now = _now()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT id FROM referrals WHERE org_id = ? AND user_id = ? AND rule_id = ?",
                                     (org_id, user_id, rule_id)).fetchone()
            if row:
                ref_id = row["id"]
                self._conn.execute("UPDATE referrals SET status = ?, updated_at = ? WHERE id = ?",
                                   (status, now, ref_id))
            else:
                ref_id = uuid.uuid4().hex[:16]
                self._conn.execute(
                    "INSERT INTO referrals (id, org_id, user_id, rule_id, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)", (ref_id, org_id, user_id, rule_id, status, now, now))
            if partner_id is not Store._KEEP:
                self._conn.execute("UPDATE referrals SET partner_id = ? WHERE id = ?", (partner_id, ref_id))
            self._conn.execute(
                "INSERT INTO referral_events (referral_id, status, note, by_user, at) VALUES (?, ?, ?, ?, ?)",
                (ref_id, status, self._cipher.encrypt(note) if note else None, by_user, now))
        return self.referral(ref_id)

    def referral(self, ref_id: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM referrals WHERE id = ?", (ref_id,))
        if not rows:
            return None
        out = dict(rows[0])
        events = self._query("SELECT status, note, by_user, at FROM referral_events WHERE referral_id = ? ORDER BY id",
                             (ref_id,))
        out["history"] = [{"status": e["status"], "at": e["at"], "by_user": e["by_user"],
                           "note": self._cipher.decrypt(e["note"]) if e["note"] else None} for e in events]
        return out

    def referrals_for_org(self, org_id: str) -> list[dict]:
        refs = self._query("SELECT id FROM referrals WHERE org_id = ?", (org_id,))
        return [self.referral(r["id"]) for r in refs]

    def referrals_for_patient(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT r.rule_id, r.status, r.updated_at, o.name AS org_name, o.id AS org_id, "
                           "p.name AS partner_name FROM referrals r JOIN organizations o ON o.id = r.org_id "
                           "LEFT JOIN partners p ON p.id = r.partner_id WHERE r.user_id = ? "
                           "ORDER BY r.updated_at DESC", (user_id,))
        return [dict(r) for r in rows]

    # --- referral partners ------------------------------------------------------------
    def create_partner(self, name: str, kind: str, webhook_url: Optional[str]) -> tuple[dict, str, str]:
        """Returns (partner, api_key, webhook_secret); the key and secret are shown once."""
        partner_id, now = uuid.uuid4().hex[:12], _now()
        api_key, secret = "fhgp_" + new_token(), "whsec_" + new_token()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO partners (id, name, kind, api_key_hash, webhook_url, webhook_secret, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (partner_id, name, kind, hash_token(api_key), webhook_url, self._cipher.encrypt(secret), now))
        return self.partner(partner_id), api_key, secret

    def partner(self, partner_id: str) -> Optional[dict]:
        rows = self._query("SELECT id, name, kind, webhook_url, active, created_at FROM partners WHERE id = ?",
                           (partner_id,))
        return dict(rows[0]) if rows else None

    def partners(self, active_only: bool = True) -> list[dict]:
        rows = self._query("SELECT id, name, kind, webhook_url, active, created_at FROM partners "
                           + ("WHERE active = 1 " if active_only else "") + "ORDER BY name")
        return [dict(r) for r in rows]

    def partner_for_key(self, api_key: str) -> Optional[dict]:
        rows = self._query("SELECT id FROM partners WHERE api_key_hash = ? AND active = 1", (hash_token(api_key),))
        return self.partner(rows[0]["id"]) if rows else None

    # --- test bookings ----------------------------------------------------------
    def set_partner_catalog(self, partner_id: str, catalog: list[dict]) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE partners SET catalog = ? WHERE id = ?", (json.dumps(catalog), partner_id))

    def partners_with_catalog(self) -> list[dict]:
        rows = self._query("SELECT id, name, kind, catalog FROM partners WHERE active = 1 AND catalog IS NOT NULL")
        return [{"id": r["id"], "name": r["name"], "kind": r["kind"], "catalog": json.loads(r["catalog"])} for r in rows]

    def create_booking(self, user_id: str, partner_id: str, rule_id: Optional[str], tests: list[str],
                       preferred_date: Optional[str], slot: Optional[str], contact: dict, price_inr: Optional[float]) -> str:
        booking_id, now = uuid.uuid4().hex[:16], _now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO bookings (id, user_id, partner_id, rule_id, tests, status, preferred_date, slot, contact, "
                "price_inr, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'requested', ?, ?, ?, ?, ?, ?)",
                (booking_id, user_id, partner_id, rule_id, json.dumps(tests), preferred_date, slot,
                 self._cipher.encrypt(json.dumps(contact)), price_inr, now, now))
        return booking_id

    def _booking_row(self, r: sqlite3.Row, with_contact: bool) -> dict:
        out = {k: r[k] for k in ("id", "user_id", "partner_id", "rule_id", "status", "preferred_date", "slot",
                                 "scheduled_for", "price_inr", "created_at", "updated_at")}
        out["tests"] = json.loads(r["tests"])
        out["partner_name"] = r["partner_name"]
        out["note"] = self._cipher.decrypt(r["note"]) if r["note"] else None
        if with_contact:
            out["contact"] = json.loads(self._cipher.decrypt(r["contact"]))
        return out

    _BOOKING_SQL = "SELECT b.*, p.name AS partner_name FROM bookings b JOIN partners p ON p.id = b.partner_id "

    def booking(self, booking_id: str, with_contact: bool = False) -> Optional[dict]:
        rows = self._query(self._BOOKING_SQL + "WHERE b.id = ?", (booking_id,))
        return self._booking_row(rows[0], with_contact) if rows else None

    def bookings_for_user(self, user_id: str) -> list[dict]:
        rows = self._query(self._BOOKING_SQL + "WHERE b.user_id = ? ORDER BY b.created_at DESC", (user_id,))
        return [self._booking_row(r, False) for r in rows]

    def bookings_for_partner(self, partner_id: str, status: Optional[str] = None) -> list[dict]:
        sql, params = self._BOOKING_SQL + "WHERE b.partner_id = ?", [partner_id]
        if status:
            sql += " AND b.status = ?"
            params.append(status)
        rows = self._query(sql + " ORDER BY b.created_at DESC", tuple(params))
        return [self._booking_row(r, True) for r in rows]

    def update_booking(self, booking_id: str, *, status: str, scheduled_for: Optional[str] = None,
                       note: Optional[str] = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE bookings SET status = ?, scheduled_for = COALESCE(?, scheduled_for), "
                "note = COALESCE(?, note), updated_at = ? WHERE id = ?",
                (status, scheduled_for, self._cipher.encrypt(note) if note else None, _now(), booking_id))

    def booking_metrics(self) -> list[dict]:
        rows = self._query("SELECT p.name AS partner, b.status, COUNT(*) AS n, SUM(COALESCE(b.price_inr, 0)) AS value_inr "
                           "FROM bookings b JOIN partners p ON p.id = b.partner_id GROUP BY p.name, b.status ORDER BY p.name")
        return [dict(r) for r in rows]

    def add_risk_result(self, user_id: str, partner_id: str, referral_id: Optional[str], data: dict) -> str:
        rid = uuid.uuid4().hex[:16]
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO risk_results (id, user_id, partner_id, referral_id, data, created_at) "
                               "VALUES (?, ?, ?, ?, ?, ?)",
                               (rid, user_id, partner_id, referral_id, self._cipher.encrypt(json.dumps(data)), _now()))
        return rid

    def risk_results(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT r.*, p.name AS partner_name FROM risk_results r JOIN partners p ON p.id = r.partner_id "
                           "WHERE r.user_id = ? ORDER BY r.created_at DESC", (user_id,))
        return [{"id": r["id"], "partner_id": r["partner_id"], "partner_name": r["partner_name"],
                 "referral_id": r["referral_id"], "created_at": r["created_at"],
                 **json.loads(self._cipher.decrypt(r["data"]))} for r in rows]

    # --- pilot report -----------------------------------------------------------------------------
    def save_survey_answer(self, user_id: str, question: str, answer: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO survey_answers (user_id, question, answer, answered_at) "
                               "VALUES (?, ?, ?, ?)", (user_id, question, answer, _now()))

    def survey_answers(self, user_id: Optional[str] = None) -> list[dict]:
        sql, params = "SELECT user_id, question, answer, answered_at FROM survey_answers", ()
        if user_id:
            sql, params = sql + " WHERE user_id = ?", (user_id,)
        return [dict(r) for r in self._query(sql, params)]

    def users_overview(self) -> list[dict]:
        """Per account: when it was created and last used. For pilot metrics only."""
        rows = self._query("SELECT u.id, u.created_at, MAX(s.last_used_at) AS last_seen FROM users u "
                           "LEFT JOIN sessions s ON s.user_id = u.id WHERE u.practice = 0 GROUP BY u.id")
        return [dict(r) for r in rows]

    def all_bookings(self) -> list[dict]:
        return [self._booking_row(r, False) for r in self._query(self._BOOKING_SQL + "ORDER BY b.created_at")]

    def all_referrals(self) -> list[dict]:
        return [dict(r) for r in self._query("SELECT org_id, user_id, rule_id, status, created_at, updated_at FROM referrals")]

    def saved_document_users(self) -> set[str]:
        return {r["user_id"] for r in self._query("SELECT DISTINCT user_id FROM documents WHERE status = 'saved'")}

    def all_dose_logs(self, since: str) -> list[dict]:
        return [dict(r) for r in self._query("SELECT owner_id, member_id, med_id, day, slot, status FROM dose_log WHERE day >= ?",
                                             (since,))]

    # --- operations overview (admin console) -----------------------------------------------------
    def counts(self) -> dict:
        one = lambda sql, *p: self._query(sql, p)[0][0]  # noqa: E731
        return {
            "users": one("SELECT COUNT(*) FROM users WHERE practice = 0"),
            "documents": one("SELECT COUNT(*) FROM documents"),
            "care_circles": one("SELECT COUNT(DISTINCT owner_id || member_id) FROM care_circle"),
            "caregivers": one("SELECT COUNT(*) FROM care_circle"),
            "doses_logged_7d": one("SELECT COUNT(*) FROM dose_log WHERE at >= ?",
                                   (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()),
            "clinics": one("SELECT COUNT(*) FROM organizations WHERE practice = 0"),
            "practice_clinics": one("SELECT COUNT(*) FROM organizations WHERE practice = 1"),
            "partners_active": one("SELECT COUNT(*) FROM partners WHERE active = 1"),
            "grievances_open": one("SELECT COUNT(*) FROM grievances WHERE status = 'open'"),
            "grievances_overdue": one("SELECT COUNT(*) FROM grievances WHERE status = 'open' AND due_at < ?", _now()),
            "breaches": one("SELECT COUNT(*) FROM breaches"),
        }

    def partner_catalogs(self) -> dict[str, list]:
        return {r["id"]: json.loads(r["catalog"]) for r in self._query("SELECT id, catalog FROM partners WHERE catalog IS NOT NULL")}

    # --- language -------------------------------------------------------------------------------
    def set_user_lang(self, user_id: str, lang: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, user_id))

    def user_lang(self, user_id: str) -> str:
        rows = self._query("SELECT lang FROM users WHERE id = ?", (user_id,))
        return (rows[0]["lang"] if rows else None) or "en"

    # --- background jobs and backups -----------------------------------------------------------
    def job_run(self, name: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM job_runs WHERE name = ?", (name,))
        return dict(rows[0]) | {"detail": json.loads(rows[0]["detail"] or "{}")} if rows else None

    def job_runs(self) -> list[dict]:
        return [dict(r) | {"detail": json.loads(r["detail"] or "{}")} for r in self._query("SELECT * FROM job_runs ORDER BY name")]

    def record_job_run(self, name: str, at: str, status: str, detail: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO job_runs (name, last_run_at, status, detail) VALUES (?, ?, ?, ?)",
                               (name, at, status, json.dumps(detail, default=str)[:4000]))

    def backup(self, out_dir: str, key: str, keep: int, upload=None) -> dict:
        from .backup import make_backup
        with self._lock:
            return make_backup(self._conn, out_dir, key, keep, upload)

    def writable(self) -> bool:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO job_runs (name, last_run_at, status, detail) VALUES "
                               "('_health', ?, 'ok', NULL)", (_now(),))
        return True

    # --- privacy rights (DPDP Act) -------------------------------------------------------------
    def set_nominee(self, user_id: str, data: Optional[dict]) -> None:
        with self._lock, self._conn:
            if data is None:
                self._conn.execute("DELETE FROM nominees WHERE user_id = ?", (user_id,))
            else:
                self._conn.execute("INSERT OR REPLACE INTO nominees (user_id, data, updated_at) VALUES (?, ?, ?)",
                                   (user_id, self._cipher.encrypt(json.dumps(data)), _now()))

    def nominee(self, user_id: str) -> Optional[dict]:
        rows = self._query("SELECT data, updated_at FROM nominees WHERE user_id = ?", (user_id,))
        return json.loads(self._cipher.decrypt(rows[0]["data"])) | {"updated_at": rows[0]["updated_at"]} if rows else None

    def create_grievance(self, user_id: str, category: str, message: str, due_at: str) -> str:
        gid = uuid.uuid4().hex[:12]
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO grievances (id, user_id, category, message, status, created_at, due_at) "
                               "VALUES (?, ?, ?, ?, 'open', ?, ?)",
                               (gid, user_id, category, self._cipher.encrypt(message), _now(), due_at))
        return gid

    def _grievance(self, r: sqlite3.Row) -> dict:
        return {k: r[k] for k in ("id", "user_id", "category", "status", "created_at", "due_at", "resolved_at")} | {
            "message": self._cipher.decrypt(r["message"]),
            "response": self._cipher.decrypt(r["response"]) if r["response"] else None}

    def grievances(self, user_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        sql, params = "SELECT * FROM grievances WHERE 1=1", []
        if user_id:
            sql += " AND user_id = ?"; params.append(user_id)
        if status:
            sql += " AND status = ?"; params.append(status)
        return [self._grievance(r) for r in self._query(sql + " ORDER BY due_at", tuple(params))]

    def resolve_grievance(self, gid: str, response: str, status: str) -> Optional[dict]:
        with self._lock, self._conn:
            self._conn.execute("UPDATE grievances SET response = ?, status = ?, resolved_at = CASE WHEN ? = 'resolved' "
                               "THEN ? ELSE NULL END WHERE id = ?",
                               (self._cipher.encrypt(response), status, status, _now(), gid))
        rows = self._query("SELECT * FROM grievances WHERE id = ?", (gid,))
        return self._grievance(rows[0]) if rows else None

    def record_breach(self, data: dict, occurred_at: Optional[str], detected_at: str, affected: int) -> str:
        bid = uuid.uuid4().hex[:12]
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO breaches (id, data, occurred_at, detected_at, affected, created_at) "
                               "VALUES (?, ?, ?, ?, ?, ?)",
                               (bid, self._cipher.encrypt(json.dumps(data)), occurred_at, detected_at, affected, _now()))
        return bid

    def breaches(self) -> list[dict]:
        return [{k: r[k] for k in ("id", "occurred_at", "detected_at", "affected", "board_intimated_at", "board_report_at",
                                   "created_at")} | json.loads(self._cipher.decrypt(r["data"]))
                for r in self._query("SELECT * FROM breaches ORDER BY created_at DESC")]

    def mark_breach_board(self, bid: str, stage: str) -> bool:
        column = {"intimation": "board_intimated_at", "report": "board_report_at"}[stage]
        with self._lock, self._conn:
            cur = self._conn.execute(f"UPDATE breaches SET {column} = ? WHERE id = ?", (_now(), bid))
        return cur.rowcount > 0

    def housekeeping(self) -> dict:
        """Delete what has expired: sign-in codes, connect states, OAuth codes and tokens, care invites,
        emergency links (kept 30 days after expiry for the audit trail's context), and old reminder records."""
        now = _now()
        month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        out = {}
        with self._lock, self._conn:
            for table, where, params in [
                ("login_codes", "expires_at < ?", (now,)), ("connect_states", "expires_at < ?", (now,)),
                ("oauth_codes", "expires_at < ?", (now,)), ("oauth_tokens", "expires_at < ?", (now,)),
                ("care_invites", "expires_at < ? OR used_at IS NOT NULL", (now,)),
                ("emergency_links", "expires_at < ? OR revoked_at < ?", (month_ago, month_ago)),
                ("nudges", "sent_at < ?", (year_ago,)),
            ]:
                out[table] = self._conn.execute(f"DELETE FROM {table} WHERE {where}", params).rowcount
        return out

    # --- caregiver mode ---------------------------------------------------------------------
    def add_caregiver(self, owner_id: str, member_id: str, caregiver_id: str, name: Optional[str]) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO care_circle (owner_id, member_id, caregiver_id, name, joined_at) "
                               "VALUES (?, ?, ?, ?, ?)", (owner_id, member_id, caregiver_id,
                                                         self._cipher.encrypt(name) if name else None, _now()))

    def remove_caregiver(self, owner_id: str, member_id: str, caregiver_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM care_circle WHERE owner_id = ? AND member_id = ? AND caregiver_id = ?",
                                     (owner_id, member_id, caregiver_id))
        return cur.rowcount > 0

    def caregivers(self, owner_id: str, member_id: str) -> list[dict]:
        rows = self._query("SELECT caregiver_id, name, joined_at FROM care_circle WHERE owner_id = ? AND member_id = ? "
                           "ORDER BY joined_at", (owner_id, member_id))
        return [{"user_id": r["caregiver_id"], "name": self._cipher.decrypt(r["name"]) if r["name"] else None,
                 "joined_at": r["joined_at"]} for r in rows]

    def caring_for(self, caregiver_id: str) -> list[tuple[str, str]]:
        return [(r["owner_id"], r["member_id"]) for r in
                self._query("SELECT owner_id, member_id FROM care_circle WHERE caregiver_id = ?", (caregiver_id,))]

    def is_caregiver(self, owner_id: str, member_id: str, user_id: str) -> bool:
        return bool(self._query("SELECT 1 FROM care_circle WHERE owner_id = ? AND member_id = ? AND caregiver_id = ?",
                                (owner_id, member_id, user_id)))

    def set_care_whatsapp(self, owner_id: str, member_id: str, phone_key: str, phone: str, lang: str, status: str,
                          set_by: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO care_whatsapp VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (owner_id, member_id, phone_key, self._cipher.encrypt(phone), lang, status, set_by, _now()))

    def set_care_whatsapp_status(self, owner_id: str, member_id: str, status: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE care_whatsapp SET status = ?, updated_at = ? WHERE owner_id = ? AND member_id = ?",
                               (status, _now(), owner_id, member_id))

    def _care_wa(self, r: sqlite3.Row) -> dict:
        return {"owner_id": r["owner_id"], "member_id": r["member_id"], "phone": self._cipher.decrypt(r["phone"]),
                "lang": r["lang"], "status": r["status"], "updated_at": r["updated_at"]}

    def care_whatsapp(self, owner_id: str, member_id: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM care_whatsapp WHERE owner_id = ? AND member_id = ?", (owner_id, member_id))
        return self._care_wa(rows[0]) if rows else None

    def care_whatsapp_for_key(self, phone_key: str) -> list[dict]:
        """Everyone this number gets reminders for (one person, or a parent looked after by two families)."""
        return [self._care_wa(r) for r in self._query("SELECT * FROM care_whatsapp WHERE phone_key = ? AND status != 'stopped'",
                                                      (phone_key,))]

    def drop_care_for_member(self, owner_id: str, member_id: str) -> None:
        with self._lock, self._conn:
            for table in ("care_circle", "care_invites", "dose_log", "emergency_links", "care_whatsapp"):
                self._conn.execute(f"DELETE FROM {table} WHERE owner_id = ? AND member_id = ?", (owner_id, member_id))

    def create_care_invite(self, token_hash: str, owner_id: str, member_id: str, expires_at: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO care_invites (token_hash, owner_id, member_id, expires_at) VALUES (?, ?, ?, ?)",
                               (token_hash, owner_id, member_id, expires_at))

    def use_care_invite(self, token_hash: str) -> Optional[tuple[str, str]]:
        with self._lock, self._conn:
            rows = self._conn.execute("SELECT owner_id, member_id FROM care_invites WHERE token_hash = ? AND used_at IS NULL "
                                      "AND expires_at > ?", (token_hash, _now())).fetchall()
            if not rows:
                return None
            self._conn.execute("UPDATE care_invites SET used_at = ? WHERE token_hash = ?", (_now(), token_hash))
        return rows[0]["owner_id"], rows[0]["member_id"]

    def log_dose(self, owner_id: str, member_id: str, med_id: str, day: str, slot: str, status: Optional[str],
                 by_user: str) -> None:
        with self._lock, self._conn:
            if status is None:
                self._conn.execute("DELETE FROM dose_log WHERE owner_id = ? AND member_id = ? AND med_id = ? AND day = ? "
                                   "AND slot = ?", (owner_id, member_id, med_id, day, slot))
            else:
                self._conn.execute("INSERT OR REPLACE INTO dose_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (owner_id, member_id, med_id, day, slot, status, by_user, _now()))

    def dose_log(self, owner_id: str, member_id: str, since: str) -> list[dict]:
        return [dict(r) for r in self._query("SELECT med_id, day, slot, status, by_user, at FROM dose_log WHERE owner_id = ? "
                                             "AND member_id = ? AND day >= ? ORDER BY day, slot", (owner_id, member_id, since))]

    def care_targets(self) -> list[tuple[str, str]]:
        """Every (owner, relative) with medicine reminders switched on, for the hourly job."""
        out = []
        for uid in self.user_ids():
            for m in self.get_profile(uid).family:
                if any(med.reminders for med in m.medications):
                    out.append((uid, m.id))
        return out

    def create_emergency_link(self, token_hash: str, owner_id: str, member_id: str, created_by: str,
                              expires_at: str) -> str:
        link_id = uuid.uuid4().hex[:12]
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO emergency_links (token_hash, id, owner_id, member_id, created_by, expires_at, "
                               "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (token_hash, link_id, owner_id, member_id, created_by, expires_at, _now()))
        return link_id

    def emergency_links(self, owner_id: str, member_id: str) -> list[dict]:
        return [dict(r) for r in self._query(
            "SELECT id, expires_at, revoked_at, views, created_at FROM emergency_links WHERE owner_id = ? AND member_id = ? "
            "AND revoked_at IS NULL AND expires_at > ? ORDER BY created_at DESC", (owner_id, member_id, _now()))]

    def revoke_emergency_link(self, owner_id: str, member_id: str, link_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("UPDATE emergency_links SET revoked_at = ? WHERE id = ? AND owner_id = ? AND "
                                     "member_id = ? AND revoked_at IS NULL", (_now(), link_id, owner_id, member_id))
        return cur.rowcount > 0

    def open_emergency_link(self, token_hash: str) -> Optional[dict]:
        with self._lock, self._conn:
            rows = self._conn.execute("SELECT * FROM emergency_links WHERE token_hash = ? AND revoked_at IS NULL "
                                      "AND expires_at > ?", (token_hash, _now())).fetchall()
            if not rows:
                return None
            self._conn.execute("UPDATE emergency_links SET views = views + 1 WHERE token_hash = ?", (token_hash,))
        return dict(rows[0])

    def nudges(self, user_id: str) -> list[dict]:
        return [dict(r) for r in self._query("SELECT key, sent_at FROM nudges WHERE user_id = ?", (user_id,))]

    def record_nudge(self, user_id: str, key: str, at: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO nudges (user_id, key, sent_at) VALUES (?, ?, ?)", (user_id, key, at))

    def user_ids(self) -> list[str]:
        return [r["id"] for r in self._query("SELECT id FROM users")]

    def set_partner_oauth(self, partner_id: str, redirect_uris: list[str], confidential: bool) -> Optional[str]:
        """Register OAuth redirect URIs; returns a new client secret for confidential clients (shown once)."""
        secret = ("fhgcs_" + new_token()) if confidential else None
        with self._lock, self._conn:
            self._conn.execute("UPDATE partners SET redirect_uris = ?, client_secret_hash = ? WHERE id = ?",
                               (json.dumps(redirect_uris), hash_token(secret) if secret else None, partner_id))
        return secret

    def partner_oauth(self, partner_id: str) -> Optional[dict]:
        rows = self._query("SELECT id, name, kind, active, redirect_uris, client_secret_hash FROM partners WHERE id = ?",
                           (partner_id,))
        if not rows or not rows[0]["active"] or not rows[0]["redirect_uris"]:
            return None
        r = rows[0]
        return {"id": r["id"], "name": r["name"], "kind": r["kind"], "redirect_uris": json.loads(r["redirect_uris"]),
                "client_secret_hash": r["client_secret_hash"]}

    # --- OAuth grants (consent artefacts) -------------------------------------
    def upsert_grant(self, user_id: str, partner_id: str, scopes: list[str], days: int) -> str:
        """One active grant per user and partner; approving again replaces its scopes and expiry."""
        now = datetime.now(timezone.utc)
        expires = (now + timedelta(days=days)).isoformat()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT id FROM oauth_grants WHERE user_id = ? AND partner_id = ? AND revoked_at IS NULL "
                                     "AND expires_at > ?", (user_id, partner_id, now.isoformat())).fetchone()
            if row:
                self._conn.execute("UPDATE oauth_grants SET scopes = ?, expires_at = ? WHERE id = ?",
                                   (json.dumps(scopes), expires, row["id"]))
                return row["id"]
            grant_id = uuid.uuid4().hex[:16]
            self._conn.execute("INSERT INTO oauth_grants (id, user_id, partner_id, scopes, created_at, expires_at) "
                               "VALUES (?, ?, ?, ?, ?, ?)", (grant_id, user_id, partner_id, json.dumps(scopes), now.isoformat(), expires))
            return grant_id

    def grant(self, grant_id: str) -> Optional[dict]:
        rows = self._query("SELECT g.*, p.name AS partner_name, p.kind AS partner_kind, p.active AS partner_active "
                           "FROM oauth_grants g JOIN partners p ON p.id = g.partner_id WHERE g.id = ?", (grant_id,))
        if not rows:
            return None
        g = dict(rows[0])
        g["scopes"] = json.loads(g["scopes"])
        g["active"] = bool(g["partner_active"]) and g["revoked_at"] is None and g["expires_at"] > _now()
        return g

    def grants_for_user(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT id FROM oauth_grants WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ? "
                           "ORDER BY created_at", (user_id, _now()))
        return [self.grant(r["id"]) for r in rows]

    def revoke_grant(self, user_id: str, grant_id: str) -> bool:
        with self._lock, self._conn:
            n = self._conn.execute("UPDATE oauth_grants SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
                                   (_now(), grant_id, user_id)).rowcount
            self._conn.execute("DELETE FROM oauth_tokens WHERE grant_id = ?", (grant_id,))
        return n == 1

    def touch_grant(self, grant_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE oauth_grants SET last_used_at = ? WHERE id = ?", (_now(), grant_id))

    def save_oauth_code(self, code_hash: str, grant_id: str, redirect_uri: str, challenge: str, minutes: int) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO oauth_codes (code_hash, grant_id, redirect_uri, code_challenge, expires_at) "
                               "VALUES (?, ?, ?, ?, ?)", (code_hash, grant_id, redirect_uri, challenge, expires))

    def pop_oauth_code(self, code_hash: str) -> Optional[dict]:
        """Single use; expired codes are never returned."""
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM oauth_codes WHERE code_hash = ? AND expires_at > ?",
                                     (code_hash, _now())).fetchone()
            self._conn.execute("DELETE FROM oauth_codes WHERE code_hash = ? OR expires_at <= ?", (code_hash, _now()))
        return dict(row) if row else None

    def save_oauth_token(self, token_hash: str, grant_id: str, kind: str, seconds: int) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO oauth_tokens (token_hash, grant_id, kind, expires_at) VALUES (?, ?, ?, ?)",
                               (token_hash, grant_id, kind, expires))

    def oauth_token(self, token_hash: str, kind: str) -> Optional[dict]:
        rows = self._query("SELECT grant_id FROM oauth_tokens WHERE token_hash = ? AND kind = ? AND expires_at > ?",
                           (token_hash, kind, _now()))
        if not rows:
            return None
        g = self.grant(rows[0]["grant_id"])
        return g if g and g["active"] else None

    def delete_oauth_token(self, token_hash: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM oauth_tokens WHERE token_hash = ?", (token_hash,))

    def partner_webhook_secret(self, partner_id: str) -> Optional[str]:
        rows = self._query("SELECT webhook_secret FROM partners WHERE id = ?", (partner_id,))
        return self._cipher.decrypt(rows[0]["webhook_secret"]) if rows and rows[0]["webhook_secret"] else None

    def set_partner_active(self, partner_id: str, active: bool) -> bool:
        with self._lock, self._conn:
            return self._conn.execute("UPDATE partners SET active = ? WHERE id = ?",
                                      (1 if active else 0, partner_id)).rowcount == 1

    def referrals_for_partner(self, partner_id: str) -> list[dict]:
        refs = self._query("SELECT id FROM referrals WHERE partner_id = ? ORDER BY created_at DESC", (partner_id,))
        return [self.referral(r["id"]) for r in refs]

    def org_patients(self, org_id: str) -> list[dict]:
        rows = self._query("SELECT user_id, display, connected_at, source FROM org_patients WHERE org_id = ? "
                           "ORDER BY connected_at", (org_id,))
        return [{"user_id": r["user_id"], "display": self._cipher.decrypt(r["display"]),
                 "connected_at": r["connected_at"], "source": r["source"] or "code"} for r in rows]

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
    def set_consent(self, user_id: str, scope: str, granted: bool, version: Optional[str] = None) -> None:
        now = _now()
        with self._lock, self._conn:
            if granted:
                self._conn.execute(
                    "INSERT INTO consents (user_id, scope, granted_at, revoked_at, version) VALUES (?, ?, ?, NULL, ?) "
                    "ON CONFLICT(user_id, scope) DO UPDATE SET granted_at = excluded.granted_at, revoked_at = NULL, "
                    "version = excluded.version",
                    (user_id, scope, now, version),
                )
            else:
                self._conn.execute(
                    "UPDATE consents SET revoked_at = ? WHERE user_id = ? AND scope = ?",
                    (now, user_id, scope),
                )

    def decline_consent(self, user_id: str, scope: str) -> None:
        """Record "not now" for something offered once (the pilot study), so it isn't offered again."""
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO consents (user_id, scope, granted_at, revoked_at) "
                               "VALUES (?, ?, NULL, ?)", (user_id, scope, _now()))

    def consent_row(self, user_id: str, scope: str) -> Optional[dict]:
        rows = self._query("SELECT scope, granted_at, revoked_at, version FROM consents WHERE user_id = ? AND scope = ?",
                           (user_id, scope))
        return dict(rows[0]) if rows else None

    def consent_counts(self, scope: str) -> dict:
        """Across real accounts: active, withdrawn (agreed, then stopped) and declined."""
        one = lambda where: self._query(  # noqa: E731
            f"SELECT COUNT(*) FROM consents c JOIN users u ON u.id = c.user_id WHERE c.scope = ? AND u.practice = 0 "
            f"AND {where}", (scope,))[0][0]
        return {"active": one("c.revoked_at IS NULL"), "withdrawn": one("c.revoked_at IS NOT NULL AND c.granted_at IS NOT NULL"),
                "declined": one("c.granted_at IS NULL")}

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

    # --- documents -----------------------------------------------------------
    def create_document(self, user_id: str, *, doc_type: str, doc_date: Optional[str], filename: Optional[str],
                        media_type: str, file: bytes, text: str, extraction: dict, method: str,
                        ocr_confidence: Optional[float], ai_model: Optional[str], ai_mode: Optional[str],
                        input_tokens: int, output_tokens: int, keep_file: bool = True, source: str = "upload") -> str:
        doc_id = uuid.uuid4().hex[:16]
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO documents (id, user_id, status, doc_type, doc_date, filename, media_type, size, file, text, "
                "extraction, method, ocr_confidence, ai_model, ai_mode, input_tokens, output_tokens, created_at, source) "
                "VALUES (?, ?, 'review', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, user_id, doc_type, doc_date, filename, media_type, len(file),
                 self._cipher.encrypt_bytes(file) if keep_file else None, self._cipher.encrypt(text),
                 self._cipher.encrypt(json.dumps(extraction)), method, ocr_confidence, ai_model, ai_mode,
                 input_tokens, output_tokens, _now(), source))
        return doc_id

    def _doc_row(self, r: sqlite3.Row, full: bool) -> dict:
        out = {k: r[k] for k in ("id", "status", "source", "doc_type", "doc_date", "subject", "subject_member_id", "filename", "media_type", "size",
                                 "method", "ocr_confidence", "ai_model", "ai_mode", "input_tokens", "output_tokens",
                                 "created_at", "saved_at")}
        out["has_file"] = r["has_file"]
        if full:
            out["extraction"] = json.loads(self._cipher.decrypt(r["extraction"]))
            out["text"] = self._cipher.decrypt(r["text"])
        return out

    _DOC_COLS = ("id, status, source, doc_type, doc_date, subject, subject_member_id, filename, media_type, size, method, ocr_confidence, ai_model, "
                 "ai_mode, input_tokens, output_tokens, created_at, saved_at, file IS NOT NULL AS has_file")

    def document(self, user_id: str, doc_id: str) -> Optional[dict]:
        rows = self._query(f"SELECT {self._DOC_COLS}, extraction, text FROM documents WHERE id = ? AND user_id = ?",
                           (doc_id, user_id))
        return self._doc_row(rows[0], full=True) if rows else None

    def documents(self, user_id: str, member_id: Optional[str] = None) -> list[dict]:
        where, params = "user_id = ? AND status != 'discarded'", [user_id]
        if member_id is not None:
            where += " AND subject_member_id = ?"
            params.append(member_id)
        rows = self._query(f"SELECT {self._DOC_COLS} FROM documents WHERE {where} "
                           "ORDER BY COALESCE(doc_date, substr(created_at, 1, 10)) DESC, created_at DESC", tuple(params))
        return [self._doc_row(r, full=False) for r in rows]

    def document_file(self, user_id: str, doc_id: str) -> Optional[tuple[str, bytes, Optional[str]]]:
        rows = self._query("SELECT media_type, file, filename FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        if not rows or rows[0]["file"] is None:
            return None
        return rows[0]["media_type"], self._cipher.decrypt_bytes(rows[0]["file"]), rows[0]["filename"]

    def save_document(self, user_id: str, doc_id: str, *, doc_type: str, doc_date: Optional[str], subject: str,
                      extraction: dict, subject_member_id: Optional[str] = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE documents SET status = 'saved', doc_type = ?, doc_date = ?, subject = ?, subject_member_id = ?, "
                "extraction = ?, saved_at = ? WHERE id = ? AND user_id = ?",
                (doc_type, doc_date, subject, subject_member_id, self._cipher.encrypt(json.dumps(extraction)), _now(),
                 doc_id, user_id))

    def delete_document(self, user_id: str, doc_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        return cur.rowcount > 0

    def documents_this_hour(self, user_id: str) -> int:
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        return self._query("SELECT COUNT(*) AS n FROM documents WHERE user_id = ? AND created_at > ?",
                           (user_id, since))[0]["n"]

    # --- connected sources ------------------------------------------------------
    def put_connect_state(self, state_hash: str, user_id: str, kind: str, data: dict, minutes: int = 15) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM connect_states WHERE expires_at < ?", (_now(),))
            self._conn.execute("INSERT INTO connect_states (state_hash, user_id, kind, data, expires_at) VALUES (?, ?, ?, ?, ?)",
                               (state_hash, user_id, kind, self._cipher.encrypt(json.dumps(data)), expires))

    def pop_connect_state(self, state_hash: str, kind: str) -> Optional[tuple[str, dict]]:
        """Single use: the state is deleted as it's read."""
        with self._lock, self._conn:
            row = self._conn.execute("SELECT user_id, data FROM connect_states WHERE state_hash = ? AND kind = ? AND expires_at > ?",
                                     (state_hash, kind, _now())).fetchone()
            self._conn.execute("DELETE FROM connect_states WHERE state_hash = ?", (state_hash,))
        return (row["user_id"], json.loads(self._cipher.decrypt(row["data"]))) if row else None

    def create_connection(self, user_id: str, kind: str, provider: str, display_name: str, secret: dict,
                          status: str = "active") -> str:
        conn_id = uuid.uuid4().hex[:16]
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO connections (id, user_id, kind, provider, display_name, secret, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (conn_id, user_id, kind, provider, display_name, self._cipher.encrypt(json.dumps(secret)), status, _now()))
        return conn_id

    def connections(self, user_id: str) -> list[dict]:
        rows = self._query("SELECT id, kind, provider, display_name, status, last_sync_at, last_sync_summary, created_at "
                           "FROM connections WHERE user_id = ? AND status != 'revoked' ORDER BY created_at", (user_id,))
        return [dict(r) | {"last_sync_summary": json.loads(r["last_sync_summary"]) if r["last_sync_summary"] else None}
                for r in rows]

    def connection(self, user_id: str, conn_id: str) -> Optional[dict]:
        rows = self._query("SELECT * FROM connections WHERE id = ? AND user_id = ? AND status != 'revoked'", (conn_id, user_id))
        if not rows:
            return None
        row = dict(rows[0])
        row["secret"] = json.loads(self._cipher.decrypt(row["secret"])) if row["secret"] else {}
        return row

    def connection_by_secret_field(self, kind: str, key: str, value: str) -> Optional[tuple[str, str]]:
        """(user_id, connection id) whose encrypted secret has secret[key] == value (e.g. an ABDM consent id)."""
        for r in self._query("SELECT id, user_id, secret FROM connections WHERE kind = ? AND status != 'revoked'", (kind,)):
            if r["secret"] and json.loads(self._cipher.decrypt(r["secret"])).get(key) == value:
                return r["user_id"], r["id"]
        return None

    def update_connection(self, conn_id: str, *, secret: Optional[dict] = None, status: Optional[str] = None,
                          sync_summary: Optional[dict] = None) -> None:
        sets, params = [], []
        if secret is not None:
            sets.append("secret = ?"); params.append(self._cipher.encrypt(json.dumps(secret)))
        if status is not None:
            sets.append("status = ?"); params.append(status)
        if sync_summary is not None:
            sets += ["last_sync_at = ?", "last_sync_summary = ?"]; params += [_now(), json.dumps(sync_summary)]
        if not sets:
            return
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE connections SET {', '.join(sets)} WHERE id = ?", (*params, conn_id))

    def revoke_connection(self, user_id: str, conn_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("UPDATE connections SET status = 'revoked', secret = NULL WHERE id = ? AND user_id = ? "
                                     "AND status != 'revoked'", (conn_id, user_id))
        return cur.rowcount > 0

    # --- forwarding channels ---------------------------------------------------
    def inbound(self, user_id: str) -> dict:
        rows = self._query("SELECT * FROM inbound_channels WHERE user_id = ?", (user_id,))
        return dict(rows[0]) if rows else {}

    def _upsert_inbound(self, user_id: str, **fields) -> None:
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO inbound_channels (user_id, {cols}, updated_at) VALUES (?, {marks}, ?) "
                f"ON CONFLICT(user_id) DO UPDATE SET {updates}, updated_at = excluded.updated_at",
                (user_id, *fields.values(), _now()))

    def set_email_token(self, user_id: str, token: str) -> None:
        self._upsert_inbound(user_id, email_token=token)

    def user_for_email_token(self, token: str) -> Optional[str]:
        rows = self._query("SELECT user_id FROM inbound_channels WHERE email_token = ?", (token,))
        return rows[0]["user_id"] if rows else None

    def set_whatsapp_link_code(self, user_id: str, code_hash: str, expires: str) -> None:
        self._upsert_inbound(user_id, link_code_hash=code_hash, link_code_expires=expires)

    def user_for_link_code(self, code_hash: str) -> Optional[str]:
        rows = self._query("SELECT user_id FROM inbound_channels WHERE link_code_hash = ? AND link_code_expires > ?",
                           (code_hash, _now()))
        return rows[0]["user_id"] if rows else None

    def link_whatsapp(self, user_id: str, key: str, phone: str) -> None:
        with self._lock, self._conn:
            # A number belongs to one account: linking it here unlinks it anywhere else.
            self._conn.execute("UPDATE inbound_channels SET whatsapp_key = NULL, whatsapp_phone = NULL "
                               "WHERE whatsapp_key = ? AND user_id != ?", (key, user_id))
        self._upsert_inbound(user_id, whatsapp_key=key, whatsapp_phone=self._cipher.encrypt(phone),
                             link_code_hash=None, link_code_expires=None)

    def unlink_whatsapp(self, user_id: str) -> None:
        self._upsert_inbound(user_id, whatsapp_key=None, whatsapp_phone=None)

    def user_for_whatsapp(self, key: str) -> Optional[str]:
        rows = self._query("SELECT user_id FROM inbound_channels WHERE whatsapp_key = ?", (key,))
        return rows[0]["user_id"] if rows else None

    def set_whatsapp_lang(self, user_id: str, lang: str) -> None:
        self._upsert_inbound(user_id, lang=lang)

    def set_whatsapp_pending(self, user_id: str, pending: Optional[dict]) -> None:
        self._upsert_inbound(user_id, pending=self._cipher.encrypt(json.dumps(pending)) if pending else None)

    def whatsapp_pending(self, user_id: str) -> Optional[dict]:
        row = self.inbound(user_id)
        return json.loads(self._cipher.decrypt(row["pending"])) if row.get("pending") else None

    def whatsapp_phone(self, user_id: str) -> Optional[str]:
        row = self.inbound(user_id)
        return self._cipher.decrypt(row["whatsapp_phone"]) if row.get("whatsapp_phone") else None

    # --- deletion ----------------------------------------------------------
    def delete_user(self, user_id: str) -> None:
        """Erase all health data and credentials. The audit trail is retained
        (it contains no health data) as evidence the deletion happened."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.audit(user_id, "user", "account.deleted")
