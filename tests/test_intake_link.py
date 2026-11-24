import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fhg.api import Settings, create_app


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(
        db_path=str(tmp_path / "i.db"), encryption_key=Fernet.generate_key().decode(),
        public_url="https://app.example.org", ios_app_ids=("TEAM.com.example.familyhealthgraph",))))


def account(client):
    return {"Authorization": f"Bearer {client.post('/v1/users').json()['token']}"}


@pytest.fixture
def clinic(client):
    admin = account(client)
    org = client.post("/v1/orgs", json={"name": "Riverside Family Practice"}, headers=admin).json()
    return admin, org


def test_intake_url_public_lookup_and_pages(client, clinic):
    admin, org = clinic
    assert org["intake_url"] == f"https://app.example.org/c/{org['patient_code']}"

    assert client.get(f"/v1/public/clinics/{org['patient_code']}").json() == {
        "name": "Riverside Family Practice", "code": org["patient_code"], "lang": "hi"}
    assert client.get("/v1/public/clinics/NOPE-NOPE").status_code == 404
    assert client.get(f"/v1/public/clinics/{org['staff_code']}").status_code == 404   # staff code is not public

    page = client.get(f"/c/{org['patient_code']}")
    assert page.status_code == 200 and "Share with my clinic" in page.text
    assert client.get("/c/NOPE-NOPE").status_code == 404

    qr = client.get(f"/c/{org['patient_code']}/qr.svg")
    assert qr.headers["content-type"].startswith("image/svg+xml") and qr.text.lstrip().startswith("<svg")

    poster = client.get(f"/c/{org['patient_code']}/poster").text
    assert "Riverside Family Practice" in poster and org["intake_url"] in poster and org["patient_code"] in poster


def test_poster_escapes_clinic_name(client):
    admin = account(client)
    org = client.post("/v1/orgs", json={"name": "<script>alert(1)</script> Clinic"}, headers=admin).json()
    poster = client.get(f"/c/{org['patient_code']}/poster").text
    assert "<script>alert(1)" not in poster and "&lt;script&gt;" in poster


def test_joining_via_link_is_counted(client, clinic):
    admin, org = clinic
    via_link, via_code = account(client), account(client)
    client.post("/v1/ingest/text", json={"text": "My mother had breast cancer at 45."}, headers=via_link)
    r = client.post("/v1/clinics", headers=via_link,
                    json={"code": org["patient_code"], "display_name": "Ana Ruiz", "source": "link"})
    assert r.status_code == 201
    client.post("/v1/clinics", headers=via_code, json={"code": org["patient_code"], "display_name": "Sam Ortiz"})
    assert client.post("/v1/clinics", headers=via_code, json={
        "code": org["patient_code"], "display_name": "x y", "source": "spam"}).status_code == 422

    data = client.get(f"/v1/orgs/{org['id']}/patients", headers=admin).json()
    assert data["impact"]["joined_via_link"] == 1
    assert {p["display_name"]: p["joined_via"] for p in data["patients"]} == {"Ana Ruiz": "link", "Sam Ortiz": "code"}
    audit = client.get("/v1/audit", headers=via_link).json()
    assert any(a["action"] == "clinic.connected" and a["detail"].get("via") == "link" for a in audit)


def test_app_links_cover_intake_path(client):
    comps = client.get("/.well-known/apple-app-site-association").json()["applinks"]["details"][0]["components"]
    assert {"/": "/c/*", "comment": "Clinic intake links open in the app"} in comps


def test_staff_guide(client, clinic):
    admin, org = clinic
    guide = client.get(f"/c/{org['patient_code']}/staff-guide")
    assert guide.status_code == 200
    text = guide.text
    assert "Riverside Family Practice" in text and org["intake_url"] in text and "https://app.example.org/portal" in text
    assert "डॉक्टर से मिलने से पहले" in text                       # the Hindi reception script
    assert org["staff_code"] not in text                             # never the staff code
    assert client.get("/c/NOPE-NOPE/staff-guide").status_code == 404
    evil = client.post("/v1/orgs", json={"name": "<b>x</b> Clinic"}, headers=account(client)).json()
    assert "<b>x</b>" not in client.get(f"/c/{evil['patient_code']}/staff-guide").text


def test_intake_and_poster_have_hindi(client, clinic):
    admin, org = clinic
    page = client.get(f"/c/{org['patient_code']}").text
    assert '"hi"' in page and "मेरे क्लिनिक के साथ साझा करें" in page and 'id="lang"' in page
    poster = client.get(f"/c/{org['patient_code']}/poster").text
    assert "मुलाक़ात से पहले" in poster


def test_clinic_language_marathi(client, clinic):
    admin, org = clinic
    code = org["patient_code"]
    assert client.get(f"/v1/public/clinics/{code}").json()["lang"] == "hi"
    assert 'data-lang="hi"' in client.get(f"/c/{code}/poster").text
    stranger = account(client)
    assert client.put(f"/v1/orgs/{org['id']}/language", headers=stranger, json={"lang": "mr"}).status_code == 404
    assert client.put(f"/v1/orgs/{org['id']}/language", headers=admin, json={"lang": "xx"}).status_code == 422
    assert client.put(f"/v1/orgs/{org['id']}/language", headers=admin, json={"lang": "mr"}).json() == {"lang": "mr"}
    assert client.get(f"/v1/public/clinics/{code}").json()["lang"] == "mr"
    poster = client.get(f"/c/{code}/poster").text
    assert 'data-lang="mr"' in poster and "मराठीत लिहिले तरी चालेल" in poster and "Marathi is fine" in poster
    guide = client.get(f"/c/{code}/staff-guide").text
    assert 'data-lang="mr"' in guide and "Marathi is fine" in guide
    assert "मराठी" in client.get(f"/c/{code}").text and next(
        o for o in client.get("/v1/orgs", headers=admin).json() if o["id"] == org["id"])["lang"] == "mr"


def test_preview_names_conditions_in_the_readers_language(client):
    h = account(client)
    text = "माझ्या आईला 46 व्या वर्षी स्तनाचा कर्करोग झाला."
    r = client.post("/v1/ingest/text?preview=true&lang=mr", headers=h, json={"text": text}).json()
    assert r["parsed"]["family"][0]["conditions"][0]["display"] == "स्तनाचा कर्करोग"
    r = client.post("/v1/ingest/text?preview=true", headers=h, json={"text": text}).json()
    assert "display" not in r["parsed"]["family"][0]["conditions"][0]
