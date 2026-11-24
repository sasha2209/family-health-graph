# Hereditary-risk models from the family tree

Most family-history tools ask one questionnaire and flag a pattern. Family Health Graph already holds a living
family record, so it can feed the established models directly, and give a counseling partner a ready-to-run input
instead of a phone call.

## What's built

| Model | What it answers | How it's done | Where |
|---|---|---|---|
| **Pedigree** | Who is whose parent | Relatives recorded by relationship are placed in a real tree; unaffected placeholders link relatives whose connecting parent wasn't recorded (a cousin's parent, a niece's parent). Anyone who can't be placed (sex unknown, side unknown, half-siblings) is listed, never guessed. | `fhg/pedigree.py` |
| **Amsterdam II criteria** (Vasen 1999) | Does the family meet the clinical definition of Lynch syndrome? | ≥3 relatives with colorectal/endometrial cancer, one a first-degree relative of the other two, ≥2 successive generations, ≥1 before 50. Computed on the tree, with the people who met each part. | `fhg/risk_models.py` |
| **Revised Bethesda guidelines** (Umar 2004) | Should someone's colorectal tumour be tested for mismatch-repair deficiency? | Per person with colorectal cancer: before 50; more than one Lynch-associated cancer; a first-degree relative with one, either before 50; two or more first/second-degree relatives with one. Criterion 3 (MSI-H histology) needs a pathology report and is reported as not assessable. | `fhg/risk_models.py` |
| **BOADICEA via CanRisk** | Breast and ovarian cancer risk (10-year, lifetime), and BRCA1/2 etc. carrier probability | We don't re-implement BOADICEA. We export the family as a **CanRisk 2.0 pedigree file** (27 tab-separated columns, no names). The counselor loads it in canrisk.org and can post the figures back. | `risk_models.canrisk_file` |

The criteria raise a new action item, **"Family pattern meets Lynch syndrome criteria"** (`lynch_criteria`, high),
which offers genetic counseling through the test-booking flow and the clinic referral program
"Genetic counseling: Lynch syndrome".

## API

For the person:

- `GET /v1/risk`: the tree summary (people, placeholders, who couldn't be placed), the Lynch results, the calculators
  available, and any risk figures a counselor has shared.
- `GET /v1/risk/canrisk`: download the CanRisk file. `409` until the person's own sex is set. Warnings for the
  counselor (unknown diagnosis ages written as `AU`, placeholders, an unspecified BRCA variant) are in the
  `X-FHG-Warnings` header. Audited.

For a genetic counseling partner holding a referral (API key):

- `GET /v1/partner/referrals/{id}/canrisk`: the same file for the referred person. Audited.
- `POST /v1/partner/referrals/{id}/risk-assessment`:

  ```json
  {"model": "BOADICEA v6 (CanRisk)",
   "predictions": [{"outcome": "Breast cancer", "probability_percent": 9.1, "horizon": "next 10 years",
                    "population_percent": 2.3}],
   "note": "Discussed at counseling on 3 Dec."}
  ```

  Stored encrypted, shown on the action item, and the person is notified.

In the app, the hereditary breast/ovarian, colorectal and Lynch action items have **For your genetic counselor →
Share the CanRisk file**, and show the counselor's figures once posted.

## The CanRisk file

The format was checked against CanRisk's own reader and writer (`es/canrisk_file.js` in
[pedigreejs](https://github.com/CCGE-BOADICEA/pedigreejs)), since canrisk.org wasn't reachable from the build
environment:

```
##CanRisk 2.0
##BMI=24.1                      (female proband, when a BMI result exists)
##FamID Name Target IndivID FathID MothID Sex MZtwin Dead Age Yob BC1 BC2 OC PRO PAN Ashkn BRCA1 … BRIP1 ER:PR:HER2:CK14:CK56
```

Cancer columns hold the age at diagnosis, `0` for unaffected, `AU` for affected at an unknown age. Ovarian cancer
is only written for women and prostate cancer only for men. Gene-test columns are `0:0` (untested) because the record
doesn't yet hold structured test results. **Before go-live:** load a few exported files in CanRisk to confirm they
open cleanly.

## Deliberately not built yet

- **PREMM5** (Lynch syndrome probability) and the **Manchester scoring system** (BRCA1/2). Both need published
  coefficients or point tables. The primary papers (PubMed Central, the DFCI PREMM site) were unreachable from the
  build environment, and these numbers must not be typed in from memory. Once someone can check the papers, both
  slot in next to the criteria in `fhg/risk_models.py`.
- **The CanRisk web-services API** (running BOADICEA server-side). It needs a CanRisk account and API token, and
  terms that allow it. With that, the counselor's manual step becomes automatic.
- **WHO South Asia cardiovascular risk charts**: still waiting on the official 2019 tables (see
  `docs/DATA_SOURCES.md`).
- **Structured genetic test results** (gene, variant, who was tested), which would fill the CanRisk gene columns.

All criteria and exports need review by a genetic counselor before clinical use.
