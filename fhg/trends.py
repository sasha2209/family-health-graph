"""Test results over time, each placed in a published guideline range.

Ranges are general adult reference points for context, not a diagnosis; labs print their own reference
intervals, and the app shows the lab's H/L flag alongside. Units are normalised (mmol/L to mg/dL) so a series
read from different labs lines up. BMI uses the WHO / Indian cut-offs for Asian adults (overweight from 23,
obesity from 25), because the platform launches in India first.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .models import Observation
from .terminology import OBSERVATION_TO_LOINC

# code -> (unit, [(upper bound, exclusive; None = no upper bound), label, tone]), source of the bands
# tone: good | watch | high (high = outside the range in the direction that matters)
BANDS: dict[str, tuple[str, list[tuple[Optional[float], str, str]], str]] = {
    "hba1c": ("%", [(5.7, "Normal", "good"), (6.5, "Prediabetes range", "watch"), (None, "Diabetes range", "high")],
              "ADA Standards of Care"),
    "fasting_glucose": ("mg/dL", [(100, "Normal", "good"), (126, "Prediabetes range", "watch"),
                                  (None, "Diabetes range", "high")], "ADA Standards of Care"),
    "postprandial_glucose": ("mg/dL", [(140, "Normal", "good"), (200, "Prediabetes range", "watch"),
                                       (None, "Diabetes range", "high")], "ADA (2-hour glucose)"),
    "ldl_cholesterol": ("mg/dL", [(100, "Optimal", "good"), (130, "Near optimal", "good"), (160, "Borderline high", "watch"),
                                  (190, "High", "high"), (None, "Very high", "high")], "NCEP ATP III"),
    "total_cholesterol": ("mg/dL", [(200, "Desirable", "good"), (240, "Borderline high", "watch"), (None, "High", "high")],
                          "NCEP ATP III"),
    "hdl_cholesterol": ("mg/dL", [(40, "Low", "high"), (60, "Normal", "good"), (None, "Protective", "good")],
                        "NCEP ATP III"),
    "triglycerides": ("mg/dL", [(150, "Normal", "good"), (200, "Borderline high", "watch"), (500, "High", "high"),
                                (None, "Very high", "high")], "NCEP ATP III"),
    "tsh": ("µIU/mL", [(0.4, "Below the usual range", "watch"), (4.0, "Usual range", "good"),
                       (None, "Above the usual range", "watch")], "Typical adult lab range"),
    "egfr": ("mL/min/1.73m²", [(60, "Reduced", "high"), (90, "Mildly reduced", "watch"), (None, "Normal", "good")],
             "KDIGO"),
    "vitamin_d": ("ng/mL", [(20, "Deficient", "high"), (30, "Insufficient", "watch"), (None, "Sufficient", "good")],
                  "Endocrine Society"),
    "vitamin_b12": ("pg/mL", [(200, "Low", "high"), (300, "Borderline", "watch"), (None, "Normal", "good")],
                    "Typical adult lab range"),
    "bmi": ("kg/m²", [(18.5, "Underweight", "watch"), (23, "Healthy", "good"), (25, "Overweight", "watch"),
                      (None, "Obesity", "high")], "WHO / ICMR cut-offs for Asian adults"),
    "systolic_bp": ("mmHg", [(120, "Normal", "good"), (130, "Elevated", "watch"), (140, "Stage 1 high", "high"),
                             (None, "Stage 2 high", "high")], "ACC/AHA 2017"),
    "diastolic_bp": ("mmHg", [(80, "Normal", "good"), (90, "Stage 1 high", "high"), (None, "Stage 2 high", "high")],
                     "ACC/AHA 2017"),
}

_MMOL_FACTOR = {"fasting_glucose": 18.0, "postprandial_glucose": 18.0, "ldl_cholesterol": 38.67,
                "hdl_cholesterol": 38.67, "total_cholesterol": 38.67, "triglycerides": 88.57}


def normalise(code: str, value: float, unit: str) -> tuple[float, str]:
    if code in _MMOL_FACTOR and "mmol" in (unit or "").lower():
        return round(value * _MMOL_FACTOR[code], 1), "mg/dL"
    if code in BANDS:
        return value, BANDS[code][0]
    return value, unit or ""


def band_for(code: str, value: float) -> Optional[dict]:
    if code not in BANDS:
        return None
    for upper, label, tone in BANDS[code][1]:
        if upper is None or value < upper:
            return {"label": label, "tone": tone}
    return None


def _bands(code: str) -> list[dict]:
    out, lower = [], None
    for upper, label, tone in BANDS.get(code, ("", [], ""))[1]:
        out.append({"from": lower, "to": upper, "label": label, "tone": tone})
        lower = upper
    return out


def _source_kind(source: str) -> str:
    if source.startswith("document:"):
        return "document"
    if source.startswith(("linked", "fhir")):
        return "record"
    return "typed"


def build(observations: list[Observation]) -> list[dict]:
    """One entry per test, most clinically relevant first, each with its dated series."""
    groups: dict[str, list[Observation]] = {}
    for o in observations:
        groups.setdefault(o.code, []).append(o)
    order = list(BANDS) + sorted(c for c in groups if c not in BANDS)
    tests = []
    for code in order:
        if code not in groups:
            continue
        points = []
        for o in sorted(groups[code], key=lambda o: o.effective_date or date.min):
            value, unit = normalise(code, o.value, o.unit)
            points.append({"date": o.effective_date.isoformat() if o.effective_date else None, "value": value,
                           "unit": unit, "source": _source_kind(o.source),
                           "document_id": o.source.split(":", 1)[1] if o.source.startswith("document:") else None})
        latest = points[-1]
        previous = points[-2] if len(points) > 1 else None
        tests.append({
            "code": code,
            "display": OBSERVATION_TO_LOINC.get(code, (None, code.replace("_", " ")))[1],
            "unit": latest["unit"],
            "points": points,
            "latest": latest,
            "change": round(latest["value"] - previous["value"], 2) if previous else None,
            "latest_band": band_for(code, latest["value"]),
            "bands": _bands(code),
            "bands_source": BANDS[code][2] if code in BANDS else None,
        })
    return tests


def rising_hba1c(observations: list[Observation], years: float = 3.0) -> Optional[tuple[Observation, Observation]]:
    """(earliest, latest) HbA1c within ``years`` when it has risen at least 0.3 points into the prediabetes
    range or above; None otherwise."""
    dated = sorted((o for o in observations if o.code == "hba1c" and o.effective_date),
                   key=lambda o: o.effective_date)
    if len(dated) < 2:
        return None
    latest = dated[-1]
    window = [o for o in dated if (latest.effective_date - o.effective_date).days <= years * 365.25]
    first = window[0]
    if first is latest or latest.value < 5.7 or latest.value - first.value < 0.3:
        return None
    return first, latest
