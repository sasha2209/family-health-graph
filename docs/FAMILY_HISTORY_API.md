# Connect with Family Health Graph: the family-history API for partners

Genetic-testing and counseling services, labs, clinics and digital-health apps can read a person's family health
history, **with that person's consent**, as standard FHIR R4. It works like "Sign in with…": the partner sends
the person to us, the person chooses what to share, and the partner receives an access token for just that.

```
Partner app ──/oauth/authorize (PKCE)──▶ consent screen in the Family Health Graph app ──Allow──▶ redirect_uri?code&state
Partner server ──/oauth/token (code + code_verifier)──▶ access token (1 hour) + refresh token (rotating)
Partner server ──GET /fhir/r4/FamilyMemberHistory, RiskAssessment, …  (Bearer)──▶ FHIR searchset Bundles
```

## Getting access
The operator registers you as a partner (`POST /admin/partners`, see `PARTNER_API.md`) and then your OAuth details:

```bash
curl -X PUT https://<host>/admin/partners/$PARTNER_ID/oauth -H "X-Admin-Key: $ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["https://yourapp.example.com/fhg/callback"], "confidential": true}'
```

- Your `client_id` is your partner id.
- **Confidential clients** (with a server) get a `client_secret`, shown once. Send it with `client_secret_post` or HTTP Basic.
- **Public clients** (mobile or browser-only apps) use PKCE alone.
- Redirect URIs must be `https`, or `http://localhost` for development, and must match exactly.

Discovery is at `/.well-known/oauth-authorization-server`, and at `/fhir/r4/.well-known/smart-configuration` for
SMART client libraries.

## Scopes
| Scope | What it shares |
|---|---|
| `family_history.read` | `FamilyMemberHistory`: each relative's relationship (HL7 v3 RoleCode), sex, deceased, age, and conditions (SNOMED CT or ICD-10 coded where known) with age at onset. **Never names.** |
| `risk.read` | `RiskAssessment`: the guideline-based action items: outcome, qualitative risk (high/moderate/low), the evidence it rests on, the recommendation, and references. Rule-based, not a diagnosis. |
| `patient.read` | `Patient`: sex and **year** of birth only |
| `conditions.read` | `Condition`: the person's own diagnoses |
| `observations.read` | `Observation`: lab results and vitals (LOINC) |
| `medications.read` | `MedicationStatement` |

The person can untick any scope on the consent screen. The token's `scope` says what was actually granted. Reading
something not granted returns `403` with an `OperationOutcome`.

## Authorize
`GET /oauth/authorize?response_type=code&client_id=…&redirect_uri=…&scope=family_history.read%20risk.read&state=…&code_challenge=…&code_challenge_method=S256`

- PKCE with `S256` is required.
- An unknown client or redirect URI gets an error page and is never redirected.
- An invalid scope or request redirects back with `error=invalid_scope` / `invalid_request`.
- Declining redirects with `error=access_denied`.

## Token
`POST /oauth/token` (form-encoded):
- `grant_type=authorization_code&code=…&redirect_uri=…&client_id=…&code_verifier=…`
- `grant_type=refresh_token&refresh_token=…&client_id=…`

Codes last 10 minutes and are single use. Refresh tokens rotate on every use. The response includes `patient`:
a stable id **specific to your organization**, so partners can't link a person across services.

## Read
`GET /fhir/r4/{FamilyMemberHistory|RiskAssessment|Patient|Condition|Observation|MedicationStatement}` returns a
`searchset` Bundle. `GET /fhir/r4/{type}/{id}` returns one resource. `GET /fhir/r4/metadata` returns the
CapabilityStatement.

## The person stays in control
- **What's shared:** consent lasts up to 12 months. It covers the person's **own record only**. History that
  linked relatives shared with them from their own accounts is never passed on, because those relatives agreed to
  share with family, not with third parties.
- **What the person sees:** each grant appears in the app under *Settings → Apps with access* (scopes and last
  read), with *Remove access*.
- **What revoking does:** removing access, or the operator deactivating a partner, invalidates every token at once.
- **What's logged:** every token issue and every read is recorded in the person's own activity log.
