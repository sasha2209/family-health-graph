# Family Health Graph: mobile app

iOS and Android app for Family Health Graph, built with **Expo SDK 58**, **React Native 0.88**,
**Expo Router** and TypeScript. It's a client of the API in `../fhg` and has no backend logic of its own.

## What's in v0.1

| Tab / screen | What it does |
|---|---|
| **Welcome** | Create a private account, or paste an invite link a relative sent |
| **Insights** | Guideline-based insights with evidence and sources, family alerts, plain-language summary, pull to refresh |
| **Family** | Pedigree cards (with *Linked* badges for relatives who joined), linked relatives, per-relative sharing controls, unlink |
| **Invite** | Pick the relationship and what you share, then send the link through the phone's share sheet |
| **Add history** (modal) | Type family history in plain sentences, check what was understood, save; load a sample record |
| **Invite link** (`/invite/[token]`) | See who invited you and what they share, choose what you share, accept or decline |
| **Settings** | Sex and date of birth, AI-summary consent, FHIR export, sign out, delete all data |

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

Scan the QR code with **Expo Go** (iOS/Android). Everything in v0.1 runs in Expo Go; no native build is needed yet.

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

1. **Real sign-in and account recovery** (Sign in with Apple / Google). Today a lost device means a lost account; the app warns before signing out.
2. **Push notifications** for family alerts: add a backend `POST /v1/devices` endpoint and send pushes where the backend calls `notify()`. Keep health details out of the lock-screen text.
3. **Apple Health Records import** (HealthKit clinical records → FHIR → `POST /v1/ingest/fhir`) and a SMART on FHIR "connect your patient portal" flow. These need a development build (`npx expo run:ios` or `eas build --profile development`).
4. Universal/App Links, an app lock (Face ID / fingerprint), app icon and splash artwork, then TestFlight / Play internal testing via EAS.

See [`../docs/MOBILE_APP.md`](../docs/MOBILE_APP.md) for the full plan and app store requirements.

`AGENTS.md` (from the Expo template) has guidance for AI coding agents working in this folder.
