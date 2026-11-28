"""The pilot as a research study: participant information and informed consent (docs/ETHICS.md).

When the pilot's results will be published, an Institutional Ethics Committee (IEC) must approve the study first, and
each participant gives informed consent to it, separately from using the app. This module holds the participant
information sheet in English, Hindi and Marathi, written to the ICMR guidelines' headings. The IEC will ask for
changes. The approved wording replaces this text, and FHG_STUDY_VERSION names the approved version, so each consent
records exactly what the person agreed to.

With FHG_STUDY=on:
* the app and the clinic intake page offer the study, and record consent with its version;
* the pilot report counts only families who consented (and haven't withdrawn), and the optional survey is only
  asked of them;
* people withdraw in the app at any time. Their care and their record are unaffected; from then on they aren't
  counted.
"""
from __future__ import annotations

from typing import Optional

CONSENT_STUDY = "pilot_study"
LANGS = ("en", "hi", "mr")

INFO: dict[str, dict] = {
    "en": {
        "title": "Taking part in the Family Health Graph pilot study",
        "summary": "Your clinic is testing whether Family Health Graph helps families record their health history and "
                   "get the right check-ups. You can use the app either way: taking part in the study is your choice.",
        "sections": [
            ("Why is this study being done?",
             "To learn whether recording family health history in this app helps families and their doctors notice "
             "when earlier screening or a check-up may be useful, and whether families find it easy to use."),
            ("What happens if I take part?",
             "You use the app as usual. During the pilot (about three months) we count how families use it, for "
             "example how many relatives were added and whether a suggested test was done, and we may ask you two "
             "short optional questions. There are no extra visits, tests or samples."),
            ("What information is used?",
             "Only counts across all the families taking part. Your name, phone number and anything else that "
             "identifies you are never used for the study, and groups smaller than five are never reported. Your "
             "health record stays encrypted and is used only for your own care and what you choose to share."),
            ("Are there any risks?",
             "There are no physical risks. A health suggestion in the app can be worrying: it is not a diagnosis, "
             "and you can talk to your clinic about it. As with any app there is a small risk to privacy; your data "
             "is encrypted and every access is recorded."),
            ("Are there any benefits?",
             "You may learn about check-ups that suit your family's history, and the study may help other families. "
             "There is no payment and no cost to you."),
            ("Do I have to take part?",
             "No. Taking part is voluntary. Saying no, or stopping later, will not change your care at the clinic in "
             "any way. You can stop at any time in the app (Settings → Pilot study). From then on you are not "
             "counted, and you can also delete your account and everything in it."),
        ],
        "statements": [
            "I have read this information (or had it read to me) and could ask questions about it.",
            "I understand that taking part is voluntary and that I can stop at any time without my care being "
            "affected.",
            "I agree that counts of how I use the app, without my name or anything that identifies me, can be used "
            "for this study and its reports.",
        ],
        "contact": "Questions about the study",
        "investigator": "Study lead",
        "committee": "Ethics committee",
        "version": "Information sheet version",
        "agree": "I agree to take part",
        "decline": "Not now",
        "withdraw": "Stop taking part",
    },
    "hi": {
        "title": "Family Health Graph पायलट अध्ययन में भाग लेना",
        "summary": "आपका क्लिनिक यह जाँच रहा है कि क्या Family Health Graph परिवारों को अपना स्वास्थ्य इतिहास दर्ज करने और सही "
                   "जाँच कराने में मदद करता है। आप ऐप दोनों तरह से इस्तेमाल कर सकते हैं: अध्ययन में भाग लेना आपकी मर्ज़ी है।",
        "sections": [
            ("यह अध्ययन क्यों किया जा रहा है?",
             "यह जानने के लिए कि क्या इस ऐप में पारिवारिक स्वास्थ्य इतिहास दर्ज करने से परिवारों और उनके डॉक्टरों को पता चलता है कि "
             "कब जल्दी जाँच या चेक-अप फ़ायदेमंद हो सकता है, और क्या परिवारों को ऐप इस्तेमाल करना आसान लगता है।"),
            ("भाग लेने पर क्या होगा?",
             "आप ऐप हमेशा की तरह इस्तेमाल करेंगे। पायलट के दौरान (लगभग तीन महीने) हम गिनेंगे कि परिवार इसे कैसे इस्तेमाल करते हैं, "
             "जैसे कितने रिश्तेदार जोड़े गए और क्या सुझाई गई जाँच हुई, और आपसे दो छोटे वैकल्पिक सवाल पूछ सकते हैं। कोई अतिरिक्त "
             "मुलाक़ात, जाँच या सैंपल नहीं है।"),
            ("कौन-सी जानकारी इस्तेमाल होगी?",
             "सिर्फ़ भाग लेने वाले सभी परिवारों की मिली-जुली गिनती। आपका नाम, फ़ोन नंबर या आपकी पहचान बताने वाली कोई भी बात अध्ययन "
             "में कभी इस्तेमाल नहीं होती, और पाँच से छोटे समूह कभी नहीं बताए जाते। आपका स्वास्थ्य रिकॉर्ड एन्क्रिप्टेड रहता है और "
             "सिर्फ़ आपकी अपनी देखभाल और आपकी चुनी हुई साझेदारी के लिए इस्तेमाल होता है।"),
            ("क्या कोई जोखिम है?",
             "कोई शारीरिक जोखिम नहीं है। ऐप की कोई स्वास्थ्य सलाह चिंता में डाल सकती है: यह निदान नहीं है, और आप इसके बारे में अपने "
             "क्लिनिक से बात कर सकते हैं। किसी भी ऐप की तरह निजता को थोड़ा जोखिम है; आपका डेटा एन्क्रिप्टेड है और हर पहुँच दर्ज "
             "होती है।"),
            ("क्या कोई फ़ायदा है?",
             "आपको अपने परिवार के इतिहास के हिसाब से सही जाँचों के बारे में पता चल सकता है, और यह अध्ययन दूसरे परिवारों की मदद कर "
             "सकता है। इसके लिए कोई भुगतान नहीं है और आपका कोई ख़र्च नहीं है।"),
            ("क्या भाग लेना ज़रूरी है?",
             "नहीं। भाग लेना आपकी मर्ज़ी है। मना करने से, या बाद में छोड़ने से, क्लिनिक में आपकी देखभाल पर कोई असर नहीं पड़ेगा। आप "
             "कभी भी ऐप में (Settings → पायलट अध्ययन) भाग लेना बंद कर सकते हैं। उसके बाद आपको गिना नहीं जाएगा, और आप अपना खाता "
             "और उसमें सब कुछ मिटा भी सकते हैं।"),
        ],
        "statements": [
            "मैंने यह जानकारी पढ़ी है (या मुझे पढ़कर सुनाई गई है) और इसके बारे में सवाल पूछ सका/सकी।",
            "मैं समझता/समझती हूँ कि भाग लेना मेरी मर्ज़ी है और मैं कभी भी, अपनी देखभाल पर असर डाले बिना, छोड़ सकता/सकती हूँ।",
            "मैं सहमत हूँ कि मेरे ऐप इस्तेमाल की गिनती, मेरे नाम या मेरी पहचान बताने वाली किसी बात के बिना, इस अध्ययन और इसकी "
            "रिपोर्टों में इस्तेमाल हो सकती है।",
        ],
        "contact": "अध्ययन के बारे में सवाल",
        "investigator": "अध्ययन प्रमुख",
        "committee": "आचार समिति (Ethics committee)",
        "version": "सूचना पत्र संस्करण",
        "agree": "मैं भाग लेने के लिए सहमत हूँ",
        "decline": "अभी नहीं",
        "withdraw": "भाग लेना बंद करें",
    },
    "mr": {
        "title": "Family Health Graph पायलट अभ्यासात सहभागी होणे",
        "summary": "Family Health Graph मुळे कुटुंबांना त्यांचा आरोग्य इतिहास नोंदवण्यास आणि योग्य तपासण्या करून घेण्यास मदत होते "
                   "का, हे तुमचे क्लिनिक तपासत आहे. तुम्ही अ‍ॅप दोन्ही प्रकारे वापरू शकता: अभ्यासात सहभागी होणे ही तुमची निवड आहे.",
        "sections": [
            ("हा अभ्यास का केला जात आहे?",
             "या अ‍ॅपमध्ये कौटुंबिक आरोग्य इतिहास नोंदवल्याने कुटुंबांना आणि त्यांच्या डॉक्टरांना लवकर तपासणी किंवा चेक-अप केव्हा "
             "उपयोगी ठरेल हे लक्षात येते का, आणि कुटुंबांना अ‍ॅप वापरणे सोपे वाटते का, हे जाणून घेण्यासाठी."),
            ("सहभागी झाल्यास काय होईल?",
             "तुम्ही अ‍ॅप नेहमीप्रमाणे वापराल. पायलटच्या काळात (साधारण तीन महिने) कुटुंबे ते कसे वापरतात हे आम्ही मोजू, उदा. किती "
             "नातेवाईक जोडले आणि सुचवलेली चाचणी झाली का, आणि तुम्हाला दोन छोटे ऐच्छिक प्रश्न विचारू शकतो. कोणतीही जादा भेट, चाचणी "
             "किंवा नमुना नाही."),
            ("कोणती माहिती वापरली जाते?",
             "फक्त सहभागी सर्व कुटुंबांची एकत्रित आकडेवारी. तुमचे नाव, फोन नंबर किंवा तुमची ओळख पटवणारे काहीही अभ्यासासाठी कधीही "
             "वापरले जात नाही, आणि पाचपेक्षा लहान गट कधीही दाखवले जात नाहीत. तुमची आरोग्य नोंद एन्क्रिप्टेड राहते आणि फक्त तुमच्या "
             "स्वतःच्या काळजीसाठी आणि तुम्ही निवडलेल्या शेअरिंगसाठी वापरली जाते."),
            ("काही धोका आहे का?",
             "कोणताही शारीरिक धोका नाही. अ‍ॅपमधील एखादा आरोग्य सल्ला काळजी वाढवू शकतो: तो निदान नाही, आणि तुम्ही त्याबद्दल तुमच्या "
             "क्लिनिकशी बोलू शकता. कोणत्याही अ‍ॅपप्रमाणे गोपनीयतेला थोडा धोका असतो; तुमचा डेटा एन्क्रिप्टेड असतो आणि तो प्रत्येक वेळी "
             "कोणी पाहिला याची नोंद होते."),
            ("काही फायदा आहे का?",
             "तुमच्या कुटुंबाच्या इतिहासानुसार योग्य तपासण्यांबद्दल तुम्हाला कळू शकते, आणि हा अभ्यास इतर कुटुंबांना मदत करू शकतो. "
             "यासाठी कोणताही मोबदला नाही आणि तुम्हाला कोणताही खर्च नाही."),
            ("सहभागी होणे आवश्यक आहे का?",
             "नाही. सहभागी होणे ऐच्छिक आहे. नकार दिल्याने, किंवा नंतर थांबवल्याने, क्लिनिकमधील तुमच्या उपचारांवर कोणताही परिणाम "
             "होणार नाही. तुम्ही अ‍ॅपमध्ये (सेटिंग्ज → पायलट अभ्यास) कधीही थांबवू शकता. त्यानंतर तुम्हाला मोजले जाणार नाही, आणि "
             "तुम्ही तुमचे खाते आणि त्यातील सर्व काही हटवूही शकता."),
        ],
        "statements": [
            "मी ही माहिती वाचली आहे (किंवा मला वाचून दाखवली आहे) आणि तिच्याबद्दल प्रश्न विचारू शकलो/शकले.",
            "सहभागी होणे ऐच्छिक आहे आणि माझ्या उपचारांवर परिणाम न होता मी कधीही थांबवू शकतो/शकते, हे मला समजले आहे.",
            "माझ्या अ‍ॅप वापराची आकडेवारी, माझ्या नावाशिवाय किंवा माझी ओळख पटवणाऱ्या कशाशिवाय, या अभ्यासासाठी आणि त्याच्या "
            "अहवालांसाठी वापरली जाऊ शकते, याला माझी संमती आहे.",
        ],
        "contact": "अभ्यासाबद्दल प्रश्न",
        "investigator": "अभ्यास प्रमुख",
        "committee": "नैतिकता समिती (Ethics committee)",
        "version": "माहिती पत्रक आवृत्ती",
        "agree": "मी सहभागी होण्यास संमती देतो/देते",
        "decline": "आत्ता नाही",
        "withdraw": "सहभाग थांबवा",
    },
}


def info(lang: str, version: str, investigator: Optional[str] = None, investigator_contact: Optional[str] = None,
         committee: Optional[str] = None, committee_contact: Optional[str] = None) -> dict:
    """The participant information sheet and consent statements, in ``lang`` (English if not available)."""
    lang = lang if lang in INFO else "en"
    t = INFO[lang]
    contacts = [{"role": t["investigator"], "name": investigator, "contact": investigator_contact},
                {"role": t["committee"], "name": committee, "contact": committee_contact}]
    return {
        "lang": lang, "available_languages": list(LANGS), "version": version, "title": t["title"],
        "summary": t["summary"], "sections": [{"heading": h, "text": x} for h, x in t["sections"]],
        "statements": t["statements"], "contact_heading": t["contact"], "contacts": contacts,
        "version_label": t["version"],
        "buttons": {"agree": t["agree"], "decline": t["decline"], "withdraw": t["withdraw"]},
    }
