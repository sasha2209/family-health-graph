# Partner API: receiving referrals

For **referral partners** (genetic counseling services, testing labs, specialists, prevention programs) who
receive referrals from clinics on Family Health Graph and report outcomes back.

```
Clinic portal ──"Referred to <you>"──▶ webhook (signed, no health data) ──▶ your server
                                                                             │
                     GET /v1/partner/referrals/{id}  ◀───────────────────────┘ (API key)
                     POST /v1/partner/referrals/{id}/status  scheduled → completed
                                   │
        clinic's referral funnel, the patient's app and the patient's audit log update
```

## Getting access

The platform operator creates your partner account (after the contract and BAA are signed):

```bash
curl -X POST https://<host>/admin/partners -H "X-Admin-Key: $ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"name": "GenomeCo Genetic Counseling", "kind": "genetic_counseling", "webhook_url": "https://genomeco.example/fhg/webhooks"}'
```

The response contains your **API key** (`fhgp_…`) and **webhook secret** (`whsec_…`). They're shown **once**;
store them in a secrets manager. Kinds: `genetic_counseling`, `genetic_testing`, `lab`, `specialist`,
`prevention_program`, `other`.

## Authentication

Send your API key in the `X-API-Key` header. Requests without a valid key get `401`. You only ever see
referrals routed to you, and you lose access to a referral if the patient disconnects from the referring clinic.
Every read and update is recorded in the patient's own audit log.

## Webhooks

When a clinic routes a referral to you (`referral.created`) or changes it (`referral.updated`), we `POST`:

```json
{"id": "evt_3f9c…", "type": "referral.created", "created": "2026-11-17T19:40:00+00:00",
 "data": {"referral_id": "a1b2c3d4e5f60718"}}
```

Webhooks deliberately contain **no health data**. Fetch the referral with your API key. Delivery is best effort;
you can always poll `GET /v1/partner/referrals?status=referred` instead.

**Verify every webhook.** The `X-FHG-Signature` header is `t=<unix seconds>,v1=<hex>`, where
`v1 = HMAC-SHA256(webhook_secret, "<t>." + raw_body)`. Reject signatures older than 5 minutes.

```python
import hashlib, hmac, time

def verify(secret: str, raw_body: bytes, header: str, tolerance=300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    t = int(parts["t"])
    if abs(time.time() - t) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

## Endpoints

| Method & path | Description |
|---|---|
| `GET /v1/partner/referrals` (`?status=referred\|scheduled\|completed\|declined`) | Your referrals, newest first |
| `GET /v1/partner/referrals/{id}` | One referral |
| `GET /v1/partner/referrals/{id}/summary` | The clinician summary (HTML, print-ready): flagged items with guideline criteria, pedigree, family history table |
| `POST /v1/partner/referrals/{id}/status` | Report back: `{"status": "scheduled" \| "completed" \| "declined", "note": "optional"}` |

A referral looks like this:

```json
{
  "referral_id": "a1b2c3d4e5f60718",
  "status": "referred",
  "program": "Genetic counseling: hereditary breast/ovarian cancer",
  "clinic": {"id": "c0ffee123456", "name": "Riverside Family Practice"},
  "patient": {"display_name": "Priya Shah"},
  "history": [{"status": "referred", "at": "…", "by": "clinic", "note": "Please see within 4 weeks"}],
  "service_request": {
    "resourceType": "ServiceRequest", "id": "a1b2c3d4e5f60718", "status": "active", "intent": "order",
    "code": {"text": "Genetic counseling: hereditary breast/ovarian cancer"},
    "reasonCode": [{"text": "Family pattern worth a hereditary cancer risk assessment"}],
    "note": [{"text": "Family history (patient-reported): Mother: Breast cancer (diagnosed at 46); Maternal aunt: Ovarian cancer (diagnosed at 58)"}],
    "subject": {"display": "Priya Shah"}, "requester": {"display": "Riverside Family Practice"},
    "performer": [{"display": "GenomeCo Genetic Counseling"}], "authoredOn": "…"
  }
}
```

`service_request` is a FHIR R4 `ServiceRequest` you can load into an EHR or scheduling system. Its status is
`active` (referred or scheduled), `completed`, or `revoked` (declined).

## Report outcomes

```bash
curl -X POST https://<host>/v1/partner/referrals/$ID/status -H "X-API-Key: $FHG_API_KEY" \
  -H "Content-Type: application/json" -d '{"status": "scheduled", "note": "Telehealth visit 3 Dec"}'
```

`scheduled` notifies the patient ("<your name> scheduled your appointment…"). `completed` counts toward the
clinic's referral funnel and pilot report, which is the number clinics, payers and funders care about.
