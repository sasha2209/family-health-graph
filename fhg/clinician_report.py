"""Clinician summary: a one-document family health history to take to an appointment.

Written for the clinician, not the patient: findings are stated as the criteria
met and the guideline they come from, the family history is laid out as a
standard pedigree plus a table, and everything is clearly marked as
patient-reported. The HTML is print-ready (the mobile app turns it into a PDF).

All user-entered text is HTML-escaped: condition names, relative names and
medications come from free text.
"""
from __future__ import annotations

from datetime import date
from html import escape
from typing import Optional

from .insights.engine import DISCLAIMER
from .models import FamilyMember, HealthProfile, InsightReport, Relationship as R

LEVEL_TEXT = {"high": "Discuss soon", "moderate": "Next routine visit", "info": "For awareness"}

ABBREV = {
    "breast_cancer": "Breast ca", "ovarian_cancer": "Ovarian ca", "pancreatic_cancer": "Pancreatic ca",
    "prostate_cancer": "Prostate ca", "colorectal_cancer": "CRC", "endometrial_cancer": "Endometrial ca",
    "stomach_cancer": "Gastric ca", "melanoma": "Melanoma", "cancer_unspecified": "Cancer (type ?)",
    "coronary_artery_disease": "CAD/MI", "stroke": "Stroke", "hypertension": "HTN",
    "hyperlipidemia": "HLD", "familial_hypercholesterolemia": "FH", "type_2_diabetes": "T2D",
    "type_1_diabetes": "T1D", "hboc_variant": "BRCA+", "lynch_syndrome": "Lynch",
    "malignant_hyperthermia": "MH", "dementia": "Dementia", "congenital_heart_disease": "CHD",
}

LABS = [("ldl_cholesterol", "LDL cholesterol"), ("hba1c", "HbA1c"), ("bmi", "BMI"),
        ("lipoprotein_a", "Lipoprotein(a)")]


def _label(rel: R) -> str:
    return rel.value.replace("_", " ").capitalize()


def _conditions(m: FamilyMember) -> str:
    if not m.conditions:
        return '<span class="muted">None known</span>'
    parts = []
    for c in m.conditions:
        age = "" if c.onset_age is None else f", dx {'~' if c.age_estimated else ''}{c.onset_age}"
        parts.append(escape(c.display_name) + age)
    return "; ".join(parts)


def _status(m: FamilyMember) -> str:
    parts = ["Deceased" if m.deceased else "Living" if m.deceased is False else ""]
    if m.age is not None:
        parts.append(f"age {m.age}" if parts[0] else f"Age {m.age}")
    return ", ".join(p for p in parts if p) or "—"


def _short(m: FamilyMember) -> list[str]:
    out = []
    for c in m.conditions[:3]:
        name = ABBREV.get(c.category or "", (c.name or "?")[:14])
        out.append(f"{name}{'' if c.onset_age is None else ' ' + str(c.onset_age)}")
    if len(m.conditions) > 3:
        out.append(f"+{len(m.conditions) - 3} more")
    return out


# --- pedigree ----------------------------------------------------------------------------

SIZE, GAP_X, GAP_Y = 30, 104, 120


def _symbol(x: float, y: float, sex: Optional[str], affected: bool, deceased: bool,
            missing: bool = False) -> str:
    fill = "#444" if affected else "#fff"
    dash = ' stroke-dasharray="4 3"' if missing else ""
    h = SIZE / 2
    if sex == "male":
        shape = f'<rect x="{x - h}" y="{y - h}" width="{SIZE}" height="{SIZE}" fill="{fill}" stroke="#222" stroke-width="1.5"{dash}/>'
    elif sex == "female":
        shape = f'<circle cx="{x}" cy="{y}" r="{h}" fill="{fill}" stroke="#222" stroke-width="1.5"{dash}/>'
    else:
        shape = (f'<polygon points="{x},{y - h} {x + h},{y} {x},{y + h} {x - h},{y}" fill="{fill}" '
                 f'stroke="#222" stroke-width="1.5"{dash}/>')
    if deceased:
        shape += f'<line x1="{x - h - 5}" y1="{y + h + 5}" x2="{x + h + 5}" y2="{y - h - 5}" stroke="#222" stroke-width="1.5"/>'
    return shape


def _text(x: float, y: float, lines: list[str], muted: bool = False) -> str:
    color = "#777" if muted else "#222"
    return "".join(
        f'<text x="{x}" y="{y + i * 12}" text-anchor="middle" font-size="{10 if i else 10.5}" '
        f'font-weight="{600 if i == 0 else 400}" fill="{color}">{escape(t)}</text>'
        for i, t in enumerate(lines))


