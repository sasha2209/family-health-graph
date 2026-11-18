"""Rule-based reading of OCR'd medical documents: prescriptions, lab reports, discharge summaries.

Written for the formats common in India first (day-first dates, "Tab./Cap." prescriptions,
"K/C/O DM, HTN" shorthand, Indian lab-chain report layouts), but nothing here is India-only.
The rules run on every document for free; the AI reader is only consulted when they come up short.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from ..ingest.text import parse_family_history_text
from ..terminology import CONCEPTS_BY_CATEGORY, OBSERVATION_TO_LOINC, category_from_text
from .models import Extraction, ExtractedCondition, ExtractedMedication, ExtractedObservation, ExtractedRelative, PatientInfo

# --- clinical shorthand --------------------------------------------------------------------

_SHORTHAND: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I), r) for p, r in (
    (r"\b(t2dm|dm\s*-?\s*(?:type\s*)?(?:2|ii)|type\s*(?:2|ii)\s*dm|niddm)\b", "type 2 diabetes"),
    (r"\b(t1dm|dm\s*-?\s*(?:type\s*)?(?:1|i)|type\s*(?:1|i)\s*dm|iddm)\b", "type 1 diabetes"),
    (r"\bdm\b", "diabetes"),
    (r"\b(ihd)\b", "ischemic heart disease"),
    (r"\b(cad|ascvd)\b", "coronary artery disease"),
    (r"\b(acs|stemi|nstemi|old mi|mi)\b", "myocardial infarction"),
    (r"\bdlp\b", "dyslipidemia"),
    (r"\b(?:ca|carcinoma|cancer)\.?\s+(?:of\s+)?(?:the\s+)?(breast|ovary|ovaries|colon|rectum|prostate|pancreas|stomach|endometrium|uterus)\b",
     "\\1 cancer"),
)]
_SITE_FIX = {"ovary cancer": "ovarian cancer", "ovaries cancer": "ovarian cancer", "rectum cancer": "rectal cancer",
             "pancreas cancer": "pancreatic cancer", "endometrium cancer": "endometrial cancer",
             "uterus cancer": "uterine cancer"}


def expand_shorthand(text: str) -> str:
    for pattern, repl in _SHORTHAND:
        text = pattern.sub(repl, text)
    for k, v in _SITE_FIX.items():
        text = re.sub(k, v, text, flags=re.I)
    return text


# --- dates -----------------------------------------------------------------------------------

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_DATE_RES = [
    re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"),                      # 2026-03-14
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b"),                # 14/03/2026 (day first)
    re.compile(r"\b(\d{1,2})[\s-]*([A-Za-z]{3,9})[\s,.-]*(\d{4})\b"),             # 14 Mar 2026, 14-Mar-2026
    re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"),                  # March 14, 2026
]
_DATE_LABEL = re.compile(r"(report(?:ed)?|collect(?:ed|ion)|sample|visit|consult|date|admission|discharge|dated|dt)", re.I)


def _mk_date(y: int, m: int, d: int) -> Optional[date]:
    if y < 100:
        y += 2000
    try:
        found = date(y, m, d)
    except ValueError:
        return None
    return found if date(1990, 1, 1) <= found <= date.today() else None


def _dates_in(line: str) -> list[date]:
    out = []
    for i, rx in enumerate(_DATE_RES):
        for m in rx.finditer(line):
            a, b, c = m.groups()
            if i == 0:
                d = _mk_date(int(a), int(b), int(c))
            elif i == 1:
                d = _mk_date(int(c), int(b), int(a))
            elif i == 2:
                mon = _MONTHS.get(b[:3].lower())
                d = _mk_date(int(c), mon, int(a)) if mon else None
            else:
                mon = _MONTHS.get(a[:3].lower())
                d = _mk_date(int(c), mon, int(b)) if mon else None
            if d:
                out.append(d)
    return out


def find_date(lines: list[str]) -> Optional[date]:
    labelled = [d for line in lines if _DATE_LABEL.search(line) and "birth" not in line.lower()
                and "dob" not in line.lower() for d in _dates_in(line)]
    if labelled:
        return labelled[0]
    every = [d for line in lines if "birth" not in line.lower() and "dob" not in line.lower() for d in _dates_in(line)]
    return every[0] if every else None


# --- labs ------------------------------------------------------------------------------------

# (code, name pattern, default unit, plausible range in the default unit)
_LABS: list[tuple[str, str, str, tuple[float, float]]] = [
    ("hba1c", r"hb\s*a[1il]c|glyc(?:osyl)?ated\s+ha?emoglobin|\ba1c\b", "%", (3, 20)),
    ("fasting_glucose", r"fasting\s+(?:blood\s+|plasma\s+)?(?:sugar|glucose)|(?:glucose|sugar)\s*[,(-]?\s*fasting|\bfbs\b|\bfbg\b|\bfpg\b",
     "mg/dL", (30, 600)),
    ("postprandial_glucose", r"post\s*-?\s*prandial|\bpp\s*(?:bs|bg|ps)\b|(?:glucose|sugar)\s*[,(-]?\s*(?:pp|post\s*-?\s*prandial)",
     "mg/dL", (30, 700)),
    ("ldl_cholesterol", r"(?<![a-z])ldl(?:\s*-?\s*c\b)?(?:\s*cholesterol)?|low\s+density\s+lipoprotein", "mg/dL", (10, 500)),
    ("hdl_cholesterol", r"(?<![a-z])hdl(?:\s*-?\s*c\b)?(?:\s*cholesterol)?|high\s+density\s+lipoprotein", "mg/dL", (5, 200)),
    ("total_cholesterol", r"(?:total|serum)\s+cholesterol|cholesterol\s*[,-]?\s*total|^\s*cholesterol\b", "mg/dL", (50, 600)),
    ("triglycerides", r"triglycerides?|\btg\b", "mg/dL", (10, 3000)),
    ("lipoprotein_a", r"lipoprotein\s*\(\s*a\s*\)|lp\s*\(\s*a\s*\)", "mg/dL", (0, 500)),
    ("tsh", r"\btsh\b|thyroid\s+stimulating\s+hormone", "µIU/mL", (0.005, 150)),
    ("hemoglobin", r"^\s*(?:ha?emoglobin|hb|hgb)\b(?!\s*a1c)", "g/dL", (3, 25)),
    ("creatinine", r"(?:serum\s+|s\.\s*)?creatinine(?!\s*(?:clearance|ratio|kinase))", "mg/dL", (0.1, 20)),
    ("egfr", r"\begfr\b|estimated\s+gfr", "mL/min/1.73m²", (1, 200)),
    ("vitamin_d", r"vitamin\s*d\b|25\s*-?\s*(?:oh|hydroxy)", "ng/mL", (1, 200)),
    ("vitamin_b12", r"vitamin\s*b\s*-?\s*12|cobalamin", "pg/mL", (50, 4000)),
]
_LAB_RES = [(code, re.compile(rx, re.I), unit, rng) for code, rx, unit, rng in _LABS]
_UNIT_RE = re.compile(r"^\s*(mg\s*/\s*dl|g\s*/\s*dl|gm\s*/\s*dl|mmol\s*/\s*l|%|µiu\s*/\s*ml|uiu\s*/\s*ml|miu\s*/\s*l|"
                      r"m?iu\s*/\s*ml|ng\s*/\s*ml|pg\s*/\s*ml|ml\s*/\s*min(?:\s*/\s*1\.73\s*m(?:2|²))?)", re.I)
_NUM_RE = re.compile(r"(?<![\w.])([<>]?\s*\d+(?:\.\d+)?)(?![\d])")
_SKIP_LAB_LINE = re.compile(r"\bratio\b|reference|interval|method|prediabet|desirable|borderline|optimal|"
                            r"normal\s*:|risk\s*:|target|goal|<\s*\d+\s*:|≥|>=\s*\d+\s*:", re.I)
_UNIT_DISPLAY = {"mg/dl": "mg/dL", "g/dl": "g/dL", "gm/dl": "g/dL", "mmol/l": "mmol/L", "%": "%", "uiu/ml": "µIU/mL",
                 "µiu/ml": "µIU/mL", "miu/l": "mIU/L", "iu/ml": "IU/mL", "miu/ml": "mIU/mL", "ng/ml": "ng/mL", "pg/ml": "pg/mL"}


def _unit(raw: str) -> str:
    key = re.sub(r"\s+", "", raw.lower())
    if key.startswith("ml/min"):
        return "mL/min/1.73m²"
    return _UNIT_DISPLAY.get(key, raw)


def _plausible(code: str, value: float, unit: str, rng: tuple[float, float]) -> bool:
    if unit == "mmol/L":  # glucose/cholesterol reported in SI units
        return 0.5 <= value <= 40
    return rng[0] <= value <= rng[1]


def _read_value(rest: str, code: str, default_unit: str, rng: tuple[float, float]) -> Optional[tuple[float, str, Optional[str]]]:
    rest = re.sub(r"\([^)]*\)", " ", rest)  # "(Glycosylated Haemoglobin)", "(HPLC)"
    for m in _NUM_RE.finditer(rest):
        token = m.group(1).replace(" ", "")
        if token.startswith(("<", ">")):
            continue  # a reference bound, not a result
        after = rest[m.end():]
        if re.match(r"\s*(?:-|–|to)\s*\d", after):
            continue  # start of a reference range
        value = float(token)
        fm = re.match(r"[.,]?\s*\b(high|low|h|l)[o0*\-]?(?=\s|$)\s*", after, re.I)  # "7.8  H  %"
        flag = fm.group(1).lower()[0] if fm else None
        if fm:
            after = after[fm.end():]
        um = _UNIT_RE.match(after)
        unit = _unit(um.group(1)) if um else default_unit
        if not _plausible(code, value, unit, rng):
            continue
        if flag is None and um:
            fm = re.match(r"\s*\b(high|low|h|l)\b", after[um.end():], re.I)
            flag = fm.group(1).lower()[0] if fm else None
        return value, unit, flag
    return None


def find_observations(lines: list[str]) -> list[ExtractedObservation]:
    found: dict[str, ExtractedObservation] = {}
    for i, line in enumerate(lines):
        bp = re.search(r"\b(?:bp|blood\s+pressure)\b[^0-9]{0,15}(\d{2,3})\s*/\s*(\d{2,3})", line, re.I)
        if bp:
            sbp, dbp = int(bp.group(1)), int(bp.group(2))
            if 70 <= sbp <= 260 and 40 <= dbp <= 160 and "systolic_bp" not in found:
                found["systolic_bp"] = ExtractedObservation(code="systolic_bp", value=sbp, unit="mmHg", evidence=line.strip())
                found["diastolic_bp"] = ExtractedObservation(code="diastolic_bp", value=dbp, unit="mmHg", evidence=line.strip())
        bmi = re.search(r"\bbmi\b[^0-9]{0,12}(\d{2}(?:\.\d+)?)", line, re.I)
        if bmi and 10 <= float(bmi.group(1)) <= 80 and "bmi" not in found:
            found["bmi"] = ExtractedObservation(code="bmi", value=float(bmi.group(1)), unit="kg/m²", evidence=line.strip())
        if _SKIP_LAB_LINE.search(line) and not re.search(r"\d\s*(?:mg|g|%|ng|pg)", line, re.I):
            continue
        for code, rx, unit, rng in _LAB_RES:
            m = rx.search(line)
            if not m or code in found:
                continue
            got = _read_value(line[m.end():], code, unit, rng)
            if got is None and i + 1 < len(lines):  # value printed on the next line of a table
                got = _read_value(lines[i + 1], code, unit, rng) if re.match(r"\s*[\d.]", lines[i + 1]) else None
            if got:
                value, u, flag = got
                found[code] = ExtractedObservation(code=code, value=value, unit=u, flag=flag, evidence=line.strip())
            break  # one test per line
    return list(found.values())


# --- medicines -------------------------------------------------------------------------------

_FORM = r"tab(?:let)?s?|cap(?:sule)?s?|syp|syr(?:up)?|inj(?:ection)?|oint(?:ment)?|drops?|susp(?:ension)?|sachet|gel|cream|inhaler|inh|lotion|spray"
_MED_RE = re.compile(rf"^\s*(?:\d+\s*[.)]\s*)?(?:rx\s*[:.]?\s*)?({_FORM})\b\.?\s*(.+)$", re.I)
_DOSE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|iu|units?)\b(?:\s*/\s*\d+\s*(?:mg|mcg|ml))?", re.I)
_FREQ_RE = re.compile(r"\b[01½]\s*-\s*[01½]\s*-\s*[01½](?:\s*-\s*[01½])?\b|\b(?:od|bd|bid|tds|tid|qid|hs|sos|qhs|stat|"
                      r"once\s+(?:a\s+)?(?:daily|day|week)|weekly|alternate\s+days?|twice\s+(?:a\s+)?daily|thrice\s+daily|at\s+night|before\s+(?:food|meals?|breakfast)|"
                      r"after\s+(?:food|meals?|breakfast|dinner)|empty\s+stomach)\b", re.I)
_DUR_RE = re.compile(r"(?:x|for|×)\s*\d+\s*(?:days?|d|weeks?|wks?|months?|m)\b|\b\d+\s*(?:days?|weeks?|months?)\b", re.I)
_FORM_NAMES = {"tab": "Tab.", "cap": "Cap.", "syp": "Syrup", "syr": "Syrup", "inj": "Inj.", "oint": "Ointment",
               "drop": "Drops", "susp": "Suspension", "inh": "Inhaler"}


def _clean_drug(name: str) -> str:
    name = re.split(r"[(\[]|\s{2,}|\s-\s|,", name)[0]
    name = re.sub(r"[^A-Za-z0-9 +./-]", "", name).strip(" .-")
    return name


def find_medications(lines: list[str], in_rx_section: list[bool]) -> list[ExtractedMedication]:
    meds: list[ExtractedMedication] = []
    seen = set()
    for line, in_rx in zip(lines, in_rx_section):
        m = _MED_RE.match(line)
        body = m.group(2) if m else (line if in_rx and _DOSE_RE.search(line) and _FREQ_RE.search(line) else None)
        if not body:
            continue
        dose = _DOSE_RE.search(body)
        cut = min([x.start() for x in (dose, _FREQ_RE.search(body)) if x] or [len(body)])
        drug = _clean_drug(body[:cut])
        if not re.search(r"[A-Za-z]{3,}", drug) or drug.lower() in seen:
            continue
        seen.add(drug.lower())
        name = drug
        if dose and dose.start() < cut + 1 and not re.search(r"\s\d+\s*$", drug):
            name = f"{drug} {dose.group(0)}"
        generic = re.search(r"\(([A-Za-z][^)]{2,40})\)", body)  # "Telma 40 (Telmisartan 40mg)"
        if generic:
            name = f"{name} ({generic.group(1).strip()})"
        parts = [f.group(0) for f in _FREQ_RE.finditer(body)]
        dur = _DUR_RE.search(body[cut:])
        if dur:
            parts.append(dur.group(0).lstrip("x× ").strip())
        meds.append(ExtractedMedication(name=name.strip(), dosage=", ".join(parts) or None, evidence=line.strip()))
    return meds


# --- diagnoses & family history --------------------------------------------------------------

_DX_LABEL = re.compile(r"^\s*(?:provisional\s+|final\s+|working\s+)?(?:diagnosis|diagnoses|dx|impression|assessment|"
                       r"k\s*/\s*c\s*/\s*o|known\s+case\s+of|h\s*/\s*o|past\s+history|medical\s+history|co-?morbidit(?:y|ies))"
                       r"\s*[:\-.]?\s*(.*)$", re.I)
_FH_LABEL = re.compile(r"^\s*(?:family\s+history|f\s*/\s*h|fhx?|history\s+in\s+family)\s*(?:of)?\s*[:\-.]?\s*(.*)$", re.I)
_NEGATED = re.compile(r"\b(?:no|not|nil|denies|negative|rule\s+out|r\s*/\s*o|\?|screening|risk|unlikely)\b", re.I)
_SECTION_END = re.compile(r"^\s*(?:rx|advice|adv|investigations?|treatment|medications?|plan|follow\s*-?\s*up|"
                          r"vitals?|examination|o\s*/\s*e|chief\s+complaints?|c\s*/\s*o)\b", re.I)


def _conditions_from(fragment: str, evidence: str, keep_unknown: bool) -> list[ExtractedCondition]:
    out = []
    for part in re.split(r"[,;+/]|\band\b|\bwith\b|\n", expand_shorthand(fragment), flags=re.I):
        part = part.strip(" .:-()")
        if len(part) < 3 or _NEGATED.search(part):
            continue
        cat = category_from_text(part)
        if cat and cat != "cancer_unspecified":
            out.append(ExtractedCondition(name=CONCEPTS_BY_CATEGORY[cat].display, category=cat, evidence=evidence))
        elif keep_unknown and re.fullmatch(r"[A-Za-z][A-Za-z '\-]{2,50}", part) and len(part.split()) <= 6:
            out.append(ExtractedCondition(name=part[0].upper() + part[1:], category=cat, evidence=evidence))
    return out


def find_conditions(lines: list[str], doc_type: str, skip: set[int]) -> list[ExtractedCondition]:
    found: list[ExtractedCondition] = []
    i = 0
    while i < len(lines):
        m = _DX_LABEL.match(lines[i])
        if m and i not in skip:
            # The label's own line, plus following lines until the next section heading.
            chunk, j = [m.group(1)], i + 1
            while j < len(lines) and j - i <= 4 and lines[j].strip() and not _SECTION_END.match(lines[j]) \
                    and not _DX_LABEL.match(lines[j]) and not _FH_LABEL.match(lines[j]) and not _MED_RE.match(lines[j]):
                chunk.append(lines[j])
                j += 1
            for k, text in enumerate(chunk):
                skip.add(i + k)
                found += _conditions_from(text, lines[i + k].strip(), keep_unknown=True)
            i = j
            continue
        i += 1
    if doc_type in ("prescription", "discharge_summary"):
        # Unlabelled mentions ("T2DM, HTN" in a box). Lab reports are skipped: their
        # interpretation tables mention "diabetes" without it being a diagnosis.
        for i, line in enumerate(lines):
            if i in skip or _NEGATED.search(line) or _MED_RE.match(line):
                continue
            found += _conditions_from(line, line.strip(), keep_unknown=False)
    unique: dict[str, ExtractedCondition] = {}
    for c in found:
        unique.setdefault(c.category or c.name.lower(), c)
    return list(unique.values())


def find_family(lines: list[str], skip: set[int]) -> list[ExtractedRelative]:
    chunks = []
    for i, line in enumerate(lines):
        m = _FH_LABEL.match(line)
        if m:
            skip.add(i)
            chunks.append(m.group(1))
            if i + 1 < len(lines) and lines[i + 1].strip() and not _SECTION_END.match(lines[i + 1]) \
                    and not _DX_LABEL.match(lines[i + 1]):
                skip.add(i + 1)
                chunks.append(lines[i + 1])
    if not chunks:
        return []
    text = expand_shorthand(" . ".join(chunks))
    # "Mother - diabetes" reads as a sentence to the family-history parser once "had" is there.
    rel = r"(?:mother|father|brother|sister|grandmother|grandfather|aunt|uncle|son|daughter|maternal|paternal)"
    text = re.sub(rf",\s*(?={rel}\b)", ". ", text, flags=re.I)
    text = re.sub(r"\b(mother|father|brother|sister|grandmother|grandfather|aunt|uncle|son|daughter)\s*[-:]\s*",
                  r"\1 had ", text, flags=re.I)
    fragment = parse_family_history_text(text)
    return [ExtractedRelative(relationship=m.relationship.value, conditions=[
        ExtractedCondition(name=c.display_name, category=c.category, onset_age=c.onset_age, evidence="Family history")
        for c in m.conditions]) for m in fragment.family if m.conditions]


# --- header fields ---------------------------------------------------------------------------

def find_patient(lines: list[str]) -> PatientInfo:
    info = PatientInfo()
    for line in lines[:25]:
        if info.name is None:
            m = re.search(r"(?:patient(?:'?s)?\s*name|name\s+of\s+(?:the\s+)?patient|pt\.?\s*name|^\s*name)\s*[:\-]\s*"
                          r"(?:(?:mr|mrs|ms|miss|master|baby|smt|shri|sri)\.?\s+)?([A-Za-z][A-Za-z .]{1,40}?)"
                          r"(?=\s{2,}|\s+(?:age|sex|gender|uhid|mrn|id|ref|dob)\b|$)", line, re.I)
            if m:
                info.name = m.group(1).strip(" .").title()
        if info.age is None:
            m = re.search(r"\bage\s*(?:/\s*(?:sex|gender))?\s*[:\-]?\s*(\d{1,3})\s*(?:y|yr|yrs|years?)?\b", line, re.I)
            if m and 0 < int(m.group(1)) < 120:
                info.age = int(m.group(1))
        if info.sex is None:
            m = re.search(r"\b(?:sex|gender)\s*[:\-]?\s*(male|female|m|f)\b|\d{1,3}\s*(?:y|yrs?|years?)?\s*/\s*(male|female|m|f)\b",
                          line, re.I)
            if m:
                info.sex = "female" if (m.group(1) or m.group(2)).lower().startswith("f") else "male"
    return info


_FACILITY_RE = re.compile(r"hospital|clinic|diagnostic|labs?\b|laborator|pathology|healthcare|health\s+care|medical\s+cent|"
                          r"nursing\s+home|polyclinic|imaging|scans?\b|medicare|institute", re.I)


def find_facility(lines: list[str]) -> Optional[str]:
    for line in lines[:8]:
        if _FACILITY_RE.search(line) and len(line.strip()) <= 70 and not re.search(r"\d{5,}|@|www\.", line):
            return line.strip(" .,:-")
    return None


def find_doctor(lines: list[str]) -> Optional[str]:
    for line in lines:
        m = re.search(r"\b(?i:dr)\.?\s+([A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,3})", line)
        if m:
            return "Dr. " + re.split(r"\s+(?:MBBS|MD|MS|DNB|DM|MRCP|FRCS|M\.?D\.?|Consultant)\b", m.group(1))[0].strip(" .")
    return None


# --- document type ---------------------------------------------------------------------------

def classify(text: str, n_obs: int, n_meds: int) -> str:
    low = text.lower()
    if re.search(r"discharge\s+summary|date\s+of\s+discharge|course\s+in\s+(?:the\s+)?hospital|date\s+of\s+admission", low):
        return "discharge_summary"
    lab_words = len(re.findall(r"reference\s+(?:range|interval)|biological\s+ref|bio\.?\s*ref|specimen|sample\s+(?:collected|type)|"
                               r"test\s+(?:name|description)|pathology|laboratory|method\s*:", low))
    if n_obs >= 2 and lab_words >= 1 or n_obs >= 3 and n_meds == 0:
        return "lab_report"
    if n_meds or re.search(r"(?m)^\s*rx\b|prescription|\badv(?:ice)?\s*:", low):
        return "prescription"
    if lab_words >= 2:
        return "lab_report"
    return "other"


def _rx_sections(lines: list[str]) -> list[bool]:
    flags, inside = [], False
    for line in lines:
        if re.match(r"^\s*(?:rx|℞|medications?|treatment|advised|medicines)\b", line, re.I):
            inside = True
        elif re.match(r"^\s*(?:advice|investigations?|follow\s*-?\s*up|review|diet)\b", line, re.I):
            inside = False
        flags.append(inside)
    return flags


def parse_document(text: str) -> Extraction:
    lines = [re.sub(r"[ \t]+", " ", raw).strip() for raw in text.splitlines()]
    lines = [line for line in lines if line]
    skip: set[int] = set()
    family = find_family(lines, skip)
    observations = find_observations(lines)
    medications = find_medications(lines, _rx_sections(lines))
    doc_type = classify(text, len(observations), len(medications))
    obs_lines = {o.evidence for o in observations}
    skip |= {i for i, line in enumerate(lines) if line in obs_lines}
    conditions = find_conditions(lines, doc_type, skip)
    return Extraction(
        doc_type=doc_type, doc_date=find_date(lines), facility=find_facility(lines), doctor=find_doctor(lines),
        patient=find_patient(lines), conditions=conditions, medications=medications,
        observations=[o.model_copy(update={"display": OBSERVATION_TO_LOINC.get(o.code, ("", o.code))[1]}) for o in observations],
        family=family, read_by="rules",
    )
