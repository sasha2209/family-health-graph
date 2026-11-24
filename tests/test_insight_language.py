"""Action items in Hindi: every template the rules use has a translation, and the English output is untouched."""
import ast
import re
from datetime import date
from pathlib import Path

from fhg.insights import generate_insights
from fhg.insights.hi import HI as RULES_HI
from fhg.notices_hi import NOTICES_HI

HI = {**RULES_HI, **NOTICES_HI}
from fhg.insights.lang import language, tr
from fhg.insights.rules import ACTIVITY_LABEL
from fhg.models import Condition, FamilyMember, HealthProfile, Observation, Relationship, Sex
from fhg.terminology import CONCEPTS

ROOT = Path(__file__).parent.parent / "fhg"


def templates() -> set[str]:
    """Every literal passed to tr() or mark() in the rules (both sides of a conditional), plus the names that
    appear inside sentences."""
    out: set[str] = set()
    for path in (ROOT / "insights" / "rules.py", ROOT / "risk_models.py", ROOT / "notices.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "mark") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Subscript) and isinstance(arg.value, ast.Dict):
                    arg = arg.value                       # tr({"maternal": "...", "paternal": "..."}[side])
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and len(sub.value) > 1 and \
                            not (isinstance(arg, ast.Dict) and sub in arg.keys):
                        out.add(sub.value)
    out.update(c.display for c in CONCEPTS)
    out.update(FamilyMember(relationship=r).label for r in Relationship)
    out.update(ACTIVITY_LABEL.values())
    out.update({"You", "Placeholder", "mother", "father", "waist size", "sex", "physical activity", " and ", " or "})
    return out


def test_every_template_has_hindi():
    missing = sorted(t for t in templates() if t not in HI)
    assert missing == [], "Add to fhg/insights/hi.py:\n" + "\n".join(repr(m) for m in missing)


def test_placeholders_match():
    for en, hi in HI.items():
        assert sorted(re.findall(r"\{\w+\}", en)) == sorted(re.findall(r"\{\w+\}", hi)), en


def profile():
    mother = FamilyMember(relationship=Relationship.MOTHER, conditions=[
        Condition(name="breast cancer", category="breast_cancer", onset_age=44),
        Condition(name="type 2 diabetes", category="type_2_diabetes")])
    father = FamilyMember(relationship=Relationship.FATHER, conditions=[
        Condition(name="heart attack", category="coronary_artery_disease", onset_age=50)])
    return HealthProfile(sex=Sex.FEMALE, birth_date=date(1980, 1, 1), activity="sedentary", family=[mother, father],
                         observations=[Observation(code="hba1c", value=6.1, unit="%", effective_date=date(2026, 1, 1)),
                                       Observation(code="systolic_bp", value=142, unit="mmHg"),
                                       Observation(code="diastolic_bp", value=92, unit="mmHg"),
                                       Observation(code="waist_circumference", value=92, unit="cm")])


def test_hindi_insights_read_in_hindi_and_english_is_default():
    english = generate_insights(profile())
    with language("hi"):
        hindi = generate_insights(profile())
    assert [i.rule_id for i in english.insights] == [i.rule_id for i in hindi.insights]
    hboc = next(i for i in hindi.insights if i.rule_id == "hboc_family_pattern")
    assert hboc.title == HI["Family pattern worth a hereditary cancer risk assessment"]
    assert "माँ: स्तन कैंसर" in hboc.evidence[0] and "44" in hboc.evidence[0]
    for i in hindi.insights:                                   # no English sentence left in the text people read
        for text in [i.title, i.summary, i.recommendation, *i.evidence]:
            assert not re.search(r"\b(the|your|and|with|is)\b", text), (i.rule_id, text)
    eng = next(i for i in english.insights if i.rule_id == "hboc_family_pattern")
    assert eng.evidence[0] == "Mother: Breast cancer (diagnosed at 44)"     # English unchanged
    assert tr("Home") == "Home"                                              # outside a language block: English


def test_api_language(tmp_path):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient

    from fhg.api import Settings, create_app
    api = TestClient(create_app(Settings(db_path=str(tmp_path / "l.db"), encryption_key=Fernet.generate_key().decode())))
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.post("/v1/ingest/text", headers=h, json={"text": "My mother had breast cancer at 44."})
    title = lambda r: next(i["title"] for i in r["insights"] if i["rule_id"] == "hboc_family_pattern")  # noqa: E731
    assert title(api.get("/v1/insights", headers=h).json()) == "Family pattern worth a hereditary cancer risk assessment"
    assert title(api.get("/v1/insights?lang=hi", headers=h).json()).startswith("परिवार में")
    api.put("/v1/profile/language", headers=h, json={"lang": "hi"})
    report = api.get("/v1/insights", headers=h).json()
    assert title(report).startswith("परिवार में") and report["disclaimer"].startswith("ये सलाह")
    assert title(api.get("/v1/insights?lang=en", headers=h).json()).startswith("Family pattern")
    # The doctor's summary stays in English whatever the person's language.
    assert "Family pattern worth a hereditary cancer risk assessment" in api.get("/v1/report/clinician", headers=h).text


def test_notices_in_the_readers_language(tmp_path):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient

    from fhg.api import Settings, create_app
    admin = {"X-Admin-Key": "k"}
    api = TestClient(create_app(Settings(db_path=str(tmp_path / "n.db"), encryption_key=Fernet.generate_key().decode(),
                                         admin_key="k"), webhooks_in_background=False, push_in_background=False,
                                webhook_sender=type("S", (), {"send": lambda *a: None})()))
    hi = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    en = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.put("/v1/profile/language", headers=hi, json={"lang": "hi"})
    lab = api.post("/admin/partners", headers=admin, json={"name": "Thyro Labs", "kind": "lab"}).json()
    key = {"X-API-Key": lab["api_key"]}
    api.put(f"/admin/partners/{lab['partner']['id']}/catalog", headers=admin, json=[{"test": "hba1c", "price_inr": 450},
                                                                                   {"test": "fasting_glucose", "price_inr": 150}])
    for h in (hi, en):
        b = api.post("/v1/bookings", headers=h, json={"partner_id": lab["partner"]["id"], "tests": ["hba1c", "fasting_glucose"],
                                                      "contact": {"name": "P", "phone": "+91 98123 45678"}}).json()
        api.post(f"/v1/partner/bookings/{b['id']}/status", headers=key,
                 json={"status": "scheduled", "scheduled_for": "2026-12-01T08:00:00+05:30"})
    last = lambda h: api.get("/v1/notifications", headers=h).json()[0]["message"]  # noqa: E731
    assert last(en) == "Thyro Labs confirmed your HbA1c, Fasting blood sugar for 1 Dec 2026."
    assert last(hi) == "Thyro Labs ने आपका HbA1c, खाली पेट शुगर 1 Dec 2026 के लिए पक्का किया।"
