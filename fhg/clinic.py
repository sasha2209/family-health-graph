"""Clinic portal: what a care organisation sees about patients who connected to it.

Patients choose to connect with a clinic's code (and can disconnect at any
time). Staff then get:
* a worklist of connected patients sorted by priority, with the care programs
  each one may qualify for, and the clinician summary for each;
* an impact view: how many connected patients were identified for each
  program. These are the numbers a pilot reports to a buyer or funder.

Patients are identified to the clinic only by the name they chose to show
and a per-clinic pseudonymous ID. Every staff access is written to the
patient's own audit log.
"""
from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from datetime import date
from typing import Optional

from .models import HealthProfile, InsightReport, LEVEL_ORDER

# Insight rule -> care program a clinic can act on (a referral or screening pathway).
PROGRAMS: dict[str, str] = {
    "hboc_family_pattern": "Genetic counseling: hereditary breast/ovarian cancer",
    "colorectal_family_history": "Earlier colorectal screening / Lynch evaluation",
    "familial_hypercholesterolemia": "Lipid clinic: possible familial hypercholesterolemia",
    "premature_ascvd_family_history": "Cardiovascular risk assessment",
    "diabetes_risk": "Diabetes screening / prevention program",
    "prostate_family_history": "Earlier prostate cancer screening",
    "malignant_hyperthermia": "Anesthesia safety alert",
    "blood_pressure": "Blood pressure follow-up",
}
CORE_RELATIVES = {"mother", "father"}
GRANDPARENTS = {"maternal_grandmother", "maternal_grandfather", "paternal_grandmother", "paternal_grandfather",
                "grandmother", "grandfather"}


def patient_ref(secret: str, org_id: str, user_id: str) -> str:
    """Stable per-clinic ID: the same patient has unrelated IDs at different clinics."""
    return hmac.new(secret.encode(), f"org:{org_id}:{user_id}".encode(), hashlib.sha256).hexdigest()[:14]


def completeness(profile: HealthProfile) -> int:
    """0-100: how much of the record that drives screening decisions is filled in."""
    rels = {m.relationship.value for m in profile.family}
    key_conditions = [c for m in profile.family for c in m.conditions if c.category != "cancer_unspecified"]
    checks = [
        bool(profile.birth_date and profile.sex),
        CORE_RELATIVES <= rels,
        bool(rels & GRANDPARENTS),
        len(profile.family) >= 5,
        all(c.onset_age is not None for c in key_conditions) if key_conditions else False,
    ]
    return round(100 * sum(checks) / len(checks))


def patient_row(ref: str, display: str, connected_at: str, profile: HealthProfile,
                report: InsightReport, today: Optional[date] = None) -> dict:
    flags = [i for i in report.insights if i.rule_id in PROGRAMS]
    top = min((LEVEL_ORDER[i.level] for i in flags), default=3)
    return {
        "patient_ref": ref,
        "display_name": display,
        "age": profile.age(today),
        "sex": profile.sex.value if profile.sex else None,
        "connected_at": connected_at,
        "priority": ["high", "moderate", "info", "none"][top],
        "flags": [{"rule_id": i.rule_id, "level": i.level.value, "title": i.title,
                   "program": PROGRAMS[i.rule_id]} for i in flags],
        "relatives": len(profile.family),
        "completeness": completeness(profile),
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def sort_worklist(rows: list[dict]) -> list[dict]:
    rank = {"high": 0, "moderate": 1, "info": 2, "none": 3}
    return sorted(rows, key=lambda r: (rank[r["priority"]], -len(r["flags"]), r["display_name"].lower()))


def impact(rows: list[dict]) -> dict:
    """Population view across connected patients."""
    programs: Counter = Counter()
    for r in rows:
        for f in r["flags"]:
            programs[f["program"]] += 1
    n = len(rows)
    return {
        "patients_connected": n,
        "patients_with_high_priority": sum(1 for r in rows if r["priority"] == "high"),
        "patients_flagged": sum(1 for r in rows if r["flags"]),
        "programs": [{"program": p, "patients": c} for p, c in programs.most_common()],
        "avg_completeness": round(sum(r["completeness"] for r in rows) / n) if n else 0,
        "avg_relatives_recorded": round(sum(r["relatives"] for r in rows) / n, 1) if n else 0,
    }
