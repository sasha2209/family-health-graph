"""HTTP API (FastAPI)."""
from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from . import auth, clinic, push
from .clinician_report import render_html as clinician_report_html
from .family_links import (
    SHARE_LEVELS,
    cascade_categories,
    effective_profile,
    inverse_relationship,
    notify_cascade,
)
from .ingest import CsvImportError, parse_family_csv, parse_family_history_text, parse_fhir, to_fhir_bundle
from .insights import generate_insights, summarize
from .merge import merge_into
from .models import Condition, FamilyMember, HealthProfile, Observation, Relationship, Sex
from .security import constant_time_equals, load_cipher, pseudonym
from .sharing import CONSENT_LLM, CONSENT_RESEARCH, PARTNERS, deidentify, partner_payload, share_scope
from .storage import Store
from .terminology import OBSERVATION_ALIASES, category_from_text

PKG_DIR = Path(__file__).parent
log = logging.getLogger(__name__)
MAX_INGEST_BYTES = 5 * 1024 * 1024


@dataclass
class Settings:
    db_path: str = "data/fhg.sqlite3"
    encryption_key: Optional[str] = None
    key_file: str = "data/dev.key"
    admin_key: Optional[str] = None
    pseudonym_secret: str = "dev-pseudonym-secret"
    # Browser origins allowed to call the API (e.g. the Expo web preview at
    # http://localhost:8081). Native mobile apps don't need this.
    cors_origins: tuple[str, ...] = ()
    # Keyed hashing for email lookups and sign-in codes. Set a long random value in production.
    auth_secret: str = "dev-auth-secret"
    # OIDC audiences: your iOS bundle ID / Services ID for Apple, OAuth client IDs for Google.
    apple_audiences: tuple[str, ...] = ()
    google_audiences: tuple[str, ...] = ()
    # Public origin used in invite links, e.g. https://app.example.org (defaults to the request host).
    public_url: Optional[str] = None
    # Universal Links / App Links: "TEAMID.bundle.id" for iOS; package + signing-cert SHA-256s for Android.
    ios_app_ids: tuple[str, ...] = ()
    android_package: Optional[str] = None
    android_cert_sha256: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.environ.get("FHG_DB_PATH", cls.db_path),
            encryption_key=os.environ.get("FHG_ENCRYPTION_KEY"),
            key_file=os.environ.get("FHG_KEY_FILE", cls.key_file),
            admin_key=os.environ.get("FHG_ADMIN_KEY"),
            pseudonym_secret=os.environ.get("FHG_PSEUDONYM_SECRET", cls.pseudonym_secret),
            cors_origins=_csv("FHG_CORS_ORIGINS"),
            auth_secret=os.environ.get("FHG_AUTH_SECRET", cls.auth_secret),
            apple_audiences=_csv("FHG_APPLE_AUDIENCES"),
            google_audiences=_csv("FHG_GOOGLE_AUDIENCES"),
            public_url=os.environ.get("FHG_PUBLIC_URL") or None,
            ios_app_ids=_csv("FHG_IOS_APP_IDS"),
            android_package=os.environ.get("FHG_ANDROID_PACKAGE") or None,
            android_cert_sha256=_csv("FHG_ANDROID_CERT_SHA256"),
        )


def _csv(name: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in os.environ.get(name, "").split(",") if v.strip())


# --- request bodies -------------------------------------------------------------

class TextIn(BaseModel):
    text: str = Field(..., max_length=50_000)


class CsvIn(BaseModel):
    content: str = Field(..., max_length=MAX_INGEST_BYTES)


class DemographicsIn(BaseModel):
    sex: Optional[Sex] = None
    birth_date: Optional[date] = None


class ConditionIn(BaseModel):
    name: str
    onset_age: Optional[int] = Field(None, ge=0, le=120)


class FamilyMemberIn(BaseModel):
    relationship: Relationship
    name: Optional[str] = None
    sex: Optional[Sex] = None
    deceased: Optional[bool] = None
    conditions: list[ConditionIn] = Field(default_factory=list)


class ObservationIn(BaseModel):
    code: str
    value: float
    unit: str = ""
    effective_date: Optional[date] = None


class ConsentIn(BaseModel):
    scope: str
    granted: bool


ShareLevel = Field("conditions", pattern="^(" + "|".join(SHARE_LEVELS) + ")$")


class InvitationIn(BaseModel):
    relationship: Optional[Relationship] = None  # what the invitee is to you
    member_id: Optional[str] = None  # your existing record for this relative
    inviter_name: Optional[str] = Field(None, max_length=60)
    message: Optional[str] = Field(None, max_length=500)
    share_level: str = ShareLevel  # what you will share with them


class AcceptIn(BaseModel):
    share_level: str = ShareLevel  # what you will share with the inviter
    relationship: Optional[Relationship] = None  # correct what the inviter is to you


class DeviceIn(BaseModel):
    device: Optional[str] = Field(None, max_length=80)  # e.g. "iPhone", shown in the devices list


