"""Family-history-aware insight rules.

Each rule is a pure function ``HealthProfile -> Insight | None``. Rules are
deliberately transparent: every insight lists the exact facts that triggered it
and the published guidance it is based on, so a user (or their clinician) can
check the reasoning. Thresholds are simplified summaries of the cited
guidance; they flag "worth discussing", they do not diagnose.

Clinical content must be reviewed by qualified clinicians and genetic
counselors before any production use, and re-reviewed when guidelines change.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..models import Condition, FamilyMember, HealthProfile, Insight, Level, Reference
from ..terminology import ldl_mg_dl
from ..trends import rising_hba1c
from .lang import join_and, mark, tr

Rule = Callable[[HealthProfile], Optional[Insight]]

REF_USPSTF_BRCA = Reference(
    title="USPSTF (2019): BRCA-Related Cancer: Risk Assessment, Genetic Counseling, and Genetic Testing",
    url="https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/brca-related-cancer-risk-assessment-genetic-counseling-and-genetic-testing",
)
REF_NCCN = Reference(
    title="NCCN Guidelines: Genetic/Familial High-Risk Assessment (Breast, Ovarian, Pancreatic, Prostate; Colorectal)",
    url="https://www.nccn.org/guidelines/category_2",
)
REF_USMSTF_CRC = Reference(
    title="US Multi-Society Task Force (2017): Colorectal Cancer Screening Recommendations",
    url="https://pubmed.ncbi.nlm.nih.gov/28555630/",
)
REF_USPSTF_CRC = Reference(
    title="USPSTF (2021): Colorectal Cancer Screening",
    url="https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/colorectal-cancer-screening",
)
REF_ACC_AHA_CHOL = Reference(
    title="2018 AHA/ACC Guideline on the Management of Blood Cholesterol",
    url="https://www.ahajournals.org/doi/10.1161/CIR.0000000000000625",
)
REF_ADA = Reference(
    title="ADA Standards of Care in Diabetes: Diagnosis and Classification / Screening",
    url="https://professional.diabetes.org/standards-of-care",
)
REF_ACS_PROSTATE = Reference(
    title="American Cancer Society: Recommendations for Prostate Cancer Early Detection",
    url="https://www.cancer.org/cancer/types/prostate-cancer/detection-diagnosis-staging/acs-recommendations.html",
)
REF_MHAUS = Reference(
    title="Malignant Hyperthermia Association of the United States (MHAUS)",
    url="https://www.mhaus.org/",
)
REF_ACC_AHA_BP = Reference(
    title="2017 ACC/AHA Guideline for High Blood Pressure in Adults",
    url="https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065",
)
REF_SURGEON_GENERAL = Reference(
    title="U.S. Surgeon General's My Family Health Portrait",
    url="https://phgkb.cdc.gov/FHH/html/index.html",
)


def who(member: FamilyMember) -> str:
    return tr(member.label)


def cond_name(cond: Condition) -> str:
    return tr(cond.display_name)


def describe(member: FamilyMember, cond: Condition) -> str:
    if cond.onset_age is None:
        age = tr("age at diagnosis unknown")
    elif cond.age_estimated:
        age = tr("diagnosed at about {age}", age=cond.onset_age)
    else:
        age = tr("diagnosed at {age}", age=cond.onset_age)
    return f"{who(member)}: {cond_name(cond)} ({age})"


def describe_self(cond: Condition) -> str:
    if cond.onset_age is None:
        return tr("You: {condition}", condition=cond_name(cond))
    return tr("You: {condition}, diagnosed at {age}", condition=cond_name(cond), age=cond.onset_age)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


# --- hereditary breast & ovarian cancer (HBOC) --------------------------------

def hereditary_breast_ovarian(p: HealthProfile) -> Optional[Insight]:
    evidence, reasons = [], []
    level = Level.MODERATE

    for m, c in p.affected({"hboc_variant"}, max_degree=3):
        evidence.append(describe(m, c))
        reasons.append(tr("a relative has a known BRCA1/BRCA2 variant"))
        level = Level.HIGH

    for m, c in p.affected({"breast_cancer"}, max_degree=2):
        if c.onset_age is not None and c.onset_age <= 50:
            evidence.append(describe(m, c))
            reasons.append(tr("breast cancer at or before age 50 in a close relative"))
        if m.effective_sex == "male":
            evidence.append(describe(m, c))
            reasons.append(tr("male breast cancer in the family"))

    for m, c in p.affected({"ovarian_cancer"}, max_degree=2):
        evidence.append(describe(m, c))
        reasons.append(tr("ovarian cancer in a close relative (any age)"))

    for m, c in p.affected({"pancreatic_cancer"}, max_degree=2):
        evidence.append(describe(m, c))
        reasons.append(tr("pancreatic cancer in a close relative (any age)"))

    for side in ("maternal", "paternal"):
        same_side = {
            m.id: (m, c) for m, c in p.affected({"breast_cancer"}, max_degree=3)
            if side in m.lineage_sides
        }
        if len(same_side) >= 2:
            evidence.extend(describe(m, c) for m, c in same_side.values())
            reasons.append(tr({"maternal": "two or more relatives with breast cancer on your maternal side",
                                "paternal": "two or more relatives with breast cancer on your paternal side"}[side]))

    for c in p.own_conditions({"breast_cancer"}):
        if c.onset_age is not None and c.onset_age <= 50:
            evidence.append(describe_self(c))
            reasons.append(tr("your own breast cancer diagnosis at or before 50"))
    for c in p.own_conditions({"ovarian_cancer", "pancreatic_cancer"}):
        evidence.append(describe_self(c))
        reasons.append(tr("your own {condition} diagnosis", condition=cond_name(c).lower()))

    if not reasons:
        return None

    return Insight(
        rule_id="hboc_family_pattern",
        category="hereditary_cancer",
        level=level,
        title=tr("Family pattern worth a hereditary cancer risk assessment"),
        summary=tr(
            "Your family history includes {reasons}. Patterns like this are the ones guidelines use to decide who "
            "should be offered genetic counseling for inherited cancer risk (for example BRCA1/BRCA2). It does not "
            "mean you have a variant.", reasons="; ".join(_dedupe(reasons))),
        evidence=_dedupe(evidence),
        recommendation=tr(
            "Ask your clinician about a formal familial risk assessment and, if appropriate, referral to a genetic "
            "counselor. If a relative has already had genetic testing, ask for a copy of their result: it makes your "
            "own testing far more informative. This applies to people of any sex; inherited variants also affect "
            "prostate, pancreatic and male breast cancer risk."),
        references=[REF_USPSTF_BRCA, REF_NCCN],
    )


# --- colorectal cancer & Lynch syndrome ---------------------------------------

LYNCH_CANCERS = {"colorectal_cancer", "endometrial_cancer", "ovarian_cancer", "stomach_cancer"}


def colorectal_family_history(p: HealthProfile) -> Optional[Insight]:
    fdr = p.affected({"colorectal_cancer"}, max_degree=1)
    known_lynch = p.affected({"lynch_syndrome"}, max_degree=3)
    early = [
        (m, c) for m, c in p.affected({"colorectal_cancer", "endometrial_cancer"}, max_degree=2)
        if c.onset_age is not None and c.onset_age < 50
    ]
    lynch_relatives = {m.id for m, _ in p.affected(LYNCH_CANCERS, max_degree=2)}

    genetic = bool(known_lynch or early or len(lynch_relatives) >= 3)
    if not fdr and not genetic:
        return None

    evidence = [describe(m, c) for m, c in fdr + known_lynch + early]
    parts, recs = [], []
    level = Level.MODERATE

    if fdr:
        ages = [c.onset_age for _, c in fdr if c.onset_age is not None]
        higher = len({m.id for m, _ in fdr}) >= 2 or any(a < 60 for a in ages)
        start = 40
        if ages and higher:
            start = min(40, min(ages) - 10)
        parts.append(tr("a parent, sibling or child has had colorectal cancer"))
        if higher:
            recs.append(tr(
                "Guidelines for this pattern suggest colonoscopy starting around age {start} (age 40, or 10 years "
                "before the youngest affected relative's diagnosis, whichever is earlier) and repeating about every "
                "5 years.", start=start))
        else:
            recs.append(tr("Guidelines for this pattern suggest starting screening at age 40 rather than 45."))
        if any(c.onset_age is None for _, c in fdr):
            recs.append(tr(
                "At least one relative's age at diagnosis is unknown; if it was before 60, screening may need to start "
                "earlier and be more frequent."))
        age = p.age()
        if age is not None and age >= start:
            level = Level.HIGH
            recs.append(tr("You are {age}, so if you haven't been screened yet this is worth raising now.", age=age))

    if genetic:
        level = Level.HIGH
        parts.append(tr(
            "a known Lynch syndrome diagnosis in the family" if known_lynch
            else "a pattern (early-onset or multiple Lynch-associated cancers) that can point to Lynch syndrome"))
        evidence.extend(describe(m, c) for m, c in p.affected(LYNCH_CANCERS, max_degree=2))
        recs.append(tr(
            "Ask about genetic counseling for Lynch syndrome, which raises the risk of colorectal, endometrial and "
            "several other cancers and changes screening substantially."))

    return Insight(
        rule_id="colorectal_family_history",
        category="hereditary_cancer",
        level=level,
        title=tr("Colorectal cancer in the family may change when screening starts"),
        summary=tr("Your record shows {findings}. The general-population screening start age is 45; family history "
                   "can move it earlier.", findings=join_and(parts)),
        evidence=_dedupe(evidence),
        recommendation=" ".join(recs),
        references=[REF_USMSTF_CRC, REF_USPSTF_CRC, REF_NCCN],
    )


# --- premature cardiovascular disease -----------------------------------------

def premature_ascvd(p: HealthProfile) -> Optional[Insight]:
    # Relatives with unknown onset age are surfaced by record_gaps instead.
    premature = []
    for m, c in p.affected({"coronary_artery_disease", "stroke"}, max_degree=1):
        sex = m.effective_sex
        threshold = 55 if sex == "male" else 65 if sex == "female" else None
        if c.onset_age is not None and threshold is not None and c.onset_age < threshold:
            premature.append((m, c))

    if not premature:
        return None

    evidence = [describe(m, c) for m, c in premature]
    level = Level.MODERATE
    ldl = p.latest("ldl_cholesterol")
    extra = ""
    if ldl:
        mg = ldl_mg_dl(ldl.value, ldl.unit)
        evidence.append(tr("Your most recent LDL cholesterol: {value}", value=f"{ldl.value:g} {ldl.unit}".strip()))
        if mg >= 160:
            level = Level.HIGH
            extra = " " + tr("Combined with an LDL of 160 mg/dL or higher, this is worth discussing soon.")
    if not ldl:
        extra += " " + tr("There's no cholesterol result in your record yet.")

    return Insight(
        rule_id="premature_ascvd_family_history",
        category="cardiovascular",
        level=level,
        title=tr("Early heart disease or stroke in a parent or sibling"),
        summary=tr(
            "A first-degree relative had heart disease or stroke at a young age (men before 55, women before 65). "
            "Cardiology guidelines treat this as a 'risk-enhancing factor' that can tip decisions about cholesterol "
            "treatment.") + extra,
        evidence=_dedupe(evidence),
        recommendation=tr(
            "Ask your clinician to estimate your 10-year cardiovascular risk with this family history included, check "
            "a lipid panel if you haven't recently, and consider measuring lipoprotein(a) at least once. Lp(a) is "
            "largely inherited and isn't part of a standard panel."),
        references=[REF_ACC_AHA_CHOL],
    )


def familial_hypercholesterolemia(p: HealthProfile) -> Optional[Insight]:
    evidence = []
    ldl = p.latest("ldl_cholesterol")
    high_ldl = ldl is not None and ldl_mg_dl(ldl.value, ldl.unit) >= 190
    if high_ldl:
        evidence.append(tr("Your most recent LDL cholesterol: {value}", value=f"{ldl.value:g} {ldl.unit}".strip()))
    fh_family = p.affected({"familial_hypercholesterolemia"}, max_degree=2)
    evidence.extend(describe(m, c) for m, c in fh_family)
    # A first-degree relative's very high LDL (from their own lab report, on a managed profile) is one of
    # the family criteria clinicians use to look for FH.
    relative_ldl = [(m, o) for m in p.family if m.degree == 1
                    for o in [m.latest("ldl_cholesterol")] if o and ldl_mg_dl(o.value, o.unit) >= 190]
    evidence.extend(tr("{who}: LDL cholesterol {value} (from their lab report)", who=who(m),
                       value=f"{o.value:g} {o.unit}".strip()) for m, o in relative_ldl)
    own_fh = p.own_conditions({"familial_hypercholesterolemia"})

    if not (high_ldl or fh_family or relative_ldl) or own_fh:
        return None

    return Insight(
        rule_id="familial_hypercholesterolemia",
        category="cardiovascular",
        level=Level.HIGH,
        title=tr("Possible inherited high cholesterol (familial hypercholesterolemia)"),
        summary=tr(
            "Your record shows {findings}. Guidelines use this as a signal to look for familial hypercholesterolemia, "
            "a common inherited condition that is very treatable when found early.",
            findings=join_and([tr(s) for s, on in (
                (mark("an LDL of 190 mg/dL or higher"), high_ldl),
                (mark("a relative diagnosed with familial hypercholesterolemia"), bool(fh_family)),
                (mark("a parent, sibling or child with an LDL of 190 mg/dL or higher"), bool(relative_ldl)),
            ) if on])),
        evidence=evidence,
        recommendation=tr(
            "Discuss evaluation for familial hypercholesterolemia with your clinician. If it is confirmed, your "
            "parents, siblings and children should also have their cholesterol checked."),
        references=[REF_ACC_AHA_CHOL],
    )


# --- diabetes -------------------------------------------------------------------

def diabetes_risk(p: HealthProfile) -> Optional[Insight]:
    if p.own_conditions({"type_2_diabetes", "type_1_diabetes"}):
        return None
    fdr = p.affected({"type_2_diabetes"}, max_degree=1)
    a1c = p.latest("hba1c")
    bmi = p.latest("bmi")
    age = p.age()

    evidence = [describe(m, c) for m, c in fdr]
    findings, level = [], None

    if a1c:
        evidence.append(tr("Your most recent HbA1c: {value}%", value=f"{a1c.value:g}"))
        if a1c.value >= 6.5:
            level = Level.HIGH
            findings.append(tr(
                "your most recent HbA1c is in the diabetes range (6.5% or higher); a diagnosis needs a confirming "
                "test, so please follow up with your clinician"))
        elif a1c.value >= 5.7:
            level = Level.MODERATE
            findings.append(tr("your most recent HbA1c is in the prediabetes range (5.7–6.4%)"))

    rise = rising_hba1c(p.observations)
    if rise:
        first, last = rise
        evidence.append(tr("Your HbA1c rose from {first}% ({first_date}) to {last}% ({last_date})",
                           first=f"{first.value:g}", first_date=f"{first.effective_date:%b %Y}",
                           last=f"{last.value:g}", last_date=f"{last.effective_date:%b %Y}"))
        level = level or Level.MODERATE
        findings.append(tr("your HbA1c has been rising across your recent tests"))

    if fdr:
        if bmi:
            evidence.append(tr("Your most recent BMI: {value}", value=f"{bmi.value:g}"))
        overweight = bmi is not None and bmi.value >= 25
        if overweight or (age is not None and age >= 35) or level:
            level = level or Level.MODERATE
            findings.append(tr("a parent or sibling has type 2 diabetes, and your BMI is 25 or higher") if overweight
                            else tr("a parent or sibling has type 2 diabetes"))
        else:
            level = level or Level.INFO
            findings.append(tr("a parent or sibling has type 2 diabetes"))

    if not findings:
        return None

    return Insight(
        rule_id="diabetes_risk",
        category="metabolic",
        level=level,
        title=tr("Type 2 diabetes risk"),
        summary=tr("Your record shows {findings}.", findings="; ".join(findings)),
        evidence=_dedupe(evidence),
        recommendation=tr(
            "Ask about diabetes screening (an HbA1c or fasting glucose test). Family history plus overweight is a "
            "standard reason to screen, and prediabetes is often reversible with structured lifestyle programs such "
            "as the National Diabetes Prevention Program."),
        references=[REF_ADA],
    )


# --- Indian Diabetes Risk Score (MDRF) -------------------------------------------

REF_IDRS = Reference(
    title="Mohan V et al. A simplified Indian Diabetes Risk Score for screening for undiagnosed diabetic subjects. "
          "J Assoc Physicians India 2005;53:759-63 (Madras Diabetes Research Foundation)",
    url="https://pubmed.ncbi.nlm.nih.gov/?term=simplified+Indian+Diabetes+Risk+Score+Mohan+2005",
)
ACTIVITY_POINTS = {"exercise_and_active_work": 0, "exercise_or_active_work": 20, "sedentary": 30}
ACTIVITY_LABEL = {"exercise_and_active_work": "regular exercise and an active job or housework",
                  "exercise_or_active_work": "regular exercise or an active job, not both",
                  "sedentary": "no regular exercise and mostly sitting"}


def idrs(p: HealthProfile) -> Optional[dict]:
    """The Indian Diabetes Risk Score (0-100): age, waist, physical activity and parents' diabetes.
    Returns the score with its parts, or None without an age. Missing parts are listed, not guessed."""
    age = p.age()
    if age is None:
        return None
    parts: dict[str, int] = {"age": 0 if age < 35 else 20 if age < 50 else 30}
    missing = []
    waist = p.latest("waist_circumference")
    sex = p.sex.value if p.sex else None
    if waist and sex in ("female", "male"):
        cm = waist.value * 2.54 if "in" in (waist.unit or "").lower() else waist.value
        low, high = (80, 90) if sex == "female" else (90, 100)
        parts["waist"] = 0 if cm < low else 10 if cm < high else 20
    else:
        missing.append("waist size" if waist is None else "sex")
    if p.activity in ACTIVITY_POINTS:
        parts["activity"] = ACTIVITY_POINTS[p.activity]
    else:
        missing.append("physical activity")
    diabetic_parents = {m.relationship.value for m in p.family if m.relationship.value in ("mother", "father")
                        and any(c.category == "type_2_diabetes" for c in m.conditions)}
    parts["family"] = 10 * len(diabetic_parents)
    return {"score": sum(parts.values()), "parts": parts, "missing": missing, "age": age,
            "waist": waist, "parents": sorted(diabetic_parents)}


def indian_diabetes_risk(p: HealthProfile) -> Optional[Insight]:
    if p.own_conditions({"type_2_diabetes", "type_1_diabetes"}):
        return None
    a1c = p.latest("hba1c")
    if a1c is not None and a1c.value >= 6.5:
        return None  # already in the diabetes range: the diabetes insight covers it
    r = idrs(p)
    if r is None:
        return None
    score, missing = r["score"], r["missing"]
    if missing and score < 60:
        return None  # not enough to say anything yet; the app asks for the missing answers
    evidence = [tr("Age {age}: {points} points", age=r["age"], points=r["parts"]["age"])]
    if "waist" in r["parts"]:
        evidence.append(tr("Waist {value}: {points} points", value=f"{r['waist'].value:g} {r['waist'].unit}".strip(),
                           points=r["parts"]["waist"]))
    if "activity" in r["parts"]:
        evidence.append(tr("Activity ({activity}): {points} points", activity=tr(ACTIVITY_LABEL[p.activity]),
                           points=r["parts"]["activity"]))
    parents = join_and([tr(x) for x in r["parents"]]) or tr("none recorded")
    evidence.append(tr("Parents with diabetes: {parents}: {points} points", parents=parents, points=r["parts"]["family"]))
    band = tr("high (60 or more)" if score >= 60 else "moderate (30–50)" if score >= 30 else "low (under 30)")
    partial = (" " + tr("It may be higher: we don't have your {missing} yet.",
                        missing=tr(" or ").join(tr(x) for x in missing))) if missing else ""
    return Insight(
        rule_id="indian_diabetes_risk",
        category="metabolic",
        level=Level.MODERATE if score >= 60 else Level.INFO,
        title=tr("Indian Diabetes Risk Score: {score} of 100", score=score),
        summary=tr("Your score is {band}. This score was developed and validated for Indian adults; scores of 60 or "
                   "more mean undiagnosed diabetes is much more likely.", band=band) + partial,
        evidence=evidence,
        recommendation=tr(
            "With a score of 60 or more, ask your doctor for a fasting blood sugar, HbA1c or glucose tolerance test."
            if score >= 60 else
            "Keep your weight and waist in check and stay active; re-check your score every year or if anything changes."),
        references=[REF_IDRS, REF_ADA],
    )


# --- prostate cancer ------------------------------------------------------------

def prostate_family_history(p: HealthProfile) -> Optional[Insight]:
    if p.sex is not None and p.sex.value == "female":
        return None
    fdr = p.affected({"prostate_cancer"}, max_degree=1)
    if not fdr:
        return None
    early = [(m, c) for m, c in fdr if c.onset_age is not None and c.onset_age < 65]
    multiple = len({m.id for m, _ in fdr}) >= 2
    if not early and not multiple:
        return None
    start = 40 if (multiple and early) else 45
    return Insight(
        rule_id="prostate_family_history",
        category="hereditary_cancer",
        level=Level.MODERATE,
        title=tr("Prostate cancer in close relatives"),
        summary=tr("A father, brother or son with prostate cancer (especially before 65) puts you in a higher-risk "
                   "group for prostate cancer.") + ("" if p.sex else " " + tr("This applies if you have a prostate.")),
        evidence=[describe(m, c) for m, c in fdr],
        recommendation=tr("The American Cancer Society suggests higher-risk men talk with a clinician about PSA "
                          "screening starting around age {start}, rather than 50.", start=start),
        references=[REF_ACS_PROSTATE, REF_NCCN],
    )


# --- safety ---------------------------------------------------------------------

def anesthesia_safety(p: HealthProfile) -> Optional[Insight]:
    hits = p.affected({"malignant_hyperthermia"}, max_degree=99)
    own = p.own_conditions({"malignant_hyperthermia"})
    if not hits and not own:
        return None
    return Insight(
        rule_id="malignant_hyperthermia",
        category="safety",
        level=Level.HIGH,
        title=tr("Tell any surgical or anesthesia team about this family history"),
        summary=tr(
            "Malignant hyperthermia is an inherited, potentially life-threatening reaction to some anesthesia drugs. "
            "Blood relatives of someone who had it may carry the same risk."),
        evidence=[describe(m, c) for m, c in hits] + [describe_self(c) for c in own],
        recommendation=tr(
            "Before any procedure that involves anesthesia (including dental surgery), tell the team about this "
            "history so they can use safe alternatives. Ask your clinician whether genetic testing or a medical alert "
            "ID is appropriate."),
        references=[REF_MHAUS],
    )


def blood_pressure(p: HealthProfile) -> Optional[Insight]:
    sbp, dbp = p.latest("systolic_bp"), p.latest("diastolic_bp")
    if not sbp and not dbp:
        return None
    s = sbp.value if sbp else 0
    d = dbp.value if dbp else 0
    reading = (f"{s:g}/{d:g} mmHg" if sbp and dbp else
               tr("systolic {value}", value=f"{s:g}") if sbp else tr("diastolic {value}", value=f"{d:g}"))
    family_htn = p.affected({"hypertension"}, max_degree=1)
    evidence = [tr("Your most recent blood pressure: {reading}", reading=reading)] + [describe(m, c) for m, c in family_htn]

    if s >= 180 or d >= 120:
        level, band = Level.HIGH, tr("severely elevated")
        rec = tr("Contact a clinician promptly to recheck it. If you have chest pain, shortness of breath, severe "
                 "headache, weakness, or vision or speech changes, seek emergency care.")
    elif s >= 140 or d >= 90:
        level, band = Level.MODERATE, tr("in the stage 2 high blood pressure range")
        rec = tr("Ask your clinician about confirming this with repeat or home readings.")
    elif s >= 130 or d >= 80:
        level, band = Level.INFO, tr("in the stage 1 high blood pressure range")
        rec = tr("One reading isn't a diagnosis; home monitoring over a few weeks gives a clearer picture.")
    else:
        return None

    return Insight(
        rule_id="blood_pressure",
        category="cardiovascular",
        level=level,
        title=tr("Blood pressure reading above target"),
        summary=tr("Your most recent reading ({reading}) is {band} under the 2017 ACC/AHA definitions.",
                   reading=reading, band=band),
        evidence=evidence,
        recommendation=rec,
        references=[REF_ACC_AHA_BP],
    )


# --- data completeness ------------------------------------------------------------

AGE_SENSITIVE = {
    "breast_cancer", "colorectal_cancer", "endometrial_cancer", "prostate_cancer",
    "coronary_artery_disease", "stroke",
}


def record_gaps(p: HealthProfile) -> Optional[Insight]:
    questions = []
    for m in p.family:
        for c in m.conditions:
            if c.category == "cancer_unspecified":
                questions.append(tr("What type of cancer did your {who} have, and at what age?", who=who(m).lower()))
            elif c.category in AGE_SENSITIVE and c.onset_age is None:
                questions.append(tr("How old was your {who} when diagnosed with {condition}? Age changes the guidance.",
                                    who=who(m).lower(), condition=cond_name(c).lower()))
            elif c.category is None:
                questions.append(tr("Can you find out more about your {who}'s '{name}'?", who=who(m).lower(), name=c.name))

    rels = {m.relationship.value for m in p.family}
    if "mother" not in rels:
        questions.append(tr("Add your mother's health history (even 'no known conditions' helps)."))
    if "father" not in rels:
        questions.append(tr("Add your father's health history (even 'no known conditions' helps)."))
    if not any(r.startswith("maternal_grand") for r in rels) and not any(
        r.startswith("paternal_grand") for r in rels
    ):
        questions.append(tr("Add what you know about your grandparents on both sides."))
    if not p.birth_date or not p.sex:
        questions.append(tr("Add your date of birth and sex so age- and sex-specific guidance can apply."))
    if not any(m.linked for m in p.family):
        questions.insert(0, tr("Invite a parent or sibling to add their own history. When they share it, your "
                               "insights update automatically, and theirs do too."))

    if not questions:
        return None
    return Insight(
        rule_id="record_gaps",
        category="data_quality",
        level=Level.INFO,
        title=tr("Questions to ask your family"),
        summary=tr(
            "A few missing details could change your insights. Family gatherings are a good time to ask; relatives can "
            "also be invited to add their own history."),
        evidence=_dedupe(questions)[:10],
        recommendation=tr("Fill in what you can; your insights update automatically."),
        references=[REF_SURGEON_GENERAL],
    )


# --- Lynch syndrome clinical criteria, computed on the family tree -------------------------------

REF_AMSTERDAM = Reference(
    title="Vasen et al. (1999): New clinical criteria for HNPCC (Lynch syndrome) proposed by the ICG-HNPCC",
    url="https://pubmed.ncbi.nlm.nih.gov/10348829/",
)
REF_BETHESDA = Reference(
    title="Umar et al. (2004): Revised Bethesda Guidelines for HNPCC (Lynch syndrome) and microsatellite instability",
    url="https://pubmed.ncbi.nlm.nih.gov/14970275/",
)


def lynch_criteria(p: HealthProfile) -> Optional[Insight]:
    from ..pedigree import build
    from ..risk_models import amsterdam_ii, revised_bethesda
    try:
        ped = build(p)
    except ValueError:
        return None
    ams, beth = amsterdam_ii(ped), revised_bethesda(ped)
    if not ams.met and not beth:
        return None
    if ams.met:
        summary = tr("Your family meets the Amsterdam II criteria for Lynch syndrome: three or more relatives with "
                     "Lynch-associated cancers across successive generations, one diagnosed before 50.")
        evidence = ams.evidence
    else:
        summary = tr("Someone in your family with colorectal cancer meets the revised Bethesda guidelines, which "
                     "recommend testing their tumour (or genetic testing) for Lynch syndrome.")
        evidence = [e for b in beth for e in [tr(x) for x in b.criteria] + b.evidence]
    return Insight(
        rule_id="lynch_criteria", category="cancer", level=Level.HIGH,
        title=tr("Family pattern meets Lynch syndrome criteria"),
        summary=summary, evidence=_dedupe(evidence)[:12],
        recommendation=tr("Ask for genetic counseling. If a relative's colorectal or endometrial tumour can be tested "
                          "for mismatch-repair deficiency, that is often the quickest first step. Confirmed Lynch "
                          "syndrome means colonoscopy every 1-2 years, usually from age 20-25."),
        references=[REF_AMSTERDAM, REF_BETHESDA, REF_NCCN],
    )


ALL_RULES: list[Rule] = [
    anesthesia_safety,
    hereditary_breast_ovarian,
    colorectal_family_history,
    lynch_criteria,
    familial_hypercholesterolemia,
    premature_ascvd,
    diabetes_risk,
    indian_diabetes_risk,
    prostate_family_history,
    blood_pressure,
    record_gaps,
]
