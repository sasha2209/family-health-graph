# Caregiver mode

Most family-history tools are used once a year. The person who manages a family's health paperwork (usually an adult
child looking after ageing parents) needs something every day: which medicines are due, whether Mum took them, when a
strip runs out, and what to hand a doctor in an emergency. Caregiver mode builds that on the relative profiles the app
already keeps, and is what brings people back daily.

## What it does

| | |
|---|---|
| **Schedules from the prescription** | `fhg/care.py` reads Indian notation ("1-0-1", "½-0-½", "1-1-1-1"), abbreviations (OD, BD, TDS, QID, HS, SOS), durations ("x 30 days", "2 weeks", "1 month") and food timing (after food, before food, empty stomach). A caregiver can correct the times with one tap. |
| **Today's doses** | Morning (8 am), afternoon (2 pm) and night (9 pm), shown as due, taken, skipped or *not marked* 3 hours after the slot. Anyone in the circle can mark a dose; the others see who did. A 7-day adherence strip counts from the day each medicine started. |
| **Refill alerts** | From "tablets at home today", or from the course length on the prescription. *Reorder soon* when 5 days or fewer are left. |
| **Care circle** | The person who added the relative invites siblings with a one-time link (valid 7 days). Caregivers see medicines, mark doses, keep emergency details and get the same reminders. Only the owner sees and manages the circle; anyone can leave. Deleting the relative ends the circle. |
| **Emergency summary** | One page: blood group, allergies (highlighted), conditions, current medicines with generic names and morning-afternoon-night amounts, latest key results, emergency contact, doctor, usual hospital. Printable from the app, or shared as a link that works without signing in for 1-72 hours. The link is revocable, `noindex` and `no-store`; every opening is audited and the whole circle is notified. |
| **Reminders** | `POST /admin/tasks/care`, run **hourly**, sends each slot's reminder, the missed-dose notice and the daily refill alert to everyone in the circle, once each. Times are India time (IST). |

## API

All `/v1/care/{care_id}` endpoints take a care id `<owner user id>.<relative id>`, and answer 404 to anyone who isn't the
owner or in the circle.

- `GET /v1/care`: everyone you look after, with today's doses and refills due.
- `GET /v1/care/{id}`: medicines (schedule, refill), today, last 7 days, emergency details, circle (owner only), active links.
- `PUT /v1/care/{id}/info`: blood group (validated), allergies, contacts, doctor, hospital, notes.
- `POST /v1/care/{id}/medications` and `PATCH …/medications/{med_id}`: add a medicine (brand → generic via the medicine list), or change reminders, schedule, tablets at home, or mark it stopped.
- `POST /v1/care/{id}/doses`: `{med_id, slot, status: taken|skipped|null}`, for today or the past 7 days.
- `POST /v1/care/{id}/invite`, `POST /v1/care/join/{token}`, `DELETE /v1/care/{id}/caregivers/{user_id|me}`.
- `GET /v1/care/{id}/summary`: the printable page.
- `POST /v1/care/{id}/emergency-links` `{hours}` and `DELETE …/emergency-links/{link_id}`; the public page is `GET /e/{token}`.
- `POST /admin/tasks/care`: hourly job (admin key).

In the app: **Home → Caring for**, a relative's page → **Caregiver mode**, and invite links open `/app/care-join/<token>`.

## Reminders on the parent's own WhatsApp

For a parent who doesn't use the app, a caregiver can send the reminders to the parent's own WhatsApp (care screen →
*Reminders on their WhatsApp*):

1. **Set up.** The caregiver enters the number and the language (Hindi, Marathi or English), and confirms the parent agreed.
   `PUT /v1/care/{id}/whatsapp` sends the **invitation template**.
2. **Opt in.** Nothing more is sent until the parent replies **YES** (or हाँ / haan).
3. **Reminders.** At each dose time the hourly job sends the **reminder template**, once per slot, naming the
   medicines.
4. **Marking doses.** The parent replies **1** (or "taken", "ले ली", "ho gaya"). The doses for the latest open slot
   are marked taken, and the family sees *marked by Asha (WhatsApp)*.
5. **Stopping.** **STOP** (or रोको / बंद) ends the reminders. The family can also turn them off in the app
   (`DELETE /v1/care/{id}/whatsapp`).
6. **Unclear replies** get a short help message.

The number is stored encrypted, and replies are matched by a keyed hash of it. Reminders carry only the person's
own medicine names, sent to their own phone after they opted in.

### Templates to submit to Meta (WhatsApp Manager → Message templates, category *Utility*)

Template names are configurable: `FHG_WA_TEMPLATE_CARE_OPTIN` and `FHG_WA_TEMPLATE_CARE_REMINDER`.

| Name | Language | Body |
|---|---|---|
| `care_optin` | English (`en`) | Your family has set up medicine reminders for you in Family Health Graph. Reply YES to get them here, or STOP to say no. |
| `care_optin` | Hindi (`hi`) | आपके परिवार ने Family Health Graph में आपके लिए दवा के रिमाइंडर सेट किए हैं। इन्हें यहाँ पाने के लिए YES भेजें, या मना करने के लिए STOP भेजें। |
| `medicine_reminder` | English (`en`) | Time for your {{1}} medicines: {{2}}. Reply 1 when you've taken them. |
| `medicine_reminder` | Hindi (`hi`) | आपकी {{1}} की दवाइयों का समय: {{2}}। दवा लेने के बाद 1 भेजें। |
| `care_optin` | Marathi (`mr`) | तुमच्या कुटुंबाने Family Health Graph मध्ये तुमच्यासाठी औषधांच्या आठवणी सेट केल्या आहेत. त्या इथे मिळवण्यासाठी YES (होय) पाठवा, किंवा नको असल्यास STOP पाठवा. |
| `medicine_reminder` | Marathi (`mr`) | तुमच्या औषधांची वेळ ({{1}}): {{2}}. औषध घेतल्यावर 1 पाठवा. |

`{{1}}` is the time of day (morning, सुबह or सकाळ) and `{{2}}` the medicine names. Replies within 24 hours of the parent's
last message are free text (`fhg/care.py`, `WA_TEXT`).

## To go live

- **Schedule the hourly job** (e.g. a Render cron job: `curl -X POST -H "X-Admin-Key: …" https://<host>/admin/tasks/care`),
  next to the daily `/admin/tasks/reminders`.
- Turn on **push notifications** so reminders reach phones, not just the in-app list.
- Submit the two WhatsApp templates above for approval, so reminders can reach parents who don't use the app.
- The hourly job loads every profile. That's fine for a pilot; past a few thousand users, keep an index of who has
  reminders on.
- Reminder times are fixed (8 am, 2 pm, 9 pm IST). Per-family times are a small addition.
- Schedules are read from the prescription text and can be wrong. The app shows "couldn't read the schedule" and asks
  the caregiver to confirm. It is a reminder tool, not medical advice.
