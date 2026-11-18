# Family Health Graph

A platform that **ingests** a person's medical records and their family's health history,
**stores** them securely, and generates **explainable, guideline-based insights** about what
is worth discussing with a clinician, such as earlier cancer screening, genetic counseling or
cardiovascular risk checks.

> Family history is one of the strongest, cheapest predictors of disease risk, but it is
> usually incomplete, scattered across relatives' memories, and missing from the EHR. This
> project turns it into structured data that can drive action.

**Clinic portal (B2B):** open `/portal` for the clinician worklist, impact dashboard and demo patients; see [docs/B2B_AND_FUNDING.md](docs/B2B_AND_FUNDING.md).

For how this grows through partnerships with existing companies, see
**[docs/PARTNERSHIP_STRATEGY.md](docs/PARTNERSHIP_STRATEGY.md)**. For the path to iOS and
Android apps, see **[docs/MOBILE_APP.md](docs/MOBILE_APP.md)**; the app itself (Expo / React Native)
is in **[mobile/](mobile/README.md)**.

---

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sasha2209/family-health-graph)

One click deploys the API, web dashboard, clinic portal and the mobile app as a web app (`/app`). See
[docs/DEPLOY.md](docs/DEPLOY.md) for plans, secrets and the steps before real patient data.

## Quick start

```bash
cd family-health-graph
pip install -r requirements.txt
python -m fhg            # http://127.0.0.1:8000  (dashboard)  ·  /docs (OpenAPI)
python -m pytest -q      # 138 tests
```

CI (`.github/workflows/ci.yml`) runs the backend tests and the mobile app's typecheck, lint and tests on every pull request.

In the dashboard, click **Import sample FHIR record**, then **Use sample text** → **Add to my
record**. The text describes the same family, so it is merged and de-duplicated rather than
added twice.

To try **family invitations**, create an invite link in the "Invite family" panel and open it in a
*different browser or a private window* (each browser holds one account). Accept, add some
history as the relative (e.g. "I have a BRCA1 mutation. My sister had colon cancer at 45."),
then reload the first window.

## What it does

```
          INGEST                         STORE                         INSIGHTS
 ┌──────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────┐
 │ FHIR R4 bundle       │     │ Merge + de-duplicate     │     │ Rule engine (pure funcs) │
 │  (EHR, payer, Apple  │ ──▶ │ into one longitudinal    │ ──▶ │  each insight carries:   │
 │   Health, aggregator)│     │ HealthProfile            │     │  · evidence (the facts)  │
 │ Free text ("my mom   │     │                          │     │  · recommendation        │
 │  had breast cancer   │     │ Encrypted at rest        │     │  · guideline citations   │
 │  at 46")             │     │ Provenance per import    │     │                          │
 │ CSV / spreadsheet    │     │ Consent + audit log      │     │ Optional AI rewrite into │
 │ Manual entry         │     │                          │     │ plain language (Claude)  │
 └──────────────────────┘     └──────────────────────────┘     └──────────────────────────┘
                                          │
                                          ▼
                         SHARE (consent-gated, minimum necessary)
              FHIR export · partner payloads · de-identified research export
```

### Ingestion (`fhg/ingest/`)
| Source | Handles |
|---|---|
| **FHIR R4** (`fhir.py`) | `Patient`, `Condition`, `Observation` (incl. BP panels), `MedicationStatement/Request`, `FamilyMemberHistory`. Maps SNOMED CT, ICD-10-CM, LOINC and HL7 v3 RoleCodes. Full export too (round-trip tested). |
| **Free text** (`text.py`) | "Grandpa on my father's side died of colon cancer when he was 72", "my mother and sister both had breast and ovarian cancer", "in her late 50s" (stored as ~58, flagged as estimated), "my other sister…". Deterministic, with a **preview** mode so users confirm before saving. |
| **CSV** (`csv_import.py`) | `relationship,condition,age_at_diagnosis,sex,deceased,name`, with per-row warnings. |
| **Photos & PDFs** (`fhg/documents/`) | Prescriptions, lab reports, discharge summaries. Read on the server (PDF text layer or Tesseract OCR, then rules for Indian formats); an AI reader is an opt-in, token-light fallback. The user reviews before anything is saved, and a relative's document feeds their history. See [docs/DOCUMENT_UPLOAD.md](docs/DOCUMENT_UPLOAD.md). |

