"""The one-page emergency summary for someone you care for: what a doctor or ambulance crew needs first.

Printed by the family, or opened from a time-limited link. Shows identity basics, blood group, allergies,
conditions, current medicines with how they're taken, the latest key results, and who to call.
"""
from __future__ import annotations

from datetime import date
from html import escape
from typing import Optional

from .care import schedule_for
from .models import FamilyMember

KEY_RESULTS = ("hba1c", "fasting_glucose", "systolic_bp", "diastolic_bp", "creatinine", "egfr", "ldl_cholesterol",
               "hemoglobin", "tsh")
RESULT_NAMES = {"hba1c": "HbA1c", "fasting_glucose": "Fasting sugar", "systolic_bp": "BP (systolic)",
                "diastolic_bp": "BP (diastolic)", "creatinine": "Creatinine", "egfr": "eGFR",
                "ldl_cholesterol": "LDL cholesterol", "hemoglobin": "Haemoglobin", "tsh": "TSH"}


def summary(member: FamilyMember) -> dict:
    care = member.care
    meds = []
    for m in member.medications:
        if m.status != "active":
            continue
        s = schedule_for(m)
        how = " · ".join(filter(None, [
            "-".join(f"{s.slots.get(k, 0):g}" for k in ("morning", "afternoon", "night")) if s.slots else None,
            "when needed" if s.as_needed else None, s.food]))
        meds.append({"name": m.name, "generic": m.generic, "how": how or (m.dosage or "")})
    results = []
    for code in KEY_RESULTS:
        o = member.latest(code)
        if o:
            results.append({"name": RESULT_NAMES[code], "value": f"{o.value:g} {o.unit}".strip(),
                            "date": o.effective_date.isoformat() if o.effective_date else None})
    return {
        "name": member.name or member.label, "relationship": member.label, "age": member.age,
        "sex": member.effective_sex, "blood_group": care.blood_group if care else None,
        "allergies": care.allergies if care else [],
        "conditions": [c.display_name + (f" (since age {c.onset_age})" if c.onset_age else "") for c in member.conditions],
        "medicines": meds, "results": results,
        "contacts": [x for x in [
            {"role": "Emergency contact", "name": care.emergency_contact_name, "phone": care.emergency_contact_phone} if care else None,
            {"role": "Doctor", "name": care.doctor_name, "phone": care.doctor_phone} if care else None] if x and (x["name"] or x["phone"])],
        "hospital": care.hospital if care else None, "notes": care.notes if care else None,
    }


def render_html(s: dict, *, generated: Optional[date] = None, expires: Optional[str] = None) -> str:
    e = lambda v: escape(str(v)) if v is not None else ""  # noqa: E731
    allergies = ", ".join(map(e, s["allergies"])) if s["allergies"] else "None recorded"
    rows = lambda items, cols: "".join("<tr>" + "".join(f"<td>{e(i.get(c))}</td>" for c in cols) + "</tr>" for i in items)  # noqa: E731
    contacts = "".join(f"<p><b>{e(c['role'])}:</b> {e(c['name'])} "
                       + (f"<a href='tel:{e(c['phone'])}'>{e(c['phone'])}</a>" if c["phone"] else "") + "</p>"
                       for c in s["contacts"])
    footer = f"Generated {e((generated or date.today()).isoformat())}"
    if expires:
        footer += f" · link valid until {e(expires[:16].replace('T', ' '))} UTC"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Emergency summary: {e(s['name'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;color:#111}}
h1{{font-size:22px;margin:0}}h2{{font-size:15px;text-transform:uppercase;letter-spacing:.04em;color:#555;margin:20px 0 6px}}
.alert{{background:#fdecea;border:1px solid #f5c2c0;border-radius:8px;padding:10px 12px;font-size:17px}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #ddd;padding:6px 4px;vertical-align:top}}
.muted{{color:#666;font-size:13px}}@media print{{a{{color:inherit;text-decoration:none}}}}</style></head><body>
<h1>{e(s['name'])}</h1>
<p>{e(s['relationship'])} · {e(s['sex'] or 'sex not recorded')} · {e(f"age {s['age']}" if s['age'] else 'age not recorded')}
 · <b>Blood group: {e(s['blood_group'] or 'not recorded')}</b></p>
<div class="alert"><b>Allergies:</b> {allergies}</div>
<h2>Conditions</h2>{"<p>" + "<br>".join(map(e, s["conditions"])) + "</p>" if s["conditions"] else "<p class='muted'>None recorded</p>"}
<h2>Current medicines</h2>{f"<table>{rows(s['medicines'], ('name', 'generic', 'how'))}</table>" if s['medicines'] else "<p class='muted'>None recorded</p>"}
<h2>Latest results</h2>{f"<table>{rows(s['results'], ('name', 'value', 'date'))}</table>" if s['results'] else "<p class='muted'>None recorded</p>"}
<h2>Who to call</h2>{contacts or "<p class='muted'>No contacts recorded</p>"}
{f"<p><b>Usual hospital:</b> {e(s['hospital'])}</p>" if s['hospital'] else ""}
{f"<h2>Notes</h2><p>{e(s['notes'])}</p>" if s['notes'] else ""}
<p class="muted">{footer}. Kept by the family in Family Health Graph; check details with the patient or family where
possible. Medicines show morning-afternoon-night amounts.</p></body></html>"""
