# Connecting records from hospitals: SMART on FHIR (US) and ABDM (India)

Phase 3 brings in records at the source, with the patient's consent, instead of one document at a time.

## SMART on FHIR patient portals (built)

Patients sign in at their hospital's own portal (Epic MyChart, Oracle Health, any SMART-enabled EHR). We read
their records and merge them in. Imported items carry `source: smart:<connection id>`, so they can be traced back.

```
App → POST /v1/connect/smart {provider} → authorize_url (PKCE S256, state) → patient signs in and approves
EHR → /connect/smart/callback?code&state → token exchange → reads Patient, Condition, Observation (labs, vitals),
      MedicationRequest/Statement, FamilyMemberHistory (paged, same host only) → merged → "Return to the app"
```

- **Endpoints:** `GET /v1/connections` (connected and available) · `POST /v1/connect/smart` ·
  `POST /v1/connections/{id}/sync` (refreshes the token when needed) · `DELETE /v1/connections/{id}` (tokens deleted;
  imported records stay).
- **Security:**
  - Public client with PKCE.
  - The `state` value is single-use, stored hashed, and expires after 15 minutes.
  - Access and refresh tokens are encrypted at rest.
  - Paging links pointing to another host are never followed.
  - The return path must be on this site.
  - Every step is audit-logged.
- **Configuration:** `FHG_SMART_PROVIDERS` is a JSON list of `{"id", "name", "iss", "client_id"}`. The redirect URI to
  register is `https://<your host>/connect/smart/callback`.
- **Registering with EHRs:**
  - **Epic:** create a patient-facing app at fhir.epic.com (USCDI read scopes), use its non-production client ID in
    Epic's sandbox, then request production distribution; each health system's FHIR base URL is a separate provider entry.
  - **Oracle Health (Cerner):** register at the code console.
  - **The public SMART sandbox** (`https://launch.smarthealthit.org`) accepts any client ID and is good for demos.
- **Scopes requested:** SMART v1 `patient/*.read` for Patient, Condition, Observation, MedicationRequest,
  MedicationStatement and FamilyMemberHistory, plus `launch/patient openid fhirUser offline_access`.

## India: ABDM

### Built now: health record files
Users can download a record from the ABHA app or a hospital as a FHIR R4 file (`.json`) and add it like any document.
- The Composition gives the record type (prescription, diagnostic report, discharge summary) and the date.
- Conditions, medications, observations and family history go to the review screen.
- If the record only contains a PDF (DocumentReference, DiagnosticReport.presentedForm or Binary), that PDF is read
  by the OCR pipeline.

This needs no ABDM certification and works today.

### Next: become an ABDM Health Information User (HIU) / PHR app
This needs the ABDM sandbox (client ID and secret), the gateway callbacks, and then certification (functional and
security audit) before going live.

Confirmed from NHA's own ABDM-wrapper repository (v3 gateway):
- Session token: `POST https://dev.abdm.gov.in/api/hiecm/gateway/v3/sessions`, with headers `REQUEST-ID` (UUID),
  `TIMESTAMP` (ISO 8601 UTC with milliseconds) and `X-CM-ID` (`sbx` in sandbox, `abdm` in production), and body
  `{"clientId", "clientSecret", "grantType": "client_credentials"}`. Later calls send `Authorization: Bearer <token>`.
- Register the callback base URL: `PATCH …/gateway/v3/bridge/url` with body `{"url": …}`.

Health data is encrypted with **Fidelius** (confirmed from the open-source fidelius-cli code):
- ECDH on Curve25519 in BouncyCastle's form. Public keys are 65-byte uncompressed points (`04‖X‖Y`, base64) or X.509.
- XOR the two 32-byte nonces. The **first 20 bytes** are the HKDF salt and the **last 12 bytes** are the IV.
- HKDF-SHA256 over the shared secret, with no info, gives a 32-byte key.
- AES-256-GCM with a 128-bit tag appended to the ciphertext, then base64.

Because BouncyCastle's curve form differs from standard X25519 libraries, we will verify against sandbox test
vectors (or run fidelius-cli alongside the server) before decrypting real data.

To confirm in the sandbox before building: the v3 paths and payloads for the consent request (init and on-init),
the consent notification, the health-information request, and the data push to our `dataPushUrl`.

The planned flow:
1. The user enters their ABHA address in the app.
2. We raise a consent request (purpose `SELF`, which is self-requested, or care management) for the record types
   and date range they choose.
3. They approve it in their ABHA app.
4. We request the data.
5. The HIPs push Fidelius-encrypted FHIR bundles to us.
6. Each bundle goes through the same reader as the record files above and waits in review.