Terminology normalization (`terminology.py`) maps everything onto canonical concepts
(e.g. `breast_cancer`, `coronary_artery_disease`). Adding a concept is a data change.

### Storage (`fhg/storage.py`, `fhg/security.py`)
- Health data and raw imported documents are **encrypted at rest** (Fernet, AES + HMAC). The key comes from `FHG_ENCRYPTION_KEY`; use a KMS in production.
- **Sign-in**: start without an account, then secure it with a one-time **email code** (or **Sign in with Apple / Google**). Each sign-in is a separate per-device session that expires after 90 days of inactivity and can be revoked from any other device. Email addresses are stored encrypted and looked up by keyed hash; codes are single use, expire in 10 minutes, allow 5 attempts, and are limited to 5 an hour. See `fhg/auth.py`.
- Session tokens are stored as SHA-256 hashes only.
- **Provenance**: every import is recorded (source type, merge stats, encrypted original).
- **Consent** scopes (`share:<partner>`, `ai_summary`, `research_deidentified`) are granted and revoked by the user.
- **Audit log** of every read, import, share and export. **Right to delete** via `DELETE /v1/me`.

### Family invitations (`fhg/family_links.py`)
The growth loop: relatives join and enrich each other's insights.
- **Invite**: `POST /v1/invitations` returns a single-use link (expires in 14 days; only a hash of the token is stored). It can point at an existing relative in your record so their data merges into that entry.
- **Accept**: the relative sees a preview with no health data, then accepts as a new or existing user. The relationship is inverted automatically (you invited your *mother*, so she sees her *daughter*) and can be corrected.
- **Sharing is per side and revocable**: `none`, `conditions` (their own diagnoses), or `conditions_and_tree` (also the family history they've recorded, re-expressed from your point of view: your mother's sister becomes your maternal aunt, but ambiguous cases such as "my mother's daughter" are never guessed).
- **Live, not copied**: shared data is merged into an *effective profile* each time insights are generated, so changing sharing, unlinking or deleting an account takes effect immediately.
- **Family alerts**: when someone adds a result that runs in families (BRCA variant, Lynch syndrome, familial hypercholesterolemia, malignant hyperthermia), linked relatives who can see it are notified in the app and by push notification. Push text is always generic ("A relative shared a health update that may affect you"), because it shows on lock screens and passes through Apple, Google and Expo; the details appear only inside the app. Dead device tokens are pruned automatically. See `fhg/push.py`.
- **Stays in the family**: relatives' shared data feeds only your insights. It is never included in partner payloads, FHIR exports or research exports.
- Known limitation: when a shared relative might be the same person you already recorded (e.g. two unnamed maternal aunts with different conditions), they are kept separate rather than guessed together.

### Insights (`fhg/insights/`)
| Rule | Triggers on (simplified from cited guidance) | Source |
|---|---|---|
| Hereditary breast/ovarian cancer | close relative with breast cancer ≤50, ovarian or pancreatic cancer at any age, male breast cancer, ≥2 same-side breast cancers, known BRCA variant | USPSTF 2019, NCCN |
| Colorectal cancer / Lynch | first-degree relative with CRC → screening start age (40, or 10 yrs before youngest dx); early-onset or ≥3 Lynch-spectrum cancers → genetic counseling | USMSTF 2017, USPSTF 2021 |
| Premature ASCVD | first-degree male relative <55 / female <65 with MI/CAD/stroke; escalates with LDL ≥160 | 2018 AHA/ACC |
| Familial hypercholesterolemia | LDL ≥190 mg/dL (mmol/L converted) or FH in family | 2018 AHA/ACC |
| Type 2 diabetes | first-degree relative + BMI ≥25 / age ≥35; HbA1c prediabetes or diabetes range | ADA Standards |
| Prostate cancer | father/brother/son <65 or ≥2 affected | ACS |
| Malignant hyperthermia | any blood relative → anesthesia safety alert | MHAUS |
| Blood pressure | stage 1 / stage 2 / severe ranges | 2017 ACC/AHA |
| Record gaps | unknown cancer types, missing ages that would change guidance, missing parents/grandparents | Surgeon General's Family Health Portrait |

Design principles:
- **Rules decide; the LLM only explains.** Clinical logic is deterministic, testable and cites its sources. The optional Claude summary (`narrative.py`) receives only the already-computed insights, never raw records or relatives' names. It runs only with the user's `ai_summary` consent and falls back to a template without an API key.
- **Every insight shows its evidence**, so a user or clinician can check the reasoning.
- **Conservative language**: "worth discussing", never a diagnosis.

