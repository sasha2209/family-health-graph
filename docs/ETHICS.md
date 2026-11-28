# Running the pilot as an ethics-approved study

A pilot whose results stay inside the clinic is service evaluation. To **publish** outcomes (a paper, a conference
abstract, a funder report presented as evidence), get approval from an Institutional Ethics Committee (IEC) under the
**ICMR National Ethical Guidelines for Biomedical and Health Research Involving Human Participants (2017)** before
the pilot starts, and take informed consent from each family. The product supports this. The committee's decisions,
and the legal sign-off, are yours.

## What the product does

| Need | Where |
|---|---|
| Participant information sheet and consent form, in English, Hindi and Marathi, written to the ICMR headings | `fhg/study.py`. Printable at **`/study`** (`?lang=hi`, `?lang=mr`), with signature, thumb-impression and impartial-witness lines for paper consent. |
| Consent separate from care, and voluntary | Offered after a family has shared with the clinic (intake page), as a card on the app's Home (asked once), and in Settings → Pilot study. "Not now" changes nothing. |
| Each statement agreed, to a known version | Every statement must be ticked. The version is stored with the consent (`FHG_STUDY_VERSION`), and consent to an outdated version is refused. |
| Withdrawal at any time, without affecting care | Settings → Pilot study → Stop taking part. The record and care are untouched; from then on they aren't counted. They can also delete the account. |
| Only participants in the results | With `FHG_STUDY=on`, the pilot report counts only families who consented and haven't withdrawn, the optional survey is asked only of them, and the report says how many withdrew or declined. |
| Under-18s | Can't consent (the same rule as other optional uses), so they're never counted. |
| Confidentiality | The study uses only aggregate counts. Counts from 1 to 4 are shown as "<5" in the shareable report. No names, phone numbers or record contents leave the system for the study. |

## The submission

Most IECs want these. Ask the committee for its own forms and checklist first.

1. **Protocol** (8–12 pages):
   - title, investigators and site;
   - background: family history guides earlier screening, and most families never record it;
   - objectives: the share of families who build a three-generation history, the share with an action item, and
     follow-through on tests and referrals;
   - design: a single-site, prospective, observational pilot of about 12 weeks;
   - participants: adults who are patients of the clinic;
   - recruitment: the intake link and posters at reception (the staff guide's script);
   - consent process (below);
   - outcome measures: the pilot report's sections (`fhg/pilot.py`);
   - sample size: 150–300 families, based on feasibility (no power calculation);
   - analysis: descriptive, with counts and proportions;
   - data management (below);
   - risks and benefits;
   - stopping rules;
   - dissemination.

   [PILOT.md](PILOT.md) has the plan, targets and weekly review to draw on.
2. **Participant information sheet and informed consent form** in each language participants use: print `/study`,
   `/study?lang=hi` and `/study?lang=mr`. The committee will edit the wording. Put its approved text into
   `fhg/study.py` (an English sentence and its translations together), and set `FHG_STUDY_VERSION` to the approved
   version.
3. **Translation certificates.** Committees usually ask for a certificate that the Hindi and Marathi match the
   English, and sometimes for a back-translation. The review sheets (`python -m fhg.translation_review`) don't
   cover `fhg/study.py`. Have the information sheet translated and certified on its own.
4. **Data management plan:**
   - storage: an encrypted database, encrypted backups and access logs (see
     [TRUST_AND_COMPLIANCE.md](TRUST_AND_COMPLIANCE.md) and [RUNNING_IN_PRODUCTION.md](RUNNING_IN_PRODUCTION.md));
   - what the study uses: aggregate counts only;
   - retention: how long the study's aggregate data is kept;
   - who can see what: clinic staff see their own patients for care, and only the coordinator sees the pilot report;
   - DPDP Act compliance: notice, consent, withdrawal, grievance officer, erasure.
5. **Investigator documents:** the principal investigator's CV, GCP training certificate, and a declaration of
   conflicts of interest. Disclose any financial interest in the app.
6. **Site permission** from the clinic, and the clinic agreement (see PILOT.md, "Consent and ethics").
7. **CTRI.** Ask the committee whether registering with the Clinical Trials Registry of India applies. An
   observational pilot often doesn't need it, but many journals expect registration before enrolment.

### The consent process to describe

- Reception staff mention the pilot. Staff don't take study consent at reception: the family reads the
  information sheet on their phone (intake page or app) or on paper, and decides.
- **Using the app is not conditional on taking part.** Families who decline get exactly the same app and care.
- People who can't read are read the sheet aloud by staff, and use the paper form with an impartial witness and a
  thumb impression. Record paper consents in the study file. The app's own consent applies to families who
  consent on their phone.
- Withdrawal: in the app at any time, or by telling the clinic. Staff then ask the coordinator to note it, and the
  family can withdraw in the app themselves.

## Switching it on

Once the committee has approved the study:

```bash
FHG_STUDY=on
FHG_STUDY_VERSION="IEC/2026/014 v2.0, 12 Jan 2027"   # exactly as on the approval letter
FHG_STUDY_INVESTIGATOR="Dr A. Kulkarni, Kothrud Family Clinic"
FHG_STUDY_INVESTIGATOR_CONTACT="+91 20 0000 0000"
FHG_STUDY_COMMITTEE="Institutional Ethics Committee, …"
FHG_STUDY_COMMITTEE_CONTACT="iec@example.org"
```

These are not secrets; set them in the service's environment (render.yaml or the Render dashboard). Then:

- check `/study` in all three languages against the approved documents;
- confirm the console's **Pilot report** says "Run as a study";
- start enrolment.

If the committee later approves an amendment that changes the information sheet, update the text and the version.
People who consented to the old version stay counted. Re-consent only if the committee asks for it; then decide how
to handle it with the committee before changing anything.
