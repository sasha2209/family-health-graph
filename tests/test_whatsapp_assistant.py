"""The WhatsApp assistant: Indian languages, Hindi/Hinglish family history, save-by-reply, opt-in summaries."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_documents import FIX  # noqa: E402
from test_forwarding import FakeWhatsApp, account, api, wa, wa_payload, wa_post  # noqa: E402,F401

from fhg.i18n import MESSAGES, detect_script, normalize_family_text  # noqa: E402
from fhg.ingest.text import parse_family_history_text  # noqa: E402

PHONE = "919812345678"


def link(api, wa, h, phone=PHONE):
    code = api.post("/v1/inbound/whatsapp/code", headers=h).json()["code"]
    wa_post(api, wa_payload(phone, {"type": "text", "text": {"body": f"LINK {code}"}}))


def say(api, text, phone=PHONE):
    wa_post(api, wa_payload(phone, {"type": "text", "text": {"body": text}}))


def family(api, h):
    return {m["relationship"]: m for m in api.get("/v1/profile", headers=h).json()["family"]}


# --- language ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("mummy ko sugar hai, papa ko 52 mein heart attack hua", {"mother": [("type_2_diabetes", None)],
                                                             "father": [("coronary_artery_disease", 52)]}),
    ("Nani ko stan cancer tha 60 saal ki umar mein aur dadi ko BP hai",
     {"maternal_grandmother": [("breast_cancer", 60)], "paternal_grandmother": [("hypertension", None)]}),
    ("माँ को मधुमेह है और पिताजी को ५२ की उम्र में दिल का दौरा पड़ा",
     {"mother": [("type_2_diabetes", None)], "father": [("coronary_artery_disease", 52)]}),
    ("chacha ko lakwa hua tha 65 me", {"paternal_uncle": [("stroke", 65)]}),
    ("मेरी मौसी को कैंसर था", {"maternal_aunt": [("cancer_unspecified", None)]}),
])
def test_hindi_and_hinglish_family_history(text, expected):
    f = parse_family_history_text(text)
    assert {m.relationship.value: [(c.category, c.onset_age) for c in m.conditions] for m in f.family} == expected


def test_english_is_untouched():
    for text in ("My mother had breast cancer at 46. My blood sugar is fine.", "Dada Bhai is my uncle's name"):
        assert normalize_family_text(text) == text


def test_script_detection_and_messages_complete():
    assert detect_script("माँ को मधुमेह है") == "hi"
    assert detect_script("আমার মায়ের ডায়াবেটিস") == "bn"
    assert detect_script("அம்மாவுக்கு நீரிழிவு") == "ta"
    assert detect_script("అమ్మకు మధుమేహం") == "te"
    assert detect_script("mummy ko sugar") is None
    for key, table in MESSAGES.items():
        assert set(table) == {"en", "hi", "bn", "ta", "te", "mr"}, key


# --- the assistant ----------------------------------------------------------------------------------

def test_type_family_history_in_hinglish_and_save_with_1(api, wa):
    h = account(api)
    link(api, wa, h)
    say(api, "mummy ko sugar hai, papa ko 52 mein heart attack hua")
    assert wa.sent[-1][1].startswith("Thanks. Reply 1 to save")          # no health details without consent
    assert api.get("/v1/profile", headers=h).json()["family"] == []      # nothing saved yet
    say(api, "1")
    assert wa.sent[-1][1].startswith("Saved to your record")
    fam = family(api, h)
    assert fam["mother"]["conditions"][0]["category"] == "type_2_diabetes"
    assert fam["father"]["conditions"][0]["onset_age"] == 52
    say(api, "1")
    assert "nothing waiting" in wa.sent[-1][1]
    say(api, "the weather is nice today")
    assert "didn't catch" in wa.sent[-1][1]
    # Without consent, nothing the user's record contains is echoed back.
    assert not any("Type 2 diabetes" in body or "heart attack" in body.lower() for _, body in wa.sent)


def test_with_consent_a_photo_is_summarised_and_saved_for_mother(api, wa):
    h = account(api)
    link(api, wa, h)
    api.post("/v1/consents", headers=h, json={"scope": "whatsapp_summaries", "granted": True})
    wa.media["m1"] = (FIX / "lab_report.jpg").read_bytes()
    wa_post(api, wa_payload(PHONE, {"type": "image", "image": {"id": "m1", "mime_type": "image/jpeg"}}))
    reply = wa.sent[-1][1]
    assert reply.startswith("Read your lab report (14 Mar 2026)")
    assert "Hemoglobin A1c: 7.8 % (diabetes range)" in reply and "Reply 1 to save" in reply
    say(api, "2")
    mother = family(api, h)["mother"]
    assert any(o["code"] == "hba1c" and o["value"] == 7.8 for o in mother["observations"])
    assert api.get("/v1/documents", headers=h).json()[0]["status"] == "saved"

    say(api, "SUMMARY")
    assert wa.sent[-1][1].startswith("Your action items:") or "Nothing needs attention" in wa.sent[-1][1]


def test_summary_needs_consent_and_typed_echo_with_consent(api, wa):
    h = account(api)
    link(api, wa, h)
    say(api, "summary")
    assert "WhatsApp summaries" in wa.sent[-1][1]
    api.post("/v1/consents", headers=h, json={"scope": "whatsapp_summaries", "granted": True})
    say(api, "Nani ko stan cancer tha 60 saal ki umar mein")
    assert "Maternal grandmother: Breast cancer (at 60)" in wa.sent[-1][1]


def test_language_follows_the_user(api, wa):
    h = account(api)
    link(api, wa, h)
    assert wa.sent[-1][1].startswith("Your WhatsApp is now connected")
    say(api, "माँ को मधुमेह है")
    assert wa.sent[-1][1].startswith("धन्यवाद")                              # replies in Hindi from now on
    say(api, "help")
    assert "पर्चे" in wa.sent[-1][1]
    say(api, "LANG ta")
    assert wa.sent[-1][1] == "சரி, நான் தமிழில் பதிலளிப்பேன்."
    wa_post(api, wa_payload(PHONE, {"type": "audio", "audio": {"id": "a1"}}))
    assert wa.sent[-1][1].startswith("குரல்")
    say(api, "LANG en")
    say(api, "STOP")
    assert "disconnected" in wa.sent[-1][1]
    assert api.get("/v1/inbound", headers=h).json()["whatsapp"]["linked"] is False
    say(api, "hello")
    assert "isn't connected" in wa.sent[-1][1]


def test_ocr_reads_hindi_when_installed():
    from fhg.documents.ocr import ocr_languages, tesseract_available
    if not tesseract_available():
        pytest.skip("tesseract not installed")
    assert ocr_languages().startswith("eng")
