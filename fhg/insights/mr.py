"""Marathi for the action items (fhg/insights/rules.py) and the Lynch syndrome criteria (fhg/risk_models.py).

Keyed by the English template; {placeholders} must match. tests/test_insight_language.py fails if a template the
rules use is missing here. Written for the Pune pilot; needs review by a native speaker and a clinician before
families see it.
"""

MR: dict[str, str] = {
    # --- joining words and names --------------------------------------------------------------------
    " and ": " आणि ",
    " or ": " किंवा ",
    "You": "तुम्ही",
    "Placeholder": "अज्ञात व्यक्ती",
    "mother": "आई",
    "father": "वडील",
    "Mother": "आई",
    "Father": "वडील",
    "Parent": "आई/वडील",
    "Sister": "बहीण",
    "Brother": "भाऊ",
    "Sibling": "भावंड",
    "Daughter": "मुलगी",
    "Son": "मुलगा",
    "Child": "अपत्य",
    "Maternal grandmother": "आजी (आईकडील)",
    "Maternal grandfather": "आजोबा (आईकडील)",
    "Paternal grandmother": "आजी (वडिलांकडील)",
    "Paternal grandfather": "आजोबा (वडिलांकडील)",
    "Grandmother": "आजी",
    "Grandfather": "आजोबा",
    "Granddaughter": "नात",
    "Grandson": "नातू",
    "Grandchild": "नातवंड",
    "Maternal aunt": "मावशी",
    "Maternal uncle": "मामा",
    "Paternal aunt": "आत्या",
    "Paternal uncle": "काका",
    "Aunt": "मावशी/आत्या",
    "Uncle": "काका/मामा",
    "Niece": "पुतणी/भाची",
    "Nephew": "पुतण्या/भाचा",
    "Half sister": "सावत्र बहीण",
    "Half brother": "सावत्र भाऊ",
    "Maternal cousin": "मामे/मावस भावंड",
    "Paternal cousin": "चुलत/आतेभावंड",
    "Cousin": "चुलत/मामे भावंड",
    "Other": "इतर",

    # --- conditions ---------------------------------------------------------------------------------
    "Breast cancer": "स्तनाचा कर्करोग",
    "Ovarian cancer": "अंडाशयाचा कर्करोग",
    "Pancreatic cancer": "स्वादुपिंडाचा (पॅन्क्रियास) कर्करोग",
    "Prostate cancer": "प्रोस्टेटचा कर्करोग",
    "Colorectal cancer": "आतड्याचा (कोलोरेक्टल) कर्करोग",
    "Endometrial (uterine) cancer": "गर्भाशयाचा कर्करोग",
    "Stomach cancer": "जठराचा कर्करोग",
    "Melanoma": "मेलानोमा (त्वचेचा कर्करोग)",
    "Cancer (type not recorded)": "कर्करोग (प्रकार नोंदवलेला नाही)",
    "Coronary artery disease / heart attack": "हृदयविकार / हृदयविकाराचा झटका",
    "Congenital heart disease": "जन्मजात हृदयविकार",
    "Stroke": "पक्षाघात (स्ट्रोक)",
    "High blood pressure": "उच्च रक्तदाब (हाय BP)",
    "Familial hypercholesterolemia": "आनुवंशिक उच्च कोलेस्टेरॉल (FH)",
    "High cholesterol": "उच्च कोलेस्टेरॉल",
    "Type 1 diabetes": "टाइप 1 मधुमेह",
    "Type 2 diabetes": "टाइप 2 मधुमेह",
    "Known BRCA1/BRCA2 variant": "BRCA1/BRCA2 व्हेरिअंटची खात्री",
    "Lynch syndrome": "लिंच सिंड्रोम",
    "Malignant hyperthermia / anesthesia reaction": "मॅलिग्नंट हायपरथर्मिया / भुलीच्या औषधाची प्रतिक्रिया",
    "Alzheimer's disease / dementia": "अल्झायमर / विस्मरणाचा आजार",

    # --- evidence lines -----------------------------------------------------------------------------
    "age at diagnosis unknown": "निदानाचे वय माहीत नाही",
    "diagnosed at {age}": "वयाच्या {age} व्या वर्षी निदान",
    "diagnosed at about {age}": "साधारण वयाच्या {age} व्या वर्षी निदान",
    "You: {condition}": "तुम्ही: {condition}",
    "You: {condition}, diagnosed at {age}": "तुम्ही: {condition}, वयाच्या {age} व्या वर्षी निदान",
    "at {age}": "वयाच्या {age} व्या वर्षी",
    "(age unknown)": "(वय माहीत नाही)",
    "Your most recent LDL cholesterol: {value}": "तुमचे सर्वात अलीकडचे LDL कोलेस्टेरॉल: {value}",
    "{who}: LDL cholesterol {value} (from their lab report)": "{who}: LDL कोलेस्टेरॉल {value} (त्यांच्या लॅब रिपोर्टमधून)",
    "Your most recent HbA1c: {value}%": "तुमचे सर्वात अलीकडचे HbA1c: {value}%",
    "Your HbA1c rose from {first}% ({first_date}) to {last}% ({last_date})":
        "तुमचे HbA1c {first}% ({first_date}) वरून {last}% ({last_date}) पर्यंत वाढले",
    "Your most recent BMI: {value}": "तुमचा सर्वात अलीकडचा BMI: {value}",
    "Your most recent blood pressure: {reading}": "तुमचा सर्वात अलीकडचा BP: {reading}",
    "systolic {value}": "वरचा {value}",
    "diastolic {value}": "खालचा {value}",
    "Age {age}: {points} points": "वय {age}: {points} गुण",
    "Waist {value}: {points} points": "कंबर {value}: {points} गुण",
    "Activity ({activity}): {points} points": "हालचाल ({activity}): {points} गुण",
    "Parents with diabetes: {parents}: {points} points": "मधुमेह असलेले आई-वडील: {parents}: {points} गुण",
    "none recorded": "काहीही नोंदवलेले नाही",
    "regular exercise and an active job or housework": "नियमित व्यायाम आणि धावपळीचे काम किंवा घरकाम",
    "regular exercise or an active job, not both": "नियमित व्यायाम किंवा धावपळीचे काम, दोन्ही नाही",
    "no regular exercise and mostly sitting": "नियमित व्यायाम नाही आणि बहुतेक वेळ बसून",
    "waist size": "कंबरेचे माप",
    "sex": "लिंग",
    "physical activity": "शारीरिक हालचाल",

    # --- hereditary breast and ovarian cancer ---------------------------------------------------------
    "Family pattern worth a hereditary cancer risk assessment":
        "कुटुंबातील असा पॅटर्न ज्यासाठी आनुवंशिक कर्करोगाच्या जोखमीची तपासणी करून घ्यावी",
    "a relative has a known BRCA1/BRCA2 variant": "एका नातेवाइकामध्ये BRCA1/BRCA2 व्हेरिअंटची खात्री झाली आहे",
    "breast cancer at or before age 50 in a close relative": "जवळच्या नातेवाइकाला वयाच्या 50 किंवा त्याआधी स्तनाचा कर्करोग",
    "male breast cancer in the family": "कुटुंबातील एखाद्या पुरुषाला स्तनाचा कर्करोग",
    "ovarian cancer in a close relative (any age)": "जवळच्या नातेवाइकाला अंडाशयाचा कर्करोग (कोणत्याही वयात)",
    "pancreatic cancer in a close relative (any age)": "जवळच्या नातेवाइकाला स्वादुपिंडाचा कर्करोग (कोणत्याही वयात)",
    "two or more relatives with breast cancer on your maternal side": "आईकडील दोन किंवा जास्त नातेवाइकांना स्तनाचा कर्करोग",
    "two or more relatives with breast cancer on your paternal side": "वडिलांकडील दोन किंवा जास्त नातेवाइकांना स्तनाचा कर्करोग",
    "your own breast cancer diagnosis at or before 50": "तुम्हाला स्वतःला वयाच्या 50 किंवा त्याआधी स्तनाचा कर्करोग",
    "your own {condition} diagnosis": "तुम्हाला स्वतःला {condition}",
    "Your family history includes {reasons}. Patterns like this are the ones guidelines use to decide who should be "
    "offered genetic counseling for inherited cancer risk (for example BRCA1/BRCA2). It does not mean you have a "
    "variant.":
        "तुमच्या कौटुंबिक इतिहासात हे आहे: {reasons}. आनुवंशिक कर्करोगाच्या जोखमीसाठी (उदा. BRCA1/BRCA2) कोणाला जेनेटिक "
        "काउन्सेलिंग द्यावे, हे मार्गदर्शक तत्त्वे अशाच पॅटर्नवरून ठरवतात. याचा अर्थ तुमच्यात व्हेरिअंट आहे असा नाही.",
    "Ask your clinician about a formal familial risk assessment and, if appropriate, referral to a genetic counselor. "
    "If a relative has already had genetic testing, ask for a copy of their result: it makes your own testing far "
    "more informative. This applies to people of any sex; inherited variants also affect prostate, pancreatic and "
    "male breast cancer risk.":
        "तुमच्या डॉक्टरांना कौटुंबिक जोखमीच्या पूर्ण तपासणीबद्दल विचारा, आणि गरज असल्यास जेनेटिक काउन्सेलरकडे पाठवायला "
        "सांगा. एखाद्या नातेवाइकाची जेनेटिक चाचणी आधीच झाली असेल, तर तिच्या रिपोर्टची प्रत मागा: त्यामुळे तुमची स्वतःची "
        "चाचणी खूप जास्त उपयोगी ठरते. हे स्त्री आणि पुरुष दोघांनाही लागू आहे; आनुवंशिक व्हेरिअंटमुळे प्रोस्टेट, "
        "स्वादुपिंड आणि पुरुषांच्या स्तनाच्या कर्करोगाची जोखीमही वाढते.",

    # --- colorectal cancer and Lynch syndrome -----------------------------------------------------------
    "Colorectal cancer in the family may change when screening starts":
        "कुटुंबात आतड्याचा (कोलोरेक्टल) कर्करोग असल्याने तपासणी सुरू करण्याचे वय बदलू शकते",
    "a parent, sibling or child has had colorectal cancer": "आई-वडील, भावंड किंवा अपत्य यांपैकी कोणाला आतड्याचा कर्करोग झाला आहे",
    "Guidelines for this pattern suggest colonoscopy starting around age {start} (age 40, or 10 years before the "
    "youngest affected relative's diagnosis, whichever is earlier) and repeating about every 5 years.":
        "अशा पॅटर्नसाठी मार्गदर्शक तत्त्वे साधारण वयाच्या {start} व्या वर्षापासून कोलोनोस्कोपी सुरू करण्याचा सल्ला देतात "
        "(वय 40, किंवा सर्वात कमी वयात निदान झालेल्या नातेवाइकाच्या निदानाच्या 10 वर्षे आधी, जे आधी येईल ते), आणि "
        "साधारण दर 5 वर्षांनी पुन्हा करण्याचा.",
    "Guidelines for this pattern suggest starting screening at age 40 rather than 45.":
        "अशा पॅटर्नसाठी मार्गदर्शक तत्त्वे 45 ऐवजी वयाच्या 40 व्या वर्षापासून तपासणी सुरू करण्याचा सल्ला देतात.",
    "At least one relative's age at diagnosis is unknown; if it was before 60, screening may need to start earlier "
    "and be more frequent.":
        "किमान एका नातेवाइकाचे निदानाचे वय माहीत नाही; ते 60 च्या आधी असेल, तर तपासणी आणखी लवकर आणि जास्त वेळा करावी "
        "लागू शकते.",
    "You are {age}, so if you haven't been screened yet this is worth raising now.":
        "तुमचे वय {age} आहे, त्यामुळे अजून तपासणी झाली नसेल तर आताच डॉक्टरांशी बोलणे योग्य ठरेल.",
    "a known Lynch syndrome diagnosis in the family": "कुटुंबात लिंच सिंड्रोमची खात्री",
    "a pattern (early-onset or multiple Lynch-associated cancers) that can point to Lynch syndrome":
        "असा पॅटर्न (कमी वयात किंवा लिंचशी संबंधित अनेक कर्करोग) जो लिंच सिंड्रोमकडे निर्देश करू शकतो",
    "Ask about genetic counseling for Lynch syndrome, which raises the risk of colorectal, endometrial and several "
    "other cancers and changes screening substantially.":
        "लिंच सिंड्रोमसाठी जेनेटिक काउन्सेलिंगबद्दल विचारा. यामुळे आतडे, गर्भाशय आणि इतर अनेक कर्करोगांची जोखीम वाढते "
        "आणि तपासणीची पद्धत बरीच बदलते.",
    "Your record shows {findings}. The general-population screening start age is 45; family history can move it "
    "earlier.":
        "तुमच्या नोंदीत दिसते की {findings}. सर्वसामान्य लोकांसाठी तपासणी वयाच्या 45 व्या वर्षी सुरू होते; कौटुंबिक "
        "इतिहासामुळे ती आधी करावी लागू शकते.",
    "Family pattern meets Lynch syndrome criteria": "कुटुंबाचा पॅटर्न लिंच सिंड्रोमच्या निकषांशी जुळतो",
    "Your family meets the Amsterdam II criteria for Lynch syndrome: three or more relatives with Lynch-associated "
    "cancers across successive generations, one diagnosed before 50.":
        "तुमचे कुटुंब लिंच सिंड्रोमच्या Amsterdam II निकषांशी जुळते: सलग पिढ्यांमध्ये तीन किंवा जास्त नातेवाइकांना "
        "लिंचशी संबंधित कर्करोग, त्यांपैकी एकाचे निदान 50 च्या आधी.",
    "Someone in your family with colorectal cancer meets the revised Bethesda guidelines, which recommend testing "
    "their tumour (or genetic testing) for Lynch syndrome.":
        "तुमच्या कुटुंबातील आतड्याचा कर्करोग असलेली एक व्यक्ती सुधारित Bethesda मार्गदर्शक तत्त्वांशी जुळते. ही तत्त्वे "
        "लिंच सिंड्रोमसाठी त्यांच्या ट्यूमरची (किंवा जेनेटिक) चाचणी करण्याचा सल्ला देतात.",
    "Ask for genetic counseling. If a relative's colorectal or endometrial tumour can be tested for mismatch-repair "
    "deficiency, that is often the quickest first step. Confirmed Lynch syndrome means colonoscopy every 1-2 years, "
    "usually from age 20-25.":
        "जेनेटिक काउन्सेलिंग मागा. एखाद्या नातेवाइकाच्या आतड्याच्या किंवा गर्भाशयाच्या ट्यूमरची mismatch-repair चाचणी "
        "होऊ शकत असेल, तर बहुतेक वेळा तेच सर्वात जलद पहिले पाऊल असते. लिंच सिंड्रोमची खात्री झाल्यास साधारणपणे वयाच्या "
        "20-25 व्या वर्षापासून दर 1-2 वर्षांनी कोलोनोस्कोपी करावी लागते.",
    "Three or more relatives with a Lynch-associated cancer": "तीन किंवा जास्त नातेवाइकांना लिंचशी संबंधित कर्करोग",
    "One is a first-degree relative of the other two": "त्यांपैकी एक जण इतर दोघांचा जवळचा (प्रथम-श्रेणी) नातेवाईक आहे",
    "Two or more successive generations affected": "दोन किंवा जास्त सलग पिढ्या बाधित",
    "At least one diagnosed before 50": "किमान एकाचे निदान 50 च्या आधी",
    "Colorectal cancer diagnosed before 50": "आतड्याच्या कर्करोगाचे निदान 50 च्या आधी",
    "More than one Lynch-associated cancer in the same person": "एकाच व्यक्तीला लिंचशी संबंधित एकापेक्षा जास्त कर्करोग",
    "A first-degree relative with a Lynch-associated cancer, one of them diagnosed before 50":
        "एका जवळच्या नातेवाइकाला लिंचशी संबंधित कर्करोग, आणि दोघांपैकी एकाचे निदान 50 च्या आधी",
    "Two or more first- or second-degree relatives with Lynch-associated cancers, any age":
        "दोन किंवा जास्त जवळच्या किंवा दुसऱ्या श्रेणीच्या नातेवाइकांना लिंचशी संबंधित कर्करोग, कोणत्याही वयात",

    # --- heart disease and cholesterol ------------------------------------------------------------------
    "Early heart disease or stroke in a parent or sibling": "आई-वडील किंवा भावंडाला कमी वयात हृदयविकार किंवा पक्षाघात",
    "A first-degree relative had heart disease or stroke at a young age (men before 55, women before 65). Cardiology "
    "guidelines treat this as a 'risk-enhancing factor' that can tip decisions about cholesterol treatment.":
        "एका जवळच्या नातेवाइकाला कमी वयात हृदयविकार किंवा पक्षाघात झाला (पुरुषांमध्ये 55 च्या आधी, स्त्रियांमध्ये 65 च्या "
        "आधी). हृदयरोगतज्ज्ञांची मार्गदर्शक तत्त्वे याला 'जोखीम वाढवणारा घटक' मानतात, ज्यामुळे कोलेस्टेरॉलच्या "
        "उपचाराचा निर्णय बदलू शकतो.",
    "Combined with an LDL of 160 mg/dL or higher, this is worth discussing soon.":
        "याच्या जोडीला LDL 160 mg/dL किंवा जास्त आहे, त्यामुळे यावर लवकर बोलणे योग्य ठरेल.",
    "There's no cholesterol result in your record yet.": "तुमच्या नोंदीत अजून कोलेस्टेरॉलचा कोणताही निकाल नाही.",
    "Ask your clinician to estimate your 10-year cardiovascular risk with this family history included, check a "
    "lipid panel if you haven't recently, and consider measuring lipoprotein(a) at least once. Lp(a) is largely "
    "inherited and isn't part of a standard panel.":
        "हा कौटुंबिक इतिहास धरून तुमची पुढील 10 वर्षांची हृदयविकाराची जोखीम काढायला डॉक्टरांना सांगा. अलीकडे केली "
        "नसेल तर लिपिड प्रोफाइल करून घ्या, आणि किमान एकदा लिपोप्रोटीन(a) तपासण्याचा विचार करा. Lp(a) बहुतांशी "
        "आनुवंशिक असते आणि नेहमीच्या प्रोफाइलमध्ये नसते.",
    "Possible inherited high cholesterol (familial hypercholesterolemia)":
        "कदाचित आनुवंशिक उच्च कोलेस्टेरॉल (फॅमिलियल हायपरकोलेस्टेरोलेमिया)",
    "an LDL of 190 mg/dL or higher": "LDL 190 mg/dL किंवा जास्त आहे",
    "a relative diagnosed with familial hypercholesterolemia": "एका नातेवाइकामध्ये आनुवंशिक उच्च कोलेस्टेरॉलची (FH) खात्री झाली आहे",
    "a parent, sibling or child with an LDL of 190 mg/dL or higher":
        "आई-वडील, भावंड किंवा अपत्य यांपैकी कोणाचे LDL 190 mg/dL किंवा जास्त आहे",
    "Your record shows {findings}. Guidelines use this as a signal to look for familial hypercholesterolemia, a "
    "common inherited condition that is very treatable when found early.":
        "तुमच्या नोंदीत दिसते की {findings}. मार्गदर्शक तत्त्वे हे आनुवंशिक उच्च कोलेस्टेरॉलच्या (FH) तपासणीचे लक्षण "
        "मानतात. ही एक सामान्य आनुवंशिक स्थिती आहे, आणि लवकर कळल्यास तिच्यावर चांगले उपचार होऊ शकतात.",
    "Discuss evaluation for familial hypercholesterolemia with your clinician. If it is confirmed, your parents, "
    "siblings and children should also have their cholesterol checked.":
        "आनुवंशिक उच्च कोलेस्टेरॉलच्या (FH) तपासणीबद्दल तुमच्या डॉक्टरांशी बोला. खात्री झाल्यास तुमचे आई-वडील, भावंडे "
        "आणि मुले यांनीही आपले कोलेस्टेरॉल तपासून घ्यावे.",

    # --- diabetes ---------------------------------------------------------------------------------------
    "Type 2 diabetes risk": "टाइप 2 मधुमेहाची जोखीम",
    "your most recent HbA1c is in the diabetes range (6.5% or higher); a diagnosis needs a confirming test, so please "
    "follow up with your clinician":
        "तुमचे सर्वात अलीकडचे HbA1c मधुमेहाच्या पातळीत आहे (6.5% किंवा जास्त); खात्रीसाठी दुसरी चाचणी लागते, म्हणून "
        "तुमच्या डॉक्टरांना नक्की भेटा",
    "your most recent HbA1c is in the prediabetes range (5.7–6.4%)": "तुमचे सर्वात अलीकडचे HbA1c प्रीडायबिटीजच्या पातळीत आहे (5.7–6.4%)",
    "your HbA1c has been rising across your recent tests": "तुमच्या अलीकडच्या चाचण्यांमध्ये HbA1c सतत वाढत आहे",
    "a parent or sibling has type 2 diabetes": "आई-वडील किंवा भावंड यांपैकी कोणाला टाइप 2 मधुमेह आहे",
    "a parent or sibling has type 2 diabetes, and your BMI is 25 or higher":
        "आई-वडील किंवा भावंड यांपैकी कोणाला टाइप 2 मधुमेह आहे, आणि तुमचा BMI 25 किंवा जास्त आहे",
    "Your record shows {findings}.": "तुमच्या नोंदीत दिसते की {findings}.",
    "Ask about diabetes screening (an HbA1c or fasting glucose test). Family history plus overweight is a standard "
    "reason to screen, and prediabetes is often reversible with structured lifestyle programs such as the National "
    "Diabetes Prevention Program.":
        "मधुमेहाच्या तपासणीबद्दल (HbA1c किंवा उपाशीपोटी साखर) विचारा. कौटुंबिक इतिहासासोबत जास्त वजन हे तपासणीचे एक "
        "नेहमीचे कारण आहे, आणि प्रीडायबिटीज बहुतेक वेळा आहार आणि व्यायामाच्या नियमित कार्यक्रमाने बरी होऊ शकते.",
    "Indian Diabetes Risk Score: {score} of 100": "Indian Diabetes Risk Score: 100 पैकी {score}",
    "high (60 or more)": "जास्त (60 किंवा त्याहून अधिक)",
    "moderate (30–50)": "मध्यम (30–50)",
    "low (under 30)": "कमी (30 पेक्षा कमी)",
    "It may be higher: we don't have your {missing} yet.": "तो जास्त असू शकतो: आमच्याकडे अजून तुमचे {missing} नाही.",
    "Your score is {band}. This score was developed and validated for Indian adults; scores of 60 or more mean "
    "undiagnosed diabetes is much more likely.":
        "तुमचा स्कोअर {band} आहे. हा स्कोअर भारतीय प्रौढांसाठी तयार करून तपासलेला आहे; 60 किंवा जास्त स्कोअर म्हणजे "
        "निदान न झालेला मधुमेह असण्याची शक्यता खूप जास्त आहे.",
    "With a score of 60 or more, ask your doctor for a fasting blood sugar, HbA1c or glucose tolerance test.":
        "60 किंवा जास्त स्कोअर असल्यास डॉक्टरांना उपाशीपोटी साखर, HbA1c किंवा ग्लुकोज टॉलरन्स चाचणीसाठी सांगा.",
    "Keep your weight and waist in check and stay active; re-check your score every year or if anything changes.":
        "वजन आणि कंबरेच्या मापावर लक्ष ठेवा आणि सक्रिय राहा; दरवर्षी, किंवा काही बदलल्यास, तुमचा स्कोअर पुन्हा तपासा.",

    # --- prostate, anaesthesia, blood pressure ------------------------------------------------------------
    "Prostate cancer in close relatives": "जवळच्या नातेवाइकांमध्ये प्रोस्टेटचा कर्करोग",
    "A father, brother or son with prostate cancer (especially before 65) puts you in a higher-risk group for "
    "prostate cancer.":
        "वडील, भाऊ किंवा मुलाला प्रोस्टेटचा कर्करोग (विशेषतः 65 च्या आधी) असल्यास तुम्ही प्रोस्टेट कर्करोगाच्या जास्त "
        "जोखमीच्या गटात येता.",
    "This applies if you have a prostate.": "तुमच्या शरीरात प्रोस्टेट असेल तर हे लागू आहे.",
    "The American Cancer Society suggests higher-risk men talk with a clinician about PSA screening starting around "
    "age {start}, rather than 50.":
        "American Cancer Society चा सल्ला आहे की जास्त जोखमीच्या पुरुषांनी 50 ऐवजी साधारण वयाच्या {start} व्या "
        "वर्षापासून PSA तपासणीबद्दल डॉक्टरांशी बोलावे.",
    "Tell any surgical or anesthesia team about this family history":
        "कोणत्याही शस्त्रक्रिया किंवा भूल देणाऱ्या टीमला हा कौटुंबिक इतिहास नक्की सांगा",
    "Malignant hyperthermia is an inherited, potentially life-threatening reaction to some anesthesia drugs. Blood "
    "relatives of someone who had it may carry the same risk.":
        "मॅलिग्नंट हायपरथर्मिया ही भुलीच्या काही औषधांमुळे होणारी आनुवंशिक आणि जीवघेणी ठरू शकणारी प्रतिक्रिया आहे. "
        "ज्यांना ती झाली, त्यांच्या रक्ताच्या नातेवाइकांनाही हीच जोखीम असू शकते.",
    "Before any procedure that involves anesthesia (including dental surgery), tell the team about this history so "
    "they can use safe alternatives. Ask your clinician whether genetic testing or a medical alert ID is appropriate.":
        "भूल लागणाऱ्या कोणत्याही प्रक्रियेपूर्वी (दातांच्या शस्त्रक्रियेसह) टीमला हा इतिहास सांगा, म्हणजे ते सुरक्षित "
        "पर्याय वापरू शकतील. जेनेटिक चाचणी किंवा मेडिकल अलर्ट कार्ड योग्य ठरेल का, हे डॉक्टरांना विचारा.",
    "Blood pressure reading above target": "BP लक्ष्यापेक्षा जास्त",
    "severely elevated": "खूप जास्त वाढलेला",
    "in the stage 2 high blood pressure range": "उच्च रक्तदाबाच्या स्टेज 2 पातळीत",
    "in the stage 1 high blood pressure range": "उच्च रक्तदाबाच्या स्टेज 1 पातळीत",
    "Contact a clinician promptly to recheck it. If you have chest pain, shortness of breath, severe headache, "
    "weakness, or vision or speech changes, seek emergency care.":
        "तो पुन्हा तपासण्यासाठी लगेच डॉक्टरांशी संपर्क साधा. छातीत दुखणे, धाप लागणे, तीव्र डोकेदुखी, अशक्तपणा, किंवा "
        "दिसण्यात किंवा बोलण्यात बदल जाणवल्यास ताबडतोब इमर्जन्सीमध्ये जा.",
    "Ask your clinician about confirming this with repeat or home readings.":
        "पुन्हा किंवा घरी मोजून याची खात्री कशी करायची, हे डॉक्टरांना विचारा.",
    "One reading isn't a diagnosis; home monitoring over a few weeks gives a clearer picture.":
        "एकाच रीडिंगवरून निदान होत नाही; काही आठवडे घरी मोजल्यास स्पष्ट चित्र मिळते.",
    "Your most recent reading ({reading}) is {band} under the 2017 ACC/AHA definitions.":
        "2017 च्या ACC/AHA व्याख्यांनुसार तुमची सर्वात अलीकडची रीडिंग ({reading}) {band} आहे.",

    # --- the disclaimer under every report (fhg/insights/engine.py) ----------------------------------------
    "These insights are educational and based on simplified summaries of published guidelines. They are not a "
    "diagnosis and do not replace advice from a clinician or genetic counselor who knows your full history. The "
    "absence of an insight does not mean your risk is low; it may mean information is missing.":
        "हे सल्ले माहितीसाठी आहेत आणि प्रकाशित मार्गदर्शक तत्त्वांच्या सोप्या सारांशावर आधारित आहेत. हे निदान नाही, आणि "
        "तुमचा संपूर्ण इतिहास जाणणाऱ्या डॉक्टरांच्या किंवा जेनेटिक काउन्सेलरच्या सल्ल्याची जागा घेत नाही. एखादा सल्ला न "
        "दिसणे म्हणजे तुमची जोखीम कमी आहे असे नाही; कदाचित काही माहिती राहून गेली असेल.",

    # --- questions to ask the family --------------------------------------------------------------------
    "Questions to ask your family": "कुटुंबाला विचारायचे प्रश्न",
    "What type of cancer did your {who} have, and at what age?": "तुमच्या {who} यांना कोणत्या प्रकारचा कर्करोग होता, आणि कोणत्या वयात?",
    "How old was your {who} when diagnosed with {condition}? Age changes the guidance.":
        "तुमच्या {who} यांना {condition} चे निदान कोणत्या वयात झाले? वयानुसार सल्ला बदलतो.",
    "Can you find out more about your {who}'s '{name}'?": "तुमच्या {who} यांच्या '{name}' बद्दल आणखी माहिती मिळवू शकाल का?",
    "Add your mother's health history (even 'no known conditions' helps).":
        "तुमच्या आईचा आरोग्य इतिहास जोडा ('कोणताही माहीत असलेला आजार नाही' हेही उपयोगी आहे).",
    "Add your father's health history (even 'no known conditions' helps).":
        "तुमच्या वडिलांचा आरोग्य इतिहास जोडा ('कोणताही माहीत असलेला आजार नाही' हेही उपयोगी आहे).",
    "Add what you know about your grandparents on both sides.": "दोन्ही बाजूंच्या आजी-आजोबांबद्दल जे माहीत आहे ते जोडा.",
    "Add your date of birth and sex so age- and sex-specific guidance can apply.":
        "तुमची जन्मतारीख आणि लिंग जोडा, म्हणजे वय आणि लिंगानुसार सल्ला मिळू शकेल.",
    "Invite a parent or sibling to add their own history. When they share it, your insights update automatically, "
    "and theirs do too.":
        "आई-वडील किंवा भावंडांना त्यांचा स्वतःचा इतिहास जोडण्यासाठी आमंत्रित करा. त्यांनी तो शेअर केल्यावर तुमचे आणि "
        "त्यांचे सल्ले आपोआप अपडेट होतील.",
    "A few missing details could change your insights. Family gatherings are a good time to ask; relatives can also "
    "be invited to add their own history.":
        "राहून गेलेल्या काही गोष्टींमुळे तुमचे सल्ले बदलू शकतात. कुटुंब एकत्र जमते तेव्हा विचारणे चांगले; नातेवाइकांना "
        "त्यांचा इतिहास जोडण्यासाठी आमंत्रितही करता येते.",
    "Fill in what you can; your insights update automatically.": "जे माहीत आहे ते भरा; तुमचे सल्ले आपोआप अपडेट होतील.",
}
