"""Hereditary-risk models that work from the whole family tree.

Two kinds:

* **Clinical criteria** computed here, transparently: the Amsterdam II criteria and the revised Bethesda
  guidelines for Lynch syndrome. They are published yes/no rules, so every result lists exactly which people and
  diagnoses met which criterion.
* **Exports for validated calculators** that we deliberately don't re-implement: a CanRisk pedigree file
  (``##CanRisk 2.0``) for BOADICEA, the model genetic counselors use for breast and ovarian cancer risk. The person
  downloads it or a counseling partner fetches it, the counselor runs it in CanRisk, and can post the figures back
  (``POST /v1/partner/referrals/{id}/risk-assessment``) so the person sees an actual risk number in the app.

Not included, on purpose: PREMM5 and the Manchester score. Both need published coefficients/point tables that
couldn't be checked against the primary papers while this was built; they must not be typed in from memory.
See docs/RISK_MODELS.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import HealthProfile
from .insights.lang import mark, tr
from .pedigree import Pedigree, Person, build

# --- CanRisk pedigree file -----------------------------------------------------------------------------
# Column layout of the CanRisk 2.0 format, as read and written by CanRisk's own pedigreejs (canrisk_file.js).
CANRISK_GENES = ("BRCA1", "BRCA2", "PALB2", "ATM", "CHEK2", "BARD1", "RAD51D", "RAD51C", "BRIP1")
CANRISK_COLUMNS = ("FamID", "Name", "Target", "IndivID", "FathID", "MothID", "Sex", "MZtwin", "Dead", "Age", "Yob",
                   "BC1", "BC2", "OC", "PRO", "PAN", "Ashkn", *CANRISK_GENES, "ER:PR:HER2:CK14:CK56")


def _ages(person: Person, category: str) -> list[str]:
    return ["AU" if c.age is None else str(c.age) for c in person.conditions if c.category == category]


def canrisk_file(profile: HealthProfile, family_id: str = "FHG") -> tuple[str, list[str]]:
    """The family as a CanRisk 2.0 pedigree file, and warnings for the counselor.

    Names are never written: the Name column is a row number, as in CanRisk's own anonymised export."""
    ped = build(profile)
    warnings = list(ped.skipped)
    lines = ["##CanRisk 2.0"]
    bmi = profile.latest("bmi")
    if ped.proband.sex == "F" and bmi:
        lines.append(f"##BMI={bmi.value:g}")
    lines.append("##" + "\t".join(CANRISK_COLUMNS))
    for n, p in enumerate(ped.people.values(), start=1):
        breast = _ages(p, "breast_cancer")
        bc1, bc2 = (breast + ["0", "0"])[:2]
        oc = (_ages(p, "ovarian_cancer") or ["0"])[0] if p.sex == "F" else "0"
        pro = (_ages(p, "prostate_cancer") or ["0"])[0] if p.sex == "M" else "0"
        pan = (_ages(p, "pancreatic_cancer") or ["0"])[0]
        if "AU" in (bc1, bc2, oc, pro, pan):
            warnings.append(f"{p.label}: a cancer's age at diagnosis is unknown (written as AU)")
        if len(breast) > 2:
            warnings.append(f"{p.label}: more than two breast cancers recorded; the first two are used")
        row = [family_id, str(n), "1" if p.proband else "0", p.id, p.father or "0", p.mother or "0", p.sex, "0",
               "1" if p.dead else "0", str(p.age or 0), str(p.yob or 0), bc1, bc2, oc, pro, pan, "0",
               *(["0:0"] * len(CANRISK_GENES)), "0:0:0:0:0"]
        lines.append("\t".join(row))
    if profile.affected({"hboc_variant"}, max_degree=3) or profile.own_conditions({"hboc_variant"}):
        warnings.append("A BRCA1/BRCA2 variant is recorded but not which gene or for whom exactly; "
                        "add the genetic test result in CanRisk")
    placeholders = sum(p.placeholder for p in ped.people.values())
    if placeholders:
        warnings.append(f"{placeholders} unaffected placeholder people link relatives whose connecting parent "
                        "wasn't recorded")
    return "\n".join(lines) + "\n", warnings


# --- Lynch syndrome clinical criteria ---------------------------------------------------------------------
AMSTERDAM_CANCERS = {"colorectal_cancer", "endometrial_cancer"}   # also small bowel, ureter, renal pelvis
BETHESDA_CANCERS = {"colorectal_cancer", "endometrial_cancer", "stomach_cancer", "ovarian_cancer",
                    "pancreatic_cancer"}                          # also ureter/renal pelvis, biliary, brain,
                                                                  # small bowel, sebaceous adenomas


@dataclass
class CriteriaResult:
    model: str
    met: bool
    criteria: list[str] = field(default_factory=list)     # which parts were met, in plain words
    evidence: list[str] = field(default_factory=list)     # "Mother: Colorectal cancer at 45"
    not_assessable: list[str] = field(default_factory=list)


