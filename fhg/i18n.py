"""Indian languages: detect the script, turn Hindi / Hinglish family history into the English the parser
reads, and the WhatsApp assistant's messages in six languages.

Most Indian families describe health in Hindi, a regional language, or Hinglish ("mummy ko sugar hai, papa ko
52 mein heart attack hua"). The normaliser maps kinship terms (nani = mother's mother, chacha = father's brother,
etc.), common condition words (sugar = diabetes, BP = high blood pressure) and age phrases onto English, then the
existing family-history parser does the rest. Ambiguous words are left alone (Latin "mama" can mean mother or
maternal uncle, so only Devanagari मामा is mapped).

Messages other than English are drafts and should be reviewed by native speakers before launch.
"""
from __future__ import annotations

import re
from typing import Optional

LANGS = {"en": "English", "hi": "हिन्दी", "bn": "বাংলা", "ta": "தமிழ்", "te": "తెలుగు", "mr": "मराठी"}

_SCRIPTS = [("hi", "ऀ", "ॿ"), ("bn", "ঀ", "৿"), ("ta", "஀", "௿"), ("te", "ఀ", "౿")]


def detect_script(text: str) -> Optional[str]:
    """The Indian language a message is mostly written in, from its script; None for Latin text. Devanagari reads as
    Hindi unless it has Marathi words."""
    counts = {lang: sum(lo <= ch <= hi for ch in text) for lang, lo, hi in _SCRIPTS}
    lang, n = max(counts.items(), key=lambda kv: kv[1])
    if lang == "hi" and n >= 2 and is_marathi(text):
        return "mr"
    return lang if n >= 2 else None


# Words common in Marathi and not used in Hindi ("होता" is both, so it isn't here).
_MR_MARKERS = ("झाला", "झाली", "झाले", "झालं", "आहे", "आणि", "वर्षी", "माझ्या", "माझी", "माझे",
               "माझा", "आजोबा", "आत्या", "मावशी", "वडील", "वडिलां", "कर्करोग", "बहीण", "बहिणी", "मुलगा", "मुलगी", "नाही",
               "आईला", "आईचे", "आईची", "बाबांना")


def is_marathi(text: str) -> bool:
    return sum(m in text for m in _MR_MARKERS) >= 1


# --- Hindi / Hinglish → English --------------------------------------------------------------------

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Devanagari is unambiguous enough to always map. Longest phrases first.
_HI = [
    ("माँ", "mother"), ("मां", "mother"), ("माता जी", "mother"), ("माताजी", "mother"), ("माता", "mother"),
    ("मम्मी", "mother"), ("अम्मा", "mother"), ("पिताजी", "father"), ("पिता जी", "father"), ("पिता", "father"),
    ("पापा", "father"), ("बाबूजी", "father"), ("नानी", "maternal grandmother"), ("नाना", "maternal grandfather"),
    ("दादी", "paternal grandmother"), ("दादा", "paternal grandfather"), ("मौसी", "maternal aunt"),
    ("मामा", "maternal uncle"), ("चाचा", "paternal uncle"), ("ताऊ", "paternal uncle"), ("बुआ", "paternal aunt"),
    ("भैया", "brother"), ("भाई", "brother"), ("बहन", "sister"), ("दीदी", "sister"), ("बेटा", "son"), ("बेटी", "daughter"),
    ("स्तन कैंसर", "breast cancer"), ("गर्भाशय कैंसर", "uterine cancer"), ("अंडाशय कैंसर", "ovarian cancer"),
    ("पेट का कैंसर", "stomach cancer"), ("आंत का कैंसर", "colon cancer"), ("प्रोस्टेट कैंसर", "prostate cancer"),
    ("कैंसर", "cancer"), ("मधुमेह", "diabetes"), ("डायबिटीज़", "diabetes"), ("डायबिटीज", "diabetes"),
    ("शुगर", "diabetes"), ("उच्च रक्तचाप", "high blood pressure"), ("हाई बीपी", "high blood pressure"),
    ("बीपी", "high blood pressure"), ("दिल का दौरा", "heart attack"), ("हार्ट अटैक", "heart attack"),
    ("दिल की बीमारी", "heart disease"), ("लकवा", "stroke"), ("ब्रेन स्ट्रोक", "stroke"),
    ("कोलेस्ट्रॉल", "high cholesterol"), ("कोलेस्ट्रोल", "high cholesterol"),
    ("साल की उम्र में", "@AGE"), ("की उम्र में", "@AGE"), ("साल में", "@AGE"), ("में", "@AGE?"),
    ("मेरी", " my "), ("मेरे", " my "), ("मेरा", " my "), ("पड़ा", ""), ("पड़ी", ""),
    ("और", " and "), ("को", " had "), ("है", ""), ("था", ""), ("थी", ""), ("हुआ", ""), ("हुई", ""), ("।", "."),
]

