"""The pilot as an ethics-approved study: information sheet, versioned informed consent, withdrawal, and a pilot
report that counts only participants."""
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg import study
from fhg.api import Settings, create_app

ADMIN = {"X-Admin-Key": "k"}


def make(tmp_path, **kw):
    return TestClient(create_app(Settings(db_path=str(tmp_path / "s.db"), encryption_key=Fernet.generate_key().decode(),
                                          admin_key="k", **kw)))


def account(api):
    return {"Authorization": f"Bearer {api.post('/v1/users').json()['token']}"}


def test_information_sheet_in_every_language():
    en = study.info("en", "v1")
    for lang in study.LANGS:
        s = study.info(lang, "v1", "Dr A. Kulkarni", "+91 20 0000 0000")
        assert len(s["sections"]) == len(en["sections"]) and len(s["statements"]) == len(en["statements"])
        assert s["contacts"][0]["name"] == "Dr A. Kulkarni" and s["version"] == "v1"
    assert study.info("xx", "v1")["lang"] == "en"


def test_off_by_default(tmp_path):
    api = make(tmp_path)
    h = account(api)
    assert api.get("/v1/study", headers=h).json()["enabled"] is False
    assert api.post("/v1/study/consent", headers=h, json={"version": "draft-1", "agreed": True}).status_code == 404
    assert api.get("/admin/pilot-report", headers=ADMIN).json()["study"]["consent_required"] is False
    assert api.get("/study").status_code == 200        # the sheet can be printed for the committee before it's on


def test_consent_withdraw_and_only_participants_counted(tmp_path):
    api = make(tmp_path, study=True, study_version="IEC-2026-14 v2", study_investigator="Dr A. Kulkarni")
    yes, no, later = account(api), account(api), account(api)
    for h in (yes, no, later):
        api.post("/v1/ingest/text", headers=h, json={"text": "My mother had breast cancer at 44."})

    s = api.get("/v1/study?lang=mr", headers=yes).json()
    assert s["enabled"] and s["status"] == "not_asked" and s["lang"] == "mr" and s["version"] == "IEC-2026-14 v2"
    assert api.get("/v1/surveys", headers=yes).json() == []                  # not asked until they take part

    # Consent must be to the current version, with every statement agreed.
    assert api.post("/v1/study/consent", headers=yes, json={"version": "draft-1", "agreed": True}).status_code == 409
    assert api.post("/v1/study/consent", headers=yes, json={"version": s["version"], "agreed": False}).status_code == 422
    s = api.post("/v1/study/consent", headers=yes, json={"version": s["version"], "agreed": True}).json()
    assert s["status"] == "taking_part" and s["consented_version"] == "IEC-2026-14 v2"
    assert api.get("/v1/surveys", headers=yes).json()                        # now asked
    assert api.post("/v1/study/decline", headers=no).json()["status"] == "declined"
    api.post("/v1/study/consent", headers=later, json={"version": s["version"], "agreed": True})

    r = api.get("/admin/pilot-report", headers=ADMIN).json()
    assert r["families"]["total"] == 2
    assert r["study"] == {"consent_required": True, "version": "IEC-2026-14 v2", "active": 2, "withdrawn": 0, "declined": 1}

    w = api.delete("/v1/study/consent", headers=later).json()
    assert w["status"] == "withdrew" and w["withdrawn_at"]
    r = api.get("/admin/pilot-report", headers=ADMIN).json()
    assert r["families"]["total"] == 1 and r["study"]["withdrawn"] == 1
    assert api.get("/v1/profile", headers=later).json()["family"]           # their record is untouched
    csv = api.get("/admin/pilot-report?format=csv", headers=ADMIN).text
    assert "IEC-2026-14 v2" in csv and "Participants" in csv


def test_under_18_cannot_consent(tmp_path):
    api = make(tmp_path, study=True)
    h = account(api)
    api.put("/v1/profile/demographics", headers=h, json={"birth_date": "2012-01-01", "sex": "female"})
    assert api.post("/v1/study/consent", headers=h, json={"version": "draft-1", "agreed": True}).status_code == 403


@pytest.mark.parametrize("lang", study.LANGS)
def test_public_sheet_and_printable_page(tmp_path, lang):
    api = make(tmp_path, study=True)
    s = api.get(f"/v1/public/study?lang={lang}").json()
    assert s["enabled"] and s["lang"] == lang and s["statements"]
    page = api.get("/study").text
    assert 'id="statements"' in page and "/v1/public/study" in page
