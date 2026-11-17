# Attracting healthcare businesses, and getting funded quickly

This builds on `PARTNERSHIP_STRATEGY.md` and focuses on what to **build and show**.

## What healthcare buyers need to see

Clinics, health systems, health plans and genetic-testing companies all buy the same outcome:
**find the patients who need earlier screening or genetic counseling, and get them into care.**
Family history is the cheapest signal for this, and it's chronically missing from records.
A buyer needs three things from us:

| Buyer question | What answers it | Status |
|---|---|---|
| "How would my patients use this?" | Patients connect to the clinic with a code; their history arrives before the visit | ✅ Clinic portal (connect code) |
| "What would my clinicians do with it?" | A risk-sorted worklist by care program, each patient one click from a clinician summary with a pedigree | ✅ Worklist + clinician summary |
| "What's the impact?" | Patients identified per program, family-history completeness | ✅ Impact tiles (first version) |
| "Does it fit our systems?" | FHIR export today; SMART on FHIR launch inside the EHR next | 🔜 |
| "Is it safe and compliant?" | Encryption, audit trail visible to patients, consent and disconnect, BAA-ready design | ✅ design, 🔜 SOC 2 / BAA paperwork |

## Fastest routes to funding

1. **A pilot with one clinic.** The portal plus the "Load demo patients" button is a complete demo
   today. Offer a free 60-day pilot to a family practice, OB-GYN or cancer-screening clinic, and report
   connected patients, patients identified per program, and referrals completed. Those three numbers are
   what seed investors and health-system buyers ask for.
2. **Non-dilutive grants.** The US NIH SBIR/STTR programs (notably NCI and NHGRI) have funded
   family-history, cascade-testing and risk-identification tools; confirm current solicitations before applying.
   A working product and a pilot letter of support strengthen the application.
3. **Accelerators and strategic partners.** Digital health accelerators, and genetic-testing or
   genetic-counseling companies, for whom identified patients are new volume. See the partnership strategy.

## Build order (next)

1. ✅ **Clinic portal MVP**: connect code, worklist by care program, clinician summary, impact tiles, demo data.
2. ✅ **Referral tracking**: *identified → referred → scheduled → completed* (or declined) per care program,
   a funnel with completion rate and median days to complete, a downloadable pilot report (CSV), and patients
   notified and shown the status in the app.
3. ✅ **Pre-visit intake link**: a link and QR code per clinic (copy from the portal, add to appointment
   reminders, or print the waiting-room poster). Patients complete a two-minute web intake with no app or
   account needed, or open it in the app with the clinic pre-filled. The portal counts "Joined via intake link".
   This is the distribution engine: every visit reminder recruits users.
4. ✅ **Partner API**: genetic-counseling, testing and other partners receive referrals as FHIR `ServiceRequest`s
   (API key, signed health-data-free webhooks) and report *scheduled / completed / declined* back, which updates
   the clinic's funnel and the patient's app. See `PARTNER_API.md`. This is the foundation of platform-fee
   partnerships with testing and counseling companies.
5. **SMART on FHIR app launch**: open the clinician summary inside Epic or Oracle Health for a patient.
   Big for health-system sales, but it needs a sandbox account.
6. **Pilot report as a PDF** (the CSV export exists): a one-page summary of the impact numbers for the clinic's leadership and for investors.
