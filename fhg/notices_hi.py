"""Hindi for the in-app notices (fhg/notices.py). Needs review by a native speaker before families see it."""

NOTICES_HI: dict[str, str] = {
    "1 document arrived by {channel} and is waiting for your review.":
        "{channel} से 1 दस्तावेज़ आया है और आपकी जाँच का इंतज़ार कर रहा है।",
    "{n} documents arrived by {channel} and are waiting for your review.":
        "{channel} से {n} दस्तावेज़ आए हैं और आपकी जाँच का इंतज़ार कर रहे हैं।",
    "email": "ईमेल",
    "WhatsApp": "WhatsApp",
    "{org} referred you for: {program}. Contact your clinic if you have questions.":
        "{org} ने आपको इसके लिए रेफ़र किया है: {program}। कोई सवाल हो तो अपने क्लिनिक से संपर्क करें।",
    "{org} referred you for: {program}, with {partner}. Contact your clinic if you have questions.":
        "{org} ने आपको {partner} के पास इसके लिए रेफ़र किया है: {program}। कोई सवाल हो तो अपने क्लिनिक से संपर्क करें।",
    "{org} scheduled your: {program}. Contact your clinic if you have questions.":
        "{org} ने आपका यह तय किया है: {program}। कोई सवाल हो तो अपने क्लिनिक से संपर्क करें।",
    "{org} scheduled your: {program}, with {partner}. Contact your clinic if you have questions.":
        "{org} ने {partner} के साथ आपका यह तय किया है: {program}। कोई सवाल हो तो अपने क्लिनिक से संपर्क करें।",
    "{partner} scheduled your appointment: {program}. They or your clinic will be in touch with details.":
        "{partner} ने आपका अपॉइंटमेंट तय किया है: {program}। वे या आपका क्लिनिक आपको जानकारी देंगे।",
    "{partner} shared your {model} risk assessment.": "{partner} ने आपका {model} जोखिम आकलन साझा किया है।",
    "{partner} confirmed your {tests}.": "{partner} ने आपका {tests} पक्का किया।",
    "{partner} confirmed your {tests} for {date}.": "{partner} ने आपका {tests} {date} के लिए पक्का किया।",
    "{partner} has collected your sample. Results will appear in the app.":
        "{partner} ने आपका सैंपल ले लिया है। नतीजे ऐप में आ जाएँगे।",
    "{partner} has completed your {tests}.": "{partner} ने आपका {tests} पूरा किया।",
    "{partner} cancelled your {tests} booking.": "{partner} ने आपकी {tests} बुकिंग रद्द कर दी।",
    "{partner} cancelled your {tests} booking: {note}": "{partner} ने आपकी {tests} बुकिंग रद्द कर दी: {note}",
    "Your test results from {partner} are in. Your insights have been updated.":
        "{partner} से आपके टेस्ट के नतीजे आ गए हैं। आपकी सलाह अपडेट हो गई है।",
    "{partner} hasn't confirmed your test booking yet. You can wait, or cancel and choose another lab in the app.":
        "{partner} ने अभी तक आपकी टेस्ट बुकिंग पक्की नहीं की है। आप इंतज़ार कर सकते हैं, या ऐप में रद्द करके दूसरी लैब चुन सकते हैं।",
    "Your results from {partner} aren't in yet. If the test was done, they'll appear in the app once the lab sends them.":
        "{partner} से आपके नतीजे अभी नहीं आए हैं। अगर टेस्ट हो चुका है, तो लैब के भेजते ही वे ऐप में आ जाएँगे।",
    "Reminder: {item}. A {tests} test is the next step; you can book one in the app.":
        "याद दिलाना: {item}। अगला कदम {tests} टेस्ट है; आप ऐप में इसे बुक कर सकते हैं।",
    "Your {who} accepted your invitation. Your insights now include what they share.":
        "आपके/आपकी {who} ने आपका आमंत्रण स्वीकार कर लिया। अब आपकी सलाह में उनकी साझा की गई जानकारी शामिल है।",
    "Your {who} accepted your invitation but isn't sharing their history yet.":
        "आपके/आपकी {who} ने आपका आमंत्रण स्वीकार कर लिया, लेकिन अभी अपना इतिहास साझा नहीं कर रहे।",
    "Answer to your privacy concern: {answer}": "आपकी गोपनीयता शिकायत का जवाब: {answer}",
    "{name} joined the care circle for {who}.": "{name} {who} के देखभाल समूह में जुड़ गए।",
    "Someone": "कोई",
    "{who}'s emergency summary was just opened from a shared link.":
        "{who} का आपातकालीन सारांश अभी एक साझा लिंक से खोला गया।",
    "Your {who} shared a result that can run in families ({conditions}). Your insights have been updated. This may "
    "affect what screening or testing is right for you, so consider discussing it with your clinician or a genetic "
    "counselor.":
        "आपके/आपकी {who} ने ऐसी जानकारी साझा की है जो परिवार में चल सकती है ({conditions})। आपकी सलाह अपडेट हो गई है। "
        "इससे आपके लिए सही जाँच बदल सकती है, इसलिए अपने डॉक्टर या जेनेटिक काउंसलर से इस पर बात करें।",
    # Program and test names inside notices.
    "Genetic counseling: hereditary breast/ovarian cancer": "जेनेटिक काउंसलिंग: वंशानुगत स्तन/अंडाशय कैंसर",
    "Earlier colorectal screening / Lynch evaluation": "आँत के कैंसर की जल्दी जाँच / लिंच की जाँच",
    "Genetic counseling: Lynch syndrome": "जेनेटिक काउंसलिंग: लिंच सिंड्रोम",
    "Lipid clinic: possible familial hypercholesterolemia": "लिपिड क्लिनिक: संभवतः विरासती हाई कोलेस्ट्रॉल",
    "Cardiovascular risk assessment": "दिल की बीमारी के जोखिम की जाँच",
    "Diabetes screening / prevention program": "डायबिटीज़ जाँच / बचाव कार्यक्रम",
    "Earlier prostate cancer screening": "प्रोस्टेट कैंसर की जल्दी जाँच",
    "Anesthesia safety alert": "बेहोशी की दवा से सुरक्षा की चेतावनी",
    "Blood pressure follow-up": "BP की आगे की जाँच",
    "HbA1c": "HbA1c",
    "Fasting blood sugar": "खाली पेट शुगर",
    "Lipid profile": "लिपिड प्रोफ़ाइल",
    "Lipoprotein(a)": "लिपोप्रोटीन(a)",
    "Kidney function": "किडनी फ़ंक्शन",
    "Genetic counseling consultation": "जेनेटिक काउंसलिंग परामर्श",
    # Relationship names as stored on links ("maternal_aunt" → "maternal aunt").
    "mother": "माँ", "father": "पिता", "parent": "माता/पिता", "sister": "बहन", "brother": "भाई", "sibling": "भाई/बहन",
    "daughter": "बेटी", "son": "बेटा", "child": "संतान", "maternal grandmother": "नानी", "maternal grandfather": "नाना",
    "paternal grandmother": "दादी", "paternal grandfather": "दादा", "grandmother": "दादी/नानी", "grandfather": "दादा/नाना",
    "granddaughter": "पोती/नातिन", "grandson": "पोता/नाती", "grandchild": "पोता-पोती/नाती-नातिन",
    "maternal aunt": "मौसी", "maternal uncle": "मामा", "paternal aunt": "बुआ", "paternal uncle": "चाचा/ताऊ",
    "aunt": "मौसी/बुआ", "uncle": "चाचा/मामा", "niece": "भतीजी/भांजी", "nephew": "भतीजा/भांजा",
    "half sister": "सौतेली बहन", "half brother": "सौतेला भाई", "maternal cousin": "ममेरे/मौसेरे भाई-बहन",
    "paternal cousin": "चचेरे/फुफेरे भाई-बहन", "cousin": "चचेरे/ममेरे भाई-बहन", "relative": "रिश्तेदार", "other": "रिश्तेदार",
}