## API

| Method & path | Purpose |
|---|---|
| `POST /v1/users` | Create an account without signing in → bearer token |
| `GET /v1/auth/config` | Which sign-in methods the server offers |
| `POST /v1/auth/email/start` · `POST /v1/auth/email/verify` | Email a one-time code; verify it to sign in, create an account, or (with a bearer token) add the email to your account |
| `POST /v1/auth/oidc/{apple,google}` | Sign in with an Apple / Google ID token (or link it to your account) |
| `GET /v1/auth/me` · `GET /v1/auth/sessions` · `DELETE /v1/auth/sessions/{id}` · `POST /v1/auth/logout` | Account, signed-in devices, sign a device out |
| `GET /v1/profile` · `PUT /v1/profile/demographics` | Read profile / set sex & birth date |
| `POST /v1/ingest/fhir` · `/text` · `/csv` (`?preview=true`) | Import data |
| `POST /v1/documents` · `POST /v1/documents/{id}/save` · `GET /v1/documents[/{id}[/file]]` · `DELETE /v1/documents/{id}` | Upload a photo/PDF, review what was read, save it to your record or a relative's |
| `POST /v1/family` · `DELETE /v1/family/{id}` · `POST /v1/observations` | Manual entry |
| `GET /v1/insights` · `GET /v1/insights/summary` | Insight report / plain-language summary |
| `GET/POST /v1/consents` | View, grant, revoke consent |
| `GET /v1/partners` · `POST /v1/partners/{id}/share` | Consent-gated partner sharing |
| `POST /v1/invitations` · `GET /v1/invitations` · `DELETE /v1/invitations/{id}` | Invite relatives, list, revoke |
| `GET /v1/invites/{token}` · `POST …/accept` · `POST …/decline` | Invite preview and response (public; accepting can create an account) |
| `GET /v1/links` · `PUT /v1/links/{id}` · `DELETE /v1/links/{id}` | Linked relatives, what you share, unlink |
| `GET /v1/notifications` · `POST /v1/notifications/read` | Family alerts |
| `PUT /v1/devices/push` · `GET /v1/devices/push` · `DELETE /v1/devices/push` | Register this device's Expo push token (tied to the session, so signing out stops pushes) |
| `GET /v1/profile?include_linked=true` | Your record plus what relatives share |
| `GET /v1/report/clinician` | Print-ready clinician summary with pedigree (`?include_shared=false` to leave out relatives' shared history) |
| `POST /v1/orgs` · `POST /v1/orgs/join` · `GET /v1/orgs` | Create a clinic, join as staff with the staff code, list your clinics |
| `GET /v1/orgs/{id}/patients` · `GET /v1/orgs/{id}/patients/{ref}/report` | Clinic worklist with impact metrics; a patient's clinician summary (logged in the patient's audit trail) |
| `POST /v1/orgs/{id}/patients/{ref}/referrals` | Staff: set a care program's referral status (referred / scheduled / completed / declined), with an optional encrypted note; notifies the patient |
| `GET /v1/referral-partners` | Staff: partners a clinic can refer to |
| `GET /v1/partner/referrals` · `GET /v1/partner/referrals/{id}` · `…/{id}/summary` · `POST …/{id}/status` | **Partner API** (`X-API-Key`): referrals routed to you as FHIR `ServiceRequest`s, the clinician summary, and outcome reporting. See [docs/PARTNER_API.md](docs/PARTNER_API.md) |
| `POST /admin/partners` · `GET /admin/partners` · `POST /admin/partners/{id}/deactivate` | Operator (`X-Admin-Key`): onboard referral partners (returns API key and webhook secret once) |
| `GET /v1/referrals` | Patient: referrals your clinics have made for you |
| `GET /c/{code}` · `GET /c/{code}/qr.svg` · `GET /c/{code}/poster` | Clinic **pre-visit intake link**: a no-install web intake, its QR code, and a printable waiting-room poster |
| `GET /v1/public/clinics/{code}` | Public: a clinic's name from its patient code (for the intake page) |
| `GET /v1/clinics/lookup/{code}` · `POST /v1/clinics` · `GET /v1/clinics` · `DELETE /v1/clinics/{id}` | Patient: find a clinic by code, connect, list, disconnect |
| `GET /v1/export/fhir` | Data portability (FHIR bundle; your own data only) |
| `GET /v1/ingests` · `GET /v1/audit` | Provenance and audit trail |
| `DELETE /v1/me` | Delete all data |
| `GET /admin/research/export` | De-identified, consented cohort (needs `X-Admin-Key`) |

