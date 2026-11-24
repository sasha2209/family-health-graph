"""HTTP API (FastAPI)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from . import auth, backup as backups, bookings, care, clinic, emergency, i18n, monitoring, pilot, practice, privacy, inbound, partners, push, risk_models, trends
from .connectors import abdm, smart
from . import partner_oauth as poauth
from .clinician_report import render_html as clinician_report_html
from .family_links import (
    compose,
    SHARE_LEVELS,
    cascade_categories,
    effective_profile,
    inverse_relationship,
    notify_cascade,
)
from . import documents as docs
from .ingest import CsvImportError, parse_family_csv, parse_family_history_text, parse_fhir, to_fhir_bundle
from .insights import generate_insights, summarize
from .insights.lang import TABLES as insight_tables, language as insight_language, tr as insight_tr
from . import notices as N
from .merge import find_match, merge_into
from .models import CareInfo, Condition, FamilyMember, HealthProfile, Medication, Observation, Relationship, Sex
from .security import constant_time_equals, hash_token, load_cipher, pseudonym
from .sharing import CONSENT_AI_DOCS, CONSENT_LLM, CONSENT_WA_SUMMARIES, CONSENT_RESEARCH, PARTNERS, deidentify, partner_payload, share_scope
from .scheduler import Job, Scheduler
from .storage import Store
from .terminology import CONCEPTS_BY_CATEGORY as _CONCEPTS, OBSERVATION_ALIASES, OBSERVATION_TO_LOINC, category_from_text

CONCEPT_CATEGORIES = set(_CONCEPTS)

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
    # Directory with the mobile app's web build (`expo export --platform web`), served at /app.
    web_app_dir: Optional[str] = None
    # Forwarding documents in (docs/FORWARDING.md).
    inbound_email_domain: Optional[str] = None     # e.g. "in.example.org"; addresses are <token>@<domain>
    inbound_email_secret: Optional[str] = None     # shared secret on the inbound-mail webhook URL
    whatsapp_number: Optional[str] = None          # the business number people message, shown in the app
    whatsapp_verify_token: Optional[str] = None
    whatsapp_app_secret: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    # Patient portals people can connect (docs/CONNECTIONS.md): JSON list of {id, name, iss, client_id}.
    smart_providers: Optional[str] = None
    # Direct ABHA link through NHA's ABDM Wrapper (docs/TRUST_AND_COMPLIANCE.md): its base URL and our HIU id.
    abdm_wrapper_url: Optional[str] = None
    abdm_hiu_id: Optional[str] = None
    abdm_requester_name: str = "Family Health Graph"
    # DPDP Act: who answers privacy questions, and in how many days (set from the notified DPDP Rules).
    data_fiduciary: str = "Family Health Graph"
    grievance_officer_name: Optional[str] = None
    grievance_officer_email: Optional[str] = None
    grievance_days: int = 30
    # Running a pilot (docs/RUNNING_IN_PRODUCTION.md): background jobs, backups, error tracking.
    # WhatsApp templates for medicine reminders on a cared-for person's own phone (docs/CAREGIVER_MODE.md).
    whatsapp_template_care_optin: str = "care_optin"
    whatsapp_template_care_reminder: str = "medicine_reminder"
    scheduler: bool = False
    backup_dir: Optional[str] = None
    backup_keep: int = 14
    backup_key: Optional[str] = None
    sentry_dsn: Optional[str] = None
    environment: str = "development"

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
            # Render sets RENDER_EXTERNAL_URL (e.g. https://family-health-graph.onrender.com).
            public_url=os.environ.get("FHG_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or None,
            web_app_dir=os.environ.get("FHG_WEB_APP_DIR") or None,
            inbound_email_domain=os.environ.get("FHG_INBOUND_EMAIL_DOMAIN") or None,
            inbound_email_secret=os.environ.get("FHG_INBOUND_EMAIL_SECRET") or None,
            whatsapp_number=os.environ.get("FHG_WHATSAPP_NUMBER") or None,
            whatsapp_verify_token=os.environ.get("FHG_WHATSAPP_VERIFY_TOKEN") or None,
            whatsapp_app_secret=os.environ.get("FHG_WHATSAPP_APP_SECRET") or None,
            whatsapp_access_token=os.environ.get("FHG_WHATSAPP_ACCESS_TOKEN") or None,
            whatsapp_phone_number_id=os.environ.get("FHG_WHATSAPP_PHONE_NUMBER_ID") or None,
            smart_providers=os.environ.get("FHG_SMART_PROVIDERS") or None,
            abdm_wrapper_url=os.environ.get("FHG_ABDM_WRAPPER_URL") or None,
            abdm_hiu_id=os.environ.get("FHG_ABDM_HIU_ID") or None,
            abdm_requester_name=os.environ.get("FHG_ABDM_REQUESTER_NAME") or cls.abdm_requester_name,
            data_fiduciary=os.environ.get("FHG_DATA_FIDUCIARY") or cls.data_fiduciary,
            grievance_officer_name=os.environ.get("FHG_GRIEVANCE_OFFICER_NAME") or None,
            grievance_officer_email=os.environ.get("FHG_GRIEVANCE_OFFICER_EMAIL") or None,
            grievance_days=int(os.environ.get("FHG_GRIEVANCE_DAYS") or cls.grievance_days),
            whatsapp_template_care_optin=os.environ.get("FHG_WA_TEMPLATE_CARE_OPTIN") or cls.whatsapp_template_care_optin,
            whatsapp_template_care_reminder=os.environ.get("FHG_WA_TEMPLATE_CARE_REMINDER") or cls.whatsapp_template_care_reminder,
            scheduler=os.environ.get("FHG_SCHEDULER", "").lower() in ("1", "on", "true", "yes"),
            backup_dir=os.environ.get("FHG_BACKUP_DIR") or None,
            backup_keep=int(os.environ.get("FHG_BACKUP_KEEP") or cls.backup_keep),
            backup_key=os.environ.get("FHG_BACKUP_KEY") or None,
            sentry_dsn=os.environ.get("FHG_SENTRY_DSN") or None,
            environment=os.environ.get("FHG_ENVIRONMENT") or cls.environment,
            ios_app_ids=_csv("FHG_IOS_APP_IDS"),
            android_package=os.environ.get("FHG_ANDROID_PACKAGE") or None,
            android_cert_sha256=_csv("FHG_ANDROID_CERT_SHA256"),
        )


def formatday(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return iso


def _connect_page(message: str, back: Optional[str]) -> str:
    import html as _html
    link = f'<p><a href="{_html.escape(back)}">Return to the app</a></p>' if back else ""
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Family Health Graph</title><body style='font:16px system-ui;max-width:32rem;margin:3rem auto;padding:0 1rem'>"
            f"<h1 style='font-size:20px'>Family Health Graph</h1><p>{_html.escape(message)}</p>{link}</body>")


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


class LifestyleIn(BaseModel):
    activity: Optional[str] = Field(None, pattern="^(exercise_and_active_work|exercise_or_active_work|sedentary)$")
    waist_cm: Optional[float] = Field(None, ge=40, le=200)


class ConditionIn(BaseModel):
    name: str
    onset_age: Optional[int] = Field(None, ge=0, le=120)


class FamilyMemberIn(BaseModel):
    relationship: Relationship
    name: Optional[str] = None
    sex: Optional[Sex] = None
    deceased: Optional[bool] = None
    conditions: list[ConditionIn] = Field(default_factory=list)


class FamilyMemberPatch(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    sex: Optional[Sex] = None
    age: Optional[int] = Field(None, ge=0, le=120)
    deceased: Optional[bool] = None


class ObservationIn(BaseModel):
    code: str
    value: float
    unit: str = ""
    effective_date: Optional[date] = None


class DocumentIn(BaseModel):
    data_base64: str = Field(description="The file (PDF, JPEG or PNG), base64-encoded")
    filename: Optional[str] = Field(None, max_length=200)


class DocConditionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: Optional[str] = None
    onset_age: Optional[int] = Field(None, ge=0, le=120)


class DocMedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dosage: Optional[str] = Field(None, max_length=200)


class DocObservationIn(BaseModel):
    code: str
    value: float
    unit: str = ""


class DocRelativeIn(BaseModel):
    relationship: Relationship
    conditions: list[DocConditionIn] = Field(default_factory=list)


class DocumentSaveIn(BaseModel):
    """The items the user kept on the review screen."""
    subject: str = Field("self", description='"self", or the relationship of the relative this document is about')
    doc_type: str = "other"
    doc_date: Optional[date] = None
    relative_age: Optional[int] = Field(None, ge=0, le=120)
    member_id: Optional[str] = Field(None, description="Which relative, when there are several (e.g. two sisters)")
    conditions: list[DocConditionIn] = Field(default_factory=list)
    medications: list[DocMedicationIn] = Field(default_factory=list)
    observations: list[DocObservationIn] = Field(default_factory=list)
    family: list[DocRelativeIn] = Field(default_factory=list)


class SmartStartIn(BaseModel):
    provider: str
    return_to: Optional[str] = Field(None, description="App path to return to afterwards, e.g. /app/connections")


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


LANG_NAME = {"hi": "Hindi", "mr": "Marathi"}


class OrgLanguageIn(BaseModel):
    lang: str = Field(pattern="^(hi|mr)$", description="The clinic's patients' language, shown next to English")


class CodeIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=20)


class ClinicConnectIn(CodeIn):
    # How the patient wants to appear to the clinic, e.g. "Priya Shah, DOB 2 May 1984".
    display_name: str = Field(..., min_length=2, max_length=120)
    source: str = Field("code", pattern="^(code|link)$")  # 'link' when joining from a clinic's intake link


class CatalogItemIn(BaseModel):
    test: str
    price_inr: Optional[float] = Field(None, ge=0)
    home_collection: bool = False
    turnaround_days: Optional[int] = Field(None, ge=0, le=60)


class ContactIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., pattern=r"^\+?[0-9 -]{7,20}$")
    address: Optional[str] = Field(None, max_length=300)
    pincode: Optional[str] = Field(None, pattern=r"^[0-9]{4,10}$")


class BookingIn(BaseModel):
    partner_id: str
    tests: list[str] = Field(..., min_length=1, max_length=6)
    rule_id: Optional[str] = None
    preferred_date: Optional[date] = None
    slot: Optional[str] = Field(None, pattern="^(morning|afternoon|evening)$")
    contact: ContactIn


class BookingStatusIn(BaseModel):
    status: str = Field(..., pattern="^(scheduled|sample_collected|completed|cancelled)$")
    scheduled_for: Optional[datetime] = None
    note: Optional[str] = Field(None, max_length=500)


class RiskPredictionIn(BaseModel):
    outcome: str = Field(min_length=1, max_length=120, description='e.g. "Breast cancer"')
    probability_percent: float = Field(ge=0, le=100)
    horizon: str = Field(max_length=60, description='e.g. "next 10 years", "lifetime (to age 80)"')
    population_percent: Optional[float] = Field(None, ge=0, le=100, description="The same figure for the population")


class RiskResultIn(BaseModel):
    model: str = Field(min_length=1, max_length=80, description='e.g. "BOADICEA v6 (CanRisk)"')
    predictions: list[RiskPredictionIn] = Field(min_length=1, max_length=20)
    note: Optional[str] = Field(None, max_length=1000)


class CareMedicationPatch(BaseModel):
    reminders: Optional[bool] = None
    dosage: Optional[str] = Field(None, max_length=200)
    schedule: Optional[dict[str, float]] = Field(None, description='{"morning": 1, "night": 0.5}; {} clears it')
    stock: Optional[float] = Field(None, ge=0, le=10000, description="Tablets at home today")
    status: Optional[str] = Field(None, pattern="^(active|stopped)$")


class CareMedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dosage: Optional[str] = Field(None, max_length=200)
    stock: Optional[float] = Field(None, ge=0, le=10000)


class DoseIn(BaseModel):
    med_id: str
    slot: str = Field(pattern="^(morning|afternoon|night)$")
    day: Optional[date] = None
    status: Optional[str] = Field(pattern="^(taken|skipped)$", description="null clears the mark")


class CareJoinIn(BaseModel):
    name: Optional[str] = Field(None, max_length=40, description="What the others in the circle call you")


class SurveyAnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=40, description='One of the question\'s options, or "skipped"')


class LanguageIn(BaseModel):
    lang: str = Field(pattern="^(en|hi|bn|ta|te|mr)$")


class CareWhatsAppIn(BaseModel):
    phone: str = Field(min_length=7, max_length=24, description="Their own WhatsApp number")
    lang: str = Field("en", pattern="^(en|hi|mr)$")
    agreed: bool = Field(description="They agreed to get reminders on WhatsApp")


class EmergencyLinkIn(BaseModel):
    hours: int = Field(24, ge=1, le=72)


class AbhaIn(BaseModel):
    abha_address: str = Field(description="e.g. priya.shah@abdm (sandbox: @sbx)")


class NomineeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    relationship: str = Field(min_length=1, max_length=40)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=120)


class GrievanceIn(BaseModel):
    category: str = Field(pattern="^(access|correction|erasure|consent|sharing|security|other)$")
    message: str = Field(min_length=5, max_length=2000)


class GrievanceAnswerIn(BaseModel):
    response: str = Field(min_length=1, max_length=2000)
    status: str = Field("resolved", pattern="^(open|resolved)$")


class BreachIn(BaseModel):
    nature: str = Field(min_length=5, max_length=1000, description="What happened, in plain words")
    data_affected: list[str] = Field(min_length=1, max_length=20)
    occurred_at: Optional[datetime] = None
    detected_at: datetime
    likely_consequences: str = Field(min_length=5, max_length=1000)
    measures_taken: str = Field(min_length=5, max_length=1000)
    what_you_can_do: str = Field(min_length=5, max_length=1000)
    affected_user_ids: Optional[list[str]] = None
    all_users: bool = False


class ReferralIn(BaseModel):
    rule_id: str = Field(..., max_length=60)
    status: str = Field(..., pattern="^(referred|scheduled|completed|declined)$")
    note: Optional[str] = Field(None, max_length=500)
    # Route to a referral partner (null = handled in-house). Omit to keep the current routing.
    partner_id: Optional[str] = Field(None, max_length=40)


class PracticeClinicIn(BaseModel):
    name: str = Field("Practice clinic", min_length=2, max_length=120)
    lang: str = Field("hi", pattern="^(hi|mr)$")


class PartnerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    kind: str = Field("other", pattern="^(" + "|".join(partners.PARTNER_KINDS) + ")$")
    webhook_url: Optional[str] = Field(None, max_length=500, pattern=r"^https?://\S+$")


class PartnerOAuthIn(BaseModel):
    redirect_uris: list[str] = Field(..., min_length=1, max_length=10)
    confidential: bool = Field(False, description="Issue a client secret (server-side partners)")


class OAuthApproveIn(BaseModel):
    client_id: str
    redirect_uri: str
    scopes: list[str] = Field(..., min_length=1)
    state: Optional[str] = Field(None, max_length=500)
    code_challenge: str = Field(..., min_length=43, max_length=128)
    code_challenge_method: str = "S256"


class OAuthDenyIn(BaseModel):
    client_id: str
    redirect_uri: str
    state: Optional[str] = Field(None, max_length=500)


class PartnerStatusIn(BaseModel):
    status: str = Field(..., pattern="^(" + "|".join(partners.PARTNER_STATUSES) + ")$")
    note: Optional[str] = Field(None, max_length=500)


class ShareIn(BaseModel):
    share_level: str = Field(..., pattern="^(" + "|".join(SHARE_LEVELS) + ")$")


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json")


def create_app(settings: Optional[Settings] = None,
               email_sender: Optional[auth.EmailSender] = None,
               oidc_key_resolver: Optional[auth.KeyResolver] = None,
               push_sender: Optional[push.PushSender] = None,
               push_in_background: bool = True,
               webhook_sender: Optional[partners.WebhookSender] = None,
               webhooks_in_background: bool = True,
               document_ai_client: Optional[object] = None,
               whatsapp_client: Optional[inbound.WhatsAppClient] = None,
               smart_http: Optional[smart.Http] = None,
               abdm_http: Optional[abdm.JsonHttp] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    email_sender = email_sender or auth.email_sender_from_env()
    if settings.auth_secret == Settings.auth_secret:
        log.warning("FHG_AUTH_SECRET is not set; using a development value. Do not use this in production.")
    monitoring.init(settings.sentry_dsn, settings.environment, os.environ.get("RENDER_GIT_COMMIT"))
    store = Store(settings.db_path, load_cipher(settings.encryption_key, Path(settings.key_file)))
    app = FastAPI(
        title="Family Health Graph",
        version="0.1.0",
        description="Ingest personal and family medical history, store it securely, and "
                    "generate guideline-based, explainable preventive-care insights.",
    )
    app.state.store = store
    notifier = push.Notifier(store, push_sender or push.push_sender_from_env(), background=push_in_background)
    partner_hooks = partners.PartnerNotifier(store, webhook_sender or partners.HttpWebhookSender(),
                                             background=webhooks_in_background)
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), payment=()")
        if request.url.scheme == "https" or (settings.public_url or "").startswith("https://"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    def require_adult(user_id: str, what: str) -> None:
        """DPDP Act s.9: a child's data needs verifiable parental consent before it's shared or used beyond the
        app's core purpose. Until that flow exists, these are switched off for account holders under 18."""
        if privacy.is_minor(store.get_profile(user_id)):
            raise HTTPException(403, f"{what} isn't available for people under 18 yet: it needs a parent's "
                                     "verified consent first.")

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    valid_scopes = {CONSENT_LLM, CONSENT_AI_DOCS, CONSENT_WA_SUMMARIES, CONSENT_RESEARCH} | {share_scope(p) for p in PARTNERS}

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

    if settings.web_app_dir and Path(settings.web_app_dir, "index.html").exists():
        web_root = Path(settings.web_app_dir).resolve()

        @app.get("/app", include_in_schema=False)
        @app.get("/app/{path:path}", include_in_schema=False)
        def web_app(path: str = ""):
            """The mobile app's web build. Unknown paths fall back to index.html so
            client-side routes (e.g. /app/invite/<token>) work on reload."""
            candidate = (web_root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(web_root):
                return FileResponse(candidate)
            return FileResponse(web_root / "index.html", headers={"Cache-Control": "no-cache"})

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
            "components": [{"/": "/invite/*", "comment": "Family invitations open in the app"},
                           {"/": "/c/*", "comment": "Clinic intake links open in the app"}],
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

    @app.get("/health/ready")
    def health_ready() -> JSONResponse:
        """For uptime monitors: the database takes writes and the background jobs are running on time."""
        problems = []
        try:
            store.writable()
        except Exception:  # noqa: BLE001 (report, don't crash the probe)
            problems.append("database not writable")
        if settings.scheduler:
            now = datetime.now(timezone.utc)
            for name, limit in (("care", timedelta(hours=2)), ("reminders", timedelta(hours=26)),
                                ("backup", timedelta(hours=26)), ("housekeeping", timedelta(hours=26))):
                run = store.job_run(name)
                if run and run["status"] == "error":
                    problems.append(f"{name} job failed")
                elif run and now - datetime.fromisoformat(run["last_run_at"]) > limit:
                    problems.append(f"{name} job overdue")
        return JSONResponse({"status": "ok" if not problems else "degraded", "problems": problems},
                            status_code=200 if not problems else 503)

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
                "secured": bool(identities), "identities": identities, "lang": store.user_lang(session["user_id"])}

    @app.get("/v1/surveys")
    def surveys_due(user_id: str = Depends(current_user)) -> list[dict]:
        """Optional pilot questions to show now (at sign-up, and again after 8 weeks). Answers are only reported
        as counts across all families."""
        created = next((u["created_at"] for u in store.users_overview() if u["id"] == user_id), None)
        answered = {a["question"] for a in store.survey_answers(user_id)}
        due = pilot.due_questions(created, answered, datetime.now(timezone.utc)) if created else []
        return [{"id": q, "text": pilot.QUESTIONS[q]["text"], "options": pilot.QUESTIONS[q]["options"]} for q in due]

    @app.post("/v1/surveys/{question}", status_code=204)
    def answer_survey(question: str, body: SurveyAnswerIn, user_id: str = Depends(current_user)) -> Response:
        q = pilot.QUESTIONS.get(question)
        if q is None:
            raise HTTPException(404, "No such question")
        if body.answer not in q["options"] and body.answer != "skipped":
            raise HTTPException(422, f"Answer with one of {q['options']}, or skipped")
        store.save_survey_answer(user_id, question, body.answer)
        return Response(status_code=204)

    @app.put("/v1/profile/language")
    def set_language(body: LanguageIn, user_id: str = Depends(current_user)) -> dict:
        """The language for notifications and reminders (the app's own language is chosen on the phone)."""
        store.set_user_lang(user_id, body.lang)
        return {"lang": body.lang}

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
        """Erase the account and all health data (DPDP Act s.12). Partners holding data under a grant are told
        to erase it too (a health-data-free webhook with their pseudonymous patient id)."""
        for g in store.grants_for_user(user_id):
            partner_hooks.notify_event(g["partner_id"], "patient.erasure_requested", {"patient": partner_patient_id(g)})
        for b in store.bookings_for_user(user_id):
            partner_hooks.notify_event(b["partner_id"], "booking.erasure_requested", {"booking_id": b["id"]})
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

    @app.put("/v1/profile/lifestyle")
    def set_lifestyle(body: LifestyleIn, user_id: str = Depends(current_user)) -> dict:
        """Physical activity and waist size: the two questions the Indian Diabetes Risk Score needs."""
        with store.write_lock:
            profile = store.get_profile(user_id)
            if body.activity is not None:
                profile.activity = body.activity
            if body.waist_cm is not None:
                profile.observations.append(Observation(code="waist_circumference", value=body.waist_cm, unit="cm",
                                                        effective_date=date.today(), source="manual"))
            profile.touch()
            store.save_profile(profile)
        store.audit(user_id, "user", "profile.lifestyle")
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

    def member_out(m: FamilyMember) -> dict:
        return m.model_dump(mode="json") | {"degree": m.degree, "side": m.side}

    @app.get("/v1/family/{member_id}")
    def get_family_member(member_id: str, user_id: str = Depends(current_user)) -> dict:
        """A relative's managed profile: diagnoses, medicines, test results, and the documents filed under them."""
        member = next((m for m in store.get_profile(user_id).family if m.id == member_id), None)
        if member is None:
            raise HTTPException(404, "No such relative")
        return member_out(member) | {"documents": store.documents(user_id, member_id=member_id)}

    @app.patch("/v1/family/{member_id}")
    def update_family_member(member_id: str, body: FamilyMemberPatch, user_id: str = Depends(current_user)) -> dict:
        changes = body.model_dump(exclude_unset=True)
        with store.write_lock:
            profile = store.get_profile(user_id)
            member = next((m for m in profile.family if m.id == member_id), None)
            if member is None:
                raise HTTPException(404, "No such relative")
            for key, value in changes.items():
                setattr(member, key, value)
            profile.touch()
            store.save_profile(profile)
        store.audit(user_id, "user", "family.update", {"member_id": member_id, "fields": sorted(changes)})
        return member_out(member)

    @app.delete("/v1/family/{member_id}/items/{item_id}", status_code=204)
    def delete_family_item(member_id: str, item_id: str, user_id: str = Depends(current_user)) -> Response:
        """Remove one diagnosis, medicine or test result from a relative's record."""
        with store.write_lock:
            profile = store.get_profile(user_id)
            member = next((m for m in profile.family if m.id == member_id), None)
            if member is None:
                raise HTTPException(404, "No such relative")
            before = len(member.conditions) + len(member.medications) + len(member.observations)
            member.conditions = [x for x in member.conditions if x.id != item_id]
            member.medications = [x for x in member.medications if x.id != item_id]
            member.observations = [x for x in member.observations if x.id != item_id]
            if len(member.conditions) + len(member.medications) + len(member.observations) == before:
                raise HTTPException(404, "No such item")
            profile.touch()
            store.save_profile(profile)
        store.audit(user_id, "user", "family.item_delete", {"member_id": member_id, "item_id": item_id})
        return Response(status_code=204)

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
        store.drop_care_for_member(user_id, member_id)
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
                    lang: Optional[str] = Query(None, pattern="^[a-z]{2}$",
                                                description="Adds each condition's name in this language"),
                    user_id: str = Depends(current_user)) -> dict:
        fragment = parse_family_history_text(body.text)
        warnings = [] if (fragment.family or fragment.conditions) else [
            "No relatives or conditions were recognised. Try sentences like "
            "'My mother had breast cancer at 46.'"
        ]
        out = ingest(user_id, "text", body.text, fragment, preview, warnings)
        if lang:  # the intake page shows "what we understood" in the reader's language
            parsed = out.get("parsed") or {}
            with insight_language(lang):
                for c in [c for m in parsed.get("family", []) for c in m["conditions"]] + parsed.get("conditions", []):
                    concept = _CONCEPTS.get(c.get("category"))
                    c["display"] = insight_tr(concept.display) if concept else c["name"]
        return out

    @app.post("/v1/ingest/csv")
    def ingest_csv(body: CsvIn, preview: bool = Query(False),
                   user_id: str = Depends(current_user)) -> dict:
        try:
            fragment, warnings = parse_family_csv(body.content)
        except CsvImportError as exc:
            raise HTTPException(422, str(exc)) from exc
        return ingest(user_id, "csv", body.content, fragment, preview, warnings)

    # --- documents (photos / PDFs of prescriptions, lab reports, discharge summaries) ---
    MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
    DOCUMENTS_PER_HOUR = 30

    def doc_out(doc: dict, read: Optional[docs.ReadResult] = None) -> dict:
        out = {k: v for k, v in doc.items() if k != "text"}
        out["text_preview"] = doc.get("text", "")[:4000]
        out["ai_used"] = bool(doc.get("ai_model"))
        if read is not None:
            out["warnings"] = read.warnings
            out["ai_reason"] = read.ai_reason
        return out

    def read_and_store(user_id: str, data: bytes, filename: Optional[str], source: str) -> tuple[dict, docs.ReadResult]:
        """Read one file into a document waiting for review (uploads, email and WhatsApp share this)."""
        if not data:
            raise HTTPException(422, "The file is empty.")
        if len(data) > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, "Files can be up to 12 MB. Try a smaller photo or a PDF.")
        if store.documents_this_hour(user_id) >= DOCUMENTS_PER_HOUR:
            raise HTTPException(429, "That's a lot of documents in one hour. Please try again a little later.")
        allow_ai = store.has_consent(user_id, CONSENT_AI_DOCS)
        try:
            read = docs.read_document(data, allow_ai=allow_ai, client=document_ai_client)
        except docs.UnsupportedDocument as exc:
            raise HTTPException(415, str(exc)) from exc
        e = read.extraction
        doc_id = store.create_document(
            user_id, doc_type=e.doc_type, doc_date=e.doc_date.isoformat() if e.doc_date else None,
            filename=filename, media_type=read.media_type, file=data, text=read.text.text,
            extraction=e.model_dump(mode="json"), method=read.text.method, ocr_confidence=read.text.confidence,
            ai_model=read.ai.model if read.ai else None, ai_mode=read.ai.mode if read.ai else None,
            input_tokens=read.ai.input_tokens if read.ai else 0, output_tokens=read.ai.output_tokens if read.ai else 0,
            source=source)
        store.audit(user_id, "user" if source == "upload" else source, "document.uploaded", {
            "document_id": doc_id, "doc_type": e.doc_type, "method": read.text.method, "source": source,
            "ai": read.ai.model if read.ai else None,
            "tokens": (read.ai.input_tokens + read.ai.output_tokens) if read.ai else 0})
        return store.document(user_id, doc_id), read

    @app.post("/v1/documents", status_code=201)
    def upload_document(body: DocumentIn, user_id: str = Depends(current_user)) -> dict:
        """Read a document and return a draft for review. Nothing is added to the record until it's saved."""
        import base64
        import binascii

        try:
            data = base64.b64decode(body.data_base64.split(",", 1)[-1], validate=False)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, "The file isn't valid base64.") from exc
        doc, read = read_and_store(user_id, data, body.filename, source="upload")
        return doc_out(doc, read)

    @app.get("/v1/documents")
    def list_documents(user_id: str = Depends(current_user)) -> list[dict]:
        return store.documents(user_id)

    def own_document(user_id: str, doc_id: str) -> dict:
        doc = store.document(user_id, doc_id)
        if doc is None:
            raise HTTPException(404, "No such document")
        return doc

    @app.get("/v1/documents/{doc_id}")
    def get_document(doc_id: str, user_id: str = Depends(current_user)) -> dict:
        return doc_out(own_document(user_id, doc_id))

    @app.get("/v1/documents/{doc_id}/file")
    def document_file(doc_id: str, user_id: str = Depends(current_user)) -> Response:
        found = store.document_file(user_id, doc_id)
        if found is None:
            raise HTTPException(404, "No file stored for this document")
        media_type, data, _ = found
        store.audit(user_id, "user", "document.viewed", {"document_id": doc_id})
        return Response(data, media_type=media_type, headers={
            "Cache-Control": "no-store", "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})

    @app.post("/v1/documents/{doc_id}/save")
    def save_document(doc_id: str, body: DocumentSaveIn, user_id: str = Depends(current_user)) -> dict:
        """Add the reviewed items to the record: yours, or a relative's if the document is about them."""
        doc = own_document(user_id, doc_id)
        if doc["status"] == "saved":
            raise HTTPException(409, "This document has already been added to your record")
        if body.doc_type not in docs.DOC_TYPES:
            raise HTTPException(422, f"doc_type must be one of {list(docs.DOC_TYPES)}")
        unknown = [o.code for o in body.observations if o.code not in OBSERVATION_TO_LOINC]
        if unknown:
            raise HTTPException(422, f"Unknown test codes: {unknown}")
        source = f"document:{doc_id}"

        def conditions(items: list[DocConditionIn]) -> list[Condition]:
            return [Condition(name=c.name, category=c.category if c.category in CONCEPT_CATEGORIES else category_from_text(c.name),
                              onset_age=c.onset_age, status="active", source=source) for c in items]

        warnings: list[str] = []
        subject_member_id: Optional[str] = None
        if body.subject == "self":
            fragment = HealthProfile(
                conditions=conditions(body.conditions),
                medications=[Medication(name=m.name, dosage=m.dosage, prescribed_on=body.doc_date, source=source)
                             for m in body.medications],
                observations=[Observation(code=o.code, value=o.value, unit=o.unit, effective_date=body.doc_date, source=source)
                              for o in body.observations],
                family=[FamilyMember(relationship=r.relationship, conditions=conditions(r.conditions), source=source)
                        for r in body.family if r.conditions])
        else:
            try:
                subject = Relationship(body.subject)
            except ValueError as exc:
                raise HTTPException(422, "subject must be \"self\" or a relationship such as \"mother\"") from exc
            target = FamilyMember(
                relationship=subject, age=body.relative_age, conditions=conditions(body.conditions), source=source,
                medications=[Medication(name=m.name, dosage=m.dosage, prescribed_on=body.doc_date, source=source)
                             for m in body.medications],
                observations=[Observation(code=o.code, value=o.value, unit=o.unit, effective_date=body.doc_date,
                                          source=source) for o in body.observations])
            existing = store.get_profile(user_id).family
            if body.member_id:
                chosen = next((m for m in existing if m.id == body.member_id), None)
                if chosen is None or chosen.relationship != subject:
                    raise HTTPException(422, "member_id doesn't match a relative with that relationship")
                target.id = chosen.id  # merge_into matches on id first
            else:
                chosen = find_match(existing, target)
            subject_member_id = chosen.id if chosen else target.id
            members = [target]
            # Their family history is yours too, when the relationship can be worked out (their mother = your grandmother).
            for r in body.family:
                mine = compose(subject, r.relationship)
                if mine and r.conditions:
                    members.append(FamilyMember(relationship=mine, conditions=conditions(r.conditions), source=source))
            fragment = HealthProfile(family=members)
        result = ingest(user_id, "document", json.dumps({"document_id": doc_id, "subject": body.subject}),
                        fragment, preview=False, warnings=warnings)
        store.save_document(user_id, doc_id, doc_type=body.doc_type,
                            doc_date=body.doc_date.isoformat() if body.doc_date else None, subject=body.subject,
                            subject_member_id=subject_member_id,
                            # Keep what was read (patient, facility...) with the items as the user kept them.
                            extraction=doc["extraction"] | body.model_dump(
                                mode="json", include={"doc_type", "doc_date", "conditions", "medications",
                                                      "observations", "family"}))
        return result | {"document": doc_out(store.document(user_id, doc_id))}

    @app.delete("/v1/documents/{doc_id}", status_code=204)
    def delete_document(doc_id: str, user_id: str = Depends(current_user)) -> Response:
        """Delete the stored file and what was read from it. Items already added to your record stay there."""
        if not store.delete_document(user_id, doc_id):
            raise HTTPException(404, "No such document")
        store.audit(user_id, "user", "document.deleted", {"document_id": doc_id})
        return Response(status_code=204)

    # --- forwarding documents in: email and WhatsApp ----------------------------------------
    wa_client = whatsapp_client or (
        inbound.GraphWhatsAppClient(settings.whatsapp_access_token, settings.whatsapp_phone_number_id)
        if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else None)
    LINK_CODE_MINUTES = 15

    def link_code_hash(code: str) -> str:
        return hmac.new(settings.auth_secret.encode(), b"wa-link:" + code.encode(), "sha256").hexdigest()

    def inbound_out(user_id: str) -> dict:
        row = store.inbound(user_id)
        email = None
        if settings.inbound_email_domain:
            if not row.get("email_token"):
                store.set_email_token(user_id, inbound.new_email_token())
                row = store.inbound(user_id)
            email = f"{row['email_token']}@{settings.inbound_email_domain}"
        return {"email": {"available": bool(settings.inbound_email_domain), "address": email},
                "whatsapp": {"available": bool(wa_client and settings.whatsapp_number), "number": settings.whatsapp_number,
                             "linked": bool(row.get("whatsapp_key"))}}

    @app.get("/v1/inbound")
    def get_inbound(user_id: str = Depends(current_user)) -> dict:
        """Your private forwarding address and WhatsApp connection."""
        return inbound_out(user_id)

    @app.post("/v1/inbound/email/rotate")
    def rotate_inbound_email(user_id: str = Depends(current_user)) -> dict:
        """Get a new forwarding address; the old one stops working."""
        if not settings.inbound_email_domain:
            raise HTTPException(404, "Email forwarding isn't set up on this server")
        store.set_email_token(user_id, inbound.new_email_token())
        store.audit(user_id, "user", "inbound.email_rotated")
        return inbound_out(user_id)

    @app.post("/v1/inbound/whatsapp/code")
    def whatsapp_link_code(user_id: str = Depends(current_user)) -> dict:
        """A one-time code to send from your WhatsApp to link the number."""
        if not (wa_client and settings.whatsapp_number):
            raise HTTPException(404, "WhatsApp isn't set up on this server")
        code = inbound.new_link_code()
        expires = datetime.now(timezone.utc) + timedelta(minutes=LINK_CODE_MINUTES)
        store.set_whatsapp_link_code(user_id, link_code_hash(code), expires.isoformat())
        return {"code": code, "message": f"LINK {code}", "number": settings.whatsapp_number,
                "expires_in_minutes": LINK_CODE_MINUTES}

    @app.delete("/v1/inbound/whatsapp", status_code=204)
    def unlink_whatsapp(user_id: str = Depends(current_user)) -> Response:
        store.unlink_whatsapp(user_id)
        store.audit(user_id, "user", "inbound.whatsapp_unlinked")
        return Response(status_code=204)

    def forwarded(user_id: str, n: int, channel: str) -> None:
        if n:
            notifier.notify(user_id, "documents_received", N.say(store.user_lang(user_id), N.DOCS_MANY if n > 1 else N.DOCS_ONE,
                                                                 translate=("channel",), n=n, channel=channel))

    @app.post("/inbound/email", include_in_schema=False)
    async def inbound_email(request: Request, secret: str = Query("")) -> dict:
        """Webhook for an inbound-mail provider (Postmark JSON format)."""
        if not (settings.inbound_email_domain and settings.inbound_email_secret) or \
                not constant_time_equals(secret, settings.inbound_email_secret):
            raise HTTPException(404, "Not found")
        try:
            payload = await request.json()
        except ValueError:
            return {"accepted": 0}
        token = inbound.token_for_domain(inbound.email_recipients(payload), settings.inbound_email_domain)
        user_id = store.user_for_email_token(token) if token else None
        if user_id is None:
            return {"accepted": 0}  # don't reveal which addresses exist; 200 stops the provider retrying
        import base64
        accepted = 0
        for a in inbound.email_attachments(payload):
            try:
                read_and_store(user_id, base64.b64decode(a.content_b64), a.filename, source="email")
                accepted += 1
            except HTTPException as exc:
                log.info("Skipped an emailed attachment: %s", exc.detail)
        forwarded(user_id, accepted, "email")
        return {"accepted": accepted}

    @app.get("/inbound/whatsapp", include_in_schema=False)
    def whatsapp_verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
                        challenge: str = Query("", alias="hub.challenge")) -> Response:
        """Meta's one-time webhook verification."""
        if mode == "subscribe" and settings.whatsapp_verify_token and \
                constant_time_equals(token, settings.whatsapp_verify_token):
            return Response(challenge, media_type="text/plain")
        raise HTTPException(403, "Verification failed")

    # --- the WhatsApp assistant (docs/FORWARDING.md) ---
    WA_SUBJECTS = {"1": "self", "2": "mother", "3": "father"}

    def wa_items(extraction: dict) -> list[str]:
        """Short lines describing what a document contained (only sent with the user's consent)."""
        lines = [f"• {c['name']}" for c in extraction.get("conditions", [])[:4]]
        for o in extraction.get("observations", [])[:5]:
            band = trends.band_for(o["code"], trends.normalise(o["code"], o["value"], o.get("unit", ""))[0])
            lines.append(f"• {o.get('display') or o['code']}: {o['value']:g} {o.get('unit', '')}".rstrip()
                         + (f" ({band['label'].lower()})" if band and band["tone"] != "good" else ""))
        for m in extraction.get("medications", [])[:5]:
            generic = m.get("generic")
            lines.append(f"• {m['name']}" + (f" ({generic})" if generic and generic.split()[0] not in m['name'].lower() else ""))
        for r in extraction.get("family", [])[:3]:
            lines.append(f"• {r['relationship'].replace('_', ' ').capitalize()}: " + ", ".join(c["name"] for c in r["conditions"]))
        return lines

    def wa_family_lines(fragment: HealthProfile) -> list[str]:
        lines = [f"• {m.relationship.value.replace('_', ' ').capitalize()}: " + ", ".join(
            c.display_name + (f" (at {c.onset_age})" if c.onset_age is not None else "") for c in m.conditions)
            for m in fragment.family if m.conditions]
        lines += [f"• You: {c.display_name}" for c in fragment.conditions]
        return lines

    def wa_save_pending(user_id: str, choice: str) -> str:
        pending = store.whatsapp_pending(user_id)
        if not pending:
            return "nothing_pending"
        if "doc" in pending:
            doc = store.document(user_id, pending["doc"])
            if doc is None or doc["status"] == "saved":
                store.set_whatsapp_pending(user_id, None)
                return "nothing_pending"
            e = doc["extraction"]
            subject = WA_SUBJECTS.get(choice, "self")
            save_document(doc["id"], DocumentSaveIn(
                subject=subject, doc_type=e.get("doc_type", "other"), doc_date=e.get("doc_date"),
                conditions=e.get("conditions", []), medications=e.get("medications", []),
                observations=e.get("observations", []), family=e.get("family", [])), user_id=user_id)
        elif "text" in pending:
            ingest(user_id, "whatsapp", pending["text"], parse_family_history_text(pending["text"]), preview=False)
        store.set_whatsapp_pending(user_id, None)
        store.audit(user_id, "whatsapp", "whatsapp.saved", {"kind": "doc" if "doc" in pending else "text"})
        return "saved"

    def wa_summary(user_id: str) -> str:
        with insight_language(store.inbound(user_id).get("lang") or store.user_lang(user_id)):
            report = generate_insights(effective_profile(store, user_id))
        if not report.insights:
            return "summary_none"
        return "\n".join(f"• {i.title}" for i in report.insights[:5])

    def handle_whatsapp(msg: inbound.WhatsAppMessage) -> None:
        key = inbound.phone_key(settings.auth_secret, msg.sender)
        user_id = store.user_for_whatsapp(key)
        if user_id is None and msg.kind == "text":
            care_rows = store.care_whatsapp_for_key(key)
            if care_rows and not re.search(r"\b\d{6}\b", msg.text):
                handle_care_whatsapp(msg, care_rows)
                return
        row = store.inbound(user_id) if user_id else {}
        lang = row.get("lang") or i18n.detect_script(msg.text) or "en"
        send = lambda text: wa_client.send_text(msg.sender, text)  # noqa: E731
        say = lambda key_, **v: send(i18n.t(key_, lang, **v))  # noqa: E731
        try:
            if msg.kind == "text":
                m = re.search(r"\b(\d{6})\b", msg.text)
                linking_user = store.user_for_link_code(link_code_hash(m.group(1))) if m else None
                if linking_user:
                    store.link_whatsapp(linking_user, key, msg.sender)
                    if i18n.detect_script(msg.text):
                        store.set_whatsapp_lang(linking_user, lang)
                    store.audit(linking_user, "whatsapp", "inbound.whatsapp_linked")
                    say("linked")
                    return
                if user_id is None:
                    say("unknown")
                    return
                if not row.get("lang") and i18n.detect_script(msg.text):
                    store.set_whatsapp_lang(user_id, lang)
                words = msg.text.strip().lower().split()
                command = words[0] if words else ""
                allowed = store.has_consent(user_id, CONSENT_WA_SUMMARIES)
                if command in ("help", "menu", "मदद", "?"):
                    say("help")
                elif command == "lang" and len(words) > 1 and words[1] in i18n.LANGS:
                    lang = words[1]
                    store.set_whatsapp_lang(user_id, lang)
                    say("lang_set")
                elif command in ("stop", "रोको", "बंद"):
                    store.unlink_whatsapp(user_id)
                    store.audit(user_id, "whatsapp", "inbound.whatsapp_unlinked")
                    say("stopped")
                elif command in ("summary", "सारांश"):
                    if not allowed:
                        say("private")
                    else:
                        body = wa_summary(user_id)
                        send(i18n.t(body, lang) if body == "summary_none" else i18n.t("summary_header", lang) + "\n" + body)
                elif msg.text.strip() in WA_SUBJECTS:
                    say(wa_save_pending(user_id, msg.text.strip()))
                else:
                    fragment = parse_family_history_text(msg.text)
                    if not (fragment.family or fragment.conditions):
                        say("not_understood")
                        return
                    store.set_whatsapp_pending(user_id, {"text": msg.text})
                    if allowed:
                        say("understood", items="\n".join(wa_family_lines(fragment)))
                    else:
                        say("understood_private")
                return
            if user_id is None:
                say("unknown")
                return
            if msg.kind == "audio":
                say("voice")
                return
            if msg.kind == "other" or not msg.media_id or (msg.mime_type and msg.mime_type not in inbound.ACCEPTED_TYPES):
                say("unsupported")
                return
            try:
                doc, _ = read_and_store(user_id, wa_client.download(msg.media_id), msg.filename, source="whatsapp")
            except HTTPException as exc:
                say("too_many" if exc.status_code == 429 else "unsupported")
                return
            forwarded(user_id, 1, "WhatsApp")
            store.set_whatsapp_pending(user_id, {"doc": doc["id"]})
            if not store.has_consent(user_id, CONSENT_WA_SUMMARIES):
                say("received")
                return
            e = doc["extraction"]
            items = wa_items(e)
            if not items:
                say("read_nothing")
                return
            doc_name = i18n.DOC_NAMES.get(e.get("doc_type", "other"), i18n.DOC_NAMES["other"])
            say("read_summary", doc=doc_name.get(lang, doc_name["en"]),
                date=f" ({formatday(e['doc_date'])})" if e.get("doc_date") else "", items="\n".join(items))
        except Exception:
            log.exception("WhatsApp message handling failed")

    @app.post("/inbound/whatsapp", include_in_schema=False)
    async def whatsapp_webhook(request: Request, background: BackgroundTasks,
                               x_hub_signature_256: Optional[str] = Header(None)) -> dict:
        """WhatsApp Business Cloud API webhook. Answers at once; documents are read in the background."""
        if not (wa_client and settings.whatsapp_app_secret):
            raise HTTPException(404, "Not found")
        raw = await request.body()
        if not inbound.verify_meta_signature(settings.whatsapp_app_secret, raw, x_hub_signature_256):
            raise HTTPException(401, "Bad signature")
        try:
            messages = inbound.whatsapp_messages(json.loads(raw))
        except ValueError:
            return {"received": 0}
        for msg in messages:
            background.add_task(handle_whatsapp, msg)
        return {"received": len(messages)}

    # --- connected record sources: SMART on FHIR patient portals ----------------------------
    smart_providers = smart.providers_from_env(settings.smart_providers)
    fhir_http = smart_http or smart.UrllibHttp()

    def state_hash(state: str) -> str:
        return hashlib.sha256(state.encode()).hexdigest()

    def smart_redirect_uri(request: Request) -> str:
        return f"{public_base(request)}/connect/smart/callback"

    @app.get("/v1/connections")
    def list_connections(user_id: str = Depends(current_user)) -> dict:
        """Connected sources, and the patient portals this server can connect to."""
        return {"connections": store.connections(user_id),
                "available": [{"id": p.id, "name": p.name, "kind": "smart"} for p in smart_providers.values()]
                + ([{"id": "abdm", "name": "ABHA (hospitals and labs across India)", "kind": "abdm"}]
                   if settings.abdm_wrapper_url and settings.abdm_hiu_id else [])}

    @app.post("/v1/connect/smart")
    def start_smart(body: SmartStartIn, request: Request, user_id: str = Depends(current_user)) -> dict:
        """Start signing in to a patient portal. Open `authorize_url` in a browser."""
        provider = smart_providers.get(body.provider)
        if provider is None:
            raise HTTPException(404, "Unknown provider")
        try:
            conf = smart.discover(fhir_http, provider.iss)
        except smart.SmartError as exc:
            raise HTTPException(502, str(exc)) from exc
        state, (verifier, challenge) = secrets.token_urlsafe(24), smart.pkce_pair()
        return_to = body.return_to if body.return_to and body.return_to.startswith("/") and \
            not body.return_to.startswith("//") else "/app/connections"
        store.put_connect_state(state_hash(state), user_id, "smart", {
            "provider": provider.id, "verifier": verifier, "return_to": return_to})
        store.audit(user_id, "user", "connection.started", {"provider": provider.id})
        return {"authorize_url": smart.authorize_url(conf, provider, smart_redirect_uri(request), state, challenge)}

    def smart_sync(user_id: str, conn: dict) -> dict:
        provider = smart_providers.get(conn["provider"])
        if provider is None:
            raise HTTPException(409, "This portal is no longer available on this server")
        secret = conn["secret"]
        try:
            conf = smart.discover(fhir_http, provider.iss)
            token = secret.get("access_token")
            expired = datetime.fromisoformat(secret.get("expires_at", "1970-01-01T00:00:00+00:00")) <= datetime.now(timezone.utc)
            if expired:
                if not secret.get("refresh_token"):
                    store.update_connection(conn["id"], status="error")
                    raise HTTPException(409, "Sign in to this portal again to sync.")
                tok = smart.refresh(fhir_http, conf, provider, secret["refresh_token"])
                secret |= {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", secret["refresh_token"]),
                           "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat()}
                token = tok["access_token"]
                store.update_connection(conn["id"], secret=secret)
            pull = smart.fetch_patient_bundle(fhir_http, provider.iss, token, secret["patient"])
        except smart.SmartError as exc:
            store.update_connection(conn["id"], status="error")
            raise HTTPException(502, str(exc)) from exc
        fragment = parse_fhir(pull.bundle, source=f"smart:{conn['id']}")
        result = ingest(user_id, "smart", json.dumps({"connection": conn["id"], "counts": pull.counts}), fragment, preview=False)
        store.update_connection(conn["id"], status="active", sync_summary={"read": pull.counts, "merged": result["merged"]})
        return result

    @app.get("/connect/smart/callback", response_class=HTMLResponse, include_in_schema=False)
    def smart_callback(request: Request, state: str = Query(""), code: str = Query(""),
                       error: str = Query("")) -> HTMLResponse:
        pending = store.pop_connect_state(state_hash(state), "smart") if state else None
        if pending is None:
            return HTMLResponse(_connect_page("This sign-in link has expired. Start again from the app.", None), status_code=400)
        user_id, data = pending
        back = data.get("return_to", "/app/connections")
        if error or not code:
            return HTMLResponse(_connect_page("The connection was cancelled. Nothing was imported.", back))
        provider = smart_providers.get(data["provider"])
        try:
            conf = smart.discover(fhir_http, provider.iss)
            tok = smart.exchange_code(fhir_http, conf, provider, code, smart_redirect_uri(request), data["verifier"])
        except smart.SmartError as exc:
            return HTMLResponse(_connect_page(str(exc), back), status_code=502)
        conn_id = store.create_connection(user_id, "smart", provider.id, provider.name, {
            "patient": tok["patient"], "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat()})
        store.audit(user_id, "user", "connection.created", {"connection_id": conn_id, "provider": provider.id})
        try:
            result = smart_sync(user_id, store.connection(user_id, conn_id))
            m = result["merged"]
            msg = (f"Connected to {provider.name}. Added {m['conditions']} diagnoses, {m['medications']} medicines, "
                   f"{m['observations']} test results and {m['relatives_added']} relatives.")
        except HTTPException as exc:
            msg = f"Connected to {provider.name}, but the first import failed: {exc.detail} Try “Sync now” in the app."
        return HTMLResponse(_connect_page(msg, back))

    @app.post("/v1/connections/{conn_id}/sync")
    def sync_connection(conn_id: str, user_id: str = Depends(current_user)) -> dict:
        conn = store.connection(user_id, conn_id)
        if conn is None:
            raise HTTPException(404, "No such connection")
        if conn["kind"] == "abdm":
            return abdm_sync(user_id, conn)
        if conn["kind"] != "smart":
            raise HTTPException(409, "This connection syncs automatically")
        return smart_sync(user_id, conn)

    @app.delete("/v1/connections/{conn_id}", status_code=204)
    def delete_connection(conn_id: str, user_id: str = Depends(current_user)) -> Response:
        """Disconnect: tokens are deleted. Records already imported stay (delete them individually)."""
        if not store.revoke_connection(user_id, conn_id):
            raise HTTPException(404, "No such connection")
        store.audit(user_id, "user", "connection.revoked", {"connection_id": conn_id})
        return Response(status_code=204)

    # --- results over time -----------------------------------------------------------------
    @app.get("/v1/trends")
    def get_trends(member_id: Optional[str] = Query(None, description="A relative's id; omit for your own results"),
                   user_id: str = Depends(current_user)) -> dict:
        """Each test's results over time, with the latest value placed in its guideline range."""
        profile = store.get_profile(user_id)
        if member_id:
            member = next((m for m in profile.family if m.id == member_id), None)
            if member is None:
                raise HTTPException(404, "No such relative")
            observations = member.observations
        else:
            observations = profile.observations
        return {"tests": trends.build(observations)}

    @app.get("/v1/ingests")
    def list_ingests(user_id: str = Depends(current_user)) -> list[dict]:
        return store.list_ingests(user_id)

    # --- insights ------------------------------------------------------------------
    def person_lang(user_id: str, override: Optional[str]) -> str:
        return override if override in ("en", *insight_tables) else store.user_lang(user_id)

    @app.get("/v1/insights")
    def insights(lang: Optional[str] = Query(None, pattern="^[a-z]{2}$", description="Language; default: the person's"),
                 user_id: str = Depends(current_user)) -> dict:
        with insight_language(person_lang(user_id, lang)):
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

    @app.get("/v1/risk")
    def risk(lang: Optional[str] = Query(None, pattern="^[a-z]{2}$"), user_id: str = Depends(current_user)) -> dict:
        """Tree-based hereditary-risk models: Lynch syndrome criteria, the CanRisk export, and any risk figures
        a counselor has shared."""
        profile = effective_profile(store, user_id)
        try:
            with insight_language(person_lang(user_id, lang)):
                out = risk_models.assess(profile)
        except ValueError as exc:
            out = {"needs": str(exc)}
        return out | {"assessments": store.risk_results(user_id)}

    @app.get("/v1/risk/canrisk", response_class=Response)
    def risk_canrisk(user_id: str = Depends(current_user)) -> Response:
        """Your family as a CanRisk 2.0 pedigree file, to give a genetic counselor. Contains no names."""
        try:
            text, warnings = risk_models.canrisk_file(effective_profile(store, user_id))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        store.audit(user_id, "user", "risk.canrisk_export", {"warnings": len(warnings)})
        return Response(text, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": 'attachment; filename="family-canrisk.txt"', "Cache-Control": "no-store",
            "X-FHG-Warnings": json.dumps(warnings)[:4000]})

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

    def public_base(request: Optional[Request] = None) -> str:
        return (settings.public_url or (str(request.base_url) if request else "")).rstrip("/")

    def intake_url(org: dict, request: Optional[Request] = None) -> str:
        return f"{public_base(request)}/c/{org['patient_code']}"

    def org_lang(org: dict) -> str:
        return org.get("lang") or "hi"

    def org_public(org: dict, role: Optional[str] = None, request: Optional[Request] = None) -> dict:
        out = {"id": org["id"], "name": org["name"], "lang": org_lang(org), "practice": bool(org.get("practice"))}
        if role:
            out |= {"role": role, "patient_code": org["patient_code"], "intake_url": intake_url(org, request)}
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

    @app.put("/v1/orgs/{org_id}/language")
    def set_org_language(org_id: str, body: OrgLanguageIn, user_id: str = Depends(current_user)) -> dict:
        """The language printed next to English on the poster and staff guide, and offered first on the intake page
        (Hindi by default; Marathi for Pune)."""
        staff_org(org_id, user_id)
        if store.staff_role(org_id, user_id) != "admin":
            raise HTTPException(403, "Only the clinic's admin can change this")
        store.set_org_lang(org_id, body.lang)
        store.audit(user_id, "user", "org.language", {"org_id": org_id, "lang": body.lang})
        return {"lang": body.lang}

    @app.get("/v1/orgs")
    def my_orgs(user_id: str = Depends(current_user)) -> list[dict]:
        return [org_public(o, o["role"]) for o in store.orgs_for_staff(user_id)]

    def org_referrals(org_id: str) -> list[dict]:
        refs = store.referrals_for_org(org_id)
        names = {p["id"]: p["name"] for p in store.partners(active_only=False)}
        for r in refs:  # expose the per-clinic pseudonym, never the internal user id
            r["user_ref"] = clinic.patient_ref(settings.auth_secret, org_id, r.pop("user_id"))
            r["partner_name"] = names.get(r.get("partner_id"))
        return refs

    def org_rows(org_id: str) -> list[tuple[dict, dict, HealthProfile]]:
        refs = org_referrals(org_id)
        status_by = {(r["user_ref"], r["rule_id"]): r["status"] for r in refs}
        partner_by = {(r["user_ref"], r["rule_id"]): r["partner_name"] for r in refs if r["partner_name"]}
        out = []
        for p in store.org_patients(org_id):
            profile = effective_profile(store, p["user_id"])
            ref = clinic.patient_ref(settings.auth_secret, org_id, p["user_id"])
            row = clinic.patient_row(ref, p["display"], p["connected_at"], profile, generate_insights(profile),
                                     referrals={rule: st for (pr, rule), st in status_by.items() if pr == ref},
                                     referral_partners={rule: n for (pr, rule), n in partner_by.items() if pr == ref},
                                     source=p["source"])
            out.append((row, p, profile))
        return out

    @app.get("/v1/orgs/{org_id}/patients")
    def org_worklist(org_id: str, request: Request, user_id: str = Depends(current_user)) -> dict:
        org = staff_org(org_id, user_id)
        rows = org_rows(org_id)
        for _, p, _ in rows:
            store.audit(p["user_id"], f"org:{org_id}", "clinic.viewed_list", {"org": org["name"]})
        worklist = clinic.sort_worklist([r for r, _, _ in rows])
        return {"org": org_public(org, store.staff_role(org_id, user_id), request),
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
        route: dict = {}
        if "partner_id" in body.model_fields_set:
            if body.partner_id is not None and org.get("practice"):
                raise HTTPException(422, "This is a practice clinic: its referrals aren't sent to partners")
            if body.partner_id is not None:
                partner = store.partner(body.partner_id)
                if partner is None or not partner["active"]:
                    raise HTTPException(422, "Unknown or inactive referral partner")
            route = {"partner_id": body.partner_id}
        previous = next((r for r in store.referrals_for_org(org_id)
                         if r["user_id"] == patient["user_id"] and r["rule_id"] == body.rule_id), None)
        referral = store.set_referral_status(org_id, patient["user_id"], body.rule_id, body.status,
                                             user_id, body.note, **route)
        if referral.get("partner_id"):
            newly_routed = not previous or previous.get("partner_id") != referral["partner_id"]
            partner_hooks.notify(referral["partner_id"], "referral.created" if newly_routed else "referral.updated",
                                 referral["id"])
            store.audit(patient["user_id"], f"org:{org_id}", "clinic.referral_sent_to_partner",
                        {"partner": store.partner(referral["partner_id"])["name"],
                         "program": clinic.PROGRAMS[body.rule_id]})
        store.audit(patient["user_id"], f"org:{org_id}", "clinic.referral",
                    {"org": org["name"], "program": clinic.PROGRAMS[body.rule_id], "status": body.status})
        if body.status in ("referred", "scheduled") and body.status != before:
            routed = store.partner(referral["partner_id"]) if referral.get("partner_id") else None
            template = ({"referred": N.REFERRED_WITH, "scheduled": N.SCHEDULED_WITH} if routed else
                        {"referred": N.REFERRED, "scheduled": N.SCHEDULED})[body.status]
            notifier.notify(patient["user_id"], "referral", N.say(
                store.user_lang(patient["user_id"]), template, translate=("program",), org=org["name"],
                program=clinic.PROGRAMS[body.rule_id], partner=routed["name"] if routed else ""))
        referral.pop("user_id", None)
        for e in referral["history"]:
            by = e.pop("by_user")
            e["by_you"], e["by_partner"] = by == user_id, by.startswith("partner:")
        return {"patient_ref": patient_ref, "program": clinic.PROGRAMS[body.rule_id], **referral}

    @app.get("/v1/referral-partners")
    def referral_partner_directory(user_id: str = Depends(current_user)) -> list[dict]:
        """Partners clinic staff can refer to (vetted and contracted by the platform)."""
        if not store.orgs_for_staff(user_id):
            raise HTTPException(403, "Only clinic staff can see referral partners")
        return [{"id": p["id"], "name": p["name"], "kind": p["kind"]} for p in store.partners()]

    # --- partner API (authenticated with the partner's API key) ---------------------------
    def current_partner(x_api_key: Optional[str] = Header(None)) -> dict:
        partner = store.partner_for_key(x_api_key) if x_api_key else None
        if partner is None:
            raise HTTPException(401, "Missing or invalid API key")
        return partner

    def partner_view(partner: dict, r: dict, profile: Optional[HealthProfile] = None) -> dict:
        org = store.org(r["org_id"])
        display = next((p["display"] for p in store.org_patients(r["org_id"]) if p["user_id"] == r["user_id"]), "")
        profile = profile or effective_profile(store, r["user_id"])
        insight = next((i for i in generate_insights(profile).insights if i.rule_id == r["rule_id"]), None)
        program = clinic.PROGRAMS.get(r["rule_id"], r["rule_id"])
        return {
            "referral_id": r["id"], "status": r["status"], "program": program, "rule_id": r["rule_id"],
            "clinic": {"id": org["id"], "name": org["name"]}, "patient": {"display_name": display},
            "created_at": r["created_at"], "updated_at": r["updated_at"],
            "history": [{"status": e["status"], "at": e["at"], "note": e["note"],
                         "by": "partner" if e["by_user"].startswith("partner:") else "clinic"} for e in r["history"]],
            "service_request": partners.service_request(
                r, program, org["name"], partner["name"], display,
                insight.title if insight else None, insight.evidence if insight else []),
        }

    def partner_referral_or_404(partner: dict, referral_id: str) -> dict:
        r = store.referral(referral_id)
        if r is None or r.get("partner_id") != partner["id"]:
            raise HTTPException(404, "No such referral")
        return r

    @app.get("/v1/partner/referrals")
    def partner_referrals(status: Optional[str] = Query(None), partner: dict = Depends(current_partner)) -> dict:
        refs = [r for r in store.referrals_for_partner(partner["id"]) if not status or r["status"] == status]
        out = []
        for r in refs:
            out.append(partner_view(partner, r))
            store.audit(r["user_id"], f"partner:{partner['id']}", "partner.viewed_referral",
                        {"partner": partner["name"]})
        return {"partner": {"id": partner["id"], "name": partner["name"]}, "referrals": out}

    @app.get("/v1/partner/referrals/{referral_id}")
    def partner_referral(referral_id: str, partner: dict = Depends(current_partner)) -> dict:
        r = partner_referral_or_404(partner, referral_id)
        store.audit(r["user_id"], f"partner:{partner['id']}", "partner.viewed_referral", {"partner": partner["name"]})
        return partner_view(partner, r)

    @app.get("/v1/partner/referrals/{referral_id}/summary", response_class=HTMLResponse)
    def partner_referral_summary(referral_id: str, partner: dict = Depends(current_partner)) -> HTMLResponse:
        r = partner_referral_or_404(partner, referral_id)
        profile = effective_profile(store, r["user_id"])
        store.audit(r["user_id"], f"partner:{partner['id']}", "partner.viewed_summary", {"partner": partner["name"]})
        return HTMLResponse(clinician_report_html(profile, generate_insights(profile)),
                            headers={"Cache-Control": "no-store"})

    @app.post("/v1/partner/referrals/{referral_id}/status")
    def partner_update_status(referral_id: str, body: PartnerStatusIn,
                              partner: dict = Depends(current_partner)) -> dict:
        r = partner_referral_or_404(partner, referral_id)
        updated = store.set_referral_status(r["org_id"], r["user_id"], r["rule_id"], body.status,
                                            f"partner:{partner['id']}", body.note)
        program = clinic.PROGRAMS.get(r["rule_id"], r["rule_id"])
        store.audit(r["user_id"], f"partner:{partner['id']}", "partner.updated_referral",
                    {"partner": partner["name"], "program": program, "status": body.status})
        if body.status == "scheduled" and r["status"] != "scheduled":
            notifier.notify(r["user_id"], "referral", N.say(store.user_lang(r["user_id"]), N.PARTNER_SCHEDULED,
                                                            translate=("program",), partner=partner["name"], program=program))
        return partner_view(partner, updated)

    @app.get("/v1/partner/referrals/{referral_id}/canrisk", response_class=Response)
    def partner_referral_canrisk(referral_id: str, partner: dict = Depends(current_partner)) -> Response:
        """The referred person's family as a CanRisk 2.0 pedigree file (no names), to run BOADICEA in CanRisk."""
        r = partner_referral_or_404(partner, referral_id)
        try:
            text, warnings = risk_models.canrisk_file(effective_profile(store, r["user_id"]))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        store.audit(r["user_id"], f"partner:{partner['id']}", "partner.canrisk_export", {"partner": partner["name"]})
        return Response(text, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="canrisk-{referral_id}.txt"', "Cache-Control": "no-store",
            "X-FHG-Warnings": json.dumps(warnings)[:4000]})

    @app.post("/v1/partner/referrals/{referral_id}/risk-assessment", status_code=201)
    def partner_risk_assessment(referral_id: str, body: RiskResultIn, partner: dict = Depends(current_partner)) -> dict:
        """A counselor posts the risk figures they calculated; the person sees them in the app."""
        r = partner_referral_or_404(partner, referral_id)
        rid = store.add_risk_result(r["user_id"], partner["id"], referral_id, body.model_dump())
        store.audit(r["user_id"], f"partner:{partner['id']}", "partner.risk_assessment",
                    {"partner": partner["name"], "model": body.model})
        notifier.notify(r["user_id"], "risk", N.say(store.user_lang(r["user_id"]), N.RISK_SHARED, partner=partner["name"],
                                                    model=body.model))
        return {"id": rid}

    # --- platform admin: manage referral partners -------------------------------------------
    admin_failures: dict[str, list[float]] = {}

    def require_admin(request: Request, x_admin_key: Optional[str] = Header(None)) -> None:
        # Lock an address out for 15 minutes after 10 wrong keys: the console makes guessing easy otherwise.
        ip = request.client.host if request.client else "?"
        now = datetime.now(timezone.utc).timestamp()
        recent = [t for t in admin_failures.get(ip, []) if now - t < 900]
        if len(recent) >= 10:
            raise HTTPException(429, "Too many wrong admin keys. Try again in 15 minutes.")
        if not settings.admin_key or not x_admin_key or not constant_time_equals(x_admin_key, settings.admin_key):
            admin_failures[ip] = recent + [now]
            raise HTTPException(403, "Admin key required")
        admin_failures.pop(ip, None)

    @app.post("/admin/practice-clinics", status_code=201, dependencies=[Depends(require_admin)])
    def admin_create_practice_clinic(body: PracticeClinicIn) -> dict:
        """A clinic of made-up families for staff training (fhg/practice.py). Staff join with the staff code."""
        coordinator, _ = store.create_user("practice clinic")
        org = store.create_org(body.name.strip(), coordinator)
        store.set_org_lang(org["id"], body.lang)
        patients = [coordinator]
        for fam in practice.FAMILIES:
            uid, _ = store.create_user("practice patient")
            store.save_profile(practice.profile(fam, uid))
            store.connect_patient(org["id"], uid, fam.name, "practice")
            patients.append(uid)
        store.mark_practice(org["id"], patients)
        for fam, uid in zip(practice.FAMILIES, patients[1:]):
            for rule_id, status in fam.referrals.items():
                store.set_referral_status(org["id"], uid, rule_id, status, coordinator, None)
        store.audit("admin", "admin", "practice_clinic.created", {"org_id": org["id"]})
        return {"id": org["id"], "name": org["name"], "staff_code": org["staff_code"], "lang": body.lang,
                "patients": len(practice.FAMILIES)}

    @app.get("/admin/practice-clinics", dependencies=[Depends(require_admin)])
    def admin_practice_clinics() -> list[dict]:
        return [{"id": o["id"], "name": o["name"], "staff_code": o["staff_code"], "lang": org_lang(o),
                 "patients": o["patients"], "staff": o["staff"] - 1, "created_at": o["created_at"]}
                for o in store.practice_orgs()]

    @app.delete("/admin/practice-clinics/{org_id}", dependencies=[Depends(require_admin)])
    def admin_delete_practice_clinic(org_id: str) -> dict:
        deleted = store.delete_practice_org(org_id)
        if deleted < 0:
            raise HTTPException(404, "No such practice clinic")
        store.audit("admin", "admin", "practice_clinic.deleted", {"org_id": org_id, "patients": deleted})
        return {"deleted": True, "patients": deleted}

    @app.post("/admin/partners", status_code=201, dependencies=[Depends(require_admin)])
    def admin_create_partner(body: PartnerIn) -> dict:
        partner, api_key, secret = store.create_partner(body.name.strip(), body.kind, body.webhook_url)
        return {"partner": partner, "api_key": api_key, "webhook_secret": secret,
                "note": "Store the API key and webhook secret securely; they are shown only once."}

    @app.get("/admin/partners", dependencies=[Depends(require_admin)])
    def admin_list_partners() -> list[dict]:
        catalogs = store.partner_catalogs()
        return [p | {"catalog": catalogs.get(p["id"], [])} for p in store.partners(active_only=False)]

    @app.post("/admin/partners/{partner_id}/activate", dependencies=[Depends(require_admin)])
    def admin_activate_partner(partner_id: str) -> dict:
        if not store.set_partner_active(partner_id, True):
            raise HTTPException(404, "No such partner")
        return store.partner(partner_id)

    @app.get("/admin/overview", dependencies=[Depends(require_admin)])
    def admin_overview() -> dict:
        """The numbers the console's first screen shows."""
        return {"counts": store.counts(), "bookings": store.booking_metrics(), "environment": settings.environment,
                "scheduler": settings.scheduler, "backups": bool(settings.backup_dir),
                "tests": {code: t["name"] for code, t in bookings.TESTS.items()}, "partner_kinds": list(partners.PARTNER_KINDS)}

    @app.get("/admin/pilot-report", dependencies=[Depends(require_admin)])
    def admin_pilot_report(format: str = Query("json", pattern="^(json|csv)$")) -> Response:
        """Outcomes across every family in the pilot: onboarding, findings, tests, referrals, caregiving, surveys.
        The CSV is for sharing: counts from 1 to 4 are shown as "<5"."""
        r = pilot.report(store)
        if format == "csv":
            return Response(pilot.to_csv(r), media_type="text/csv; charset=utf-8", headers={
                "Content-Disposition": f'attachment; filename="pilot-report-{r["generated_at"][:10]}.csv"',
                "Cache-Control": "no-store"})
        return JSONResponse(r)

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    def admin_console() -> HTMLResponse:
        return HTMLResponse((PKG_DIR / "static" / "admin.html").read_text(),
                            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

    @app.post("/admin/partners/{partner_id}/deactivate", dependencies=[Depends(require_admin)])
    def admin_deactivate_partner(partner_id: str) -> dict:
        if not store.set_partner_active(partner_id, False):
            raise HTTPException(404, "No such partner")
        return store.partner(partner_id)

    # --- Connect with Family Health Graph: consented partner access (docs/FAMILY_HISTORY_API.md) ---
    @app.put("/admin/partners/{partner_id}/oauth", dependencies=[Depends(require_admin)])
    def admin_partner_oauth(partner_id: str, body: PartnerOAuthIn) -> dict:
        if store.partner(partner_id) is None:
            raise HTTPException(404, "No such partner")
        for uri in body.redirect_uris:
            parts = urllib.parse.urlsplit(uri)
            local = parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")
            if not (parts.scheme == "https" or local) or parts.fragment or not parts.netloc:
                raise HTTPException(422, f"Redirect URIs must be https (or http://localhost for development): {uri}")
        secret = store.set_partner_oauth(partner_id, body.redirect_uris, body.confidential)
        return {"client_id": partner_id, "redirect_uris": body.redirect_uris, "client_secret": secret,
                "note": "The client secret is shown once." if secret else "Public client: use PKCE without a secret."}

    def oauth_client(client_id: str, redirect_uri: str) -> dict:
        client = store.partner_oauth(client_id)
        if client is None or redirect_uri not in client["redirect_uris"]:
            raise HTTPException(400, "Unknown app or redirect address")
        return client

    def with_query(uri: str, **params) -> str:
        params = {k: v for k, v in params.items() if v is not None}
        return uri + ("&" if urllib.parse.urlsplit(uri).query else "?") + urllib.parse.urlencode(params)

    @app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
    @app.get("/fhir/r4/.well-known/smart-configuration", include_in_schema=False)
    def oauth_metadata(request: Request) -> dict:
        base = public_base(request)
        return {"issuer": base, "authorization_endpoint": f"{base}/oauth/authorize", "token_endpoint": f"{base}/oauth/token",
                "scopes_supported": list(poauth.SCOPES), "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
                "capabilities": ["launch-standalone", "client-public", "client-confidential-symmetric"]}

    @app.get("/oauth/authorize", include_in_schema=False)
    def oauth_authorize(request: Request, client_id: str = Query(""), redirect_uri: str = Query(""),
                        response_type: str = Query(""), scope: str = Query(""), state: Optional[str] = Query(None),
                        code_challenge: str = Query(""), code_challenge_method: str = Query("")) -> Response:
        """Validates the request, then hands over to the consent screen in the app (where the user is signed in)."""
        client = store.partner_oauth(client_id)
        if client is None or redirect_uri not in client["redirect_uris"]:
            # Never redirect to an unregistered address.
            return HTMLResponse(_connect_page("This app isn't registered with Family Health Graph, or its return "
                                              "address doesn't match. Nothing was shared.", None), status_code=400)
        known, unknown = poauth.parse_scopes(scope)
        if response_type != "code":
            return RedirectResponse(with_query(redirect_uri, error="unsupported_response_type", state=state), 302)
        if unknown or not known:
            return RedirectResponse(with_query(redirect_uri, error="invalid_scope", state=state), 302)
        if code_challenge_method != "S256" or len(code_challenge) < 43:
            return RedirectResponse(with_query(redirect_uri, error="invalid_request",
                                               error_description="PKCE with S256 is required", state=state), 302)
        return RedirectResponse("/app/authorize?" + str(request.url.query), 302)

    @app.get("/v1/oauth/request")
    def oauth_request(client_id: str, redirect_uri: str, scope: str = "", user_id: str = Depends(current_user)) -> dict:
        """What the consent screen shows: who is asking, and for what."""
        client = oauth_client(client_id, redirect_uri)
        known, _ = poauth.parse_scopes(scope)
        existing = next((g for g in store.grants_for_user(user_id) if g["partner_id"] == client_id), None)
        return {"partner": {"id": client["id"], "name": client["name"], "kind": client["kind"]},
                "scopes": [{"scope": s, "description": poauth.SCOPES[s]} for s in known],
                "already_granted": existing["scopes"] if existing else [],
                "expires_in_days": poauth.GRANT_DAYS}

    @app.post("/v1/oauth/approve")
    def oauth_approve(body: OAuthApproveIn, user_id: str = Depends(current_user)) -> dict:
        require_adult(user_id, "Sharing with apps")
        client = oauth_client(body.client_id, body.redirect_uri)
        known, unknown = poauth.parse_scopes(" ".join(body.scopes))
        if unknown or not known or body.code_challenge_method != "S256":
            raise HTTPException(422, "Invalid scopes or PKCE method")
        grant_id = store.upsert_grant(user_id, client["id"], known, poauth.GRANT_DAYS)
        code = secrets.token_urlsafe(32)
        store.save_oauth_code(hash_token(code), grant_id, body.redirect_uri, body.code_challenge, poauth.CODE_MINUTES)
        store.audit(user_id, "user", "partner.consent_granted", {"partner": client["name"], "scopes": known,
                                                                  "grant_id": grant_id})
        return {"redirect_to": with_query(body.redirect_uri, code=code, state=body.state)}

    @app.post("/v1/oauth/deny")
    def oauth_deny(body: OAuthDenyIn, user_id: str = Depends(current_user)) -> dict:
        oauth_client(body.client_id, body.redirect_uri)
        return {"redirect_to": with_query(body.redirect_uri, error="access_denied", state=body.state)}

    def token_error(error: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"error": error}, status_code=status, headers={"Cache-Control": "no-store"})

    def issue_tokens(grant: dict) -> JSONResponse:
        access, refresh = "fhga_" + secrets.token_urlsafe(32), "fhgr_" + secrets.token_urlsafe(32)
        store.save_oauth_token(hash_token(access), grant["id"], "access", poauth.ACCESS_TOKEN_SECONDS)
        remaining = int((datetime.fromisoformat(grant["expires_at"]) - datetime.now(timezone.utc)).total_seconds())
        store.save_oauth_token(hash_token(refresh), grant["id"], "refresh", max(remaining, 0))
        return JSONResponse({"access_token": access, "token_type": "Bearer", "expires_in": poauth.ACCESS_TOKEN_SECONDS,
                             "refresh_token": refresh, "scope": " ".join(grant["scopes"]),
                             "patient": partner_patient_id(grant)},
                            headers={"Cache-Control": "no-store", "Pragma": "no-cache"})

    def partner_patient_id(grant: dict) -> str:
        # Different for every partner, so partners can't link users across each other.
        return pseudonym(settings.pseudonym_secret, f"{grant['partner_id']}:{grant['user_id']}")

    @app.post("/oauth/token", include_in_schema=False)
    async def oauth_token(request: Request) -> JSONResponse:
        form = {k: v[0] for k, v in urllib.parse.parse_qs((await request.body()).decode(errors="replace")).items()}
        client_id, client_secret = form.get("client_id", ""), form.get("client_secret")
        basic = request.headers.get("authorization", "")
        if basic.lower().startswith("basic "):
            try:
                client_id, _, client_secret = base64.b64decode(basic[6:]).decode().partition(":")
                client_id, client_secret = urllib.parse.unquote(client_id), urllib.parse.unquote(client_secret)
            except ValueError:
                return token_error("invalid_client", 401)
        client = store.partner_oauth(client_id)
        if client is None:
            return token_error("invalid_client", 401)
        if client["client_secret_hash"] and not (client_secret and
                                                 hmac.compare_digest(hash_token(client_secret), client["client_secret_hash"])):
            return token_error("invalid_client", 401)
        grant_type = form.get("grant_type")
        if grant_type == "authorization_code":
            code = store.pop_oauth_code(hash_token(form.get("code", "")))
            if code is None or code["redirect_uri"] != form.get("redirect_uri"):
                return token_error("invalid_grant")
            verifier = form.get("code_verifier", "")
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode() \
                if verifier else ""
            grant = store.grant(code["grant_id"])
            if not verifier or not hmac.compare_digest(challenge, code["code_challenge"]) or grant is None \
                    or not grant["active"] or grant["partner_id"] != client_id:
                return token_error("invalid_grant")
            store.audit(grant["user_id"], f"partner:{client_id}", "partner.token_issued", {"partner": client["name"]})
            return issue_tokens(grant)
        if grant_type == "refresh_token":
            old = hash_token(form.get("refresh_token", ""))
            grant = store.oauth_token(old, "refresh")
            if grant is None or grant["partner_id"] != client_id:
                return token_error("invalid_grant")
            store.delete_oauth_token(old)  # rotate refresh tokens
            return issue_tokens(grant)
        return token_error("unsupported_grant_type")

    def partner_grant(authorization: Optional[str] = Header(None)) -> dict:
        token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
        grant = store.oauth_token(hash_token(token), "access") if token else None
        if grant is None:
            raise HTTPException(401, "Missing, expired or revoked access token")
        return grant

    def fhir_json(body: dict, status: int = 200) -> JSONResponse:
        return JSONResponse(body, status_code=status, media_type="application/fhir+json",
                            headers={"Cache-Control": "no-store"})

    @app.get("/fhir/r4/metadata", include_in_schema=False)
    def fhir_metadata(request: Request) -> JSONResponse:
        return fhir_json(poauth.capability_statement(f"{public_base(request)}/fhir/r4"))

    def fhir_read(resource_type: str, grant: dict, request: Request, resource_id: Optional[str] = None) -> JSONResponse:
        scope = poauth.RESOURCE_SCOPE.get(resource_type)
        if scope is None:
            return fhir_json(poauth.outcome("not-supported", f"{resource_type} isn't available"), 404)
        if scope not in grant["scopes"]:
            return fhir_json(poauth.outcome("forbidden", f"The user didn't share {scope}"), 403)
        # The user's own record only: never what linked relatives shared with them.
        profile = store.get_profile(grant["user_id"])
        report = generate_insights(profile) if resource_type == "RiskAssessment" else None
        pid = partner_patient_id(grant)
        items = poauth.resources(resource_type, profile, report, pid)
        store.touch_grant(grant["id"])
        store.audit(grant["user_id"], f"partner:{grant['partner_id']}", "partner.read",
                    {"partner": grant["partner_name"], "resource": resource_type, "count": len(items)})
        if resource_id is not None:
            match = next((r for r in items if r.get("id") == resource_id), None)
            return fhir_json(match) if match else fhir_json(poauth.outcome("not-found", "No such resource"), 404)
        return fhir_json(poauth.searchset(f"{public_base(request)}/fhir/r4", items))

    @app.get("/fhir/r4/{resource_type}", include_in_schema=False)
    def fhir_search(resource_type: str, request: Request, grant: dict = Depends(partner_grant)) -> JSONResponse:
        return fhir_read(resource_type, grant, request)

    @app.get("/fhir/r4/{resource_type}/{resource_id}", include_in_schema=False)
    def fhir_instance(resource_type: str, resource_id: str, request: Request,
                      grant: dict = Depends(partner_grant)) -> JSONResponse:
        return fhir_read(resource_type, grant, request, resource_id)

    @app.get("/v1/grants")
    def list_grants(user_id: str = Depends(current_user)) -> list[dict]:
        """Apps you've allowed to read your family history: what, since when, last used."""
        return [{"id": g["id"], "partner": {"id": g["partner_id"], "name": g["partner_name"], "kind": g["partner_kind"]},
                 "scopes": [{"scope": s, "description": poauth.SCOPES.get(s, s)} for s in g["scopes"]],
                 "created_at": g["created_at"], "expires_at": g["expires_at"], "last_used_at": g["last_used_at"]}
                for g in store.grants_for_user(user_id)]

    @app.delete("/v1/grants/{grant_id}", status_code=204)
    def revoke_grant(grant_id: str, user_id: str = Depends(current_user)) -> Response:
        g = store.grant(grant_id)
        if g is None or g["user_id"] != user_id or not store.revoke_grant(user_id, grant_id):
            raise HTTPException(404, "No such app access")
        store.audit(user_id, "user", "partner.consent_revoked", {"partner": g["partner_name"], "grant_id": grant_id})
        return Response(status_code=204)

    # --- book a test from an action item, results back, reminders (docs/TEST_BOOKING.md) ---
    @app.put("/admin/partners/{partner_id}/catalog", dependencies=[Depends(require_admin)])
    def admin_partner_catalog(partner_id: str, items: list[CatalogItemIn]) -> dict:
        if store.partner(partner_id) is None:
            raise HTTPException(404, "No such partner")
        unknown = [i.test for i in items if i.test not in bookings.TESTS]
        if unknown:
            raise HTTPException(422, f"Unknown tests {unknown}; available: {sorted(bookings.TESTS)}")
        store.set_partner_catalog(partner_id, [i.model_dump() for i in items])
        return {"partner_id": partner_id, "catalog": [i.model_dump() for i in items]}

    @app.get("/admin/bookings/metrics", dependencies=[Depends(require_admin)])
    def admin_booking_metrics() -> list[dict]:
        return store.booking_metrics()

    def booking_out(b: dict) -> dict:
        return {k: v for k, v in b.items() if k not in ("user_id", "contact")} | {
            "test_names": [bookings.TESTS[t]["name"] for t in b["tests"] if t in bookings.TESTS]}

    @app.get("/v1/insights/{rule_id}/tests")
    def insight_tests(rule_id: str, user_id: str = Depends(current_user)) -> dict:
        """Tests that answer this action item, who offers them, and the person's bookings for it."""
        return {"tests": bookings.offers(rule_id, store.partners_with_catalog()),
                "bookings": [booking_out(b) for b in store.bookings_for_user(user_id) if b["rule_id"] == rule_id]}

    @app.post("/v1/bookings", status_code=201)
    def create_booking(body: BookingIn, user_id: str = Depends(current_user)) -> dict:
        """Book tests with a partner. Only the tests, slot and these contact details are shared with them."""
        require_adult(user_id, "Booking with a partner")
        partner = next((p for p in store.partners_with_catalog() if p["id"] == body.partner_id), None)
        if partner is None:
            raise HTTPException(404, "No such lab")
        offered = {i["test"]: i for i in partner["catalog"]}
        missing = [t for t in body.tests if t not in offered]
        if missing:
            raise HTTPException(422, f"{partner['name']} doesn't offer {missing}")
        price = sum(offered[t].get("price_inr") or 0 for t in body.tests) or None
        booking_id = store.create_booking(
            user_id, partner["id"], body.rule_id, body.tests,
            body.preferred_date.isoformat() if body.preferred_date else None, body.slot,
            body.contact.model_dump(), price)
        store.audit(user_id, "user", "booking.created", {"booking_id": booking_id, "partner": partner["name"],
                                                          "tests": body.tests, "shared": ["tests", "slot", "contact"]})
        partner_hooks.notify_event(partner["id"], "booking.created", {"booking_id": booking_id})
        return booking_out(store.booking(booking_id))

    @app.get("/v1/bookings")
    def my_bookings(user_id: str = Depends(current_user)) -> list[dict]:
        return [booking_out(b) for b in store.bookings_for_user(user_id)]

    def own_booking(user_id: str, booking_id: str) -> dict:
        b = store.booking(booking_id)
        if b is None or b["user_id"] != user_id:
            raise HTTPException(404, "No such booking")
        return b

    @app.post("/v1/bookings/{booking_id}/cancel")
    def cancel_booking(booking_id: str, user_id: str = Depends(current_user)) -> dict:
        b = own_booking(user_id, booking_id)
        if b["status"] not in bookings.ACTIVE:
            raise HTTPException(409, "This booking can't be cancelled now")
        store.update_booking(booking_id, status="cancelled", note="Cancelled by the patient")
        store.audit(user_id, "user", "booking.cancelled", {"booking_id": booking_id})
        partner_hooks.notify_event(b["partner_id"], "booking.updated", {"booking_id": booking_id})
        return booking_out(store.booking(booking_id))

    @app.post("/v1/bookings/{booking_id}/done-elsewhere")
    def booking_done_elsewhere(booking_id: str, user_id: str = Depends(current_user)) -> dict:
        """The person had the test somewhere else; stops reminders. Results can be added as a document."""
        b = own_booking(user_id, booking_id)
        if b["status"] not in bookings.ACTIVE:
            raise HTTPException(409, "This booking is already closed")
        store.update_booking(booking_id, status="completed_elsewhere")
        partner_hooks.notify_event(b["partner_id"], "booking.updated", {"booking_id": booking_id})
        return booking_out(store.booking(booking_id))

    def partner_booking(partner: dict, booking_id: str) -> dict:
        b = store.booking(booking_id, with_contact=True)
        if b is None or b["partner_id"] != partner["id"]:
            raise HTTPException(404, "No such booking")
        return b

    def partner_booking_out(b: dict) -> dict:
        return {"booking_id": b["id"], "status": b["status"], "tests": [
            {"code": t, "name": bookings.TESTS[t]["name"], "prep": bookings.TESTS[t]["prep"]} for t in b["tests"]],
            "preferred_date": b["preferred_date"], "slot": b["slot"], "scheduled_for": b["scheduled_for"],
            "price_inr": b["price_inr"], "contact": b["contact"], "created_at": b["created_at"]}

    @app.get("/v1/partner/bookings")
    def partner_bookings(status: Optional[str] = Query(None), partner: dict = Depends(current_partner)) -> list[dict]:
        return [partner_booking_out(b) for b in store.bookings_for_partner(partner["id"], status)]

    @app.get("/v1/partner/bookings/{booking_id}")
    def partner_booking_detail(booking_id: str, partner: dict = Depends(current_partner)) -> dict:
        b = partner_booking(partner, booking_id)
        store.audit(b["user_id"], f"partner:{partner['id']}", "booking.viewed", {"partner": partner["name"]})
        return partner_booking_out(b)

    @app.post("/v1/partner/bookings/{booking_id}/status")
    def partner_booking_status(booking_id: str, body: BookingStatusIn, partner: dict = Depends(current_partner)) -> dict:
        b = partner_booking(partner, booking_id)
        if b["status"] not in bookings.ACTIVE:
            raise HTTPException(409, f"The booking is {b['status']}")
        store.update_booking(booking_id, status=body.status,
                             scheduled_for=body.scheduled_for.isoformat() if body.scheduled_for else None, note=body.note)
        store.audit(b["user_id"], f"partner:{partner['id']}", f"booking.{body.status}", {"partner": partner["name"]})
        names = [bookings.TESTS[t]["name"].split(" (")[0] for t in b["tests"]]
        template = {"scheduled": N.BOOKING_CONFIRMED_ON if body.scheduled_for else N.BOOKING_CONFIRMED,
                    "sample_collected": N.BOOKING_SAMPLE, "completed": N.BOOKING_DONE,
                    "cancelled": N.BOOKING_CANCELLED_NOTE if body.note else N.BOOKING_CANCELLED}[body.status]
        msg = N.say(store.user_lang(b["user_id"]), template, translate=("tests",), partner=partner["name"], tests=names,
                    date=formatday(body.scheduled_for.isoformat()) if body.scheduled_for else "", note=body.note or "")
        notifier.notify(b["user_id"], "booking", msg)
        return partner_booking_out(store.booking(booking_id, with_contact=True))

    @app.post("/v1/partner/bookings/{booking_id}/results")
    def partner_booking_results(booking_id: str, bundle: dict, partner: dict = Depends(current_partner)) -> dict:
        """Results as FHIR R4 Observations (a Bundle or one Observation), LOINC-coded. They go straight into the
        person's record and the booking is completed."""
        b = partner_booking(partner, booking_id)
        if b["status"] not in bookings.ACTIVE and b["status"] != "completed":
            raise HTTPException(409, f"The booking is {b['status']}")
        try:
            fragment = parse_fhir(bundle, source=f"partner:{partner['id']}:booking:{booking_id}")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        allowed = set().union(*(bookings.TESTS[t]["observations"] for t in b["tests"]))
        kept = [o for o in fragment.observations if o.code in allowed]
        if not kept:
            raise HTTPException(422, f"No results for the booked tests; expected LOINC-coded {sorted(allowed)}")
        result = ingest(b["user_id"], "partner_results", json.dumps({"booking_id": booking_id}),
                        HealthProfile(observations=kept), preview=False)
        store.update_booking(booking_id, status="completed")
        store.audit(b["user_id"], f"partner:{partner['id']}", "booking.results", {"partner": partner["name"],
                                                                                   "results": len(kept)})
        notifier.notify(b["user_id"], "booking", N.say(store.user_lang(b["user_id"]), N.RESULTS_IN, partner=partner["name"]))
        return {"accepted": len(kept), "ignored": len(fragment.observations) - len(kept), "merged": result["merged"]}

    @app.post("/admin/tasks/reminders", dependencies=[Depends(require_admin)])
    def run_reminders() -> dict:
        """Follow up until tests are booked and done. Run daily (e.g. a Render cron job calling this endpoint)."""
        now, sent = bookings.utcnow(), 0
        for uid in store.user_ids():
            mine = store.bookings_for_user(uid)
            lang = store.user_lang(uid)
            with insight_language(lang):
                report = generate_insights(effective_profile(store, uid))
            for key, kind, message in bookings.due_reminders(now, report.insights, mine, store.nudges(uid), lang):
                notifier.notify(uid, kind, message)
                store.record_nudge(uid, key, now.isoformat())
                sent += 1
        return {"sent": sent}

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
        return org_public(clinic_by_code_or_404(code))

    @app.post("/v1/clinics", status_code=201)
    def connect_clinic(body: ClinicConnectIn, user_id: str = Depends(current_user)) -> dict:
        org = clinic_by_code_or_404(body.code)
        store.connect_patient(org["id"], user_id, body.display_name.strip(), body.source)
        store.audit(user_id, "user", "clinic.connected",
                    {"org_id": org["id"], "org": org["name"], "via": body.source})
        return org_public(org)

    @app.get("/v1/clinics")
    def my_clinics(user_id: str = Depends(current_user)) -> list[dict]:
        return store.orgs_for_patient(user_id)

    @app.delete("/v1/clinics/{org_id}", status_code=204)
    def disconnect_clinic(org_id: str, user_id: str = Depends(current_user)) -> None:
        if not store.disconnect_patient(org_id, user_id):
            raise HTTPException(404, "Not connected to that clinic")
        store.audit(user_id, "user", "clinic.disconnected", {"org_id": org_id})

    # --- pre-visit intake link (public: the clinic code is meant to be printed) ---------------
    def clinic_by_code_or_404(code: str) -> dict:
        org = store.org_by_code("patient", code)
        if org is None or org.get("practice"):           # a practice clinic's patients are made up; no real ones join
            raise HTTPException(404, "No clinic has that code")
        return org

    @app.get("/v1/public/clinics/{code}")
    def public_clinic(code: str) -> dict:
        """Just the clinic's name, so the intake page can say who you're sharing with."""
        org = clinic_by_code_or_404(code)
        return {"name": org["name"], "code": org["patient_code"], "lang": org_lang(org)}

    @app.get("/c/{code}", response_class=HTMLResponse, include_in_schema=False)
    def intake_page(code: str) -> str:
        clinic_by_code_or_404(code)
        return (PKG_DIR / "static" / "intake.html").read_text()

    @app.get("/c/{code}/qr.svg", include_in_schema=False)
    def intake_qr(code: str, request: Request):
        import io

        import segno

        org = clinic_by_code_or_404(code)
        buf = io.BytesIO()
        segno.make(intake_url(org, request), error="m").save(buf, kind="svg", scale=6, border=2,
                                                             dark="#1d1d1b", xmldecl=False)
        return Response(buf.getvalue(), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/c/{code}/poster", response_class=HTMLResponse, include_in_schema=False)
    def intake_poster(code: str, request: Request) -> str:
        from html import escape as esc

        org = clinic_by_code_or_404(code)
        url = intake_url(org, request)
        return (PKG_DIR / "static" / "poster.html").read_text().replace(
            "{{CLINIC}}", esc(org["name"])).replace("{{URL}}", esc(url)).replace(
            "{{CODE}}", esc(org["patient_code"])).replace("{{LANG}}", org_lang(org)).replace(
            "{{LANGNAME}}", LANG_NAME[org_lang(org)])

    @app.get("/c/{code}/staff-guide", response_class=HTMLResponse, include_in_schema=False)
    def intake_staff_guide(code: str, request: Request) -> str:
        """A printable one-pager for the clinic's staff: reception script (English and the clinic's language), patient questions,
        using the portal, do's and don'ts. Uses only the public patient code, never the staff code."""
        from html import escape as esc

        org = clinic_by_code_or_404(code)
        return (PKG_DIR / "static" / "staff-guide.html").read_text().replace(
            "{{CLINIC}}", esc(org["name"])).replace("{{URL}}", esc(intake_url(org, request))).replace(
            "{{CODE}}", esc(org["patient_code"])).replace("{{PORTAL}}", esc(public_base(request) + "/portal")).replace(
            "{{PRIVACY}}", esc(settings.grievance_officer_email or "Settings → Your privacy rights in the app")).replace(
            "{{LANG}}", org_lang(org)).replace("{{LANGNAME}}", LANG_NAME[org_lang(org)])

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
        if body.granted:
            require_adult(user_id, "This option")
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
        notifier.notify(inv["inviter_id"], "invitation_accepted", N.say(
            store.user_lang(inv["inviter_id"]), N.INVITE_ACCEPTED if body.share_level != "none" else N.INVITE_ACCEPTED_NOT_SHARING,
            translate=("who",), who=(inv["relationship"] or "relative").replace("_", " ")))
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

    # --- direct ABHA link (ABDM, through NHA's ABDM Wrapper) --------------------------------------
    abdm_client = (abdm.WrapperClient(settings.abdm_wrapper_url, settings.abdm_hiu_id, settings.abdm_requester_name,
                                      abdm_http or abdm.UrllibJsonHttp())
                   if settings.abdm_wrapper_url and settings.abdm_hiu_id else None)

    @app.post("/v1/connect/abha", status_code=201)
    def connect_abha(body: AbhaIn, user_id: str = Depends(current_user)) -> dict:
        """Ask for consent to pull records from ABDM-linked hospitals and labs. The person approves the request
        in their ABHA app; then 'Sync now' imports the records."""
        if abdm_client is None:
            raise HTTPException(404, "ABHA linking isn't set up on this server")
        address = body.abha_address.strip().lower()
        if not abdm.valid_abha_address(address):
            raise HTTPException(422, "Enter your ABHA address, like name@abdm")
        try:
            request_id = abdm_client.consent_init(address)
        except abdm.AbdmError as exc:
            raise HTTPException(502, str(exc)) from exc
        conn_id = store.create_connection(user_id, "abdm", "abdm", f"ABHA · {address}",
                                          {"abha_address": address, "consent_request_id": request_id, "fetches": {},
                                           "imported": []}, status="pending")
        store.audit(user_id, "user", "connection.started", {"provider": "abdm"})
        return {"id": conn_id, "status": "pending",
                "message": "Open your ABHA app (or the PHR app you use) and approve the request from "
                           f"{settings.abdm_requester_name}. Then tap Sync now."}

    def abdm_sync(user_id: str, conn: dict) -> dict:
        if abdm_client is None:
            raise HTTPException(409, "ABHA linking isn't set up on this server")
        secret = conn["secret"]
        state = abdm_client.consent_status(secret["consent_request_id"])
        if state.status in ("DENIED", "REVOKED", "EXPIRED"):
            store.update_connection(conn["id"], status=state.status.lower())
            raise HTTPException(409, {"DENIED": "The request was declined in the ABHA app.",
                                      "REVOKED": "Access was withdrawn in the ABHA app.",
                                      "EXPIRED": "The request expired. Remove this connection and start again."}[state.status])
        if state.status != "GRANTED":
            msg = state.message or "Waiting for you to approve the request in your ABHA app."
            store.update_connection(conn["id"], status="pending", sync_summary={"waiting": msg})
            return {"status": "pending", "message": msg, "merged": None}
        totals = {"conditions": 0, "medications": 0, "observations": 0, "relatives_added": 0}
        pending = 0
        try:
            for art in state.artefacts:
                if art["id"] in secret["imported"]:
                    continue
                if art["id"] not in secret["fetches"]:
                    secret["fetches"][art["id"]] = abdm_client.fetch_records(art["id"])
                records = abdm_client.records_status(secret["fetches"][art["id"]])
                if not records.done:
                    pending += 1
                    continue
                for bundle in records.bundles:
                    try:
                        fragment = parse_fhir(bundle, source=f"abdm:{art.get('hip_id') or 'hip'}")
                    except ValueError:
                        continue
                    merged = ingest(user_id, "abdm", json.dumps({"connection": conn["id"], "hip": art.get("hip_id")}),
                                    fragment, preview=False)["merged"]
                    for k in totals:
                        totals[k] += merged.get(k, 0)
                secret["imported"].append(art["id"])
        except abdm.AbdmError as exc:
            store.update_connection(conn["id"], secret=secret, status="error")
            raise HTTPException(502, str(exc)) from exc
        status = "pending" if pending else "active"
        store.update_connection(conn["id"], secret=secret, status=status,
                                sync_summary={"sources": len(state.artefacts), "waiting_for": pending, "merged": totals})
        return {"status": status, "merged": totals,
                "message": (f"Still fetching from {pending} source{'s' * (pending != 1)}; sync again in a minute."
                            if pending else "Records imported.")}

    # --- privacy rights (DPDP Act) -------------------------------------------------------------
    @app.get("/v1/privacy/notice")
    def privacy_notice(lang: str = Query("en", pattern="^[a-z]{2}$")) -> dict:
        """The privacy notice, in English or Hindi. Public: shown before an account exists."""
        return privacy.notice(lang, settings.data_fiduciary, settings.grievance_officer_name,
                              settings.grievance_officer_email, settings.grievance_days)

    @app.get("/v1/privacy")
    def privacy_summary(user_id: str = Depends(current_user)) -> dict:
        """What we hold about you, who it has been shared with, your consents, nominee and concerns (DPDP s.11)."""
        profile = store.get_profile(user_id)
        shared = []
        for link in store.links_for(user_id):
            if link["i_share"] != "none":
                shared.append({"with": f"Your {link['relationship'].replace('_', ' ')} (linked account)",
                               "what": "Your conditions" + (" and family tree" if link["i_share"] == "conditions_and_tree" else ""),
                               "since": link["created_at"]})
        for org in store.orgs_for_patient(user_id):
            shared.append({"with": f"{org['name']} (clinic)", "what": "Your record and insights", "since": org["connected_at"]})
        for g in store.grants_for_user(user_id):
            shared.append({"with": f"{g['partner_name']} (app)", "what": ", ".join(poauth.SCOPES.get(x, x) for x in g["scopes"]),
                           "since": g["created_at"], "until": g["expires_at"]})
        for r in store.referrals_for_patient(user_id):
            if r["partner_name"]:
                shared.append({"with": f"{r['partner_name']} (referral from {r['org_name']})",
                               "what": "The referral and your summary", "since": r["updated_at"]})
        for b in store.bookings_for_user(user_id):
            shared.append({"with": f"{b['partner_name']} (test booking)", "what": "The tests, slot and contact details you gave",
                           "since": b["created_at"]})
        for res in store.risk_results(user_id):
            shared.append({"with": f"{res['partner_name']} (counseling)", "what": "Your family tree as a CanRisk file",
                           "since": res["created_at"]})
        for m in profile.family:
            for g in store.caregivers(user_id, m.id):
                shared.append({"with": f"{g['name'] or 'A family member'} (care circle for {m.name or m.label})",
                               "what": f"{m.name or m.label}'s medicines and emergency details", "since": g["joined_at"]})
        processors = [{"name": "Document reading with AI (only if you turned it on)", "active": store.has_consent(user_id, CONSENT_AI_DOCS)}]
        return {"held": privacy.held(profile, len(store.documents(user_id))),
                "connections": [{"name": c["display_name"], "status": c["status"]} for c in store.connections(user_id)],
                "shared_with": shared, "processors": processors, "consents": store.consents(user_id),
                "nominee": store.nominee(user_id), "grievances": store.grievances(user_id=user_id),
                "minor": privacy.is_minor(profile),
                "contact": {"name": settings.grievance_officer_name, "email": settings.grievance_officer_email,
                            "response_days": settings.grievance_days}}

    @app.get("/v1/privacy/export")
    def privacy_export(user_id: str = Depends(current_user)) -> Response:
        """Everything about you in one JSON file: record, documents list, consents, sharing, bookings, care,
        notifications and the access log."""
        out = {"exported_at": datetime.now(timezone.utc).isoformat(), "profile": _dump(store.get_profile(user_id)),
               "documents": store.documents(user_id), "consents": store.consents(user_id),
               "grants": [{k: g[k] for k in ("partner_name", "scopes", "created_at", "expires_at")} for g in store.grants_for_user(user_id)],
               "connections": [{k: c[k] for k in ("display_name", "kind", "status", "created_at")} for c in store.connections(user_id)],
               "bookings": store.bookings_for_user(user_id), "risk_assessments": store.risk_results(user_id),
               "nominee": store.nominee(user_id), "grievances": store.grievances(user_id=user_id),
               "survey_answers": store.survey_answers(user_id),
               "notifications": store.notifications(user_id), "access_log": store.audit_log(user_id)}
        store.audit(user_id, "user", "privacy.export")
        return Response(json.dumps(out, default=str, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="my-family-health-graph-data.json"',
                                 "Cache-Control": "no-store"})

    @app.put("/v1/privacy/nominee")
    def set_nominee(body: NomineeIn, user_id: str = Depends(current_user)) -> dict:
        """Someone who can exercise your rights if you die or can't (DPDP s.14)."""
        store.set_nominee(user_id, body.model_dump())
        store.audit(user_id, "user", "privacy.nominee_set")
        return store.nominee(user_id)

    @app.delete("/v1/privacy/nominee", status_code=204)
    def remove_nominee(user_id: str = Depends(current_user)) -> Response:
        store.set_nominee(user_id, None)
        store.audit(user_id, "user", "privacy.nominee_removed")
        return Response(status_code=204)

    @app.post("/v1/privacy/grievances", status_code=201)
    def raise_grievance(body: GrievanceIn, user_id: str = Depends(current_user)) -> dict:
        due = datetime.now(timezone.utc) + timedelta(days=settings.grievance_days)
        gid = store.create_grievance(user_id, body.category, body.message, due.isoformat())
        store.audit(user_id, "user", "privacy.grievance", {"id": gid, "category": body.category})
        return {"id": gid, "status": "open", "due_at": due.isoformat(),
                "message": f"We'll answer within {settings.grievance_days} days."}

    @app.get("/admin/grievances", dependencies=[Depends(require_admin)])
    def admin_grievances(status: Optional[str] = Query("open")) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        return [g | {"overdue": g["status"] == "open" and g["due_at"] < now} for g in store.grievances(status=status)]

    @app.post("/admin/grievances/{gid}/answer", dependencies=[Depends(require_admin)])
    def admin_answer_grievance(gid: str, body: GrievanceAnswerIn) -> dict:
        g = store.resolve_grievance(gid, body.response, body.status)
        if g is None:
            raise HTTPException(404, "No such grievance")
        store.audit(g["user_id"], "privacy_officer", "privacy.grievance_answered", {"id": gid, "status": body.status})
        notifier.notify(g["user_id"], "privacy", N.say(store.user_lang(g["user_id"]), N.PRIVACY_ANSWER, answer=body.response))
        return g

    @app.post("/admin/breaches", status_code=201, dependencies=[Depends(require_admin)])
    def admin_record_breach(body: BreachIn) -> dict:
        """Record a personal data breach and tell every affected person (DPDP s.8(6)). Intimating the Data
        Protection Board is done outside the app; record it with /admin/breaches/{id}/board."""
        if body.all_users:
            affected = store.user_ids()
        elif body.affected_user_ids:
            known = set(store.user_ids())
            affected = [u for u in body.affected_user_ids if u in known]
        else:
            raise HTTPException(422, "Give affected_user_ids, or all_users: true")
        contact = settings.grievance_officer_email or "the privacy contact in Settings → Privacy"
        message = (f"Security notice: {body.nature} Information affected: {', '.join(body.data_affected)}. "
                   f"What this may mean: {body.likely_consequences} What we've done: {body.measures_taken} "
                   f"What you can do: {body.what_you_can_do} Questions: {contact}.")
        bid = store.record_breach(body.model_dump(mode="json", exclude={"affected_user_ids", "all_users"}) | {"notice": message},
                                  body.occurred_at.isoformat() if body.occurred_at else None, body.detected_at.isoformat(),
                                  len(affected))
        for uid in affected:
            notifier.notify(uid, "security", message)
            store.audit(uid, "privacy_officer", "privacy.breach_notified", {"breach": bid})
        return {"id": bid, "notified": len(affected)}

    @app.get("/admin/breaches", dependencies=[Depends(require_admin)])
    def admin_breaches() -> list[dict]:
        return store.breaches()

    @app.post("/admin/breaches/{bid}/board/{stage}", dependencies=[Depends(require_admin)])
    def admin_breach_board(bid: str, stage: str) -> dict:
        if stage not in ("intimation", "report") or not store.mark_breach_board(bid, stage):
            raise HTTPException(404, "No such breach or stage (intimation | report)")
        return next(b for b in store.breaches() if b["id"] == bid)

    @app.post("/admin/tasks/housekeeping", dependencies=[Depends(require_admin)])
    def run_housekeeping() -> dict:
        """Delete expired codes, tokens, invites and links. Run daily."""
        return {"deleted": store.housekeeping()}


    # --- caregiver mode ------------------------------------------------------------------------
    # A "care id" is "<owner user id>.<relative id>": the relative lives on the owner's record; caregivers in the
    # owner's care circle for that relative can see their medicines, mark doses and keep the emergency details.
    def care_target(user_id: str, care_id: str) -> tuple[str, str, str]:
        owner_id, _, member_id = care_id.partition(".")
        if owner_id == user_id:
            role = "owner"
        elif owner_id and store.is_caregiver(owner_id, member_id, user_id):
            role = "caregiver"
        else:
            raise HTTPException(404, "No such person")
        if not any(m.id == member_id for m in store.get_profile(owner_id).family):
            raise HTTPException(404, "No such person")
        return owner_id, member_id, role

    def care_member(owner_id: str, member_id: str) -> FamilyMember:
        return next(m for m in store.get_profile(owner_id).family if m.id == member_id)

    def care_name(m: FamilyMember) -> str:
        return m.name or m.label

    def care_name_in(m: FamilyMember, lang: str) -> str:
        """The relative's name, or their relationship in the reader's language."""
        return m.name or N.say(lang, "{who}", translate=("who",), who=m.label)

    def member_of(owner_id: str, member_id: str) -> FamilyMember:
        return care_member(owner_id, member_id)

    def care_wa_out(row: Optional[dict]) -> Optional[dict]:
        if row is None:
            return None
        return {"phone": "•••• " + row["phone"][-4:], "lang": row["lang"], "status": row["status"],
                "updated_at": row["updated_at"]}

    def care_out(owner_id: str, member_id: str, role: str, user_id: str) -> dict:
        m = care_member(owner_id, member_id)
        today = datetime.now(care.IST).date()
        log = store.dose_log(owner_id, member_id, (today - timedelta(days=7)).isoformat())
        names = {owner_id: "Owner", "whatsapp": care_name(m) + " (WhatsApp)"} | {c["user_id"]: c["name"] or "Caregiver" for c in store.caregivers(owner_id, member_id)}
        for e in log:
            e["by_name"] = "you" if e["by_user"] == user_id else names.get(e["by_user"], "someone")
        meds = []
        for med in m.medications:
            s = care.schedule_for(med)
            meds.append({"id": med.id, "name": med.name, "generic": med.generic, "drug_class": med.drug_class,
                         "dosage": med.dosage, "status": med.status, "reminders": med.reminders,
                         "schedule": s.slots, "as_needed": s.as_needed, "food": s.food, "understood": s.understood,
                         "course_days": s.days, "prescribed_on": med.prescribed_on, "stock": med.stock,
                         "stock_on": med.stock_on, "refill": care.refill(med, today)})
        week = []
        for back in range(6, -1, -1):
            d = today - timedelta(days=back)
            doses = care.doses_for_day(m, d, log)
            week.append({"day": d.isoformat(), "taken": sum(x["status"] == "taken" for x in doses), "scheduled": len(doses)})
        return {"care_id": f"{owner_id}.{member_id}", "role": role, "name": care_name(m), "relationship": m.label,
                "relationship_code": m.relationship.value, "has_name": bool(m.name),
                "member_id": member_id, "today": care.doses_for_day(m, today, log), "week": week,
                "medications": meds, "info": (m.care or CareInfo()).model_dump(),
                "caregivers": store.caregivers(owner_id, member_id) if role == "owner" else [],
                "emergency_links": store.emergency_links(owner_id, member_id),
                "whatsapp": care_wa_out(store.care_whatsapp(owner_id, member_id))}

    @app.get("/v1/care")
    def care_list(user_id: str = Depends(current_user)) -> list[dict]:
        """Everyone you help look after: relatives on your record with medicines or care details, and relatives
        others have added you to the care circle for."""
        out = []
        for m in store.get_profile(user_id).family:
            if m.medications or m.care:
                out.append(care_out(user_id, m.id, "owner", user_id))
        for owner_id, member_id in store.caring_for(user_id):
            if any(x.id == member_id for x in store.get_profile(owner_id).family):
                out.append(care_out(owner_id, member_id, "caregiver", user_id))
        return [{k: c[k] for k in ("care_id", "role", "name", "relationship", "relationship_code", "has_name", "today")}
                | {"refills_due": sum(1 for med in c["medications"] if med["refill"] and med["refill"]["due"])}
                for c in out]

    @app.get("/v1/care/{care_id}")
    def care_detail(care_id: str, user_id: str = Depends(current_user)) -> dict:
        owner_id, member_id, role = care_target(user_id, care_id)
        return care_out(owner_id, member_id, role, user_id)

    @app.put("/v1/care/{care_id}/info")
    def care_set_info(care_id: str, body: CareInfo, user_id: str = Depends(current_user)) -> dict:
        owner_id, member_id, role = care_target(user_id, care_id)
        with store.write_lock:
            profile = store.get_profile(owner_id)
            member = next(m for m in profile.family if m.id == member_id)
            member.care = body
            profile.touch()
            store.save_profile(profile)
        store.audit(owner_id, user_id if role == "caregiver" else "user", "care.info", {"member_id": member_id})
        return care_out(owner_id, member_id, role, user_id)

    def edit_member_meds(care_id: str, user_id: str, change) -> dict:
        owner_id, member_id, role = care_target(user_id, care_id)
        with store.write_lock:
            profile = store.get_profile(owner_id)
            member = next(m for m in profile.family if m.id == member_id)
            what = change(member)
            profile.touch()
            store.save_profile(profile)
        store.audit(owner_id, user_id if role == "caregiver" else "user", f"care.{what}", {"member_id": member_id})
        return care_out(owner_id, member_id, role, user_id)

    @app.post("/v1/care/{care_id}/medications", status_code=201)
    def care_add_medication(care_id: str, body: CareMedicationIn, user_id: str = Depends(current_user)) -> dict:
        from .medicines import lookup as lookup_medicine

        def add(member: FamilyMember) -> str:
            info = lookup_medicine(body.name)
            member.medications.append(Medication(
                name=body.name, dosage=body.dosage, generic=info.generic if info else None,
                drug_class=info.drug_class if info else None, prescribed_on=datetime.now(care.IST).date(),
                reminders=True, stock=body.stock, stock_on=datetime.now(care.IST).date() if body.stock is not None else None,
                source="caregiver"))
            return "medication_add"
        return edit_member_meds(care_id, user_id, add)

    @app.patch("/v1/care/{care_id}/medications/{med_id}")
    def care_update_medication(care_id: str, med_id: str, body: CareMedicationPatch,
                               user_id: str = Depends(current_user)) -> dict:
        changes = body.model_dump(exclude_unset=True)
        if "schedule" in changes and changes["schedule"]:
            if set(changes["schedule"]) - set(care.SLOTS) or any(v < 0 or v > 10 for v in changes["schedule"].values()):
                raise HTTPException(422, "Schedule slots are morning, afternoon and night, 0-10 each")

        def update(member: FamilyMember) -> str:
            med = next((x for x in member.medications if x.id == med_id), None)
            if med is None:
                raise HTTPException(404, "No such medicine")
            for key, value in changes.items():
                if key == "schedule":
                    med.schedule = value or None
                elif key == "stock":
                    med.stock, med.stock_on = value, datetime.now(care.IST).date() if value is not None else None
                else:
                    setattr(med, key, value)
            return "medication_update"
        return edit_member_meds(care_id, user_id, update)

    @app.post("/v1/care/{care_id}/doses")
    def care_mark_dose(care_id: str, body: DoseIn, user_id: str = Depends(current_user)) -> dict:
        owner_id, member_id, role = care_target(user_id, care_id)
        member = care_member(owner_id, member_id)
        today = datetime.now(care.IST).date()
        day = body.day or today
        if day > today or day < today - timedelta(days=7):
            raise HTTPException(422, "Doses can be marked for today and the past 7 days")
        med = next((x for x in member.medications if x.id == body.med_id), None)
        if med is None or body.slot not in care.schedule_for(med).slots:
            raise HTTPException(404, "That medicine isn't scheduled then")
        store.log_dose(owner_id, member_id, body.med_id, day.isoformat(), body.slot, body.status, user_id)
        return care_out(owner_id, member_id, role, user_id)

    @app.post("/v1/care/{care_id}/invite")
    def care_invite(care_id: str, request: Request, user_id: str = Depends(current_user)) -> dict:
        """A one-time link (valid 7 days) for a sibling or other family member to join the care circle."""
        owner_id, member_id, role = care_target(user_id, care_id)
        if role != "owner":
            raise HTTPException(403, "Only the person who added this relative can invite others")
        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        store.create_care_invite(hash_token(token), owner_id, member_id, expires.isoformat())
        store.audit(owner_id, "user", "care.invite", {"member_id": member_id})
        name = care_name(care_member(owner_id, member_id))
        url = f"{public_base(request)}/app/care-join/{token}"
        return {"token": token, "url": url, "expires_at": expires.isoformat(),
                "message": f"Help me look after {name} in Family Health Graph: {url}"}

    @app.post("/v1/care/join/{token}")
    def care_join(token: str, body: Optional[CareJoinIn] = None, user_id: str = Depends(current_user)) -> dict:
        target = store.use_care_invite(hash_token(token))
        if target is None:
            raise HTTPException(404, "This invitation has expired or was already used")
        owner_id, member_id = target
        if owner_id == user_id:
            raise HTTPException(409, "This is your own relative")
        store.add_caregiver(owner_id, member_id, user_id, body.name if body else None)
        store.audit(owner_id, user_id, "care.joined", {"member_id": member_id})
        name = care_name(care_member(owner_id, member_id))
        lang = store.user_lang(owner_id)
        joiner = body.name if body and body.name else N.say(lang, N.SOMEONE)
        notifier.notify(owner_id, "care", N.say(lang, N.CARE_JOINED, name=joiner, who=care_name_in(member_of(owner_id, member_id), lang)))
        return care_out(owner_id, member_id, "caregiver", user_id)

    @app.delete("/v1/care/{care_id}/caregivers/{caregiver_id}", status_code=204)
    def care_remove(care_id: str, caregiver_id: str, user_id: str = Depends(current_user)) -> Response:
        """The owner removes a caregiver, or a caregiver leaves (caregiver_id "me")."""
        owner_id, member_id, role = care_target(user_id, care_id)
        who = user_id if caregiver_id == "me" else caregiver_id
        if role != "owner" and who != user_id:
            raise HTTPException(403, "Only the owner can remove others")
        if not store.remove_caregiver(owner_id, member_id, who):
            raise HTTPException(404, "Not in the care circle")
        store.audit(owner_id, user_id if role == "caregiver" else "user", "care.left", {"member_id": member_id})
        return Response(status_code=204)

    @app.get("/v1/care/{care_id}/summary", response_class=HTMLResponse)
    def care_summary(care_id: str, user_id: str = Depends(current_user)) -> HTMLResponse:
        """The printable one-page emergency summary."""
        owner_id, member_id, role = care_target(user_id, care_id)
        store.audit(owner_id, user_id if role == "caregiver" else "user", "care.summary", {"member_id": member_id})
        return HTMLResponse(emergency.render_html(emergency.summary(care_member(owner_id, member_id))),
                            headers={"Cache-Control": "no-store"})

    @app.post("/v1/care/{care_id}/emergency-links", status_code=201)
    def care_emergency_link(care_id: str, request: Request, body: Optional[EmergencyLinkIn] = None,
                            user_id: str = Depends(current_user)) -> dict:
        """A link to the emergency summary that works without signing in, for 1-72 hours. Revocable; every
        opening is logged and the family is notified."""
        owner_id, member_id, role = care_target(user_id, care_id)
        hours = body.hours if body else 24
        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(hours=hours)
        link_id = store.create_emergency_link(hash_token(token), owner_id, member_id, user_id, expires.isoformat())
        store.audit(owner_id, user_id if role == "caregiver" else "user", "care.emergency_link",
                    {"member_id": member_id, "hours": hours})
        return {"id": link_id, "url": f"{public_base(request)}/e/{token}", "expires_at": expires.isoformat()}

    @app.delete("/v1/care/{care_id}/emergency-links/{link_id}", status_code=204)
    def care_revoke_link(care_id: str, link_id: str, user_id: str = Depends(current_user)) -> Response:
        owner_id, member_id, _ = care_target(user_id, care_id)
        if not store.revoke_emergency_link(owner_id, member_id, link_id):
            raise HTTPException(404, "No such link")
        return Response(status_code=204)

    @app.put("/v1/care/{care_id}/whatsapp")
    def care_whatsapp_on(care_id: str, body: CareWhatsAppIn, user_id: str = Depends(current_user)) -> dict:
        """Send medicine reminders to the cared-for person's own WhatsApp. They get an invitation (an approved
        template) and only start receiving reminders after replying YES."""
        owner_id, member_id, role = care_target(user_id, care_id)
        if not wa_client:
            raise HTTPException(409, "WhatsApp isn't set up on this server")
        if not body.agreed:
            raise HTTPException(422, "Ask them first: reminders only go to people who agreed")
        try:
            phone = care.normalize_phone(body.phone)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        try:
            wa_client.send_template(phone, settings.whatsapp_template_care_optin, body.lang, [])
        except Exception as exc:  # noqa: BLE001 (report the provider's failure, don't crash)
            log.warning("WhatsApp invitation failed: %s", exc)
            raise HTTPException(502, "WhatsApp didn't accept the invitation. Check the number and try again.") from exc
        store.set_care_whatsapp(owner_id, member_id, inbound.phone_key(settings.auth_secret, phone), phone, body.lang,
                                "invited", user_id)
        store.audit(owner_id, user_id if role == "caregiver" else "user", "care.whatsapp_invited", {"member_id": member_id})
        return care_out(owner_id, member_id, role, user_id)

    @app.delete("/v1/care/{care_id}/whatsapp")
    def care_whatsapp_off(care_id: str, user_id: str = Depends(current_user)) -> dict:
        owner_id, member_id, role = care_target(user_id, care_id)
        if store.care_whatsapp(owner_id, member_id) is None:
            raise HTTPException(404, "WhatsApp reminders aren't set up for them")
        store.set_care_whatsapp_status(owner_id, member_id, "stopped")
        store.audit(owner_id, user_id if role == "caregiver" else "user", "care.whatsapp_stopped", {"member_id": member_id})
        return care_out(owner_id, member_id, role, user_id)

    def handle_care_whatsapp(msg: inbound.WhatsAppMessage, rows: list[dict]) -> None:
        """A reply from someone who gets medicine reminders: YES to start, STOP to end, 1 to mark doses taken."""
        lang = rows[0]["lang"]
        text = msg.text.strip().lower().rstrip(".!")
        send = lambda key, **v: wa_client.send_text(msg.sender, care.wa_text(lang, key, **v))  # noqa: E731
        if text in care.WA_STOP:
            for r in rows:
                store.set_care_whatsapp_status(r["owner_id"], r["member_id"], "stopped")
                store.audit(r["owner_id"], "whatsapp", "care.whatsapp_stopped", {"member_id": r["member_id"]})
            send("stopped")
        elif text in care.WA_YES:
            for r in rows:
                store.set_care_whatsapp_status(r["owner_id"], r["member_id"], "active")
                store.audit(r["owner_id"], "whatsapp", "care.whatsapp_active", {"member_id": r["member_id"]})
            send("active")
        elif text in care.WA_TAKEN and any(r["status"] == "active" for r in rows):
            now = datetime.now(timezone.utc)
            day = now.astimezone(care.IST).date().isoformat()
            marked = []
            for r in rows:
                if r["status"] != "active":
                    continue
                member = care_member(r["owner_id"], r["member_id"])
                log_ = store.dose_log(r["owner_id"], r["member_id"], day)
                slot = care.latest_open_slot(member, log_, now)
                if slot is None:
                    continue
                for d in care.doses_for_day(member, now.astimezone(care.IST).date(), log_, now):
                    if d["slot"] == slot and d["status"] in ("due", "missed"):
                        store.log_dose(r["owner_id"], r["member_id"], d["med_id"], day, slot, "taken", "whatsapp")
                        marked.append(d["name"])
            send("taken", names=", ".join(sorted(set(marked)))) if marked else send("nothing_due")
        else:
            send("help")

    @app.get("/e/{token}", response_class=HTMLResponse, include_in_schema=False)
    def emergency_page(token: str) -> HTMLResponse:
        link = store.open_emergency_link(hash_token(token))
        headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer"}
        if link is None:
            return HTMLResponse(_connect_page("This emergency link has expired or was turned off.", None),
                                status_code=404, headers=headers)
        member = next((m for m in store.get_profile(link["owner_id"]).family if m.id == link["member_id"]), None)
        if member is None:
            return HTMLResponse(_connect_page("This emergency link is no longer valid.", None), status_code=404,
                                headers=headers)
        store.audit(link["owner_id"], "emergency_link", "care.emergency_viewed", {"member_id": member.id, "link": link["id"]})
        for uid in {link["owner_id"], *(c["user_id"] for c in store.caregivers(link["owner_id"], member.id))}:
            notifier.notify(uid, "care", N.say(store.user_lang(uid), N.EMERGENCY_OPENED, who=care_name_in(member, store.user_lang(uid))))
        return HTMLResponse(emergency.render_html(emergency.summary(member), expires=link["expires_at"]), headers=headers)

    @app.post("/admin/tasks/care", dependencies=[Depends(require_admin)])
    def run_care_alerts() -> dict:
        """Medicine reminders, missed-dose notices and refill alerts to everyone in the care circle. Run hourly."""
        now, sent = datetime.now(timezone.utc), 0
        for owner_id, member_id in store.care_targets():
            member = care_member(owner_id, member_id)
            today = now.astimezone(care.IST).date()
            doses_log = store.dose_log(owner_id, member_id, today.isoformat())
            done = {n["key"] for n in store.nudges(owner_id)}
            circle = {owner_id, *(c["user_id"] for c in store.caregivers(owner_id, member_id))}
            by_lang = {lang: dict(care.due_care_alerts(now, care_name_in(member, lang), member, doses_log, lang))
                       for lang in {store.user_lang(uid) for uid in circle}}
            wa = store.care_whatsapp(owner_id, member_id)
            if wa_client and wa and wa["status"] == "active":
                for key, slot, names in care.wa_reminders_due(now, member, doses_log):
                    if key in done:
                        continue
                    try:
                        wa_client.send_template(wa["phone"], settings.whatsapp_template_care_reminder, wa["lang"],
                                                [care.WA_SLOT.get(wa["lang"], care.WA_SLOT["en"])[slot], ", ".join(names)])
                        store.record_nudge(owner_id, key, now.isoformat())
                        sent += 1
                    except Exception:  # noqa: BLE001 (one failed send mustn't stop the job)
                        log.exception("WhatsApp medicine reminder failed")
            for key in next(iter(by_lang.values())):
                if key in done:
                    continue
                for uid in circle:
                    notifier.notify(uid, "care", by_lang[store.user_lang(uid)][key], url=f"/care?id={owner_id}.{member_id}")
                    sent += 1
                store.record_nudge(owner_id, key, now.isoformat())
        return {"sent": sent}

    # --- background jobs (docs/RUNNING_IN_PRODUCTION.md) ----------------------------------------
    def run_backup() -> dict:
        if not settings.backup_dir:
            return {"skipped": "FHG_BACKUP_DIR is not set"}
        key = settings.backup_key or store._cipher.key.decode()
        return store.backup(settings.backup_dir, key, settings.backup_keep, backups.s3_uploader_from_env())

    jobs = [Job("care", run_care_alerts, hourly=True), Job("reminders", run_reminders, at=(10, 0)),
            Job("backup", run_backup, at=(2, 30), first_run_now=True), Job("housekeeping", run_housekeeping, at=(3, 15))]
    app.state.scheduler = Scheduler(store, jobs)
    if settings.scheduler:
        app.router.on_startup.append(app.state.scheduler.start)
        app.router.on_shutdown.append(app.state.scheduler.stop)

    @app.post("/admin/tasks/backup", dependencies=[Depends(require_admin)])
    def admin_backup() -> dict:
        """Make a backup now (also runs nightly when the scheduler is on)."""
        out = run_backup()
        store.record_job_run("backup", datetime.now(timezone.utc).isoformat(), "ok", out)
        return out

    @app.post("/admin/jobs/{name}/run", dependencies=[Depends(require_admin)])
    def admin_run_job(name: str) -> dict:
        """Run a background job now and record it, as if the scheduler had (the console's "Run now")."""
        job = next((j for j in jobs if j.name == name), None)
        if job is None:
            raise HTTPException(404, f"No such job; jobs are {[j.name for j in jobs]}")
        now = datetime.now(timezone.utc).isoformat()
        try:
            out = job.run()
        except Exception as exc:
            store.record_job_run(name, now, "error", {"error": str(exc)[:500]})
            raise HTTPException(500, f"The {name} job failed: {exc}") from exc
        store.record_job_run(name, now, "ok", out)
        return out

    @app.get("/admin/jobs", dependencies=[Depends(require_admin)])
    def admin_jobs() -> dict:
        return {"scheduler": settings.scheduler, "jobs": [r for r in store.job_runs() if not r["name"].startswith("_")]}

    return app
