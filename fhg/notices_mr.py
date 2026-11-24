"""Marathi for the in-app notices (fhg/notices.py). Needs review by a native speaker before families see it."""

NOTICES_MR: dict[str, str] = {
    "1 document arrived by {channel} and is waiting for your review.":
        "{channel} वरून 1 कागदपत्र आले आहे आणि तुमच्या तपासणीची वाट पाहत आहे.",
    "{n} documents arrived by {channel} and are waiting for your review.":
        "{channel} वरून {n} कागदपत्रे आली आहेत आणि तुमच्या तपासणीची वाट पाहत आहेत.",
    "email": "ईमेल",
    "WhatsApp": "WhatsApp",
    "{org} referred you for: {program}. Contact your clinic if you have questions.":
        "{org} ने तुम्हाला यासाठी रेफर केले आहे: {program}. काही प्रश्न असल्यास तुमच्या क्लिनिकशी संपर्क साधा.",
    "{org} referred you for: {program}, with {partner}. Contact your clinic if you have questions.":
        "{org} ने तुम्हाला {partner} कडे यासाठी रेफर केले आहे: {program}. काही प्रश्न असल्यास तुमच्या क्लिनिकशी संपर्क साधा.",
    "{org} scheduled your: {program}. Contact your clinic if you have questions.":
        "{org} ने तुमचे हे ठरवले आहे: {program}. काही प्रश्न असल्यास तुमच्या क्लिनिकशी संपर्क साधा.",
    "{org} scheduled your: {program}, with {partner}. Contact your clinic if you have questions.":
        "{org} ने {partner} सोबत तुमचे हे ठरवले आहे: {program}. काही प्रश्न असल्यास तुमच्या क्लिनिकशी संपर्क साधा.",
    "{partner} scheduled your appointment: {program}. They or your clinic will be in touch with details.":
        "{partner} ने तुमची अपॉइंटमेंट ठरवली आहे: {program}. ते किंवा तुमचे क्लिनिक तुम्हाला तपशील कळवतील.",
    "{partner} shared your {model} risk assessment.": "{partner} ने तुमचे {model} जोखीम मूल्यांकन शेअर केले आहे.",
    "{partner} confirmed your {tests}.": "{partner} ने तुमची {tests} निश्चित केली.",
    "{partner} confirmed your {tests} for {date}.": "{partner} ने तुमची {tests} {date} साठी निश्चित केली.",
    "{partner} has collected your sample. Results will appear in the app.":
        "{partner} ने तुमचा नमुना घेतला आहे. निकाल अ‍ॅपमध्ये दिसतील.",
    "{partner} has completed your {tests}.": "{partner} ने तुमची {tests} पूर्ण केली.",
    "{partner} cancelled your {tests} booking.": "{partner} ने तुमचे {tests} बुकिंग रद्द केले.",
    "{partner} cancelled your {tests} booking: {note}": "{partner} ने तुमचे {tests} बुकिंग रद्द केले: {note}",
    "Your test results from {partner} are in. Your insights have been updated.":
        "{partner} कडून तुमच्या चाचण्यांचे निकाल आले आहेत. तुमचे सल्ले अपडेट झाले आहेत.",
    "{partner} hasn't confirmed your test booking yet. You can wait, or cancel and choose another lab in the app.":
        "{partner} ने अजून तुमचे चाचणी बुकिंग निश्चित केलेले नाही. तुम्ही वाट पाहू शकता, किंवा अ‍ॅपमध्ये रद्द करून दुसरी लॅब "
        "निवडू शकता.",
    "Your results from {partner} aren't in yet. If the test was done, they'll appear in the app once the lab sends them.":
        "{partner} कडून तुमचे निकाल अजून आलेले नाहीत. चाचणी झाली असेल, तर लॅबने पाठवताच ते अ‍ॅपमध्ये दिसतील.",
    "Reminder: {item}. A {tests} test is the next step; you can book one in the app.":
        "आठवण: {item}. पुढचे पाऊल {tests} चाचणी आहे; तुम्ही ती अ‍ॅपमध्ये बुक करू शकता.",
    "Your {who} accepted your invitation. Your insights now include what they share.":
        "तुमच्या {who} यांनी तुमचे आमंत्रण स्वीकारले. आता तुमच्या सल्ल्यांमध्ये त्यांनी शेअर केलेली माहिती धरली जाते.",
    "Your {who} accepted your invitation but isn't sharing their history yet.":
        "तुमच्या {who} यांनी तुमचे आमंत्रण स्वीकारले, पण अजून त्यांचा इतिहास शेअर करत नाहीत.",
    "Answer to your privacy concern: {answer}": "तुमच्या गोपनीयतेच्या तक्रारीचे उत्तर: {answer}",
    "{name} joined the care circle for {who}.": "{name} {who} यांच्या काळजी गटात सामील झाले.",
    "Someone": "कोणीतरी",
    "{who}'s emergency summary was just opened from a shared link.":
        "{who} यांचा आपत्कालीन सारांश आत्ताच एका शेअर केलेल्या लिंकवरून उघडला गेला.",
    "Your {who} shared a result that can run in families ({conditions}). Your insights have been updated. This may "
    "affect what screening or testing is right for you, so consider discussing it with your clinician or a genetic "
    "counselor.":
        "तुमच्या {who} यांनी कुटुंबात चालत येऊ शकणारी माहिती शेअर केली आहे ({conditions}). तुमचे सल्ले अपडेट झाले आहेत. "
        "यामुळे तुमच्यासाठी योग्य तपासणी बदलू शकते, म्हणून याबद्दल तुमच्या डॉक्टरांशी किंवा जेनेटिक काउन्सेलरशी बोला.",
    # Program and test names inside notices.
    "Genetic counseling: hereditary breast/ovarian cancer": "जेनेटिक काउन्सेलिंग: आनुवंशिक स्तन/अंडाशय कर्करोग",
    "Earlier colorectal screening / Lynch evaluation": "आतड्याच्या कर्करोगाची लवकर तपासणी / लिंच तपासणी",
    "Genetic counseling: Lynch syndrome": "जेनेटिक काउन्सेलिंग: लिंच सिंड्रोम",
    "Lipid clinic: possible familial hypercholesterolemia": "लिपिड क्लिनिक: कदाचित आनुवंशिक उच्च कोलेस्टेरॉल",
    "Cardiovascular risk assessment": "हृदयविकाराच्या जोखमीची तपासणी",
    "Diabetes screening / prevention program": "मधुमेह तपासणी / प्रतिबंध कार्यक्रम",
    "Earlier prostate cancer screening": "प्रोस्टेट कर्करोगाची लवकर तपासणी",
    "Anesthesia safety alert": "भुलीच्या औषधांबाबत सुरक्षा सूचना",
    "Blood pressure follow-up": "BP ची पुढील तपासणी",
    "HbA1c": "HbA1c",
    "Fasting blood sugar": "उपाशीपोटी साखर",
    "Lipid profile": "लिपिड प्रोफाइल",
    "Lipoprotein(a)": "लिपोप्रोटीन(a)",
    "Kidney function": "मूत्रपिंड कार्य (किडनी फंक्शन)",
    "Genetic counseling consultation": "जेनेटिक काउन्सेलिंग सल्ला",
    # Relationship names as stored on links ("maternal_aunt" → "maternal aunt").
    "mother": "आई", "father": "वडील", "parent": "आई/वडील", "sister": "बहीण", "brother": "भाऊ", "sibling": "भावंड",
    "daughter": "मुलगी", "son": "मुलगा", "child": "अपत्य", "maternal grandmother": "आजी (आईकडील)",
    "maternal grandfather": "आजोबा (आईकडील)", "paternal grandmother": "आजी (वडिलांकडील)",
    "paternal grandfather": "आजोबा (वडिलांकडील)", "grandmother": "आजी", "grandfather": "आजोबा",
    "granddaughter": "नात", "grandson": "नातू", "grandchild": "नातवंड",
    "maternal aunt": "मावशी", "maternal uncle": "मामा", "paternal aunt": "आत्या", "paternal uncle": "काका",
    "aunt": "मावशी/आत्या", "uncle": "काका/मामा", "niece": "पुतणी/भाची", "nephew": "पुतण्या/भाचा",
    "half sister": "सावत्र बहीण", "half brother": "सावत्र भाऊ", "maternal cousin": "मामे/मावस भावंड",
    "paternal cousin": "चुलत/आतेभावंड", "cousin": "चुलत/मामे भावंड", "relative": "नातेवाईक", "other": "नातेवाईक",
}