# Marathi in Devanagari. Applied before the Hindi table, which then picks up shared words (शुगर, बीपी, कैंसर).
# Case endings stay as separate words once the noun is replaced ("आईला" → "mother ला") and become "had" below.
_MR = [
    ("वयाच्या", ""), ("व्या वर्षी", "@AGE"), ("वर्षांची असताना", "@AGE"), ("वर्षांचे असताना", "@AGE"),
    ("वर्षांचा असताना", "@AGE"), ("वर्षी", "@AGE"),
    ("आईच्या", "mother's"), ("वडिलांच्या", "father's"),
    ("आई", "mother"), ("मम्मी", "mother"), ("वडिलां", "father"), ("वडील", "father"), ("बाबां", "father"),
    ("बाबा", "father"), ("पप्पां", "father"), ("पप्पा", "father"),
    ("आजोबां", "grandfather"), ("आजोबा", "grandfather"), ("आजी", "grandmother"),
    ("मावशी", "maternal aunt"), ("मामां", "maternal uncle"), ("मामा", "maternal uncle"), ("आत्या", "paternal aunt"),
    ("काकां", "paternal uncle"), ("काका", "paternal uncle"), ("काकू", "paternal aunt"),
    ("भावा", "brother"), ("भाऊ", "brother"), ("दादां", "brother"), ("दादा", "brother"),
    ("बहिणी", "sister"), ("बहिण", "sister"), ("बहीण", "sister"), ("ताई", "sister"),
    ("मुलगा", "son"), ("मुला", "son"), ("मुलगी", "daughter"), ("मुली", "daughter"),
    ("स्तनाचा कर्करोग", "breast cancer"), ("स्तनाचा कॅन्सर", "breast cancer"), ("ब्रेस्ट कॅन्सर", "breast cancer"),
    ("गर्भाशयाचा कर्करोग", "uterine cancer"), ("गर्भाशयाचा कॅन्सर", "uterine cancer"),
    ("अंडाशयाचा कर्करोग", "ovarian cancer"), ("अंडाशयाचा कॅन्सर", "ovarian cancer"),
    ("आतड्याचा कर्करोग", "colon cancer"), ("आतड्याचा कॅन्सर", "colon cancer"),
    ("जठराचा कर्करोग", "stomach cancer"), ("पोटाचा कॅन्सर", "stomach cancer"),
    ("प्रोस्टेटचा कर्करोग", "prostate cancer"), ("प्रोस्टेटचा कॅन्सर", "prostate cancer"),
    ("कर्करोग", "cancer"), ("कॅन्सर", "cancer"), ("मधुमेह", "diabetes"), ("डायबेटीस", "diabetes"),
    ("डायबिटीस", "diabetes"), ("उच्च रक्तदाब", "high blood pressure"), ("रक्तदाब", "high blood pressure"),
    ("हृदयविकाराचा झटका", "heart attack"), ("हार्ट अटॅक", "heart attack"), ("हृदयविकार", "heart disease"),
    ("पक्षाघात", "stroke"), ("अर्धांगवायू", "stroke"), ("कोलेस्टेरॉल", "high cholesterol"),
    ("माझ्या", " my "), ("माझी", " my "), ("माझे", " my "), ("माझा", " my "), ("आणि", " and "),
    ("झाला", ""), ("झाली", ""), ("झाले", ""), ("झालं", ""), ("आला", ""), ("आली", ""), ("होता", ""), ("होती", ""),
    ("होते", ""), ("आहेत", ""), ("आहे", ""), ("।", "."),
]
_MR_CASE = re.compile(r"(?<=\s)(?:ांना|ंना|ना|ला|ंनी|नी|ने|ाला|ीला|ेला)(?=[\s.,]|$)")

