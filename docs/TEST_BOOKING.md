# Book a test from an insight, results back, reminders until it's done

Most health apps either flag a risk or sell a test. Family Health Graph closes the loop:

```
Action item ("Type 2 diabetes risk") ──▶ Get tested: HbA1c · Fasting sugar, offers from partner labs (₹, home collection)
   └─▶ Book (day, time, contact details) ──signed webhook, no health data──▶ lab
lab ──API key──▶ reads booking (tests, slot, the contact details the person shared) ──▶ scheduled ──▶ results (FHIR)
   └─▶ results go into the person's record ──▶ insights update ──▶ person notified
Reminders: weekly (max 3) until a recommended test is booked; nudges if a lab hasn't confirmed or results are late.
```

## Tests and which action items they answer (`fhg/bookings.py`)
| Action item | Tests offered |
|---|---|
| Type 2 diabetes risk, Indian Diabetes Risk Score | HbA1c, fasting blood sugar |
| Possible familial hypercholesterolemia, early heart disease in the family | Lipid profile, lipoprotein(a) |
| Hereditary breast/ovarian pattern, colorectal family history | Genetic counseling consultation |

Kidney function is also in the catalog. Each test lists its preparation, for example fasting.

## For lab and counseling partners
1. The operator creates the partner (`POST /admin/partners`, kind `lab`, with a webhook URL) and sets its catalog:
   ```bash
   curl -X PUT https://<host>/admin/partners/$ID/catalog -H "X-Admin-Key: $ADMIN_KEY" -H "Content-Type: application/json" \
     -d '[{"test":"hba1c","price_inr":450,"home_collection":true,"turnaround_days":1}]'
   ```
2. Webhooks `booking.created` / `booking.updated` carry only `{"booking_id"}` and are signed as in `PARTNER_API.md`.
3. With `X-API-Key`:
   - `GET /v1/partner/bookings[?status=requested]` and `GET /v1/partner/bookings/{id}`: tests with preparation
     notes, preferred day and slot, contact details (name, phone, address, PIN).
   - `POST /v1/partner/bookings/{id}/status`: `{"status": "scheduled" | "sample_collected" | "completed" | "cancelled",
     "scheduled_for": "...", "note": "..."}`. The person is notified.
   - `POST /v1/partner/bookings/{id}/results`: a FHIR R4 Observation or Bundle (LOINC-coded). Only results for the
     booked tests are accepted. Diagnoses are never accepted from a lab. The booking is completed, the results join the
     person's record, and their insights update.

## For the person
- An action item's page shows **Get tested**, with offers sorted by price.
- **Book a test** asks for day, time and contact details. It says exactly what the lab receives: the test name, the
  time and those details, nothing else from the record.
- *Your bookings* on the action item has *Cancel booking* and *I had it done elsewhere* (which stops reminders).
  *Your tests* appears on Home.

## Reminders
`POST /admin/tasks/reminders` (admin key) runs the follow-through. Schedule it daily, for example with a Render
Cron Job running `curl -X POST "$FHG_PUBLIC_URL/admin/tasks/reminders" -H "X-Admin-Key: $FHG_ADMIN_KEY"`.

| When | Reminder |
|---|---|
| A recommended test hasn't been booked | Weekly, at most 3 times |
| A lab hasn't confirmed after 2 days | One reminder |
| Results are 2 days past the visit date | One reminder |
| The test is done, or done elsewhere | Reminders stop |

## Metrics
`GET /admin/bookings/metrics` returns bookings by partner and status, with value in ₹. These are the numbers for a
pilot report and for partner revenue share.
