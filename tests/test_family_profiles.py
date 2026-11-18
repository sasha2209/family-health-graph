"""Managed family profiles: a relative's own documents build their record."""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_documents import FIX, account, api, fake_ai, text_pdf, upload  # noqa: F401,E402  (fixtures)


def save(api, h, doc, **body):
    e = doc["extraction"]
    payload = {"doc_type": e["doc_type"], "doc_date": e["doc_date"], "conditions": e["conditions"],
               "medications": e["medications"], "observations": e["observations"], "family": e["family"]} | body
    r = api.post(f"/v1/documents/{doc['id']}/save", headers=h, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def member(api, h, relationship, linked=False):
    family = api.get(f"/v1/profile?include_linked={str(linked).lower()}", headers=h).json()["family"]
    return next(m for m in family if m["relationship"] == relationship)


def test_parents_lab_report_builds_their_profile_and_drives_insights(api):
    h = account(api)
    lab = (FIX / "lab_report.txt").read_text().replace("162   H", "212   H")   # mother's LDL 212
    doc = upload(api, h, text_pdf(lab.splitlines())).json()
    r = save(api, h, doc, subject="mother", relative_age=62)
    mom = member(api, h, "mother")
    assert mom["age"] == 62 and r["document"]["subject_member_id"] == mom["id"]
    ldl = next(o for o in mom["observations"] if o["code"] == "ldl_cholesterol")
    assert ldl["value"] == 212 and ldl["effective_date"] == "2026-03-14"
    assert api.get("/v1/profile", headers=h).json()["observations"] == []      # not on the user's own record

    detail = api.get(f"/v1/family/{mom['id']}", headers=h).json()
    assert detail["degree"] == 1 and [d["id"] for d in detail["documents"]] == [doc["id"]]

    fh = next(i for i in api.get("/v1/insights", headers=h).json()["insights"]
              if i["rule_id"] == "familial_hypercholesterolemia")
    assert "Mother: LDL cholesterol 212 mg/dL (from their lab report)" in fh["evidence"]

    # A later report for the same parent merges into the same profile; a newer prescription updates dosing.
    rx = upload(api, h, text_pdf(["Date: 01/05/2026", "Rx", "Tab. Metformin 500 mg 1-0-1 after food"])).json()
    save(api, h, rx, subject="mother")
    rx2 = upload(api, h, text_pdf(["Date: 01/08/2026", "Rx", "Tab. Metformin 500 mg 1-1-1 after food"])).json()
    save(api, h, rx2, subject="mother")
    mom = member(api, h, "mother")
    assert [(m["name"], m["dosage"]) for m in mom["medications"]] == [("Metformin 500 mg", "1-1-1, after food")]
    assert len(api.get(f"/v1/family/{mom['id']}", headers=h).json()["documents"]) == 3


def test_choose_which_sister(api):
    h = account(api)
    for name in ("Asha", "Meera"):
        api.post("/v1/family", headers=h, json={"relationship": "sister", "name": name})
    sisters = {m["name"]: m["id"] for m in api.get("/v1/profile", headers=h).json()["family"]}
    doc = upload(api, h, text_pdf(["Diagnosis: Hypertension"])).json()
    save(api, h, doc, subject="sister", member_id=sisters["Meera"])
    fam = {m["name"]: m for m in api.get("/v1/profile", headers=h).json()["family"]}
    assert [c["category"] for c in fam["Meera"]["conditions"]] == ["hypertension"] and fam["Asha"]["conditions"] == []
    # member_id must belong to a relative with that relationship.
    doc2 = upload(api, h, text_pdf(["Diagnosis: Hypertension"])).json()
    assert api.post(f"/v1/documents/{doc2['id']}/save", headers=h,
                    json={"subject": "mother", "member_id": sisters["Asha"]}).status_code == 422


def test_edit_relative_and_remove_items(api):
    h, other = account(api), account(api)
    doc = upload(api, h, text_pdf(["Diagnosis: Hypertension", "Rx", "Tab. Amlodipine 5 mg 1-0-0"])).json()
    save(api, h, doc, subject="father")
    dad = member(api, h, "father")
    r = api.patch(f"/v1/family/{dad['id']}", headers=h, json={"name": "Raj", "age": 70, "deceased": False})
    assert r.status_code == 200 and (r.json()["name"], r.json()["age"]) == ("Raj", 70)
    assert api.patch(f"/v1/family/{dad['id']}", headers=h, json={"age": 300}).status_code == 422
    med_id = dad["medications"][0]["id"]
    assert api.delete(f"/v1/family/{dad['id']}/items/{med_id}", headers=h).status_code == 204
    assert member(api, h, "father")["medications"] == []
    assert api.delete(f"/v1/family/{dad['id']}/items/{med_id}", headers=h).status_code == 404
    assert api.get(f"/v1/family/{dad['id']}", headers=other).status_code == 404
    assert api.patch(f"/v1/family/{dad['id']}", headers=other, json={"age": 1}).status_code == 404


def test_managed_records_are_not_shared_with_linked_relatives(api):
    """A sibling who links and sees the family tree gets Mom's diagnoses, never her medicines or labs."""
    h = account(api)
    doc = upload(api, h, text_pdf(["Diagnosis: Hypertension", "Rx", "Tab. Amlodipine 5 mg 1-0-0",
                                   "LDL Cholesterol 201 mg/dL"])).json()
    save(api, h, doc, subject="mother")
    inv = api.post("/v1/invitations", headers=h, json={"relationship": "sister", "share_level": "conditions_and_tree"}).json()
    sis = {"Authorization": "Bearer " + api.post(f"/v1/invites/{inv['token']}/accept", json={}).json()["token"]}
    mom_seen_by_sister = member(api, sis, "mother", linked=True)
    assert [c["category"] for c in mom_seen_by_sister["conditions"]] == ["hypertension"]
    assert mom_seen_by_sister["medications"] == [] and mom_seen_by_sister["observations"] == []
