"""Tree-based hereditary-risk models: the pedigree, the CanRisk export, Lynch criteria, and counselor results."""
from datetime import date

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import risk_models
from fhg.api import Settings, create_app
from fhg.insights import generate_insights
from fhg.models import Condition, FamilyMember, HealthProfile, Relationship as R, Sex
from fhg.pedigree import build

ADMIN = {"X-Admin-Key": "admin-secret"}


def rel(r, *conds, **kw):
    return FamilyMember(relationship=r, conditions=[Condition(name=c, category=c, onset_age=a) for c, a in conds], **kw)


def profile(*family, sex=Sex.FEMALE, conditions=()):
    return HealthProfile(sex=sex, birth_date=date(1985, 6, 1), family=list(family),
                         conditions=[Condition(name=c, category=c, onset_age=a) for c, a in conditions])


def test_tree_links_relatives_through_real_parents():
    p = profile(rel(R.MOTHER), rel(R.MATERNAL_AUNT, ("breast_cancer", 44)), rel(R.MATERNAL_COUSIN, sex=Sex.FEMALE),
                rel(R.SISTER), rel(R.DAUGHTER), rel(R.UNCLE), rel(R.SIBLING))
    ped = build(p, today=date(2026, 1, 1))
    by_label = {x.label: x for x in ped.real()}
    aunt, mum, sister, cousin = (by_label[k] for k in ("Maternal aunt", "Mother", "Sister", "Maternal cousin"))
    assert (aunt.father, aunt.mother) == (mum.father, mum.mother) == ("MGF", "MGM")
    assert ped.degree("P", aunt.id) == 2 and ped.degree("P", sister.id) == 1 and ped.degree("P", cousin.id) == 3
    assert ped.degree(mum.id, aunt.id) == 1 and ped.degree("P", by_label["Daughter"].id) == 1
    assert ped.proband.age == 40 and ped.proband.yob == 1985
    assert sorted(ped.skipped) == ["Sibling: sex not recorded", "Uncle: which side of the family isn't recorded"]
    assert "PGM" not in ped.people                     # no paternal relatives recorded: no empty grandparents


def test_needs_own_sex():
    with pytest.raises(ValueError):
        build(HealthProfile())


def test_canrisk_file_format():
    p = profile(rel(R.MOTHER, ("breast_cancer", 46), ("ovarian_cancer", None), deceased=True, age=58),
                rel(R.FATHER, ("prostate_cancer", 70), ("ovarian_cancer", 50)),   # OC can't apply to a man
                rel(R.MATERNAL_AUNT, ("breast_cancer", 39), ("breast_cancer", 52)), conditions=[("breast_cancer", 38)])
    text, warnings = risk_models.canrisk_file(p)
    lines = text.splitlines()
    assert lines[0] == "##CanRisk 2.0"
    header = lines[1].lstrip("#").split("\t")
    assert header[:17] == ["FamID", "Name", "Target", "IndivID", "FathID", "MothID", "Sex", "MZtwin", "Dead", "Age",
                           "Yob", "BC1", "BC2", "OC", "PRO", "PAN", "Ashkn"]
    assert header[17:26] == list(risk_models.CANRISK_GENES) and header[26] == "ER:PR:HER2:CK14:CK56"
    rows = {r.split("\t")[3]: dict(zip(header, r.split("\t"))) for r in lines[2:]}
    assert all(len(r) == 27 for r in rows.values())
    me, mum, dad = rows["P"], rows["M"], rows["F"]
    assert (me["Target"], me["Sex"], me["FathID"], me["MothID"], me["BC1"], me["Yob"]) == ("1", "F", "F", "M", "38", "1985")
    assert (mum["Dead"], mum["Age"], mum["BC1"], mum["OC"]) == ("1", "58", "46", "AU")
    assert (dad["Sex"], dad["PRO"], dad["OC"]) == ("M", "70", "0")
    aunt = next(r for r in rows.values() if r["BC2"] == "52")
    assert aunt["BC1"] == "39" and (aunt["FathID"], aunt["MothID"]) == ("MGF", "MGM")
    assert rows["MGM"]["BC1"] == "0" and rows["MGM"]["BRCA1"] == "0:0"
    assert "Mother: a cancer's age at diagnosis is unknown (written as AU)" in warnings
    assert all(r["Name"].isdigit() for r in rows.values())               # never names


def lynch_family():
    return profile(rel(R.MOTHER, ("colorectal_cancer", 47)), rel(R.MATERNAL_GRANDFATHER, ("colorectal_cancer", 66)),
                   rel(R.MATERNAL_AUNT, ("endometrial_cancer", 55)))


def test_amsterdam_ii():
    res = risk_models.amsterdam_ii(build(lynch_family()))
    assert res.met and "One is a first-degree relative of the other two" in res.criteria
    assert "Mother: Colorectal cancer at 47" in res.evidence
    # Same three cancers, but nobody under 50: not met.
    late = profile(rel(R.MOTHER, ("colorectal_cancer", 61)), rel(R.MATERNAL_GRANDFATHER, ("colorectal_cancer", 66)),
                   rel(R.MATERNAL_AUNT, ("endometrial_cancer", 55)))
    assert not risk_models.amsterdam_ii(build(late)).met
    # Three affected but scattered (cousins on different sides): no one is a first-degree relative of the other two.
    scattered = profile(rel(R.MATERNAL_COUSIN, ("colorectal_cancer", 40), sex=Sex.MALE),
                        rel(R.PATERNAL_COUSIN, ("colorectal_cancer", 45), sex=Sex.MALE), rel(R.FATHER, ("colorectal_cancer", 70)))
    assert not risk_models.amsterdam_ii(build(scattered)).met