# Marathi in Latin letters ("aaila 46 vya varshi breast cancer zala").
_MR_LATIN_HINT = re.compile(r"\b(zala|jhala|zali|jhali|zale|aahe|ahe|aani|varshi|aaila|vadilanna|babanna)\b", re.I)
_MR_LATIN = [
    (r"\b(aaila|aaeela|aai|aaee)\b", "mother"), (r"\b(vadilanna|vadil|babanna|baba|pappanna)\b", "father"),
    (r"\b(ajobanna|ajoba|aajoba)\b", "grandfather"), (r"\b(ajila|aajila|aji|aaji)\b", "grandmother"),
    (r"\b(mavshila|mavashila|mavshi|mavashi)\b", "maternal aunt"), (r"\b(mamanna|mamala)\b", "maternal uncle"),
    (r"\b(atyala|atya|aatya)\b", "paternal aunt"), (r"\b(kakanna|kakala|kaka)\b", "paternal uncle"),
    (r"\b(bhavala|bhau)\b", "brother"), (r"\b(bahinila|bahin|tai|taila)\b", "sister"),
    (r"\b(mulala|mulga)\b", "son"), (r"\b(mulila|mulgi)\b", "daughter"),
    (r"\b(sugar|madhumeh|diabetes)\b", "diabetes"), (r"\b(high bp|bp)\b", "high blood pressure"),
    (r"\b(heart attack|hruday vikar)\b", "heart attack"), (r"\b(paralysis|pakshaghat|lakva)\b", "stroke"),
    (r"\b(karkrog|kark rog)\b", "cancer"),
    (r"\b(?:vayachya\s+)?(\d{1,3})\s*(?:vya|va)?\s*varshi\b", r"at \1"),
    (r"\b(aani|ani)\b", "and"), (r"\b(zala|jhala|zali|jhali|zale|jhale|hota|hoti|aahe|ahe)\b", ""),
    (r"\b(mazya|mazhya|majhya|mazi|maza|maze)\b", "my"),
]

# Hinglish: only applied when the text reads as Hinglish, so English like "blood sugar" or "dada" in a name is safe.
_HINGLISH_HINT = re.compile(r"\b(ko|hai|tha|thi|hua|hui|mein|me|ki|ka|aur|unko|unhe|bimari)\b", re.I)
_HINGLISH = [
    (r"\b(mummy|mummi|mumma|mammi|maa|mata ?ji|mataji|ammi|amma)\b", "mother"),
    (r"\b(papa|pappa|pitaji|pita ?ji|pita|abba|appa|babuji|daddy)\b", "father"),
    (r"\bnani\b", "maternal grandmother"), (r"\bnana ?ji\b|\bnana\b", "maternal grandfather"),
    (r"\bdadi\b", "paternal grandmother"), (r"\bdada ?ji\b|\bdada\b", "paternal grandfather"),
    (r"\b(mausi|masi)\b", "maternal aunt"), (r"\bmama ?ji\b", "maternal uncle"),
    (r"\b(chacha ?ji|chacha|tau ?ji|tauji)\b", "paternal uncle"), (r"\b(bua ?ji|bua)\b", "paternal aunt"),
    (r"\b(bhaiya|bhai)\b", "brother"), (r"\b(behen|bahan|behna|didi)\b", "sister"),
    (r"\bbeta\b", "son"), (r"\bbeti\b", "daughter"),
    (r"\b(sugar ki bimari|sugar|madhumeh)\b", "diabetes"),
    (r"\b(high bp|bp ki bimari|bp)\b", "high blood pressure"),
    (r"\bdil ka daura\b|\bdil ki bimari\b", "heart attack"),
    (r"\b(lakwa|paralysis attack)\b", "stroke"),
    (r"\bstan cancer\b", "breast cancer"),
    (r"\b(\d{1,3})\s*(saal|sal|years?)\s*(ki|ke)?\s*(umar|umr|age)\s*(me|mein|par)\b", r"at \1"),
    (r"\b(\d{1,3})\s*(ki|ke)\s*(umar|umr|age)\s*(me|mein|par)\b", r"at \1"),
    (r"\b(\d{1,3})\s*(saal|sal)?\s*(me|mein)\b", r"at \1"),
    (r"\baur\b", "and"), (r"\b(ko|unko|unhe)\b", "had"),
    (r"\b(hai|tha|thi|hua|hui|he|h|bhi)\b", ""),
]


def normalize_family_text(text: str) -> str:
    """Hindi, Hinglish or Marathi family history → English the parser understands. English passes through
    unchanged."""
    out = text.translate(_DEVANAGARI_DIGITS)
    script = detect_script(out)
    if script == "mr":
        for mr, en in _MR:
            out = out.replace(mr, f" {en} ")
        out = _MR_CASE.sub(" had ", out)
    if script in ("hi", "mr"):
        for hi, en in _HI:
            out = out.replace(hi, f" {en} ")
        out = re.sub(r"(\d{1,3})\s*@AGE\??", r" at \1 ", out)
        out = out.replace("@AGE?", " ").replace("@AGE", " ")
    elif _MR_LATIN_HINT.search(out):
        for pattern, repl in _MR_LATIN:
            out = re.sub(pattern, repl, out, flags=re.I)
        out = re.sub(r"\b(mother|father|grandmother|grandfather|aunt|uncle|brother|sister|son|daughter)\b(?!\s+had)",
                     r"\1 had", out)
    elif _HINGLISH_HINT.search(out):
        for pattern, repl in _HINGLISH:
            out = re.sub(pattern, repl, out, flags=re.I)
    else:
        return text
    out = re.sub(r"\bhad\s+had\b", "had", out)
    # One relative per sentence: the parser attaches conditions to every relative in a sentence.
    out = re.sub(rf"\s*(?:,|;|\band\b)\s*(?=(?:{_RELATIVE})\b)", ". ", out, flags=re.I)
    return re.sub(r"[ \t]+", " ", out).strip()


