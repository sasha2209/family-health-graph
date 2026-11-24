"""Privacy rights under India's Digital Personal Data Protection Act, 2023 (DPDP Act).

What the app does for each obligation (see docs/TRUST_AND_COMPLIANCE.md for the full map):

* Notice (s.5): ``notice()``, in English or Hindi, shown before any data is collected and available any time.
* Consent and withdrawal (s.6): every optional use is a separate consent that can be withdrawn as easily as given.
* A summary of what is processed and who it is shared with (s.11): ``summary()``.
* Correction and erasure (s.12): edit anything in the app; delete the account erases everything, and partners who
  received data are told to erase it too.
* Grievance redressal (s.13): ``POST /v1/privacy/grievances``, answered within the configured period.
* Nomination (s.14): a nominee who can exercise these rights on the person's death or incapacity.
* Children (s.9): account holders under 18 can't turn on sharing with partners, research or AI processing until
  verifiable parental consent is in place.
* Breaches (s.8(6)): a breach register and notices to every affected person (``/admin/breaches``).

The DPDP Rules, 2025 set the detailed timelines and formats. They couldn't be checked from the build environment, so
the periods here are configuration (``FHG_GRIEVANCE_DAYS``) and must be set from the notified Rules before go-live.
"""
from __future__ import annotations

from typing import Optional

from .models import HealthProfile

ADULT_AGE = 18

DATA_CATEGORIES = {
    "en": [
        ("Your health record", "conditions, medicines, test results, date of birth and sex"),
        ("Your family's health history", "relatives' diagnoses and ages, and records you keep for relatives you look after"),
        ("Documents", "photos and PDFs you upload or forward, and what was read from them"),
        ("Contact details", "email or phone used to sign in; address and phone you give a lab for a home visit"),
        ("Activity", "a log of who accessed your record and when, and the consents you gave"),
    ],
    "hi": [
        ("आपका स्वास्थ्य रिकॉर्ड", "बीमारियाँ, दवाइयाँ, जाँच के नतीजे, जन्म तिथि और लिंग"),
        ("आपके परिवार का स्वास्थ्य इतिहास", "रिश्तेदारों की बीमारियाँ और उम्र, और जिनकी आप देखभाल करते हैं उनके रिकॉर्ड"),
        ("दस्तावेज़", "आपके द्वारा भेजी गई फ़ोटो और PDF, और उनसे पढ़ी गई जानकारी"),
        ("संपर्क विवरण", "साइन-इन के लिए ईमेल या फ़ोन; घर पर जाँच के लिए लैब को दिया गया पता और फ़ोन"),
        ("गतिविधि", "किसने आपका रिकॉर्ड कब देखा, और आपकी दी गई सहमतियों का लॉग"),
    ],
}

PURPOSES = {
    "en": [
        "Show you preventive-care insights based on your own and your family's history",
        "Read the documents you add and put the results in your record",
        "Share with the people and services you choose: relatives, your clinic, a lab or counselor, apps you connect",
        "Send reminders you turned on (tests, medicines)",
        "Keep your account secure and keep a record of access",
        "Count, across all families and never individually, how the pilot is going (including any survey answers you give)",
    ],
    "hi": [
        "आपके और आपके परिवार के इतिहास के आधार पर बचाव संबंधी सलाह दिखाना",
        "आपके जोड़े गए दस्तावेज़ पढ़कर नतीजे आपके रिकॉर्ड में डालना",
        "आपकी चुनी हुई जगहों से साझा करना: रिश्तेदार, आपका क्लिनिक, लैब या काउंसलर, जोड़े गए ऐप",
        "आपके चालू किए गए रिमाइंडर भेजना (जाँच, दवाइयाँ)",
        "आपका खाता सुरक्षित रखना और पहुँच का रिकॉर्ड रखना",
        "सभी परिवारों को मिलाकर, कभी किसी एक के बारे में नहीं, यह गिनना कि पायलट कैसा चल रहा है (आपके दिए सर्वे जवाबों सहित)",
    ],
}

