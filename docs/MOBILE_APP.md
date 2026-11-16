# Turning Family Health Graph into a Mobile App

The backend is already API-first: every feature, including invitations, is a JSON endpoint,
so a mobile app is a new client, not a rewrite. The recommended path has two steps.

## Recommendation at a glance

| | Step 1: Installable web app (PWA) | Step 2: Native app (React Native + Expo) |
|---|---|---|
| Time | Days | 6–10 weeks for a solid v1 |
| Reuses | The existing dashboard | The existing API (all of it) |
| App stores | No (installed from the browser) | Yes (App Store and Google Play) |
| Apple Health / Health Connect records | ❌ | ✅ the big win: one-tap import of hospital records |
| Push notifications for family alerts | Partial (iOS 16.4+ for installed PWAs only) | ✅ |
| Invite links open the app | ❌ | ✅ (universal links / app links) |
| Biometric lock, secure token storage | ❌ | ✅ |

Do step 1 to test demand with real families cheaply, and go straight to step 2 once you're
serious. The native app is the real product: its two killer features, importing records from
the phone's health app and push alerts when a relative shares a result, both need native code.

---

## Step 1: Make the current dashboard installable (PWA)

1. Add `fhg/static/manifest.webmanifest` with the name, icons (192 and 512 px), `"display": "standalone"`, and theme colours.
2. Add `<link rel="manifest">` and an `apple-touch-icon` to `index.html` and `invite.html`.
3. Add a small service worker that caches the page shell. **Never cache API responses**: they contain health data.
4. Serve over HTTPS (required for install and service workers).

Users can then "Add to Home Screen". It's good enough for a pilot at a Family History Day event.

## Step 2: Native app with React Native + Expo

**Why this stack:** one TypeScript codebase for iOS and Android, a large ecosystem, and Expo's
managed build and update services. Flutter is an equally valid choice if your team prefers Dart.
Fully native Swift/Kotlin gives the deepest HealthKit integration but doubles the work.

### Screens (each maps to existing endpoints)

| Screen | Endpoints |
|---|---|
| Onboarding and consent | `POST /v1/users`, `PUT /v1/profile/demographics`, `POST /v1/consents` |
| Import records | `POST /v1/ingest/fhir` (from HealthKit / Health Connect), `/v1/ingest/text` with `?preview=true` |
| My family (pedigree) | `GET /v1/profile?include_linked=true`, `POST /v1/family`, `DELETE /v1/family/{id}` |
| Insights | `GET /v1/insights`, `GET /v1/insights/summary` |
| Invite family | `POST /v1/invitations`, then the OS share sheet (Messages, WhatsApp, email) |
| Accept invite (deep link) | `GET /v1/invites/{token}`, `POST /v1/invites/{token}/accept` |
| Linked relatives and sharing | `GET/PUT/DELETE /v1/links` |
| Alerts | `GET /v1/notifications`, plus push (below) |
| Privacy centre | `GET /v1/audit`, `GET /v1/export/fhir`, `DELETE /v1/me` |

### Native capabilities to add

1. **Health records import (the biggest win)**
   - **iOS:** HealthKit *clinical records* (Apple Health Records) gives FHIR resources (conditions, labs, medications) from connected hospitals in supported countries. It needs the HealthKit capability with clinical-records access, a clear purpose string, and Apple's extra review for health records. Map the records into a FHIR Bundle and send them to the existing `/v1/ingest/fhir` endpoint. No new parser is needed.
   - **Android:** Health Connect provides vitals and labs. Medical-records support is newer and more limited, so check its current status. Combine it with a **SMART on FHIR** "connect your patient portal" flow (works on both platforms through the system browser).
   - In Expo, both need a *development build* (not Expo Go) and community or custom native modules. Check what's currently maintained before choosing one.
2. **Invite links that open the app**: configure iOS Universal Links and Android App Links for `https://<your-domain>/invite/*`. If the app is installed, the link opens the accept screen; otherwise the existing `invite.html` web page works as a fallback. Use the native share sheet to send links.
3. **Push notifications** for `family_cascade` and `invitation_accepted`, via APNs (iOS) and FCM (Android), for example with Expo Notifications. Backend work: add a `POST /v1/devices` endpoint to register push tokens, and send a push wherever `store.notify()` is called today. **Keep health details out of the push text** (it shows on lock screens). Send "You have a new family health update" and show the details only inside the app after unlock.
4. **Security on device**: keep the API token in the Keychain / Android Keystore (e.g. `expo-secure-store`), never in plain storage. Add an optional Face ID / fingerprint lock (`expo-local-authentication`), blur the app in the app switcher, use certificate pinning for the API host, and store no health data on the device beyond a short-lived cache.

### Backend changes the mobile app needs

- **Real authentication**: replace bearer-token-only accounts with OIDC (Sign in with Apple, Google, email magic link) and refresh tokens. Apple requires Sign in with Apple if you offer other social logins.
- **Account recovery**: today a lost token means a lost account; real identity fixes this.
- `POST /v1/devices` for push tokens, and push sending in `notify()`.
- Production hosting: Postgres, a KMS-managed encryption key, HTTPS, rate limiting, monitoring, backups.
- An API version policy, because old app versions stay in use for months.

### App store requirements (health apps get extra scrutiny)

- **Apple:** a privacy policy; App Privacy "nutrition labels" declaring health data; HealthKit data may not be used for advertising or sold to data brokers, and its use must be disclosed; medical-type apps must be clear about what they do and don't do (keep the "not a diagnosis" framing); account deletion must be available in the app (it already exists: `DELETE /v1/me`).
- **Google Play:** the Data safety form, the Health apps declaration, Health Connect permission rationale screens, and a privacy policy.
- **Both:** expect follow-up questions in review. Have clinical-advisor and data-handling documentation ready.

### Suggested build order (about 8 weeks with 1–2 engineers)

| Weeks | Deliverable |
|---|---|
| 1–2 | Expo app shell, auth (OIDC), onboarding, insights and family screens against the existing API |
| 3–4 | Invite flow with share sheet and universal/app links; linked-relatives screen |
| 5–6 | Push notifications (with the backend device endpoint); biometric lock; secure storage |
| 7 | Apple Health Records import (iOS) and SMART on FHIR portal connect |
| 8 | Accessibility pass, privacy centre, TestFlight / Play internal testing, store submissions |

### Repo layout

Keep the app in the same repo (`mobile/`, next to `fhg/`) so API changes and app changes land
in the same pull request, and generate a typed API client from FastAPI's OpenAPI schema
(`/openapi.json`) so the app never drifts from the backend.