def test_revised_bethesda():
    p = profile(rel(R.FATHER, ("colorectal_cancer", 62)), rel(R.PATERNAL_AUNT, ("stomach_cancer", 70)),
                rel(R.PATERNAL_GRANDMOTHER, ("endometrial_cancer", 68)))
    res = risk_models.revised_bethesda(build(p))
    assert len(res) == 1 and res[0].model == "Revised Bethesda guidelines (father)"
    assert res[0].criteria == ["Two or more first- or second-degree relatives with Lynch-associated cancers, any age"]
    young = risk_models.revised_bethesda(build(profile(conditions=[("colorectal_cancer", 42)])))
    assert young[0].criteria == ["Colorectal cancer diagnosed before 50"] and young[0].model.endswith("(you)")
    assert risk_models.revised_bethesda(build(profile(rel(R.MOTHER, ("colorectal_cancer", 72))))) == []


def test_insight_and_test_booking_follow():
    report = generate_insights(lynch_family())
    lynch = next(i for i in report.insights if i.rule_id == "lynch_criteria")
    assert lynch.level.value == "high" and "Amsterdam II" in lynch.summary
    from fhg.bookings import RECOMMENDED
    assert RECOMMENDED["lynch_criteria"] == ["genetic_counseling"]
    assert not any(i.rule_id == "lynch_criteria" for i in generate_insights(HealthProfile()).insights)


# --- API -------------------------------------------------------------------------------------------

@pytest.fixture
def api(tmp_path):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "r.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="admin-secret"), webhooks_in_background=False,
                                 webhook_sender=type("S", (), {"send": lambda *a: None})()))


def user(api):
    h = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    api.put("/v1/profile/demographics", headers=h, json={"sex": "female", "birth_date": "1985-06-01"})
    api.post("/v1/ingest/text", headers=h, json={"text": "My mother had colon cancer at 47. My maternal grandfather "
                                                         "had colon cancer at 66. My maternal aunt had uterine cancer at 55."})
    return h


def test_risk_endpoints_for_the_person(api):
    assert api.get("/v1/risk/canrisk", headers={"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
                   ).status_code == 409                                     # sex not set yet
    h = user(api)
    out = api.get("/v1/risk", headers=h).json()
    assert out["lynch"]["amsterdam_ii"]["met"] and out["lynch"]["suggests_evaluation"]
    assert out["pedigree"]["people"] == 4 and out["assessments"] == []
    r = api.get("/v1/risk/canrisk", headers=h)
    assert r.status_code == 200 and r.text.startswith("##CanRisk 2.0") and "attachment" in r.headers["content-disposition"]
    assert any(e["action"] == "risk.canrisk_export" for e in api.get("/v1/audit", headers=h).json())


def test_counselor_fetches_file_and_posts_figures(api):
    h = user(api)
    partner = api.post("/admin/partners", headers=ADMIN, json={"name": "GeneCounsel India", "kind": "genetic_counseling"}).json()
    key = {"X-API-Key": partner["api_key"]}
    clinic = {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}
    org = api.post("/v1/orgs", headers=clinic, json={"name": "Riverside"}).json()
    api.post("/v1/clinics", headers=h, json={"code": org["patient_code"], "display_name": "Priya Shah"})
    pref = api.get(f"/v1/orgs/{org['id']}/patients", headers=clinic).json()["patients"][0]["patient_ref"]
    ref = api.post(f"/v1/orgs/{org['id']}/patients/{pref}/referrals", headers=clinic,
                   json={"rule_id": "lynch_criteria", "status": "referred", "partner_id": partner["partner"]["id"]})
    assert ref.status_code == 200, ref.text
    rid = api.get("/v1/partner/referrals", headers=key).json()["referrals"][0]["referral_id"]
    f = api.get(f"/v1/partner/referrals/{rid}/canrisk", headers=key)
    assert f.status_code == 200 and f.text.startswith("##CanRisk 2.0") and "Priya" not in f.text
    other = api.post("/admin/partners", headers=ADMIN, json={"name": "Other", "kind": "lab"}).json()
    assert api.get(f"/v1/partner/referrals/{rid}/canrisk", headers={"X-API-Key": other["api_key"]}).status_code == 404
    body = {"model": "BOADICEA v6 (CanRisk)", "predictions": [
        {"outcome": "Breast cancer", "probability_percent": 9.1, "horizon": "next 10 years", "population_percent": 2.3}]}
    assert api.post(f"/v1/partner/referrals/{rid}/risk-assessment", headers=key, json=body).status_code == 201
    assert api.post(f"/v1/partner/referrals/{rid}/risk-assessment", headers=key,
                    json={**body, "predictions": [{**body["predictions"][0], "probability_percent": 140}]}).status_code == 422
    shared = api.get("/v1/risk", headers=h).json()["assessments"]
    assert shared[0]["partner_name"] == "GeneCounsel India" and shared[0]["predictions"][0]["probability_percent"] == 9.1
    assert any("risk assessment" in n["message"] for n in api.get("/v1/notifications", headers=h).json())
