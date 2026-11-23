"""Connect with Family Health Graph: partners read a user's family history with the user's consent.

Family Health Graph is the OAuth 2.0 authorization server (authorization code + PKCE; confidential partners
may also use a client secret). The user approves on a consent screen in the app, choosing what to share.
Each approval is a consent artefact (a *grant*): partner, scopes, expiry, last used, revocable at any time.
The partner then reads FHIR R4 resources limited to the granted scopes.

What is never shared:
- Names of relatives (FamilyMemberHistory carries the relationship, sex, ages and diagnoses only).
- Anything a linked relative shared with the user from their own account: that relative agreed to share
  with family, not with third parties. Partners read the user's own record only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .ingest.fhir import to_fhir_bundle
from .models import HealthProfile, InsightReport

SCOPES: dict[str, str] = {
    "family_history.read": "Your family health history: each relative’s relationship to you, diagnoses and ages "
                           "at diagnosis. Never their names.",
    "risk.read": "Your action items: the screening and counseling prompts we found, with the guideline behind each.",
    "patient.read": "Your sex and year of birth.",
    "conditions.read": "Your own diagnoses.",
    "observations.read": "Your test results.",
    "medications.read": "Your medicines.",
}
# FHIR resource type -> scope that allows reading it
RESOURCE_SCOPE = {
    "FamilyMemberHistory": "family_history.read",
    "RiskAssessment": "risk.read",
    "Patient": "patient.read",
    "Condition": "conditions.read",
    "Observation": "observations.read",
    "MedicationStatement": "medications.read",
}
GRANT_DAYS = 365
ACCESS_TOKEN_SECONDS = 3600
CODE_MINUTES = 10


def parse_scopes(raw: Optional[str]) -> tuple[list[str], list[str]]:
    """(known scopes in a stable order, unknown ones). OIDC-style extras like 'openid' are ignored."""
    asked = [s for s in (raw or "").split() if s]
    unknown = [s for s in asked if s not in SCOPES and s not in ("openid", "offline_access")]
    return [s for s in SCOPES if s in asked], unknown


def _patient(profile: HealthProfile, pid: str) -> dict:
    res = {"resourceType": "Patient", "id": pid}
    if profile.sex:
        res["gender"] = profile.sex.value
    if profile.birth_date:
        res["birthDate"] = str(profile.birth_date.year)  # year only: minimum necessary
    return res


_RISK = {"high": ("high", "High likelihood"), "moderate": ("moderate", "Moderate likelihood"),
         "info": ("low", "Low likelihood")}


def risk_assessments(report: InsightReport, pid: str) -> list[dict]:
    out = []
    for i in report.insights:
        code, text = _RISK[i.level.value]
        out.append({
            "resourceType": "RiskAssessment", "id": i.rule_id, "status": "final",
            "subject": {"reference": f"Patient/{pid}"},
            "occurrenceDateTime": report.generated_at.isoformat(),
            "method": {"text": f"Family Health Graph guideline rule ({i.rule_id}); rule-based, not a diagnosis"},
            "basis": [{"display": e} for e in i.evidence],
            "prediction": [{"outcome": {"text": i.title}, "qualitativeRisk": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/risk-probability", "code": code}],
                "text": text}}],
            "mitigation": i.recommendation,
            "note": [{"text": i.summary}] + [{"text": f"Reference: {r.title} ({r.url})"} for r in i.references],
        })
    return out


def resources(resource_type: str, profile: HealthProfile, report: Optional[InsightReport], pid: str) -> list[dict]:
    """The user's resources of one type, with references pointing at the partner-specific Patient id."""
    if resource_type == "Patient":
        return [_patient(profile, pid)]
    if resource_type == "RiskAssessment":
        return risk_assessments(report, pid) if report else []
    category = {"FamilyMemberHistory": "family_history", "Condition": "conditions", "Observation": "observations",
                "MedicationStatement": "medications"}[resource_type]
    out = []
    for n, entry in enumerate(to_fhir_bundle(profile, {category})["entry"]):
        res = entry["resource"]
        if res["resourceType"] != resource_type:
            continue
        res = dict(res)
        for key in ("subject", "patient"):
            if key in res:
                res[key] = {"reference": f"Patient/{pid}"}
        res["id"] = f"{resource_type[:3].lower()}-{n}"
        out.append(res)
    return out


def searchset(base: str, items: list[dict]) -> dict:
    return {"resourceType": "Bundle", "type": "searchset", "total": len(items),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entry": [{"fullUrl": f"{base}/{r['resourceType']}/{r.get('id', '')}", "resource": r,
                       "search": {"mode": "match"}} for r in items]}


def outcome(code: str, text: str) -> dict:
    return {"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": code, "diagnostics": text}]}


def capability_statement(base: str) -> dict:
    return {
        "resourceType": "CapabilityStatement", "status": "active", "kind": "instance", "fhirVersion": "4.0.1",
        "format": ["json"], "date": datetime.now(timezone.utc).date().isoformat(),
        "software": {"name": "Family Health Graph"},
        "implementation": {"description": "Family history shared with the patient's consent", "url": base},
        "rest": [{
            "mode": "server",
            "security": {"service": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/restful-security-service",
                                                  "code": "OAuth"}]}],
                         "description": "OAuth 2.0 authorization code with PKCE; see /.well-known/oauth-authorization-server"},
            "resource": [{"type": t, "interaction": [{"code": "search-type"}, {"code": "read"}]} for t in RESOURCE_SCOPE],
        }],
    }
