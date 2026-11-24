# Trust layer: India's data protection law, ABDM, and security

Hospitals, insurers and labs in India will only partner with a provider that is ABDM-certified and visibly compliant
with the Digital Personal Data Protection Act, 2023 (DPDP Act). This is what the product does about each, what is
configuration, and what still needs people and paperwork.

## DPDP Act: what the app does

| Obligation | In the product | Where |
|---|---|---|
| **Notice** (s.5) | A plain notice of what's collected, why, the rights and who to contact, in **English and Hindi**, public (shown before sign-up) and in Settings → Your privacy rights. | `GET /v1/privacy/notice?lang=en\|hi`, `fhg/privacy.py` |
| **Consent, withdrawn as easily as given** (s.6) | Every optional use is its own switch (AI summaries, AI document reading, WhatsApp summaries, research); every partner, clinic, app and relative can be removed in one tap. | `/v1/consents`, `/v1/grants`, `/v1/links`, `/v1/clinics` |
| **Security safeguards** (s.8(5)) | Field-level encryption of health data, hashed tokens, per-partner pseudonyms, audit log of every access, security headers, housekeeping of expired credentials. | `fhg/security.py`, `fhg/storage.py`, `POST /admin/tasks/housekeeping` |
| **Breach notice** (s.8(6)) | A breach register; one call notifies every affected person with what happened, what data, likely consequences, what we did, what they can do, and who to contact. Board intimation and report times are recorded. | `POST /admin/breaches`, `/admin/breaches/{id}/board/{intimation\|report}` |
| **Erasure** (s.8(7), s.12) | Delete account erases everything; partners holding data under a grant or a booking get an erasure webhook (no health data, just their pseudonymous id or booking id). | `DELETE /v1/me` |
| **Children** (s.9) | Account holders under 18 can't switch on sharing with apps, test bookings, research or AI processing; they're told a parent's verified consent is needed. | `require_adult` in `fhg/api.py` |
| **Summary of processing and sharing** (s.11) | *What we hold* (by category), *Who has it* (relatives, clinics, apps, referral partners, labs, counselors, care circles, with dates), processors, consents. | `GET /v1/privacy` |
| **Correction** (s.12) | Every item is editable or removable in the app. | |
| **Grievances** (s.13) | *Raise a concern*, with a due date; a privacy-officer queue that flags overdue items; the answer reaches the person in the app; the Data Protection Board is named as the next step. | `POST /v1/privacy/grievances`, `/admin/grievances` |
| **Nomination** (s.14) | A nominee who can exercise the rights on death or incapacity. | `PUT /v1/privacy/nominee` |
| **Portability** | One-file download of everything, including the access log; a FHIR export too. | `GET /v1/privacy/export`, `/v1/export/fhir` |

Configuration: `FHG_DATA_FIDUCIARY`, `FHG_GRIEVANCE_OFFICER_NAME`, `FHG_GRIEVANCE_OFFICER_EMAIL`, `FHG_GRIEVANCE_DAYS`.

### Must be checked against the notified DPDP Rules, 2025
The Rules set timelines and formats. Their official text (meity.gov.in, egazette) couldn't be reached from the build
environment, so nothing here assumes their numbers:
- the grievance response period (`FHG_GRIEVANCE_DAYS`, default 30 until set from the Rules);
- breach intimation to the Board: the initial intimation and the detailed report deadlines;
- how long access logs must be kept;
- the mechanism for **verifiable parental consent** (then the under-18 block can become a consent flow);
- whether a Consent Manager integration is expected for health data;
- the commencement dates for each obligation.

## ABDM

Direct ABHA linking is built against NHA's open-source ABDM Wrapper; see [CONNECTIONS.md](CONNECTIONS.md#india-abdm).
Certification steps: HIU registration in the sandbox → wrapper deployment → sandbox testing → ABDM functional and
security audit → production credentials.

## Security

Built:
- Health data encrypted per field (Fernet); session, API and OAuth tokens stored as hashes; secrets never logged.
- Every access by a person, clinic, partner, caregiver or emergency link is in the audit log the person can read.
- Partners see a different pseudonymous id for each person; webhooks carry no health data and are signed.
- Responses carry `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, and
  `Strict-Transport-Security` over HTTPS. Emergency pages are `noindex`, `no-store`, `no-referrer`.
- Expired sign-in codes, OAuth codes and tokens, invites and links are deleted daily (`/admin/tasks/housekeeping`).

To do before partners will sign:
- **An independent security review** (VAPT by a CERT-In empanelled auditor), fixes, and a published summary.
- A **published pilot outcome** with one clinic: how many families, what was found, what was booked and done.
- Key management in a cloud KMS rather than an environment variable; backups encrypted and restore-tested.
- Rate limiting at the edge (sign-in codes are already rate-limited in the app).
- A written incident-response runbook that uses the breach register.

See also [SECURITY.md](../SECURITY.md) for reporting vulnerabilities.
