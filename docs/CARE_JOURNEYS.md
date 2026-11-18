# How people seek care, and how we turn it into a family health graph

## 1. Where health information actually comes from

Most people never type their medical history into anything. It piles up as a by-product of getting care,
scattered across apps, paper and inboxes. Every journey below leaves a different artifact:

| How people seek care | Examples | What it leaves behind | Where it ends up |
|---|---|---|---|
| **Digital consult / booking** | Practo, Apollo 24\|7, Tata 1mg, MFine; Zocdoc, Teladoc (US) | e-prescription (PDF), consult chat, visit summary | Inside that app; downloadable PDF |
| **In-person doctor visit** | Neighbourhood GP, specialist, hospital OPD | **Handwritten prescription**, printed OPD slip, sometimes notes | A photo on the phone, or paper at home |
| **Hospital stay / procedure** | Apollo, Max, Fortis; any hospital | **Discharge summary** (diagnoses, procedures, meds), bills | PDF via email/WhatsApp, or paper; hospital portal |
| **Lab tests** | Thyrocare, Dr Lal PathLabs, Agilus/SRL, Metropolis, Redcliffe; Quest, Labcorp | **Lab report PDF** with structured values (LDL, HbA1c, TSH…) | Email, WhatsApp, lab app |
| **Annual / corporate health check-up** | Employer packages, insurer check-ups | A 20–40 page report with dozens of values | Email PDF; often never opened again |
| **Pharmacy** | 1mg, PharmEasy, Netmeds, Apollo Pharmacy | Order history = an implicit medication list | Pharmacy app |
| **Imaging** | X-ray, ultrasound, MRI centres | Radiology report (PDF/paper) | Email/WhatsApp/paper |
| **Insurance claims** | Health insurers, TPAs, government schemes | Diagnoses and procedures (codes), dates | Insurer portal |
| **National records** | India: ABDM / ABHA; US: patient-access APIs, Apple Health Records | Standardised (FHIR) records from linked facilities | ABHA app / phone |

Two observations drive our design:

1. **The single most common artifact is a photo or PDF.** Paper prescriptions, lab PDFs and discharge
   summaries cover most people in India (and a lot of people everywhere). Connectors to specific platforms
   cover only a slice of patients.
2. **One person usually manages the family's paperwork.** Typically an adult child handling ageing parents'
   reports and prescriptions, or a parent managing children's. That person already holds the family's records,
   which is exactly what a family health graph needs.

## 2. How to bring it all in (ranked by reach and effort)