_RELATIVE = ("maternal grandmother|maternal grandfather|paternal grandmother|paternal grandfather|maternal aunt|"
             "maternal uncle|paternal aunt|paternal uncle|mother|father|brother|sister|son|daughter")


# --- WhatsApp assistant messages ------------------------------------------------------------------

MESSAGES: dict[str, dict[str, str]] = {
    "linked": {
        "en": "Your WhatsApp is now connected to Family Health Graph. Send a photo or PDF of a prescription or lab report, or type your family history, like “Mother had diabetes at 50”. Reply HELP any time.",
        "hi": "आपका WhatsApp अब Family Health Graph से जुड़ गया है। पर्चे या लैब रिपोर्ट की फ़ोटो या PDF भेजें, या परिवार का स्वास्थ्य इतिहास लिखें, जैसे “मम्मी को 50 की उम्र में शुगर हुई”। मदद के लिए HELP लिखें।",
        "bn": "আপনার WhatsApp এখন Family Health Graph-এর সাথে যুক্ত। প্রেসক্রিপশন বা ল্যাব রিপোর্টের ছবি বা PDF পাঠান, অথবা পরিবারের স্বাস্থ্যের ইতিহাস লিখুন। সাহায্যের জন্য HELP লিখুন।",
        "ta": "உங்கள் WhatsApp இப்போது Family Health Graph உடன் இணைக்கப்பட்டது. மருந்துச் சீட்டு அல்லது ஆய்வக அறிக்கையின் புகைப்படம் அல்லது PDF அனுப்பவும், அல்லது குடும்ப சுகாதார வரலாற்றை எழுதவும். உதவிக்கு HELP என அனுப்பவும்.",
        "te": "మీ WhatsApp ఇప్పుడు Family Health Graph తో అనుసంధానమైంది. ప్రిస్క్రిప్షన్ లేదా ల్యాబ్ రిపోర్ట్ ఫోటో లేదా PDF పంపండి, లేదా కుటుంబ ఆరోగ్య చరిత్ర రాయండి. సహాయం కోసం HELP పంపండి.",
        "mr": "तुमचे WhatsApp आता Family Health Graph शी जोडले आहे. प्रिस्क्रिप्शन किंवा लॅब रिपोर्टचा फोटो किंवा PDF पाठवा, किंवा कुटुंबाचा आरोग्य इतिहास लिहा. मदतीसाठी HELP लिहा.",
    },
    "received": {
        "en": "Got it. Open Family Health Graph to check what we read before it's added to your record.",
        "hi": "मिल गया। रिकॉर्ड में जोड़ने से पहले Family Health Graph खोलकर देख लें कि हमने क्या पढ़ा।",
        "bn": "পেয়েছি। রেকর্ডে যোগ করার আগে Family Health Graph খুলে দেখে নিন আমরা কী পড়েছি।",
        "ta": "கிடைத்தது. உங்கள் பதிவில் சேர்க்கும் முன், நாங்கள் படித்ததை Family Health Graph-ல் சரிபார்க்கவும்.",
        "te": "అందింది. మీ రికార్డ్‌లో చేర్చే ముందు, మేము చదివినది Family Health Graph లో సరిచూడండి.",
        "mr": "मिळाले. नोंदीत जोडण्यापूर्वी आम्ही काय वाचले ते Family Health Graph उघडून तपासा.",
    },
    "read_summary": {
        "en": "Read your {doc}{date}:\n{items}\nReply 1 to save it to your record, 2 if it's your mother's, 3 if it's your father's. Or open the app to edit.",
        "hi": "आपकी {doc}{date} पढ़ ली:\n{items}\nअपने रिकॉर्ड में सेव करने के लिए 1, मम्मी का हो तो 2, पापा का हो तो 3 भेजें। या ऐप खोलकर बदलें।",
        "bn": "আপনার {doc}{date} পড়া হয়েছে:\n{items}\nনিজের রেকর্ডে রাখতে 1, মায়ের হলে 2, বাবার হলে 3 পাঠান। অথবা অ্যাপে খুলে সম্পাদনা করুন।",
        "ta": "உங்கள் {doc}{date} படிக்கப்பட்டது:\n{items}\nஉங்கள் பதிவில் சேமிக்க 1, அம்மாவுடையது என்றால் 2, அப்பாவுடையது என்றால் 3 அனுப்பவும்.",
        "te": "మీ {doc}{date} చదివాము:\n{items}\nమీ రికార్డ్‌లో సేవ్ చేయడానికి 1, అమ్మది అయితే 2, నాన్నది అయితే 3 పంపండి.",
        "mr": "तुमचा {doc}{date} वाचला:\n{items}\nतुमच्या नोंदीत जतन करण्यासाठी 1, आईचा असल्यास 2, वडिलांचा असल्यास 3 पाठवा.",
    },
    "read_nothing": {
        "en": "We couldn't find diagnoses, medicines or test results in that. Open the app to check it, or type what it says.",
        "hi": "इसमें हमें बीमारी, दवा या जाँच के नतीजे नहीं मिले। ऐप में देखें, या जो लिखा है वह टाइप करें।",
        "bn": "এতে রোগ, ওষুধ বা পরীক্ষার ফল পাওয়া যায়নি। অ্যাপে দেখুন, অথবা যা লেখা আছে টাইপ করুন।",
        "ta": "இதில் நோய், மருந்து அல்லது பரிசோதனை முடிவுகள் கிடைக்கவில்லை. செயலியில் பார்க்கவும் அல்லது அதை தட்டச்சு செய்யவும்.",
        "te": "ఇందులో వ్యాధులు, మందులు లేదా పరీక్ష ఫలితాలు కనబడలేదు. యాప్‌లో చూడండి, లేదా అందులో ఉన్నది టైప్ చేయండి.",
        "mr": "यात आजार, औषधे किंवा तपासणीचे निकाल सापडले नाहीत. ॲपमध्ये तपासा किंवा जे लिहिले आहे ते टाइप करा.",
    },
    "understood": {
        "en": "I understood:\n{items}\nReply 1 to save this to your family history.",
        "hi": "मैंने समझा:\n{items}\nपरिवार के स्वास्थ्य इतिहास में सेव करने के लिए 1 भेजें।",
        "bn": "আমি বুঝেছি:\n{items}\nপারিবারিক স্বাস্থ্য ইতিহাসে রাখতে 1 পাঠান।",
        "ta": "நான் புரிந்துகொண்டது:\n{items}\nகுடும்ப சுகாதார வரலாற்றில் சேமிக்க 1 அனுப்பவும்.",
        "te": "నేను అర్థం చేసుకున్నది:\n{items}\nకుటుంబ ఆరోగ్య చరిత్రలో సేవ్ చేయడానికి 1 పంపండి.",
        "mr": "मला समजले:\n{items}\nकुटुंबाच्या आरोग्य इतिहासात जतन करण्यासाठी 1 पाठवा.",
    },
    "understood_private": {
        "en": "Thanks. Reply 1 to save what you wrote to your family history, or open the app to check it first.",
        "hi": "धन्यवाद। जो लिखा है उसे परिवार के इतिहास में सेव करने के लिए 1 भेजें, या पहले ऐप में देख लें।",
        "bn": "ধন্যবাদ। যা লিখেছেন তা পারিবারিক ইতিহাসে রাখতে 1 পাঠান, অথবা আগে অ্যাপে দেখে নিন।",
        "ta": "நன்றி. நீங்கள் எழுதியதை குடும்ப வரலாற்றில் சேமிக்க 1 அனுப்பவும், அல்லது முதலில் செயலியில் பார்க்கவும்.",
        "te": "ధన్యవాదాలు. మీరు రాసినది కుటుంబ చరిత్రలో సేవ్ చేయడానికి 1 పంపండి, లేదా ముందుగా యాప్‌లో చూడండి.",
        "mr": "धन्यवाद. तुम्ही लिहिलेले कुटुंबाच्या इतिहासात जतन करण्यासाठी 1 पाठवा, किंवा आधी ॲपमध्ये तपासा.",
    },
    "not_understood": {
        "en": "Sorry, I didn't catch a relative and a condition. Try “Mother had diabetes at 50” or send a photo of a report. Reply HELP for options.",
        "hi": "माफ़ कीजिए, रिश्ता और बीमारी समझ नहीं आई। ऐसे लिखें: “मम्मी को 50 की उम्र में शुगर हुई”, या रिपोर्ट की फ़ोटो भेजें। विकल्पों के लिए HELP लिखें।",
        "bn": "দুঃখিত, সম্পর্ক ও রোগ বুঝতে পারিনি। যেমন লিখুন “Mother had diabetes at 50”, বা রিপোর্টের ছবি পাঠান।",
        "ta": "மன்னிக்கவும், உறவு மற்றும் நோய் புரியவில்லை. “Mother had diabetes at 50” என எழுதவும் அல்லது அறிக்கையின் புகைப்படம் அனுப்பவும்.",
        "te": "క్షమించండి, బంధుత్వం మరియు వ్యాధి అర్థం కాలేదు. “Mother had diabetes at 50” అని రాయండి లేదా రిపోర్ట్ ఫోటో పంపండి.",
        "mr": "माफ करा, नाते आणि आजार समजले नाहीत. “Mother had diabetes at 50” असे लिहा किंवा रिपोर्टचा फोटो पाठवा.",
    },
    "saved": {
        "en": "Saved to your record. Your insights are updated in the app.",
        "hi": "आपके रिकॉर्ड में सेव हो गया। ऐप में आपकी जानकारी अपडेट हो गई है।",
        "bn": "আপনার রেকর্ডে রাখা হয়েছে। অ্যাপে আপনার তথ্য আপডেট হয়েছে।",
        "ta": "உங்கள் பதிவில் சேமிக்கப்பட்டது. செயலியில் உங்கள் தகவல்கள் புதுப்பிக்கப்பட்டன.",
        "te": "మీ రికార్డ్‌లో సేవ్ అయింది. యాప్‌లో మీ సమాచారం అప్‌డేట్ అయింది.",
        "mr": "तुमच्या नोंदीत जतन झाले. ॲपमध्ये तुमची माहिती अद्ययावत झाली आहे.",
    },
    "nothing_pending": {
        "en": "There's nothing waiting to be saved. Send a photo or PDF, or type your family history.",
        "hi": "सेव करने के लिए कुछ बाकी नहीं है। फ़ोटो या PDF भेजें, या परिवार का इतिहास लिखें।",
        "bn": "রাখার মতো কিছু বাকি নেই। ছবি বা PDF পাঠান, অথবা পরিবারের ইতিহাস লিখুন।",
        "ta": "சேமிக்க எதுவும் இல்லை. புகைப்படம் அல்லது PDF அனுப்பவும், அல்லது குடும்ப வரலாற்றை எழுதவும்.",
        "te": "సేవ్ చేయడానికి ఏమీ లేదు. ఫోటో లేదా PDF పంపండి, లేదా కుటుంబ చరిత్ర రాయండి.",
        "mr": "जतन करण्यासाठी काहीही बाकी नाही. फोटो किंवा PDF पाठवा, किंवा कुटुंबाचा इतिहास लिहा.",
    },
    "help": {
        "en": "Send a photo or PDF of a prescription or lab report, or type family history (“Father had a heart attack at 52”).\nSUMMARY: your action items\nLANG hi / bn / ta / te / mr / en: change language\nSTOP: disconnect this number",
        "hi": "पर्चे या लैब रिपोर्ट की फ़ोटो/PDF भेजें, या परिवार का इतिहास लिखें (“पापा को 52 में हार्ट अटैक हुआ”)।\nSUMMARY: आपके ज़रूरी कदम\nLANG en / bn / ta / te / mr: भाषा बदलें\nSTOP: यह नंबर हटाएँ",
        "bn": "প্রেসক্রিপশন বা ল্যাব রিপোর্টের ছবি/PDF পাঠান, বা পরিবারের ইতিহাস লিখুন।\nSUMMARY: আপনার করণীয়\nLANG en / hi / ta / te / mr: ভাষা বদলান\nSTOP: এই নম্বর সরান",
        "ta": "மருந்துச் சீட்டு அல்லது ஆய்வக அறிக்கையின் புகைப்படம்/PDF அனுப்பவும், அல்லது குடும்ப வரலாற்றை எழுதவும்.\nSUMMARY: உங்கள் செயல்கள்\nLANG en / hi / bn / te / mr: மொழியை மாற்ற\nSTOP: இந்த எண்ணை நீக்க",
        "te": "ప్రిస్క్రిప్షన్ లేదా ల్యాబ్ రిపోర్ట్ ఫోటో/PDF పంపండి, లేదా కుటుంబ చరిత్ర రాయండి.\nSUMMARY: మీరు చేయాల్సినవి\nLANG en / hi / bn / ta / mr: భాష మార్చండి\nSTOP: ఈ నంబర్ తొలగించండి",
        "mr": "प्रिस्क्रिप्शन किंवा लॅब रिपोर्टचा फोटो/PDF पाठवा, किंवा कुटुंबाचा इतिहास लिहा.\nSUMMARY: तुमच्या कृती\nLANG en / hi / bn / ta / te: भाषा बदला\nSTOP: हा नंबर काढा",
    },
    "lang_set": {
        "en": "OK, I'll reply in English.", "hi": "ठीक है, मैं हिन्दी में जवाब दूँगा।", "bn": "ঠিক আছে, আমি বাংলায় উত্তর দেব।",
        "ta": "சரி, நான் தமிழில் பதிலளிப்பேன்.", "te": "సరే, నేను తెలుగులో సమాధానం ఇస్తాను.", "mr": "ठीक आहे, मी मराठीत उत्तर देईन.",
    },
    "stopped": {
        "en": "This number is disconnected. Your record stays in the app. Send a new link code from the app to reconnect.",
        "hi": "यह नंबर हटा दिया गया है। आपका रिकॉर्ड ऐप में सुरक्षित है। दोबारा जोड़ने के लिए ऐप से नया कोड भेजें।",
        "bn": "এই নম্বরটি সরানো হয়েছে। আপনার রেকর্ড অ্যাপে থাকবে। আবার যুক্ত করতে অ্যাপ থেকে নতুন কোড পাঠান।",
        "ta": "இந்த எண் துண்டிக்கப்பட்டது. உங்கள் பதிவு செயலியில் இருக்கும். மீண்டும் இணைக்க செயலியிலிருந்து புதிய குறியீட்டை அனுப்பவும்.",
        "te": "ఈ నంబర్ తొలగించబడింది. మీ రికార్డ్ యాప్‌లో ఉంటుంది. మళ్ళీ కలపడానికి యాప్ నుండి కొత్త కోడ్ పంపండి.",
        "mr": "हा नंबर काढला आहे. तुमची नोंद ॲपमध्ये राहील. पुन्हा जोडण्यासाठी ॲपमधून नवीन कोड पाठवा.",
    },
    "summary_header": {
        "en": "Your action items:", "hi": "आपके ज़रूरी कदम:", "bn": "আপনার করণীয়:", "ta": "உங்கள் செயல்கள்:",
        "te": "మీరు చేయాల్సినవి:", "mr": "तुमच्या कृती:",
    },
    "summary_none": {
        "en": "Nothing needs attention right now. Adding more family history keeps this accurate.",
        "hi": "अभी कुछ भी ज़रूरी नहीं है। परिवार का और इतिहास जोड़ने से जानकारी सटीक रहती है।",
        "bn": "এখন কিছু করার নেই। আরও পারিবারিক ইতিহাস যোগ করলে তথ্য সঠিক থাকে।",
        "ta": "இப்போது கவனிக்க வேண்டியது எதுவும் இல்லை. மேலும் குடும்ப வரலாற்றைச் சேர்ப்பது துல்லியமாக வைக்கும்.",
        "te": "ప్రస్తుతం చేయాల్సింది ఏమీ లేదు. మరింత కుటుంబ చరిత్ర చేర్చితే ఇది ఖచ్చితంగా ఉంటుంది.",
        "mr": "सध्या काहीही करायची गरज नाही. आणखी कौटुंबिक इतिहास जोडल्याने माहिती अचूक राहते.",
    },
    "private": {
        "en": "To get health details on WhatsApp, turn on “WhatsApp summaries” in the app’s Settings. Until then I only send short confirmations.",
        "hi": "WhatsApp पर स्वास्थ्य जानकारी पाने के लिए ऐप की Settings में “WhatsApp summaries” चालू करें। तब तक मैं केवल छोटी पुष्टि भेजूँगा।",
        "bn": "WhatsApp-এ স্বাস্থ্যের তথ্য পেতে অ্যাপের Settings-এ “WhatsApp summaries” চালু করুন।",
        "ta": "WhatsApp-ல் சுகாதார விவரங்களைப் பெற, செயலியின் Settings-ல் “WhatsApp summaries” ஐ இயக்கவும்.",
        "te": "WhatsApp లో ఆరోగ్య వివరాలు పొందడానికి, యాప్ Settings లో “WhatsApp summaries” ఆన్ చేయండి.",
        "mr": "WhatsApp वर आरोग्य माहिती मिळवण्यासाठी ॲपच्या Settings मध्ये “WhatsApp summaries” चालू करा.",
    },
    "voice": {
        "en": "Voice notes aren't supported yet. Please type it, or send a photo of the report.",
        "hi": "वॉइस नोट अभी समर्थित नहीं हैं। कृपया टाइप करें, या रिपोर्ट की फ़ोटो भेजें।",
        "bn": "ভয়েস নোট এখনও সমর্থিত নয়। অনুগ্রহ করে টাইপ করুন, বা রিপোর্টের ছবি পাঠান।",
        "ta": "குரல் குறிப்புகள் இன்னும் ஆதரிக்கப்படவில்லை. தட்டச்சு செய்யவும் அல்லது அறிக்கையின் புகைப்படம் அனுப்பவும்.",
        "te": "వాయిస్ నోట్స్ ఇంకా అందుబాటులో లేవు. దయచేసి టైప్ చేయండి, లేదా రిపోర్ట్ ఫోటో పంపండి.",
        "mr": "व्हॉइस नोट्स अजून समर्थित नाहीत. कृपया टाइप करा, किंवा रिपोर्टचा फोटो पाठवा.",
    },
    "unsupported": {
        "en": "Please send a photo or a PDF of the document.", "hi": "कृपया दस्तावेज़ की फ़ोटो या PDF भेजें।",
        "bn": "অনুগ্রহ করে নথির ছবি বা PDF পাঠান।", "ta": "ஆவணத்தின் புகைப்படம் அல்லது PDF அனுப்பவும்.",
        "te": "దయచేసి పత్రం ఫోటో లేదా PDF పంపండి.", "mr": "कृपया कागदपत्राचा फोटो किंवा PDF पाठवा.",
    },
    "too_many": {
        "en": "That's a lot of documents in one hour. Please send the rest a little later.",
        "hi": "एक घंटे में बहुत सारे दस्तावेज़ आ गए। बाकी थोड़ी देर बाद भेजें।",
        "bn": "এক ঘণ্টায় অনেক নথি এসেছে। বাকিগুলো একটু পরে পাঠান।",
        "ta": "ஒரு மணி நேரத்தில் பல ஆவணங்கள் வந்துள்ளன. மீதியை சிறிது நேரம் கழித்து அனுப்பவும்.",
        "te": "ఒక గంటలో చాలా పత్రాలు వచ్చాయి. మిగిలినవి కొంచెం తర్వాత పంపండి.",
        "mr": "एका तासात खूप कागदपत्रे आली. बाकीची थोड्या वेळाने पाठवा.",
    },
    "unknown": {
        "en": "This number isn't connected yet. In the Family Health Graph app, go to Add health information → Forward by WhatsApp, and send us the code shown there.",
        "hi": "यह नंबर अभी जुड़ा नहीं है। Family Health Graph ऐप में Add health information → WhatsApp पर जाएँ और वहाँ दिखा कोड हमें भेजें।",
        "bn": "এই নম্বরটি এখনও যুক্ত নয়। Family Health Graph অ্যাপে Add health information → WhatsApp-এ গিয়ে দেখানো কোডটি পাঠান।",
        "ta": "இந்த எண் இன்னும் இணைக்கப்படவில்லை. Family Health Graph செயலியில் Add health information → WhatsApp சென்று அங்குள்ள குறியீட்டை அனுப்பவும்.",
        "te": "ఈ నంబర్ ఇంకా కలపబడలేదు. Family Health Graph యాప్‌లో Add health information → WhatsApp కి వెళ్ళి అక్కడ ఉన్న కోడ్ పంపండి.",
        "mr": "हा नंबर अजून जोडलेला नाही. Family Health Graph ॲपमध्ये Add health information → WhatsApp वर जा आणि तिथे दिसणारा कोड पाठवा.",
    },
}

DOC_NAMES = {
    "prescription": {"en": "prescription", "hi": "पर्ची", "bn": "প্রেসক্রিপশন", "ta": "மருந்துச் சீட்டு", "te": "ప్రిస్క్రిప్షన్", "mr": "प्रिस्क्रिप्शन"},
    "lab_report": {"en": "lab report", "hi": "लैब रिपोर्ट", "bn": "ল্যাব রিপোর্ট", "ta": "ஆய்வக அறிக்கை", "te": "ల్యాబ్ రిపోర్ట్", "mr": "लॅब रिपोर्ट"},
    "discharge_summary": {"en": "discharge summary", "hi": "डिस्चार्ज समरी", "bn": "ডিসচার্জ সামারি", "ta": "டிஸ்சார்ஜ் சுருக்கம்", "te": "డిశ్చార్జ్ సారాంశం", "mr": "डिस्चार्ज सारांश"},
    "other": {"en": "document", "hi": "दस्तावेज़", "bn": "নথি", "ta": "ஆவணம்", "te": "పత్రం", "mr": "कागदपत्र"},
}


def t(key: str, lang: Optional[str], **values) -> str:
    table = MESSAGES[key]
    text = table.get(lang or "en") or table["en"]
    return text.format(**values) if values else text
