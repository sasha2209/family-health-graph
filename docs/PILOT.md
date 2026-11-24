# Running the pilot: a playbook

**Goal:** one clinic, one city, 150–300 families, 8–12 weeks. At the end, show with real numbers that families build a
useful family record, that it surfaces things worth acting on, and that people act on them.

## Roles

| Role | Who | Does |
|---|---|---|
| Pilot coordinator | Us | Runs the console (`/admin`), answers concerns, checks the weekly numbers, first contact for the clinic |
| Clinic lead | A doctor at the clinic | Owns the pilot inside the clinic, reviews flagged patients, decides referrals |
| Reception staff | Clinic | Invite patients at booking and check-in (staff guide, section 1) |
| Lab partner | e.g. a local diagnostics chain | Takes test bookings, posts results back |
| Genetic counselor (optional) | Partner | Takes hereditary-cancer referrals; reviews the risk rules before launch |

## Timeline

| When | What |
|---|---|
| **Weeks −4 to −2** | Sign the clinic (data-sharing terms below) and the lab partner. Decide on ethics review. Set up production with the [go-live checklist](RUNNING_IN_PRODUCTION.md#before-the-first-family-signs-up). Ship the TestFlight / Play internal builds ([RELEASE.md](RELEASE.md)). Native-speaker review of the Hindi. |
| **Week −1** | Create the clinic in the app; staff join with the staff code. Add the lab partner and its price list in the console. 30-minute staff training (below). Print the poster and staff guide: clinic portal → *Print poster* / *Staff guide*. Do a dry run: three staff members complete the intake as patients. |
| **Weeks 1–8** | Reception invites patients at booking and check-in. The clinic lead reviews the worklist weekly. Weekly 20-minute review (below). Fix anything that blocks families within days. |
| **Week 8** | Follow-up survey questions appear automatically for the first families. |
| **Weeks 8–12** | Keep going; push on follow-through (tests booked → completed, referrals → seen). |
| **Week 12** | Download the pilot report (console → Pilot report → *Download CSV to share*) and the clinic's own report (portal → *Download pilot report*). Write up with the clinic lead. |

## Staff training (30 minutes)

1. **What it is and why** (5 min): family history changes when screening should start; most families never write it down.
2. **Reception script** (10 min): role-play with the staff guide, in English and Hindi. Practice the three common
   questions: is it free, who sees it, is it a diagnosis.
3. **The portal** (10 min): the worklist, a patient summary, setting a referral status, the funnel.
4. **Do and don't** (5 min): the patient ticks consent themselves; action items are prompts, not results.

## Weekly review (20 minutes, coordinator + clinic lead)

From the console's **Pilot report** and the portal's **funnel**:
- New families this week, and the share who added relatives (target: most) and three generations.
- Families with something to act on: has the clinic lead seen each one?
- Tests booked vs completed; referrals stuck at "referred" for more than two weeks.
- Doses taken, for families using caregiver mode.
- Open concerns (none overdue), job health (all green).

Write down one thing to change for next week.

## Consent and ethics

- **Patients:** consent is built into the product. They tick to share with the clinic, every optional use is its
  own switch, the privacy notice is in English and Hindi, and they can withdraw any time
  ([TRUST_AND_COMPLIANCE.md](TRUST_AND_COMPLIANCE.md)). Participation must not affect their care, and the staff
  guide says so.
- **Using pilot results as research:** to publish outcomes, get approval from an Institutional Ethics Committee
  under the ICMR National Ethical Guidelines before the pilot starts, and use the committee's participant
  information and consent wording. The clinic's own committee, or one the partner hospital uses, is usually the
  fastest route. Ask it whether registration with the Clinical Trials Registry of India applies to the design.
- **Survey answers** are optional and reported only as counts. The shareable report hides any count below 5.
- **Clinic agreement:** agree in writing what the clinic receives (the patients who connected, their summaries and
  insights), that it uses them only for those patients' care, and how it handles access and deletion. Have a
  lawyer check this against the DPDP Rules.

## What success looks like

Agree on targets with the clinic before week 1. For example:
- 60% of invited patients complete the intake.
- 70% of families record at least one relative, and 40% record three generations.
- Every family with an item to discuss soon is reviewed by a clinician.
- 50% of booked tests are completed within 30 days.
- Most families answer "some" or "very little" at baseline, and "test" or "doctor" at follow-up.

Every one of these comes straight from the pilot report.