def pedigree_svg(profile: HealthProfile) -> str:
    """A three/four-generation pedigree in standard notation (patient marked with an arrow).

    Relatives whose side is unknown (e.g. "aunt", "cousin") are listed in the
    table rather than guessed into the diagram.
    """
    by_rel: dict[R, list[FamilyMember]] = {}
    for m in profile.family:
        by_rel.setdefault(m.relationship, []).append(m)

    def first(rel: R) -> Optional[FamilyMember]:
        return (by_rel.get(rel) or [None])[0]

    pat_sibs = by_rel.get(R.PATERNAL_AUNT, []) + by_rel.get(R.PATERNAL_UNCLE, [])
    mat_sibs = by_rel.get(R.MATERNAL_AUNT, []) + by_rel.get(R.MATERNAL_UNCLE, [])
    siblings = by_rel.get(R.SISTER, []) + by_rel.get(R.BROTHER, []) + by_rel.get(R.SIBLING, [])
    children = by_rel.get(R.DAUGHTER, []) + by_rel.get(R.SON, []) + by_rel.get(R.CHILD, [])

    nodes: list[str] = []
    lines: list[str] = []

    def person(x, y, member: Optional[FamilyMember], sex: Optional[str], label: str):
        if member is None:
            nodes.append(_symbol(x, y, sex, False, False, missing=True))
            nodes.append(_text(x, y + SIZE / 2 + 14, [label, "not recorded"], muted=True))
            return
        nodes.append(_symbol(x, y, member.effective_sex or sex, bool(member.conditions), bool(member.deceased)))
        nodes.append(_text(x, y + SIZE / 2 + 14, [label] + _short(member)))

    # Generation II layout: paternal aunts/uncles, Father, Mother, maternal aunts/uncles.
    row2 = [("pat", m) for m in pat_sibs] + [("father", None), ("mother", None)] + [("mat", m) for m in mat_sibs]
    x0 = 70
    xs2 = [x0 + i * GAP_X for i in range(len(row2))]
    father_x = xs2[len(pat_sibs)]
    mother_x = xs2[len(pat_sibs) + 1]
    y1, y2, y3, y4 = 50, 50 + GAP_Y, 50 + 2 * GAP_Y, 50 + 3 * GAP_Y

    # Generation I: grandparent couples above each side's sibship.
    def grandparents(gf: R, gm: R, sib_xs: list[float], label_side: str):
        if not (first(gf) or first(gm)):
            return
        cx = (min(sib_xs) + max(sib_xs)) / 2
        gx, mx = cx - GAP_X / 2.6, cx + GAP_X / 2.6
        person(gx, y1, first(gf), "male", f"{label_side} GF")
        person(mx, y1, first(gm), "female", f"{label_side} GM")
        lines.append(f'<line x1="{gx + SIZE / 2}" y1="{y1}" x2="{mx - SIZE / 2}" y2="{y1}"/>')
        bar_y = y2 - SIZE / 2 - 22
        lines.append(f'<line x1="{cx}" y1="{y1}" x2="{cx}" y2="{bar_y}"/>')
        lines.append(f'<line x1="{min(sib_xs)}" y1="{bar_y}" x2="{max(sib_xs)}" y2="{bar_y}"/>')
        for sx in sib_xs:
            lines.append(f'<line x1="{sx}" y1="{bar_y}" x2="{sx}" y2="{y2 - SIZE / 2}"/>')

    grandparents(R.PATERNAL_GRANDFATHER, R.PATERNAL_GRANDMOTHER, xs2[:len(pat_sibs) + 1], "Pat.")
    grandparents(R.MATERNAL_GRANDFATHER, R.MATERNAL_GRANDMOTHER, xs2[len(pat_sibs) + 1:], "Mat.")

    for (kind, m), x in zip(row2, xs2):
        if kind == "father":
            person(x, y2, first(R.FATHER), "male", "Father")
        elif kind == "mother":
            person(x, y2, first(R.MOTHER), "female", "Mother")
        else:
            person(x, y2, m, None, _label(m.relationship).replace("Paternal ", "Pat. ").replace("Maternal ", "Mat. "))
    lines.append(f'<line x1="{father_x + SIZE / 2}" y1="{y2}" x2="{mother_x - SIZE / 2}" y2="{y2}"/>')

    # Generation III: the patient and full siblings under the parents.
    sex = profile.sex.value if profile.sex else None
    row3 = [("sib", m) for m in siblings[: len(siblings) // 2]] + [("self", None)] + \
           [("sib", m) for m in siblings[len(siblings) // 2:]]
    cx = (father_x + mother_x) / 2
    xs3 = [cx + (i - (len(row3) - 1) / 2) * GAP_X for i in range(len(row3))]
    bar3 = y3 - SIZE / 2 - 22
    lines.append(f'<line x1="{cx}" y1="{y2}" x2="{cx}" y2="{bar3}"/>')
    lines.append(f'<line x1="{min(xs3)}" y1="{bar3}" x2="{max(xs3)}" y2="{bar3}"/>')
    self_x = cx
    for (kind, m), x in zip(row3, xs3):
        lines.append(f'<line x1="{x}" y1="{bar3}" x2="{x}" y2="{y3 - SIZE / 2}"/>')
        if kind == "self":
            self_x = x
            own = FamilyMember(relationship=R.OTHER, sex=profile.sex, conditions=profile.conditions)
            nodes.append(_symbol(x, y3, sex, bool(profile.conditions), False))
            nodes.append(_text(x, y3 + SIZE / 2 + 14, ["Patient"] + _short(own)))
            nodes.append(f'<path d="M{x - 34},{y3 + 22} L{x - 18},{y3 + 8}" stroke="#222" stroke-width="2"/>'
                         f'<polygon points="{x - 18},{y3 + 8} {x - 26},{y3 + 10} {x - 20},{y3 + 16}" fill="#222"/>')
        else:
            person(x, y3, m, None, _label(m.relationship))

    height = y3 + 90
    # Generation IV: the patient's children.
    if children:
        y4 += 30  # leave room for the patient's label above the descent line
        bar4 = y4 - SIZE / 2 - 22
        xs4 = [self_x + (i - (len(children) - 1) / 2) * GAP_X for i in range(len(children))]
        label_bottom = y3 + SIZE / 2 + 14 + 12 * (len(_short(FamilyMember(
            relationship=R.OTHER, conditions=profile.conditions)))) + 6
        lines.append(f'<line x1="{self_x}" y1="{label_bottom}" x2="{self_x}" y2="{bar4}"/>')
        lines.append(f'<line x1="{min(xs4)}" y1="{bar4}" x2="{max(xs4)}" y2="{bar4}"/>')
        for m, x in zip(children, xs4):
            lines.append(f'<line x1="{x}" y1="{bar4}" x2="{x}" y2="{y4 - SIZE / 2}"/>')
            person(x, y4, m, None, _label(m.relationship))
        height = y4 + 90

    all_x = xs2 + xs3 + [self_x]
    min_x, max_x = min(all_x) - 70, max(all_x) + 70
    width = max_x - min_x
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x} 0 {width} {height}" '
            f'width="100%" style="max-width:{width}px" role="img" aria-label="Family pedigree">'
            f'<g stroke="#222" stroke-width="1.5" fill="none">{"".join(lines)}</g>{"".join(nodes)}</svg>')


# --- document ----------------------------------------------------------------------------

def render_html(profile: HealthProfile, report: InsightReport, today: Optional[date] = None,
                shared_included: bool = True) -> str:
    today = today or date.today()
    age = profile.age(today)
    sex = profile.sex.value.capitalize() if profile.sex else "Not recorded"

    findings = [i for i in report.insights if i.category != "data_quality"]
    gaps = next((i for i in report.insights if i.category == "data_quality"), None)

    rows_findings = "".join(
        f"<tr><td><span class='lvl {escape(i.level.value)}'>{LEVEL_TEXT[i.level.value]}</span></td>"
        f"<td><b>{escape(i.title)}</b><ul>{''.join(f'<li>{escape(e)}</li>' for e in i.evidence)}</ul></td>"
        f"<td>{escape(i.recommendation)}</td>"
        f"<td class='refs'>{'<br>'.join(escape(r.title) for r in i.references)}</td></tr>"
        for i in findings) or "<tr><td colspan='4' class='muted'>No guideline criteria met with the information recorded.</td></tr>"

    order = {"maternal": 1, "paternal": 2, None: 3}
    family = sorted(profile.family, key=lambda m: (m.degree or 9, order.get(m.side, 3), m.relationship.value))
    rows_family = "".join(
        f"<tr><td>{escape(_label(m.relationship))}{(' (' + escape(m.name) + ')') if m.name else ''}</td>"
        f"<td>{_status(m)}</td>"
        f"<td>{_conditions(m)}</td>"
        f"<td>{'Shared by relative' if m.linked else 'Patient-reported'}</td></tr>"
        for m in family) or "<tr><td colspan='4' class='muted'>No family history recorded.</td></tr>"

    own = "; ".join(
        escape(c.display_name) + ("" if c.onset_age is None else f", dx {c.onset_age}")
        for c in profile.conditions) or "None recorded"
    meds = "; ".join(escape(m.name) for m in profile.medications) or "None recorded"
    labs = []
    for code, name in LABS:
        o = profile.latest(code)
        if o:
            when = f" ({o.effective_date.isoformat()})" if o.effective_date else ""
            labs.append(f"{name} {o.value:g} {escape(o.unit)}{when}")
    sbp, dbp = profile.latest("systolic_bp"), profile.latest("diastolic_bp")
    if sbp and dbp:
        labs.append(f"BP {sbp.value:g}/{dbp.value:g} mmHg"
                    + (f" ({sbp.effective_date.isoformat()})" if sbp.effective_date else ""))
    gaps_html = ("<ul>" + "".join(f"<li>{escape(g)}</li>" for g in gaps.evidence
                                  if not g.startswith("Invite")) + "</ul>") if gaps else "<p class='muted'>None.</p>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family health history summary</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  body {{ font: 11px/1.45 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1d1d1b; margin: 0; padding: 16px; background: #fff; }}
  h1 {{ font-size: 18px; margin: 0 0 2px; }}
  h2 {{ font-size: 13px; margin: 18px 0 6px; padding-bottom: 3px; border-bottom: 1.5px solid #2f6f62; color: #2f6f62; }}
  .meta {{ color: #555; margin-bottom: 10px; }}
  .facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 6px 16px; border: 1px solid #ddd; border-radius: 6px; padding: 8px 10px; }}
  .facts b {{ display: block; font-size: 9.5px; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; vertical-align: top; padding: 5px 6px; border-bottom: 1px solid #e3e2dc; }}
  th {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .04em; color: #666; }}
  ul {{ margin: 3px 0 0; padding-left: 16px; }}
  .lvl {{ display: inline-block; font-weight: 700; font-size: 9.5px; padding: 1px 6px; border-radius: 9px; white-space: nowrap; }}
  .lvl.high {{ background: #fbeeea; color: #b4442f; }} .lvl.moderate {{ background: #fbf3e2; color: #8a5d0d; }} .lvl.info {{ background: #ecf1f8; color: #3d6191; }}
  .refs {{ color: #555; font-size: 10px; }}
  .muted {{ color: #777; }}
  .pedigree {{ border: 1px solid #ddd; border-radius: 6px; padding: 6px; overflow-x: auto; page-break-inside: avoid; }}
  .legend {{ color: #555; font-size: 10px; margin-top: 4px; }}
  .note {{ margin-top: 18px; padding: 8px 10px; background: #f5f5f2; border-radius: 6px; color: #444; font-size: 10px; }}
  tr {{ page-break-inside: avoid; }}
</style></head><body>
<h1>Family health history summary</h1>
<div class="meta">Prepared {today.strftime('%d %b %Y')} by the patient with Family Health Graph · Patient-reported, not clinically verified</div>
<div class="facts">
  <div><b>Date of birth</b>{escape(profile.birth_date.isoformat()) if profile.birth_date else 'Not recorded'}{'' if age is None else f' (age {age})'}</div>
  <div><b>Sex</b>{escape(sex)}</div>
  <div><b>Relatives recorded</b>{len(profile.family)}{f" ({sum(1 for m in profile.family if m.linked)} shared their own history)" if shared_included and any(m.linked for m in profile.family) else ''}</div>
  <div><b>Name</b>&nbsp;</div>
</div>

<h2>Items to consider</h2>
<table><tr><th style="width:14%">Priority</th><th style="width:38%">Finding and criteria met</th><th>Suggested consideration</th><th style="width:20%">Guideline</th></tr>{rows_findings}</table>

<h2>Pedigree</h2>
<div class="pedigree">{pedigree_svg(profile)}</div>
<div class="legend">Square = male, circle = female, diamond = sex not recorded; filled = condition reported; slash = deceased; dashed = not recorded; arrow = patient. Numbers are age at diagnosis.</div>

<h2>Family history</h2>
<table><tr><th style="width:22%">Relative</th><th style="width:16%">Status</th><th>Conditions (age at diagnosis)</th><th style="width:16%">Source</th></tr>{rows_family}</table>

<h2>Patient's own history</h2>
<table>
<tr><th style="width:22%">Conditions</th><td>{own}</td></tr>
<tr><th>Medications</th><td>{meds}</td></tr>
<tr><th>Recent results</th><td>{'; '.join(labs) or 'None recorded'}</td></tr>
</table>

<h2>Information still missing</h2>
{gaps_html}

<div class="note">{escape(DISCLAIMER)} Criteria are simplified from the cited guidelines and are meant to prompt
a conversation, not to replace clinical judgement. A machine-readable version (HL7 FHIR) is available from the patient's app.</div>
</body></html>"""