class EmailStartIn(BaseModel):
    email: str = Field(..., max_length=254)


class EmailVerifyIn(DeviceIn):
    email: str = Field(..., max_length=254)
    code: str = Field(..., pattern=r"^\d{6}$")


class OidcIn(DeviceIn):
    id_token: str = Field(..., max_length=8192)
    nonce: Optional[str] = Field(None, max_length=256)


class PushTokenIn(BaseModel):
    token: str = Field(..., max_length=200)
    platform: Optional[str] = Field(None, pattern="^(ios|android|web)$")


class OrgIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)


class CodeIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=20)


class ClinicConnectIn(CodeIn):
    # How the patient wants to appear to the clinic, e.g. "Priya Shah, DOB 2 May 1984".
    display_name: str = Field(..., min_length=2, max_length=120)


class ReferralIn(BaseModel):
    rule_id: str = Field(..., max_length=60)
    status: str = Field(..., pattern="^(referred|scheduled|completed|declined)$")
    note: Optional[str] = Field(None, max_length=500)


class ShareIn(BaseModel):
    share_level: str = Field(..., pattern="^(" + "|".join(SHARE_LEVELS) + ")$")


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json")


def create_app(settings: Optional[Settings] = None,
               email_sender: Optional[auth.EmailSender] = None,
               oidc_key_resolver: Optional[auth.KeyResolver] = None,
               push_sender: Optional[push.PushSender] = None,
               push_in_background: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    email_sender = email_sender or auth.email_sender_from_env()
    if settings.auth_secret == Settings.auth_secret:
        log.warning("FHG_AUTH_SECRET is not set; using a development value. Do not use this in production.")
    store = Store(settings.db_path, load_cipher(settings.encryption_key, Path(settings.key_file)))
    app = FastAPI(
        title="Family Health Graph",
        version="0.1.0",
        description="Ingest personal and family medical history, store it securely, and "
                    "generate guideline-based, explainable preventive-care insights.",
    )
    app.state.store = store
    notifier = push.Notifier(store, push_sender or push.push_sender_from_env(), background=push_in_background)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    valid_scopes = {CONSENT_LLM, CONSENT_RESEARCH} | {share_scope(p) for p in PARTNERS}

    def optional_session(authorization: Optional[str] = Header(None)) -> Optional[dict]:
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        session = store.session_for_token(authorization[7:].strip())
        if not session:
            raise HTTPException(401, "Invalid or expired session")
        return session

    def optional_user(session: Optional[dict] = Depends(optional_session)) -> Optional[str]:
        return session["user_id"] if session else None

    def current_session(session: Optional[dict] = Depends(optional_session)) -> dict:
        if not session:
            raise HTTPException(401, "Missing bearer token")
        return session

    def current_user(session: dict = Depends(current_session)) -> str:
        return session["user_id"]

    def ingest(user_id: str, source: str, raw: str, fragment: HealthProfile,
               preview: bool, warnings: Optional[list[str]] = None) -> dict:
        if preview:
            return {"preview": True, "parsed": _dump(fragment), "warnings": warnings or []}
        with store.write_lock:
            profile = store.get_profile(user_id)
            before = cascade_categories(profile)
            stats = merge_into(profile, fragment)
            store.save_profile(profile)
        event_id = store.record_ingest(user_id, source, raw, stats)
        store.audit(user_id, "user", f"ingest.{source}", {"event_id": event_id, **stats})
        notified = notify_cascade(store, user_id, cascade_categories(profile) - before, notify=notifier.notify)
        if notified:
            store.audit(user_id, "system", "family.cascade_notified", {"relatives": notified})
        return {"preview": False, "ingest_id": event_id, "merged": stats,
                "relatives_notified": notified, "warnings": warnings or []}

    # --- UI & meta ---------------------------------------------------------
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index() -> str:
        return (PKG_DIR / "static" / "index.html").read_text()

    @app.get("/invite/{token}", response_class=HTMLResponse, include_in_schema=False)
    def invite_page(token: str) -> str:
        return (PKG_DIR / "static" / "invite.html").read_text()

    @app.get("/sample/{name}", include_in_schema=False)
    def sample(name: str):
        files = {"fhir": "fhir_bundle.json", "text": "family_history.txt", "csv": "family.csv"}
        if name not in files:
            raise HTTPException(404)
        content = (PKG_DIR / "sample_data" / files[name]).read_text()
        return JSONResponse(json.loads(content) if name == "fhir" else {"content": content})

    # Universal Links (iOS) and App Links (Android): let invite links open the app.
    @app.get("/.well-known/apple-app-site-association", include_in_schema=False)
    def apple_app_site_association():
        if not settings.ios_app_ids:
            raise HTTPException(404)
        return JSONResponse({"applinks": {"details": [{
            "appIDs": list(settings.ios_app_ids),
            "components": [{"/": "/invite/*", "comment": "Family invitations open in the app"}],
        }]}})

    @app.get("/.well-known/assetlinks.json", include_in_schema=False)
    def android_asset_links():
        if not (settings.android_package and settings.android_cert_sha256):
            raise HTTPException(404)
        return JSONResponse([{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {"namespace": "android_app", "package_name": settings.android_package,
                       "sha256_cert_fingerprints": list(settings.android_cert_sha256)},
        }])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # --- accounts --------------------------------------------------------------
    @app.post("/v1/users", status_code=201)
    def create_user(body: Optional[DeviceIn] = None) -> dict:
        """Anonymous account (try the app without signing in). Add an email or
        Apple/Google sign-in later via /v1/auth/* to secure it."""
        user_id, token = store.create_user(body.device if body else None)
        return {"user_id": user_id, "token": token,
                "note": "Store this token securely. Add a sign-in method so the account can be recovered."}

    # --- sign-in -------------------------------------------------------------------
    def complete_sign_in(provider: str, subject: str, email: Optional[str],
                         current: Optional[str], device: Optional[str]) -> dict:
        owner = store.user_for_identity(provider, subject)
        if current:
            # Already signed in: attach this sign-in method to the current account.
            if owner and owner != current:
                raise HTTPException(409, "That sign-in already belongs to a different account. "
                                         "Sign out first if you want to use that account.")
            if owner is None and not store.add_identity(current, provider, subject, email):
                raise HTTPException(409, "That sign-in already belongs to a different account.")
            return {"user_id": current, "linked": True, "new_account": False}
        if owner:
            _, token = store.create_session(owner, device)
            store.audit(owner, "user", f"auth.sign_in.{provider}")
            return {"user_id": owner, "token": token, "new_account": False}
        user_id, token = store.create_user(device)
        if not store.add_identity(user_id, provider, subject, email):
            # Lost a race with a concurrent first sign-in: use the account that won.
            store.delete_user(user_id)
            owner = store.user_for_identity(provider, subject)
            _, token = store.create_session(owner, device)
            return {"user_id": owner, "token": token, "new_account": False}
        return {"user_id": user_id, "token": token, "new_account": True}

    @app.get("/v1/auth/config")
    def auth_config() -> dict:
        """Which sign-in methods this server offers (so apps can show the right buttons)."""
        return {"email": True, "apple": bool(settings.apple_audiences),
                "google": bool(settings.google_audiences)}

    @app.post("/v1/auth/email/start")
    def email_start(body: EmailStartIn) -> dict:
        try:
            email = auth.normalize_email(body.email)
        except auth.AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        key = auth.email_key(settings.auth_secret, email)
        since = datetime.now(timezone.utc) - timedelta(hours=1)
        if store.login_codes_since(key, since) >= auth.MAX_CODES_PER_HOUR:
            raise HTTPException(429, "Too many codes requested for this address. Try again in an hour.")
        code = auth.new_code()
        store.create_login_code(key, auth.code_hash(settings.auth_secret, key, code), auth.CODE_TTL_MINUTES)
        subject, text = auth.code_email(code)
        try:
            email_sender.send(email, subject, text)
        except Exception as exc:
            log.exception("sending sign-in email failed")
            raise HTTPException(502, "We couldn't send the email. Please try again.") from exc
        # Same answer whether or not the address has an account.
        return {"sent": True, "expires_in_minutes": auth.CODE_TTL_MINUTES}

    @app.post("/v1/auth/email/verify")
    def email_verify(body: EmailVerifyIn, user_id: Optional[str] = Depends(optional_user)) -> dict:
        try:
            email = auth.normalize_email(body.email)
        except auth.AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        key = auth.email_key(settings.auth_secret, email)
        record = store.active_login_code(key)
        if record is None or record["attempts"] >= auth.MAX_CODE_ATTEMPTS:
            raise HTTPException(400, "That code has expired or was already used. Request a new one.")
        if not hmac.compare_digest(record["code_hash"], auth.code_hash(settings.auth_secret, key, body.code)):
            store.record_code_attempt(record["id"])
            left = auth.MAX_CODE_ATTEMPTS - record["attempts"] - 1
            raise HTTPException(400, f"Incorrect code. {left} attempt{'s' if left != 1 else ''} left."
                                if left > 0 else "Incorrect code. Request a new one.")
        if not store.consume_login_code(record["id"]):
            raise HTTPException(400, "That code has expired or was already used. Request a new one.")
        return complete_sign_in("email", key, email, user_id, body.device) | {"email": email}

    @app.post("/v1/auth/oidc/{provider}")
    def oidc_sign_in(provider: str, body: OidcIn, user_id: Optional[str] = Depends(optional_user)) -> dict:
        audiences = {"apple": settings.apple_audiences, "google": settings.google_audiences}.get(provider, ())
        try:
            subject, email = auth.verify_id_token(provider, body.id_token, audiences, body.nonce,
                                                  oidc_key_resolver)
        except auth.AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        return complete_sign_in(provider, subject, email, user_id, body.device)

    @app.get("/v1/auth/me")
    def auth_me(session: dict = Depends(current_session)) -> dict:
        identities = store.identities_for(session["user_id"])
        return {"user_id": session["user_id"], "session_id": session["id"],
                "secured": bool(identities), "identities": identities}

    @app.get("/v1/auth/sessions")
    def list_sessions(session: dict = Depends(current_session)) -> list[dict]:
        return [s | {"current": s["id"] == session["id"]} for s in store.sessions_for(session["user_id"])]

    @app.delete("/v1/auth/sessions/{session_id}", status_code=204)
    def revoke_session(session_id: str, session: dict = Depends(current_session)) -> None:
        if not store.revoke_session(session["user_id"], session_id):
            raise HTTPException(404, "No such session")

    @app.post("/v1/auth/logout", status_code=204)
    def logout(session: dict = Depends(current_session)) -> None:
        store.revoke_session(session["user_id"], session["id"])

    @app.delete("/v1/me", status_code=204)
    def delete_me(user_id: str = Depends(current_user)) -> None:
        store.delete_user(user_id)

    # --- profile -----------------------------------------------------------------
    @app.get("/v1/profile")
    def get_profile(include_linked: bool = Query(False, description="Merge in what linked relatives share"),
                    user_id: str = Depends(current_user)) -> dict:
        store.audit(user_id, "user", "profile.read")
        return _dump(effective_profile(store, user_id) if include_linked else store.get_profile(user_id))

    @app.put("/v1/profile/demographics")
    def set_demographics(body: DemographicsIn, user_id: str = Depends(current_user)) -> dict:
        with store.write_lock:
            profile = store.get_profile(user_id)
            if body.sex is not None:
                profile.sex = body.sex
            if body.birth_date is not None:
                profile.birth_date = body.birth_date
            profile.touch()
            store.save_profile(profile)
        store.audit(user_id, "user", "profile.demographics")
        return _dump(profile)

    @app.post("/v1/family", status_code=201)
    def add_family_member(body: FamilyMemberIn, user_id: str = Depends(current_user)) -> dict:
        member = FamilyMember(
            relationship=body.relationship, name=body.name, sex=body.sex, deceased=body.deceased,
            conditions=[Condition(name=c.name, category=category_from_text(c.name),
                                  onset_age=c.onset_age) for c in body.conditions],
        )
        return ingest(user_id, "manual", body.model_dump_json(),
                      HealthProfile(family=[member]), preview=False)

    @app.delete("/v1/family/{member_id}", status_code=204)
    def delete_family_member(member_id: str, user_id: str = Depends(current_user)) -> None:
        with store.write_lock:
            profile = store.get_profile(user_id)
            before = len(profile.family)
            profile.family = [m for m in profile.family if m.id != member_id]
            if len(profile.family) == before:
                raise HTTPException(404, "No such relative")
            profile.touch()
            store.save_profile(profile)
        store.audit(user_id, "user", "family.delete", {"member_id": member_id})

    @app.post("/v1/observations", status_code=201)
    def add_observation(body: ObservationIn, user_id: str = Depends(current_user)) -> dict:
        code = OBSERVATION_ALIASES.get(body.code.strip().lower(), body.code.strip().lower())
        obs = Observation(code=code, value=body.value, unit=body.unit, effective_date=body.effective_date)
        return ingest(user_id, "manual", body.model_dump_json(),
                      HealthProfile(observations=[obs]), preview=False)

    # --- ingestion ---------------------------------------------------------------
    @app.post("/v1/ingest/fhir")
    def ingest_fhir(bundle: dict, preview: bool = Query(False),
                    user_id: str = Depends(current_user)) -> dict:
        raw = json.dumps(bundle)
        if len(raw) > MAX_INGEST_BYTES:
            raise HTTPException(413, "Bundle too large")
        try:
            fragment = parse_fhir(bundle)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return ingest(user_id, "fhir", raw, fragment, preview)

    @app.post("/v1/ingest/text")
    def ingest_text(body: TextIn, preview: bool = Query(False),
                    user_id: str = Depends(current_user)) -> dict:
        fragment = parse_family_history_text(body.text)
        warnings = [] if (fragment.family or fragment.conditions) else [
            "No relatives or conditions were recognised. Try sentences like "
            "'My mother had breast cancer at 46.'"
        ]
        return ingest(user_id, "text", body.text, fragment, preview, warnings)

    @app.post("/v1/ingest/csv")
    def ingest_csv(body: CsvIn, preview: bool = Query(False),
                   user_id: str = Depends(current_user)) -> dict:
        try:
            fragment, warnings = parse_family_csv(body.content)
        except CsvImportError as exc:
            raise HTTPException(422, str(exc)) from exc
        return ingest(user_id, "csv", body.content, fragment, preview, warnings)

    @app.get("/v1/ingests")
    def list_ingests(user_id: str = Depends(current_user)) -> list[dict]:
        return store.list_ingests(user_id)

    # --- insights ------------------------------------------------------------------
    @app.get("/v1/insights")
    def insights(user_id: str = Depends(current_user)) -> dict:
        report = generate_insights(effective_profile(store, user_id))
        store.audit(user_id, "system", "insights.generated", {"count": len(report.insights)})
        return _dump(report)

    @app.get("/v1/insights/summary")
    def insights_summary(user_id: str = Depends(current_user)) -> dict:
        report = generate_insights(effective_profile(store, user_id))
        allow = store.has_consent(user_id, CONSENT_LLM)
        result = summarize(report, allow_llm=allow)
        store.audit(user_id, "system", "insights.summary", {"generated_by": result["generated_by"]})
        return result | {"disclaimer": report.disclaimer}

    @app.get("/v1/report/clinician", response_class=HTMLResponse)
    def clinician_report(include_shared: bool = Query(
            True, description="Include history that linked relatives share with you"),
                         user_id: str = Depends(current_user)) -> HTMLResponse:
        """Print-ready summary for the patient to give their clinician (the app makes it a PDF)."""
        profile = effective_profile(store, user_id) if include_shared else store.get_profile(user_id)
        html = clinician_report_html(profile, generate_insights(profile), shared_included=include_shared)
        store.audit(user_id, "user", "report.clinician", {"include_shared": include_shared})
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    # --- clinic portal (B2B) -------------------------------------------------------------
    def staff_org(org_id: str, user_id: str) -> dict:
        org = store.org(org_id)
        if org is None or store.staff_role(org_id, user_id) is None:
            raise HTTPException(404, "No such organization")  # don't reveal orgs you aren't in
        return org

    def org_public(org: dict, role: Optional[str] = None) -> dict:
        out = {"id": org["id"], "name": org["name"]}
        if role:
            out |= {"role": role, "patient_code": org["patient_code"]}
        if role == "admin":
            out["staff_code"] = org["staff_code"]
        return out

    @app.post("/v1/orgs", status_code=201)
    def create_org(body: OrgIn, user_id: str = Depends(current_user)) -> dict:
        return org_public(store.create_org(body.name.strip(), user_id), "admin")

    @app.post("/v1/orgs/join")
    def join_org_as_staff(body: CodeIn, user_id: str = Depends(current_user)) -> dict:
        org = store.org_by_code("staff", body.code)
        if org is None:
            raise HTTPException(404, "No organization has that staff code")
        store.add_staff(org["id"], user_id)
        store.audit(user_id, "user", "org.staff_joined", {"org_id": org["id"]})
        return org_public(org, store.staff_role(org["id"], user_id))

    @app.get("/v1/orgs")
    def my_orgs(user_id: str = Depends(current_user)) -> list[dict]:
        return [org_public(o, o["role"]) for o in store.orgs_for_staff(user_id)]

    def org_referrals(org_id: str) -> list[dict]:
        refs = store.referrals_for_org(org_id)
        for r in refs:  # expose the per-clinic pseudonym, never the internal user id
            r["user_ref"] = clinic.patient_ref(settings.auth_secret, org_id, r.pop("user_id"))
        return refs

    def org_rows(org_id: str) -> list[tuple[dict, dict, HealthProfile]]:
        status_by = {(r["user_ref"], r["rule_id"]): r["status"] for r in org_referrals(org_id)}
        out = []
        for p in store.org_patients(org_id):
            profile = effective_profile(store, p["user_id"])
            ref = clinic.patient_ref(settings.auth_secret, org_id, p["user_id"])
            row = clinic.patient_row(ref, p["display"], p["connected_at"], profile, generate_insights(profile),
                                     referrals={rule: st for (pr, rule), st in status_by.items() if pr == ref})
            out.append((row, p, profile))
        return out

    @app.get("/v1/orgs/{org_id}/patients")
    def org_worklist(org_id: str, user_id: str = Depends(current_user)) -> dict:
        org = staff_org(org_id, user_id)
        rows = org_rows(org_id)
        for _, p, _ in rows:
            store.audit(p["user_id"], f"org:{org_id}", "clinic.viewed_list", {"org": org["name"]})
        worklist = clinic.sort_worklist([r for r, _, _ in rows])
        return {"org": org_public(org, store.staff_role(org_id, user_id)),
                "impact": clinic.impact(worklist, org_referrals(org_id)), "patients": worklist}

    @app.post("/v1/orgs/{org_id}/patients/{patient_ref}/referrals")
    def update_referral(org_id: str, patient_ref: str, body: ReferralIn,
                        user_id: str = Depends(current_user)) -> dict:
        org = staff_org(org_id, user_id)
        if body.rule_id not in clinic.PROGRAMS:
            raise HTTPException(422, "Unknown care program")
        patient = next((p for p in store.org_patients(org_id) if hmac.compare_digest(
            clinic.patient_ref(settings.auth_secret, org_id, p["user_id"]), patient_ref)), None)
        if patient is None:
            raise HTTPException(404, "No such patient")
        before = next((r["status"] for r in store.referrals_for_patient(patient["user_id"])
                       if r["org_id"] == org_id and r["rule_id"] == body.rule_id), None)
        referral = store.set_referral_status(org_id, patient["user_id"], body.rule_id, body.status,
                                             user_id, body.note)
        store.audit(patient["user_id"], f"org:{org_id}", "clinic.referral",
                    {"org": org["name"], "program": clinic.PROGRAMS[body.rule_id], "status": body.status})
        if body.status in ("referred", "scheduled") and body.status != before:
            verb = "referred you for" if body.status == "referred" else "scheduled your"
            notifier.notify(patient["user_id"], "referral",
                            f"{org['name']} {verb}: {clinic.PROGRAMS[body.rule_id]}. "
                            "Contact your clinic if you have questions.")
        referral.pop("user_id", None)
        for e in referral["history"]:
            e["by_you"] = e.pop("by_user") == user_id
        return {"patient_ref": patient_ref, "program": clinic.PROGRAMS[body.rule_id], **referral}

    @app.get("/v1/referrals")
    def my_referrals(user_id: str = Depends(current_user)) -> list[dict]:
        """Patient: referrals your clinics have made for you."""
        return [r | {"program": clinic.PROGRAMS.get(r["rule_id"], r["rule_id"])}
                for r in store.referrals_for_patient(user_id)]

    @app.get("/v1/orgs/{org_id}/patients/{patient_ref}/report", response_class=HTMLResponse)
    def org_patient_report(org_id: str, patient_ref: str, user_id: str = Depends(current_user)) -> HTMLResponse:
        org = staff_org(org_id, user_id)
        for row, p, profile in org_rows(org_id):
            if hmac.compare_digest(row["patient_ref"], patient_ref):
                store.audit(p["user_id"], f"org:{org_id}", "clinic.viewed_report", {"org": org["name"]})
                html = clinician_report_html(profile, generate_insights(profile))
                return HTMLResponse(html, headers={"Cache-Control": "no-store"})
        raise HTTPException(404, "No such patient")

    # Patient side: connect to / disconnect from a clinic.
    @app.get("/v1/clinics/lookup/{code}")
    def lookup_clinic(code: str, user_id: str = Depends(current_user)) -> dict:
        org = store.org_by_code("patient", code)
        if org is None:
            raise HTTPException(404, "No clinic has that code")
        return org_public(org)

    @app.post("/v1/clinics", status_code=201)
    def connect_clinic(body: ClinicConnectIn, user_id: str = Depends(current_user)) -> dict:
        org = store.org_by_code("patient", body.code)
        if org is None:
            raise HTTPException(404, "No clinic has that code")
        store.connect_patient(org["id"], user_id, body.display_name.strip())
        store.audit(user_id, "user", "clinic.connected", {"org_id": org["id"], "org": org["name"]})
        return org_public(org)

    @app.get("/v1/clinics")
    def my_clinics(user_id: str = Depends(current_user)) -> list[dict]:
        return store.orgs_for_patient(user_id)

    @app.delete("/v1/clinics/{org_id}", status_code=204)
    def disconnect_clinic(org_id: str, user_id: str = Depends(current_user)) -> None:
        if not store.disconnect_patient(org_id, user_id):
            raise HTTPException(404, "Not connected to that clinic")
        store.audit(user_id, "user", "clinic.disconnected", {"org_id": org_id})

    @app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
    def portal_page() -> str:
        return (PKG_DIR / "static" / "portal.html").read_text()

    # --- consent, sharing, portability ---------------------------------------------
    @app.get("/v1/consents")
    def list_consents(user_id: str = Depends(current_user)) -> dict:
        return {"consents": store.consents(user_id), "available_scopes": sorted(valid_scopes)}

    @app.post("/v1/consents")
    def set_consent(body: ConsentIn, user_id: str = Depends(current_user)) -> dict:
        if body.scope not in valid_scopes:
            raise HTTPException(422, f"Unknown scope. Valid scopes: {sorted(valid_scopes)}")
        store.set_consent(user_id, body.scope, body.granted)
        store.audit(user_id, "user", "consent." + ("grant" if body.granted else "revoke"),
                    {"scope": body.scope})
        return {"consents": store.consents(user_id)}

    @app.get("/v1/partners")
    def list_partners(user_id: str = Depends(current_user)) -> list[dict]:
        return [
            {"id": p.id, "name": p.name, "kind": p.kind, "purpose": p.purpose,
             "data_shared": sorted(p.categories),
             "consented": store.has_consent(user_id, share_scope(p.id))}
            for p in PARTNERS.values()
        ]

    @app.post("/v1/partners/{partner_id}/share")
    def share_with_partner(partner_id: str, user_id: str = Depends(current_user)) -> dict:
        partner = PARTNERS.get(partner_id)
        if not partner:
            raise HTTPException(404, "Unknown partner")
        if not store.has_consent(user_id, share_scope(partner_id)):
            raise HTTPException(403, f"Consent '{share_scope(partner_id)}' has not been granted")
        payload = partner_payload(store.get_profile(user_id), partner)
        store.audit(user_id, "system", "share.partner",
                    {"partner": partner_id, "categories": sorted(partner.categories)})
        # In production this payload is POSTed to the partner's FHIR endpoint.
        return {"status": "delivered (simulated)", "payload": payload}

    @app.get("/v1/export/fhir")
    def export_fhir(user_id: str = Depends(current_user)) -> dict:
        store.audit(user_id, "user", "export.fhir")
        return to_fhir_bundle(store.get_profile(user_id))

    @app.get("/v1/audit")
    def audit(user_id: str = Depends(current_user)) -> list[dict]:
        return store.audit_log(user_id)

    # --- family invitations & linked relatives ---------------------------------------
    # Note: partner sharing, FHIR export and research export deliberately use only the
    # user's own record. Relatives consented to share with family, not third parties.

    def public_invitation(inv: dict) -> dict:
        return {k: inv[k] for k in ("id", "relationship", "member_id", "inviter_share",
                                    "inviter_name", "message", "status", "created_at",
                                    "expires_at", "responded_at")}

    @app.post("/v1/invitations", status_code=201)
    def create_invitation(body: InvitationIn, request: Request,
                          user_id: str = Depends(current_user)) -> dict:
        profile = store.get_profile(user_id)
        relationship = body.relationship
        if body.member_id:
            member = next((m for m in profile.family if m.id == body.member_id), None)
            if member is None:
                raise HTTPException(404, "No such relative in your record")
            relationship = relationship or member.relationship
        if relationship is None:
            raise HTTPException(422, "Provide relationship or member_id")
        pending = [i for i in store.invitations_for(user_id) if i["status"] == "pending"]
        if len(pending) >= 50:
            raise HTTPException(429, "Too many pending invitations; revoke some first")
        inv, token = store.create_invitation(
            user_id, relationship.value, body.member_id, body.share_level,
            body.inviter_name, body.message)
        store.audit(user_id, "user", "invitation.created",
                    {"invitation_id": inv["id"], "relationship": relationship.value})
        return {"invitation": public_invitation(inv), "token": token,
                "invite_url": (settings.public_url or str(request.base_url)).rstrip("/") + f"/invite/{token}",
                "note": "Send this link to your relative. It works once and expires in 14 days."}

    @app.get("/v1/invitations")
    def list_invitations(user_id: str = Depends(current_user)) -> list[dict]:
        return [public_invitation(i) for i in store.invitations_for(user_id)]

    @app.delete("/v1/invitations/{invitation_id}", status_code=204)
    def revoke_invitation(invitation_id: str, user_id: str = Depends(current_user)) -> None:
        if not any(i["id"] == invitation_id for i in store.invitations_for(user_id)):
            raise HTTPException(404, "No such invitation")
        if not store.set_invitation_status(invitation_id, "revoked"):
            raise HTTPException(409, "Invitation is no longer pending")
        store.audit(user_id, "user", "invitation.revoked", {"invitation_id": invitation_id})

    def pending_invitation(token: str) -> dict:
        inv = store.invitation_by_token(token)
        if inv is None:
            raise HTTPException(404, "Invitation not found")
        if inv["status"] != "pending":
            raise HTTPException(410, f"Invitation is {inv['status']}")
        return inv

    @app.get("/v1/invites/{token}")
    def preview_invite(token: str) -> dict:
        """Public: what the invitee sees before accepting. Contains no health data."""
        inv = pending_invitation(token)
        inviter_sex = store.get_profile(inv["inviter_id"]).sex
        return {
            "inviter_name": inv["inviter_name"],
            "message": inv["message"],
            "you_are_their": inv["relationship"],
            "they_are_your": inverse_relationship(
                Relationship(inv["relationship"]), inviter_sex.value if inviter_sex else None).value,
            "they_will_share": inv["inviter_share"],
            "expires_at": inv["expires_at"],
        }

    @app.post("/v1/invites/{token}/accept")
    def accept_invite(token: str, body: AcceptIn,
                      user_id: Optional[str] = Depends(optional_user)) -> dict:
        inv = pending_invitation(token)
        new_token = None
        if user_id is None:
            user_id, new_token = store.create_user()
        if user_id == inv["inviter_id"]:
            raise HTTPException(400, "You can't accept your own invitation")
        if store.are_linked(user_id, inv["inviter_id"]):
            raise HTTPException(409, "You are already linked with this relative")
        if not store.set_invitation_status(inv["id"], "accepted"):
            raise HTTPException(410, "Invitation is no longer pending")

        inviter_sex = store.get_profile(inv["inviter_id"]).sex
        inviter_to_me = body.relationship or inverse_relationship(
            Relationship(inv["relationship"]), inviter_sex.value if inviter_sex else None)
        link_id = store.create_link(
            inv["inviter_id"], user_id,
            b_to_a=inv["relationship"], a_member_id=inv["member_id"], a_share=inv["inviter_share"],
            a_to_b=inviter_to_me.value, b_member_id=None, b_share=body.share_level,
        )
        store.audit(user_id, "user", "family.link_accepted", {"link_id": link_id})
        store.audit(inv["inviter_id"], "system", "family.link_created", {"link_id": link_id})
        notifier.notify(inv["inviter_id"], "invitation_accepted",
                     f"Your {inv['relationship'].replace('_', ' ')} accepted your invitation"
                     + ("" if body.share_level != "none" else " but isn't sharing their history yet")
                     + ". Your insights now include what they share.")
        # Results already on file that run in families should reach the new relative.
        notify_cascade(store, inv["inviter_id"], cascade_categories(store.get_profile(inv["inviter_id"])),
                       only_relative=user_id, notify=notifier.notify)
        notify_cascade(store, user_id, cascade_categories(store.get_profile(user_id)),
                       only_relative=inv["inviter_id"], notify=notifier.notify)
        result = {"link_id": link_id, "they_are_your": inviter_to_me.value,
                  "you_share": body.share_level}
        if new_token:
            result |= {"user_id": user_id, "token": new_token,
                       "note": "A new account was created. Store this token securely."}
        return result

    @app.post("/v1/invites/{token}/decline", status_code=204)
    def decline_invite(token: str) -> None:
        inv = pending_invitation(token)
        store.set_invitation_status(inv["id"], "declined")
        store.audit(inv["inviter_id"], "system", "invitation.declined", {"invitation_id": inv["id"]})

    @app.get("/v1/links")
    def list_links(user_id: str = Depends(current_user)) -> list[dict]:
        return [{"link_id": l["link_id"], "relationship": l["relationship"], "member_id": l["member_id"],
                 "you_share": l["i_share"], "they_share": l["they_share"], "since": l["created_at"]}
                for l in store.links_for(user_id)]

    @app.put("/v1/links/{link_id}")
    def update_link(link_id: str, body: ShareIn, user_id: str = Depends(current_user)) -> dict:
        link = next((l for l in store.links_for(user_id) if l["link_id"] == link_id), None)
        if link is None:
            raise HTTPException(404, "No such link")
        store.set_share_level(link_id, user_id, body.share_level)
        store.audit(user_id, "user", "family.share_changed",
                    {"link_id": link_id, "share_level": body.share_level})
        if link["i_share"] == "none" and body.share_level != "none":
            notify_cascade(store, user_id, cascade_categories(store.get_profile(user_id)),
                           only_relative=link["relative_id"], notify=notifier.notify)
        return {"link_id": link_id, "you_share": body.share_level}

    @app.delete("/v1/links/{link_id}", status_code=204)
    def delete_link(link_id: str, user_id: str = Depends(current_user)) -> None:
        if not store.delete_link(link_id, user_id):
            raise HTTPException(404, "No such link")
        store.audit(user_id, "user", "family.unlinked", {"link_id": link_id})

    @app.put("/v1/devices/push")
    def register_push(body: PushTokenIn, session: dict = Depends(current_session)) -> dict:
        if not push.EXPO_TOKEN_RE.match(body.token):
            raise HTTPException(422, "Not an Expo push token")
        store.register_push_token(body.token, session["user_id"], session["id"], body.platform)
        return {"registered": True}

    @app.get("/v1/devices/push")
    def push_status(session: dict = Depends(current_session)) -> dict:
        return {"registered": store.push_registered(session["id"])}

    @app.delete("/v1/devices/push", status_code=204)
    def unregister_push(session: dict = Depends(current_session)) -> None:
        store.unregister_push_for_session(session["id"])

    @app.get("/v1/notifications")
    def notifications(user_id: str = Depends(current_user)) -> list[dict]:
        return store.notifications(user_id)

    @app.post("/v1/notifications/read", status_code=204)
    def read_notifications(user_id: str = Depends(current_user)) -> None:
        store.mark_notifications_read(user_id)

    # --- research (admin) -------------------------------------------------------------
    @app.get("/admin/research/export")
    def research_export(x_admin_key: Optional[str] = Header(None)) -> dict:
        if not settings.admin_key or not x_admin_key or not constant_time_equals(
            x_admin_key, settings.admin_key
        ):
            raise HTTPException(403, "Admin key required")
        records = []
        for uid in store.users_with_consent(CONSENT_RESEARCH):
            records.append(deidentify(store.get_profile(uid), pseudonym(settings.pseudonym_secret, uid)))
            store.audit(uid, "admin", "research.export")
        return {"count": len(records), "records": records}

    return app
