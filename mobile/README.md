# Family Health Graph: mobile app

iOS and Android app for Family Health Graph, built with **Expo SDK 58**, **React Native 0.88**,
**Expo Router** and TypeScript. It's a client of the API in `../fhg` and has no backend logic of its own.

## What's in v0.1

| Tab / screen | What it does |
|---|---|
| **Welcome** | Continue with email, Sign in with Apple (iOS, when enabled), try without an account, or paste an invite link |
| **Sign in** | Email → 6-digit code (iOS can autofill it from Mail). Also adds an email to an existing account |
| **Insights** | Guideline-based insights with evidence and sources, family alerts, plain-language summary, pull to refresh |
| **Family** | Pedigree cards (with *Linked* badges for relatives who joined), linked relatives, per-relative sharing controls, unlink |
| **Invite** | Pick the relationship and what you share, then send the link through the phone's share sheet |
| **Add history** (modal) | Type family history in plain sentences, check what was understood, save; load a sample record |
| **Invite link** (`/invite/[token]`) | See who invited you and what they share, choose what you share, accept or decline |
| **Settings** | Account protection (add email / Apple), signed-in devices with remote sign-out, family alerts on/off, sex and date of birth, AI-summary consent, FHIR export, sign out, delete all data |

Security: the API token is stored in the iOS Keychain / Android Keystore (`expo-secure-store`,
*this device only*, so it's excluded from backups). No health data is stored on the device.

## Run it

**1. Start the backend** (from the repo root) so your phone can reach it:

```bash
FHG_HOST=0.0.0.0 python -m fhg
```

**2. Start the app** (in `mobile/`), pointing it at your computer's LAN address:

```bash
npm install
```

```bash
EXPO_PUBLIC_API_URL=http://<your-computer-ip>:8000 npx expo start
```

Scan the QR code with **Expo Go** (iOS/Android). Everything runs in Expo Go; no native build is needed yet.

**Sign-in codes in development** are printed in the backend's terminal (look for `DEV EMAIL`). Set
`FHG_EMAIL_BACKEND=smtp` and the SMTP variables to send real emails.

**Sign in with Apple** needs an Apple Developer account: enable the capability for your bundle ID,
set `FHG_APPLE_AUDIENCES=<your bundle id>` on the server, and use a development build
(Expo Go is signed with Expo's bundle ID, so its tokens won't match yours).

**Push notifications** need a physical phone and an EAS project ID: run `npx eas-cli@latest init`
(it adds `extra.eas.projectId` to the app config) and start the server with `FHG_PUSH_BACKEND=expo`.
They work in Expo Go on iOS; on Android, Expo Go no longer supports push since SDK 53, so use a
development build. Turn them on in Settings, or with "Notify me when they join" after sending an invite.
Tapping a notification opens Insights.

**Browser preview** (handy for quick UI work):

```bash
FHG_CORS_ORIGINS=http://localhost:8081 python -m fhg
```

```bash
EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start --web
```

## Checks

```bash
npm run typecheck && npx expo lint && npm test
```

## Invite links

The backend returns `https://<server>/invite/<token>` links. Today:
- In the app, paste the link on the Welcome screen, or open `familyhealth://invite/<token>` in a development build.
- Without the app, the same link opens the web invite page served by the backend.

To make tapped links open the app directly, set up **Universal Links / App Links** for your
production domain (`ios.associatedDomains` and `android.intentFilters` in `app.json`, plus the
`apple-app-site-association` and `assetlinks.json` files on the server).

## Next steps (in order)

1. ~~Sign-in and account recovery~~ (email codes and Apple are done; Google needs `expo-auth-session` and OAuth client IDs).
2. ~~Push notifications for family alerts~~ (done; needs an EAS project ID and a physical device to try).
3. **Apple Health Records import** (HealthKit clinical records → FHIR → `POST /v1/ingest/fhir`) and a SMART on FHIR "connect your patient portal" flow. These need a development build (`npx expo run:ios` or `eas build --profile development`).
4. Universal/App Links, an app lock (Face ID / fingerprint), app icon and splash artwork, then TestFlight / Play internal testing via EAS.

See [`../docs/MOBILE_APP.md`](../docs/MOBILE_APP.md) for the full plan and app store requirements.

`AGENTS.md` (from the Expo template) has guidance for AI coding agents working in this folder.