## Configuration

| Env var | Default | |
|---|---|---|
| `FHG_DB_PATH` | `data/fhg.sqlite3` | SQLite path |
| `FHG_ENCRYPTION_KEY` | auto-generated dev key | Fernet key, **required in production** |
| `FHG_ADMIN_KEY` | unset (research export disabled) | |
| `FHG_PSEUDONYM_SECRET` | dev value | HMAC key for research IDs |
| `ANTHROPIC_API_KEY`, `FHG_LLM_MODEL` | unset, `claude-opus-5-5` | Optional AI summaries |
| `FHG_DOC_MODEL` | `claude-opus-5-5` | Model for the document-reading fallback (only used for documents OCR and rules can't read, and only with the user's consent) |
| `FHG_AUTH_SECRET` | dev value | Keys email lookups and sign-in codes; **set a long random value in production** |
| `FHG_EMAIL_BACKEND` | `console` | `console` prints sign-in emails to the server log; `smtp` sends them using `FHG_SMTP_HOST`, `FHG_SMTP_PORT`, `FHG_SMTP_USERNAME`, `FHG_SMTP_PASSWORD`, `FHG_EMAIL_FROM` |
| `FHG_APPLE_AUDIENCES` | unset (off) | Your iOS bundle ID (and web Services ID) to enable Sign in with Apple |
| `FHG_GOOGLE_AUDIENCES` | unset (off) | Your Google OAuth client IDs to enable Sign in with Google |
| `FHG_PUSH_BACKEND` | `console` | `console` logs pushes; `expo` sends through Expo's push service (`FHG_EXPO_ACCESS_TOKEN` optional, for Expo's enhanced push security) |
| `FHG_PUBLIC_URL` | `RENDER_EXTERNAL_URL`, else request host | Public origin for invite links, e.g. `https://app.example.org` (set this behind a proxy or load balancer) |
| `FHG_IOS_APP_IDS` | unset | `TEAMID.bundle.id` values; serves `/.well-known/apple-app-site-association` so invite links open the iOS app |
| `FHG_ANDROID_PACKAGE`, `FHG_ANDROID_CERT_SHA256` | unset | Android package and signing-certificate SHA-256 fingerprints; serves `/.well-known/assetlinks.json` |
| `FHG_WEB_APP_DIR` | unset | Directory of the mobile app's web build to serve at `/app` (set in the Docker image) |
| `FHG_CORS_ORIGINS` | unset | Comma-separated browser origins allowed to call the API (e.g. the Expo web preview) |
| `FHG_HOST`, `FHG_PORT` | `127.0.0.1`, `8000` | Use `FHG_HOST=0.0.0.0` so a phone on your network can reach the dev server |

## Before this touches real patients

This is a working prototype, not a medical device. Before any real use:
1. **Clinical review** of every rule by clinicians and genetic counselors, a documented review cycle for guideline updates, and validation against real pedigrees (sensitivity/specificity versus established tools such as the Ontario FHAT or the Tyrer-Cuzick/CanRisk models).
2. **Regulatory review**: FDA software-as-a-medical-device / clinical decision support positioning, HIPAA (when acting as a business associate), the FTC Health Breach Notification Rule, and state health-privacy laws (e.g. Washington's My Health My Data Act).
3. **Production hardening**: a transactional email provider for sign-in codes, per-IP rate limiting, SMART on FHIR app launch, Postgres with row-level security, KMS-managed keys, rate limiting, a security review and pen test, backups, and accessibility review.

## Roadmap
- Mobile app ([mobile/](mobile/README.md)): v0.1 is built; next are sign-in and recovery, push family alerts, HealthKit / Health Connect import, and invite deep links.
- Email/SMS delivery of invitations (today the user shares the link themselves).
- SMART on FHIR "connect your patient portal" and payer Patient Access API connectors.
- Risk models (CanRisk/BOADICEA, PREVENT) alongside rule flags; pedigree visualisation.
- Clinician-facing view and FHIR `FamilyMemberHistory` write-back / CDS Hooks into the EHR.
- Genetic test report ingestion (structured variant results).
