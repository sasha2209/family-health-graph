# Data sources that make the insights better

What we can plug in, grouped by what it improves. **Free / open** first, then **paid** (kept for later).
Licences change and several "free" sources are free only for non-commercial use, so confirm the terms before each
integration. ⭐ marks the ones with the biggest effect for an India-first launch.

## 1. Reading documents and understanding medicines

| Source | What it gives us | Cost / licence |
|---|---|---|
| ⭐ **Indian medicine brand → generic lists**: CDSCO approved-drug lists, the Jan Aushadhi product list, NPPA price lists | Maps "Telma 40" → telmisartan 40 mg and "Glycomet" → metformin, so prescriptions read as real medicines and duplicates across brands merge | Free, government publications (scrape or download, then normalise) |
| ⭐ **Tesseract Indic language data** (`tesseract-ocr-hin`, `-ben`, `-tam`, `-tel`, `-mar`…) | Reads bilingual reports and prescriptions | Free (Apache 2.0) |
| **AI4Bharat** models (IndicTrans2 translation, Indic OCR research models) | Translating and reading regional-language documents on our own servers | Free, open models (check each model's licence) |
| **Bhashini** (Government of India language platform) | Translation and OCR APIs for Indian languages | Free for registered use |
| **RxNorm** (US NLM) | Standard drug names and ingredients; useful for FHIR exports and US expansion | Free (UMLS licence for some content) |
| **openFDA** drug labels, **DailyMed** | Drug label text: indications and warnings | Free, public domain |
| **scispaCy** / **medspaCy** | Medical entity recognition and negation detection, to boost the rules before any AI call | Free (MIT / Apache) |

## 2. Medical vocabularies (making records interoperable)

| Source | What it gives us | Cost / licence |
|---|---|---|
| ⭐ **SNOMED CT** | The standard for diagnoses; ABDM records use it | Free within member countries; India is a member through NRCeS, which also publishes India-specific reference sets |
| ⭐ **LOINC** | Standard lab-test codes (we already use them) | Free |
| **ICD-10 / ICD-11** (WHO API) | Diagnosis codes used on Indian insurance claims and hospital records | Free API |
| **Human Phenotype Ontology (HPO)** | Describing inherited conditions, for genetic-counseling partners | Free |
| **MedlinePlus Connect** (US NLM) | Plain-language explanations of conditions, lab tests and drugs, by code | Free API |

## 3. Risk models (turning history into sharper insights)

| Source | What it gives us | Cost / licence |
|---|---|---|
| ⭐ **IDRS: Indian Diabetes Risk Score** (Madras Diabetes Research Foundation) | A validated, India-specific diabetes risk score from age, waist size, activity and family history | Free, published score (needs waist and activity questions in the app) |
| ⭐ **WHO/ISH cardiovascular risk charts, South Asia** (2019 revision) | 10-year heart-attack and stroke risk calibrated for South Asia | Free |
| **AHA PREVENT** equations (2023), **Pooled Cohort Equations** | 10-year cardiovascular risk (US-derived) | Free, published equations |
| **NCI Breast Cancer Risk Assessment Tool (Gail model)** | 5-year and lifetime breast-cancer risk | Free, public-domain code |
| **Tyrer–Cuzick (IBIS)** | Breast-cancer risk using detailed family history | Free for clinical use; commercial use needs a licence |
| **CanRisk / BOADICEA** | The gold-standard model for breast/ovarian risk and BRCA likelihood from a full pedigree | Free web tool; API and commercial use need a licence agreement |
| **PREMM5** (Dana-Farber) | Probability of Lynch syndrome from personal and family cancer history | Free, published model |
| **Dutch Lipid Clinic Network criteria** | A structured score for familial hypercholesterolemia (we use part of it today) | Free, published criteria |

## 4. Population data (context and calibration)

| Source | What it gives us | Cost / licence |
|---|---|---|
| ⭐ **NFHS-5** (National Family Health Survey, via the DHS Program) | State-level prevalence of diabetes, blood pressure, obesity and anaemia across India | Free with registration |
| ⭐ **ICMR-INDIAB** study publications | Prevalence of diabetes, prediabetes and dyslipidemia by state | Free (published papers) |
| **LASI** (Longitudinal Ageing Study in India) | Health of adults 45+, matching the parents our users manage | Free with registration |
| **NCDIR / National Cancer Registry Programme** reports | Indian cancer incidence by site and region | Free reports |
| **GBD** (IHME Global Burden of Disease) | Disease burden by country and state | Free for non-commercial use; commercial use needs a licence |
| **NHANES** (US CDC) | Lab-value distributions for US calibration | Free, public domain |

## 5. Genetics (for partners in genetic counseling and testing)

| Source | What it gives us | Cost / licence |
|---|---|---|
| ⭐ **ClinVar** (NCBI) | Whether a gene variant on a user's test report is pathogenic | Free, public domain |
| **gnomAD** | How common a variant is across populations, including South Asian | Free |
| **GenomeIndia / IndiGen** | Indian population variant data | Access by application to the Indian Biological Data Centre |
| **ClinGen** gene–disease validity | Which genes really cause which conditions | Free |

## 6. Records and test data

| Source | What it gives us | Cost / licence |
|---|---|---|
| ⭐ **ABDM sandbox** (Ayushman Bharat Digital Mission) | Pull records from hospitals and labs a user has linked to their ABHA | Free sandbox; going live requires certification and a security audit (an audit fee applies) |
| **Synthea** | Realistic synthetic patients and families in FHIR, for demos and load tests | Free (Apache 2.0) |
| **Apple Health Records / Android Health Connect** | Records and vitals already on the phone | Free platform APIs |
| **MIMIC-IV** | De-identified hospital data, for testing extraction quality | Free after credentialing (research use) |

## Paid resources (for later)

| Resource | Why we'd want it | Typical model |
|---|---|---|
| **CIMS India / MIMS India** drug database | The most complete Indian brand → composition → dosing data, plus interactions | Annual licence |
| **DrugBank** | Drug–drug interactions and mechanisms (free for academic use only) | Commercial licence |
| **First Databank, Medi-Span, Lexicomp** | Clinical-grade interaction and dosing checks, for a medication-safety feature | Enterprise licence |
| **UpToDate / BMJ Best Practice** content APIs | Clinician-grade explanations behind each insight | Enterprise licence |
| **CanRisk API (commercial), QRISK3 (ClinRisk)** | Validated risk scores inside the product | Per-use or annual licence |
| **NCCN guideline licensing** | Citing and embedding NCCN criteria commercially | Licence |
| **OMIM** (commercial use) | Detailed inherited-disease descriptions | Licence (free for academic use) |
| **IMO / Intelligent Medical Objects** | Mapping messy diagnosis text to SNOMED and ICD | Subscription |
| **Cloud document and medical NLP**: Azure Document Intelligence, Google Document AI, AWS Comprehend Medical | Higher-accuracy OCR and medical entity extraction for hard documents. English and US-centric, so test on Indian documents | Pay per page or request |
| **Indian lab and telehealth partner APIs**: Thyrocare, Dr Lal PathLabs, Redcliffe, Healthians, Tata 1mg, Practo | Results sent straight from the source; booking tests from an insight | Partnership or revenue share |
| **Genetic testing partners**: MedGenome, Strand, Mapmygenome (India); Color, Invitae (US) | Turning a "consider genetic counseling" insight into a booked test | Partnership or referral fee |
| **US interoperability networks**: Health Gorilla, Particle Health, Redox | Patient records across US providers, for US expansion | Per-record or subscription |
| **UK Biobank, All of Us** (researcher tiers) | Large family-history and outcome datasets to validate our rules | Access fees or research approval |

## Suggested order

1. **Now (free, high impact):**
   - ✅ **Indian brand → generic medicine list:** `fhg/data/india_medicines.csv`, a curated starter list of 100+
     common brands with their generic and drug class (`fhg/medicines.py`). Prescriptions show the generic, and the
     same medicine under different brands merges. Verify the list before clinical use; extend it from CDSCO/NPPA
     data, or license CIMS/MIMS for full coverage.
   - ✅ **IDRS (Indian Diabetes Risk Score):** the `indian_diabetes_risk` insight. It scores age, waist, physical
     activity and parental diabetes using the published MDRF bands (Mohan et al., 2005), and the app asks the two
     extra questions.
   - ⏳ **WHO South Asia CVD risk charts (2019):** not added yet. The chart data or model coefficients have to come
     from the WHO HEARTS technical package or the Lancet Global Health 2019 paper's supplement; those sources weren't
     reachable from our build environment, and we won't transcribe risk tables from memory. The only machine-readable
     source found (the `whoishRisk` R package) contains the older 2007 WHO/ISH charts under a GPL-3 licence.
     Next step: get the official 2019 tables from WHO, then implement and test them cell by cell.
   - The Hindi OCR pack (`tesseract-ocr-hin`).
2. **Next:** NFHS-5 / ICMR-INDIAB for state-level context, ClinVar for genetic reports, and the ABDM sandbox.
3. **With revenue or partners:** CIMS/MIMS for medicine safety, CanRisk for hereditary-cancer partners, and lab APIs.