def _describe(p: Person, category: str, age: Optional[int]) -> str:
    from .terminology import CONCEPTS_BY_CATEGORY
    name = tr(CONCEPTS_BY_CATEGORY[category].display)
    return f"{tr(p.label)}: {name} " + (tr("at {age}", age=age) if age is not None else tr("(age unknown)"))


def amsterdam_ii(ped: Pedigree) -> CriteriaResult:
    """Amsterdam II (Vasen et al., Gastroenterology 1999): at least three relatives with a Lynch-associated
    cancer, one a first-degree relative of the other two; at least two successive generations; at least one
    diagnosed before 50; familial adenomatous polyposis excluded."""
    affected = {p.id: p for p in ped.real() if any(c.category in AMSTERDAM_CANCERS for c in p.conditions)}
    result = CriteriaResult("Amsterdam II criteria", False,
                            not_assessable=["Familial adenomatous polyposis must be ruled out by a clinician",
                                            "Small bowel, ureter and renal pelvis cancers aren't recorded separately yet"])
    if len(affected) < 3:
        return result
    hub = next((x for x in affected if sum(1 for y in affected if y != x and ped.degree(x, y) == 1) >= 2), None)
    gens = sorted({p.generation for p in affected.values()})
    successive = any(b - a == 1 for a, b in zip(gens, gens[1:]))
    early = [(p, c) for p in affected.values() for c in p.conditions
             if c.category in AMSTERDAM_CANCERS and c.age is not None and c.age < 50]
    result.evidence = [_describe(p, c.category, c.age) for p in affected.values() for c in p.conditions
                       if c.category in AMSTERDAM_CANCERS]
    result.criteria = ([mark("Three or more relatives with a Lynch-associated cancer")]
                       + ([mark("One is a first-degree relative of the other two")] if hub else [])
                       + ([mark("Two or more successive generations affected")] if successive else [])
                       + ([mark("At least one diagnosed before 50")] if early else []))
    result.met = bool(hub and successive and early)
    return result


def revised_bethesda(ped: Pedigree) -> list[CriteriaResult]:
    """Revised Bethesda guidelines (Umar et al., JNCI 2004): who with colorectal cancer should have their tumour
    tested for mismatch-repair deficiency. One result per person with colorectal cancer who meets any of them."""
    out = []
    for p in ped.real():
        crc = [c for c in p.conditions if c.category == "colorectal_cancer"]
        if not crc:
            continue
        met, evidence = [], [_describe(p, c.category, c.age) for c in crc]
        if any(c.age is not None and c.age < 50 for c in crc):
            met.append(mark("Colorectal cancer diagnosed before 50"))
        if len([c for c in p.conditions if c.category in BETHESDA_CANCERS]) >= 2:
            met.append(mark("More than one Lynch-associated cancer in the same person"))
        fdr, sdr = [], []
        for q in ped.real():
            if q.id == p.id:
                continue
            tumours = [c for c in q.conditions if c.category in BETHESDA_CANCERS]
            if not tumours:
                continue
            d = ped.degree(p.id, q.id)
            if d == 1:
                fdr.append((q, tumours))
            if d in (1, 2):
                sdr.append((q, tumours))
        young = any(c.age is not None and c.age < 50 for c in crc) or any(
            c.age is not None and c.age < 50 for _, ts in fdr for c in ts)
        if fdr and young:
            met.append(mark("A first-degree relative with a Lynch-associated cancer, one of them diagnosed before 50"))
        if len(sdr) >= 2:
            met.append(mark("Two or more first- or second-degree relatives with Lynch-associated cancers, any age"))
        if met:
            evidence += [_describe(q, c.category, c.age) for q, ts in sdr for c in ts]
            out.append(CriteriaResult(f"Revised Bethesda guidelines ({p.label.lower() if not p.proband else 'you'})",
                                      True, met, list(dict.fromkeys(evidence)),
                                      ["Tumour MSI-H histology (criterion 3) needs the pathology report"]))
    return out


def assess(profile: HealthProfile) -> dict:
    """Everything the tree-based models can say about this family, for the app and for partners."""
    ped = build(profile)
    ams = amsterdam_ii(ped)
    beth = revised_bethesda(ped)
    return {
        "pedigree": {"people": len(ped.real()), "placeholders": sum(p.placeholder for p in ped.people.values()),
                     "not_placed": ped.skipped},
        "lynch": {"amsterdam_ii": ams.__dict__, "revised_bethesda": [b.__dict__ for b in beth],
                  "suggests_evaluation": ams.met or bool(beth)},
        "calculators": [{"model": "BOADICEA (CanRisk)", "for": "Breast and ovarian cancer risk",
                         "how": "Download the CanRisk file and give it to your genetic counselor, or let a "
                                "counseling partner fetch it with your consent.",
                         "download": "/v1/risk/canrisk"}],
    }