RIGHTS = {
    "en": [
        ("See what we hold and who it was shared with", "Settings → Your privacy rights"),
        ("Correct or complete it", "edit any item in the app"),
        ("Withdraw any consent", "Settings; it takes effect immediately"),
        ("Erase everything", "Settings → Delete account; partners who received data are told to erase it"),
        ("Nominate someone", "to exercise these rights if you die or can't"),
        ("Raise a grievance", "Settings → Your privacy rights → Raise a concern"),
        ("Complain to the Data Protection Board of India", "if you're not satisfied with our answer"),
    ],
    "hi": [
        ("देखें कि हमारे पास क्या है और किसके साथ साझा हुआ", "सेटिंग्स → Your privacy rights"),
        ("सुधारें या पूरा करें", "ऐप में कोई भी जानकारी बदलें"),
        ("कोई भी सहमति वापस लें", "सेटिंग्स में; तुरंत लागू होती है"),
        ("सब कुछ मिटाएँ", "सेटिंग्स → खाता हटाएँ; जिन साझेदारों को डेटा मिला उन्हें भी मिटाने को कहा जाता है"),
        ("किसी को नामित करें", "जो आपकी मृत्यु या असमर्थता पर ये अधिकार इस्तेमाल कर सके"),
        ("शिकायत दर्ज करें", "सेटिंग्स → Your privacy rights → Raise a concern"),
        ("भारतीय डेटा संरक्षण बोर्ड से शिकायत करें", "अगर आप हमारे जवाब से संतुष्ट नहीं हैं"),
    ],
}

HEADINGS = {
    "en": {"title": "How we use your information", "data": "What we collect", "purposes": "Why",
           "rights": "Your rights", "contact": "Questions or complaints", "never": (
               "We never sell your data, never show ads, and never share with anyone you haven't chosen. Health data is "
               "encrypted, and every access is logged.")},
    "hi": {"title": "हम आपकी जानकारी का उपयोग कैसे करते हैं", "data": "हम क्या जानकारी लेते हैं", "purposes": "क्यों",
           "rights": "आपके अधिकार", "contact": "प्रश्न या शिकायत", "never": (
               "हम आपका डेटा कभी नहीं बेचते, विज्ञापन नहीं दिखाते, और आपकी अनुमति के बिना किसी से साझा नहीं करते। "
               "स्वास्थ्य डेटा एन्क्रिप्टेड है और हर पहुँच दर्ज होती है।")},
}


def notice(lang: str, controller: str, officer_name: Optional[str], officer_email: Optional[str],
           grievance_days: int) -> dict:
    lang = lang if lang in HEADINGS else "en"
    h = HEADINGS[lang]
    return {
        "lang": lang, "available_languages": sorted(HEADINGS), "title": h["title"], "controller": controller,
        "summary": h["never"],
        "sections": [
            {"heading": h["data"], "items": [{"title": t, "detail": d} for t, d in DATA_CATEGORIES[lang]]},
            {"heading": h["purposes"], "items": [{"title": p} for p in PURPOSES[lang]]},
            {"heading": h["rights"], "items": [{"title": t, "detail": d} for t, d in RIGHTS[lang]]},
        ],
        "contact": {"heading": h["contact"], "name": officer_name, "email": officer_email,
                    "response_days": grievance_days},
    }


def age(profile: HealthProfile) -> Optional[int]:
    return profile.age()


def is_minor(profile: HealthProfile) -> bool:
    a = profile.age()
    return a is not None and a < ADULT_AGE


def held(profile: HealthProfile, documents: int) -> list[dict]:
    """Counts per data category, for the 'what we hold' summary."""
    managed = sum(len(m.medications) + len(m.observations) for m in profile.family)
    return [
        {"category": "Your health record", "count": len(profile.conditions) + len(profile.medications)
         + len(profile.observations), "detail": f"{len(profile.conditions)} conditions, {len(profile.medications)} "
         f"medicines, {len(profile.observations)} test results"},
        {"category": "Your family's health history", "count": len(profile.family),
         "detail": f"{len(profile.family)} relatives, {sum(len(m.conditions) for m in profile.family)} of their "
                   f"diagnoses, {managed} medicines and results you keep for them"},
        {"category": "Documents", "count": documents, "detail": f"{documents} uploaded or forwarded"},
    ]