| Priority | Channel | Covers | Needs partnerships? |
|---|---|---|---|
| **1** | **"Snap or upload any document"**: photo or PDF of a prescription, lab report, discharge summary or check-up report. AI reads it, the user reviews what was extracted, then it's saved with the original attached. | Almost every journey above | No |
| **2** | **Forward it**: a personal email address (`records+x@…`) and a WhatsApp number. Forward the lab's email, done. | Labs, check-ups, hospitals that send PDFs | No (WhatsApp Business API account) |
| **3** | **National / standards connectors**: India's **ABDM** (link ABHA, pull records from linked hospitals and labs with consent); US **SMART on FHIR** patient access, payer APIs; **Apple Health Records / Health Connect** | Digitised facilities | ABDM PHR integration and certification; EHR app registration |
| **4** | **Direct partner feeds**: labs push results, pharmacies share medication lists, teleconsult platforms share e-prescriptions (with the patient's consent) | High-volume partners | Yes |

What the AI extraction produces, per document:
- **Who it's about**: name and age on the document, matched to you or a family member ("This report is for *Asha Shah, 64*. Is that your mother?").
- **Diagnoses** mapped to our condition concepts, with ICD-10 codes where printed.
- **Medications**: name, strength and dose.
- **Lab values**, mapped to LOINC (LDL, HbA1c, TSH…) with units and reference ranges.
- **The doctor or facility, and the date.**

Everything goes through a **review screen** before saving, because handwriting and scans fail, and keeps a
link to the original image. Every value gets a **provenance level** (see section 4).

## 3. Making onboarding easier

The current onboarding asks people to *remember and type*. Better: **start from what's already on their phone.**

1. **First minute: "Upload your latest lab report or check-up."** The instant payoff is real insights from real
   values ("your LDL of 172 plus your father's heart attack at 51…"). That beats a blank form.
2. **Family members as managed profiles.** "Add Mom" creates a profile you manage. Upload her reports and
   prescriptions there. Her *actual diagnoses* (from documents) feed your family history automatically, and they're
   more accurate than recall. Managed profiles become the second way the graph grows, alongside invites. Mom
   can later take over her own profile, which turns into a linked relative.
3. **Suggest, don't interrogate.** After each document: "Your father's prescription mentions metformin. Does he
   have type 2 diabetes?" One tap confirms a family-history fact.
4. **Moments that already happen:** the clinic intake link (built), the annual check-up season, a new diagnosis
   in the family ("Mom was just diagnosed; here's what it means for you and your siblings"), and the
   pre-appointment reminder.
5. **India:** "Link your ABHA" pulls existing records in one step once the ABDM integration exists.

## 4. Building the graph

```
 Person ─── relationship ──▶ Person          (you, managed profiles, linked relatives, remembered relatives)
   │
   └── Facts: condition / medication / lab value / procedure
          each with: date, source document, provenance, reviewer
```

**People** come in four kinds:
- **You**
- **Managed profiles**: you upload their documents
- **Linked relatives**: they have their own account and share with you (built)
- **Remembered relatives**: what you've told us (built)

**Every fact carries a provenance level**, used to decide what wins when sources disagree and shown as a
badge on screen:
- **Remembered**, for example "Dad had a heart attack around 50"
- **From a document you reviewed**, for example a discharge summary with "STEMI, 2019"
- **From a connected source**, for example an ABDM or FHIR record from the hospital

Insights then say *how sure* they are ("based on your father's discharge summary" versus "based on what you remembered").

## 5. Sharing the family history with partners through APIs

This builds on the partner API (referrals, built) and adds a **consented family-history API**.

| Piece | Design |
|---|---|
| **Format** | FHIR R4 `FamilyMemberHistory` (one per relative, with conditions and onset ages), `RiskAssessment` for our insights, `Observation` for lab values, and a pedigree export for genetics partners |
| **Authorization** | "Connect with Family Health Graph": SMART-on-FHIR-style OAuth. The partner's app redirects to us, the user signs in and approves specific scopes, and the partner gets a time-limited token. No passwords are shared. |
| **Consent artefact** | A per-partner record of purpose, data categories, time window and expiry (modelled on ABDM's consent artefacts), revocable at any time, with every access in the user's audit log (built) |
| **What can be shared** | The user's own record and their family history (remembered and managed profiles). **A linked relative's own shared data is never passed on** unless that relative separately allows it ("let my family share my history with their care providers"). |
| **Who it's for** | Genetic-testing and counseling intake (they spend a lot of effort collecting pedigrees), clinics and EHRs before a visit, specialists, and consented, de-identified research. **Never** insurers for underwriting, or employers (trust pledge). |

## 6. Plan

| Phase | Build | Why first |
|---|---|---|
| **1** | ✅ **Document upload with on-server OCR, AI fallback and review** (a relative's document feeds their history); managed family profiles next | Covers the most journeys with no partnerships, and gives users an instant payoff |
| **2** | Email / WhatsApp forwarding; lab value trends; provenance badges | Ingestion with zero effort for the user; repeat engagement |
| **3** | ABDM PHR integration (India) and SMART on FHIR patient access (US) | Standards-based records at scale (needs sandbox access and certification) |
| **4** | Partner family-history API (OAuth, consent artefacts, FHIR `FamilyMemberHistory` / `RiskAssessment`) | Turns the graph into a platform partners pay for |

## 7. Decisions

1. **Launch market: India first.** It's the faster market to get users onboarded and show traction:
   - Records are mostly **paper and PDFs** (handwritten prescriptions, lab-chain PDFs over WhatsApp), so
     "snap your report" solves a real daily problem, and nobody else holds the family's history.
   - **One family member manages the family's health paperwork**, which is exactly the managed-profile behaviour
     the graph needs.
   - **Labs and telehealth companies are partners within reach** (Thyrocare, Dr Lal, Metropolis, Redcliffe,
     Practo, Tata 1mg) and pilots with clinics move faster.
   - **ABDM** gives free national rails (ABHA, PHR apps, consent manager) for phase 3.
   - Revenue per user is lower than in the US, so the US remains the market for payer and health-system contracts
     later. Everything stays FHIR-based, so nothing has to be rebuilt.
2. **AI document reading: allowed, but token-light.** Documents are read on our own server first: the PDF text
   layer, otherwise Tesseract OCR, then rules tuned for Indian prescriptions and lab reports. The AI reader is only
   a fallback (see `DOCUMENT_UPLOAD.md`), it's opt-in per user, and every call's token use is recorded.
