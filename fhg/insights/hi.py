"""Hindi for the action items (fhg/insights/rules.py) and the Lynch syndrome criteria (fhg/risk_models.py).

Keyed by the English template; {placeholders} must match. tests/test_insight_language.py fails if a template the
rules use is missing here. Needs review by a native speaker and a clinician before families see it.
"""

HI: dict[str, str] = {
    # --- joining words and names --------------------------------------------------------------------
    " and ": " और ",
    " or ": " या ",
    "You": "आप",
    "Placeholder": "अज्ञात व्यक्ति",
    "mother": "माँ",
    "father": "पिता",
    "Mother": "माँ",
    "Father": "पिता",
    "Parent": "माता/पिता",
    "Sister": "बहन",
    "Brother": "भाई",
    "Sibling": "भाई/बहन",
    "Daughter": "बेटी",
    "Son": "बेटा",
    "Child": "संतान",
    "Maternal grandmother": "नानी",
    "Maternal grandfather": "नाना",
    "Paternal grandmother": "दादी",
    "Paternal grandfather": "दादा",
    "Grandmother": "दादी/नानी",
    "Grandfather": "दादा/नाना",
    "Granddaughter": "पोती/नातिन",
    "Grandson": "पोता/नाती",
    "Grandchild": "पोता-पोती/नाती-नातिन",
    "Maternal aunt": "मौसी",
    "Maternal uncle": "मामा",
    "Paternal aunt": "बुआ",
    "Paternal uncle": "चाचा/ताऊ",
    "Aunt": "मौसी/बुआ",
    "Uncle": "चाचा/मामा",
    "Niece": "भतीजी/भांजी",
    "Nephew": "भतीजा/भांजा",
    "Half sister": "सौतेली बहन",
    "Half brother": "सौतेला भाई",
    "Maternal cousin": "ममेरे/मौसेरे भाई-बहन",
    "Paternal cousin": "चचेरे/फुफेरे भाई-बहन",
    "Cousin": "चचेरे/ममेरे भाई-बहन",
    "Other": "अन्य",

    # --- conditions ---------------------------------------------------------------------------------
    "Breast cancer": "स्तन कैंसर",
    "Ovarian cancer": "अंडाशय का कैंसर",
    "Pancreatic cancer": "अग्न्याशय (पैंक्रियास) का कैंसर",
    "Prostate cancer": "प्रोस्टेट कैंसर",
    "Colorectal cancer": "आँत (कोलोरेक्टल) का कैंसर",
    "Endometrial (uterine) cancer": "गर्भाशय का कैंसर",
    "Stomach cancer": "पेट का कैंसर",
    "Melanoma": "मेलानोमा (त्वचा का कैंसर)",
    "Cancer (type not recorded)": "कैंसर (प्रकार दर्ज नहीं)",
    "Coronary artery disease / heart attack": "दिल की बीमारी / दिल का दौरा",
    "Congenital heart disease": "जन्मजात दिल की बीमारी",
    "Stroke": "स्ट्रोक (लकवा)",
    "High blood pressure": "हाई BP",
    "Familial hypercholesterolemia": "विरासत में मिला हाई कोलेस्ट्रॉल (FH)",
    "High cholesterol": "हाई कोलेस्ट्रॉल",
    "Type 1 diabetes": "टाइप 1 डायबिटीज़",
    "Type 2 diabetes": "टाइप 2 डायबिटीज़",
    "Known BRCA1/BRCA2 variant": "BRCA1/BRCA2 वैरिएंट की पुष्टि",
    "Lynch syndrome": "लिंच सिंड्रोम",
    "Malignant hyperthermia / anesthesia reaction": "मैलिग्नेंट हाइपरथर्मिया / बेहोशी की दवा से प्रतिक्रिया",
    "Alzheimer's disease / dementia": "अल्ज़ाइमर / भूलने की बीमारी",

    # --- evidence lines -----------------------------------------------------------------------------
    "age at diagnosis unknown": "पता चलने की उम्र मालूम नहीं",
    "diagnosed at {age}": "{age} की उम्र में पता चला",
    "diagnosed at about {age}": "लगभग {age} की उम्र में पता चला",
    "You: {condition}": "आप: {condition}",
    "You: {condition}, diagnosed at {age}": "आप: {condition}, {age} की उम्र में पता चला",
    "at {age}": "{age} की उम्र में",
    "(age unknown)": "(उम्र मालूम नहीं)",
    "Your most recent LDL cholesterol: {value}": "आपका सबसे हाल का LDL कोलेस्ट्रॉल: {value}",
    "{who}: LDL cholesterol {value} (from their lab report)": "{who}: LDL कोलेस्ट्रॉल {value} (उनकी लैब रिपोर्ट से)",
    "Your most recent HbA1c: {value}%": "आपका सबसे हाल का HbA1c: {value}%",
    "Your HbA1c rose from {first}% ({first_date}) to {last}% ({last_date})":
        "आपका HbA1c {first}% ({first_date}) से बढ़कर {last}% ({last_date}) हो गया",
    "Your most recent BMI: {value}": "आपका सबसे हाल का BMI: {value}",
    "Your most recent blood pressure: {reading}": "आपका सबसे हाल का BP: {reading}",
    "systolic {value}": "ऊपर वाला {value}",
    "diastolic {value}": "नीचे वाला {value}",
    "Age {age}: {points} points": "उम्र {age}: {points} अंक",
    "Waist {value}: {points} points": "कमर {value}: {points} अंक",
    "Activity ({activity}): {points} points": "गतिविधि ({activity}): {points} अंक",
    "Parents with diabetes: {parents}: {points} points": "डायबिटीज़ वाले माता-पिता: {parents}: {points} अंक",
    "none recorded": "कोई दर्ज नहीं",
    "regular exercise and an active job or housework": "नियमित व्यायाम और सक्रिय काम या घर का काम",
    "regular exercise or an active job, not both": "नियमित व्यायाम या सक्रिय काम, दोनों नहीं",
    "no regular exercise and mostly sitting": "नियमित व्यायाम नहीं और ज़्यादातर बैठे रहना",
    "waist size": "कमर का नाप",
    "sex": "लिंग",
    "physical activity": "शारीरिक गतिविधि",

    # --- hereditary breast and ovarian cancer ---------------------------------------------------------
    "Family pattern worth a hereditary cancer risk assessment":
        "परिवार में ऐसा पैटर्न जिसके लिए वंशानुगत कैंसर जोखिम की जाँच करानी चाहिए",
    "a relative has a known BRCA1/BRCA2 variant": "एक रिश्तेदार में BRCA1/BRCA2 वैरिएंट की पुष्टि हुई है",
    "breast cancer at or before age 50 in a close relative": "किसी क़रीबी रिश्तेदार को 50 या उससे कम उम्र में स्तन कैंसर",
    "male breast cancer in the family": "परिवार में किसी पुरुष को स्तन कैंसर",
    "ovarian cancer in a close relative (any age)": "किसी क़रीबी रिश्तेदार को अंडाशय का कैंसर (किसी भी उम्र में)",
    "pancreatic cancer in a close relative (any age)": "किसी क़रीबी रिश्तेदार को अग्न्याशय का कैंसर (किसी भी उम्र में)",
    "two or more relatives with breast cancer on your maternal side": "माँ की तरफ़ दो या ज़्यादा रिश्तेदारों को स्तन कैंसर",
    "two or more relatives with breast cancer on your paternal side": "पिता की तरफ़ दो या ज़्यादा रिश्तेदारों को स्तन कैंसर",
    "your own breast cancer diagnosis at or before 50": "आपको खुद 50 या उससे कम उम्र में स्तन कैंसर",
    "your own {condition} diagnosis": "आपको खुद {condition}",
    "Your family history includes {reasons}. Patterns like this are the ones guidelines use to decide who should be "
    "offered genetic counseling for inherited cancer risk (for example BRCA1/BRCA2). It does not mean you have a "
    "variant.":
        "आपके पारिवारिक इतिहास में यह है: {reasons}। दिशानिर्देश ऐसे ही पैटर्न देखकर तय करते हैं कि किसे विरासत में मिले "
        "कैंसर जोखिम (जैसे BRCA1/BRCA2) के लिए जेनेटिक काउंसलिंग दी जानी चाहिए। इसका मतलब यह नहीं कि आपमें कोई "
        "वैरिएंट है।",
    "Ask your clinician about a formal familial risk assessment and, if appropriate, referral to a genetic counselor. "
    "If a relative has already had genetic testing, ask for a copy of their result: it makes your own testing far "
    "more informative. This applies to people of any sex; inherited variants also affect prostate, pancreatic and "
    "male breast cancer risk.":
        "अपने डॉक्टर से पारिवारिक जोखिम की पूरी जाँच के बारे में पूछें, और ज़रूरत हो तो जेनेटिक काउंसलर के पास भेजने "
        "को कहें। अगर किसी रिश्तेदार का जेनेटिक टेस्ट हो चुका है, तो उसकी रिपोर्ट की कॉपी माँगें: इससे आपका अपना टेस्ट "
        "कहीं ज़्यादा उपयोगी होता है। यह महिलाओं और पुरुषों दोनों पर लागू है; विरासत में मिले वैरिएंट प्रोस्टेट, "
        "अग्न्याशय और पुरुषों के स्तन कैंसर का जोखिम भी बढ़ाते हैं।",

    # --- colorectal cancer and Lynch syndrome -----------------------------------------------------------
    "Colorectal cancer in the family may change when screening starts":
        "परिवार में आँत (कोलोरेक्टल) का कैंसर होने से जाँच शुरू करने की उम्र बदल सकती है",
    "a parent, sibling or child has had colorectal cancer": "माता-पिता, भाई-बहन या संतान में से किसी को आँत का कैंसर हुआ है",
    "Guidelines for this pattern suggest colonoscopy starting around age {start} (age 40, or 10 years before the "
    "youngest affected relative's diagnosis, whichever is earlier) and repeating about every 5 years.":
        "ऐसे पैटर्न के लिए दिशानिर्देश लगभग {start} की उम्र से कोलोनोस्कोपी शुरू करने की सलाह देते हैं (40 की उम्र, या "
        "सबसे कम उम्र वाले प्रभावित रिश्तेदार के पता चलने से 10 साल पहले, जो भी पहले हो), और लगभग हर 5 साल में "
        "दोहराने की।",
    "Guidelines for this pattern suggest starting screening at age 40 rather than 45.":
        "ऐसे पैटर्न के लिए दिशानिर्देश 45 के बजाय 40 की उम्र से जाँच शुरू करने की सलाह देते हैं।",
    "At least one relative's age at diagnosis is unknown; if it was before 60, screening may need to start earlier "
    "and be more frequent.":
        "कम से कम एक रिश्तेदार के बीमारी पता चलने की उम्र मालूम नहीं है; अगर वह 60 से पहले थी, तो जाँच और पहले और "
        "ज़्यादा बार करानी पड़ सकती है।",
    "You are {age}, so if you haven't been screened yet this is worth raising now.":
        "आपकी उम्र {age} है, इसलिए अगर अब तक जाँच नहीं हुई है तो अभी डॉक्टर से बात करना ठीक रहेगा।",
    "a known Lynch syndrome diagnosis in the family": "परिवार में लिंच सिंड्रोम की पुष्टि",
    "a pattern (early-onset or multiple Lynch-associated cancers) that can point to Lynch syndrome":
        "ऐसा पैटर्न (कम उम्र में या कई लिंच से जुड़े कैंसर) जो लिंच सिंड्रोम की ओर इशारा कर सकता है",
    "Ask about genetic counseling for Lynch syndrome, which raises the risk of colorectal, endometrial and several "
    "other cancers and changes screening substantially.":
        "लिंच सिंड्रोम के लिए जेनेटिक काउंसलिंग के बारे में पूछें। यह आँत, गर्भाशय और कई दूसरे कैंसर का जोखिम बढ़ाता "
        "है और जाँच का तरीका काफ़ी बदल देता है।",
    "Your record shows {findings}. The general-population screening start age is 45; family history can move it "
    "earlier.":
        "आपके रिकॉर्ड में दिखता है कि {findings}। आम लोगों के लिए जाँच 45 की उम्र से शुरू होती है; पारिवारिक इतिहास "
        "से यह पहले हो सकती है।",
    "Family pattern meets Lynch syndrome criteria": "परिवार का पैटर्न लिंच सिंड्रोम के मानदंडों से मेल खाता है",
    "Your family meets the Amsterdam II criteria for Lynch syndrome: three or more relatives with Lynch-associated "
    "cancers across successive generations, one diagnosed before 50.":
        "आपका परिवार लिंच सिंड्रोम के Amsterdam II मानदंडों से मेल खाता है: लगातार पीढ़ियों में तीन या ज़्यादा "
        "रिश्तेदारों को लिंच से जुड़ा कैंसर, जिनमें से एक को 50 से पहले।",
    "Someone in your family with colorectal cancer meets the revised Bethesda guidelines, which recommend testing "
    "their tumour (or genetic testing) for Lynch syndrome.":
        "आपके परिवार में आँत के कैंसर वाला कोई व्यक्ति संशोधित Bethesda दिशानिर्देशों से मेल खाता है, जो लिंच सिंड्रोम "
        "के लिए उनके ट्यूमर की (या जेनेटिक) जाँच की सलाह देते हैं।",
    "Ask for genetic counseling. If a relative's colorectal or endometrial tumour can be tested for mismatch-repair "
    "deficiency, that is often the quickest first step. Confirmed Lynch syndrome means colonoscopy every 1-2 years, "
    "usually from age 20-25.":
        "जेनेटिक काउंसलिंग माँगें। अगर किसी रिश्तेदार के आँत या गर्भाशय के ट्यूमर की mismatch-repair जाँच हो सकती "
        "है, तो अक्सर वही सबसे जल्दी पहला कदम होता है। लिंच सिंड्रोम की पुष्टि होने पर आम तौर पर 20-25 की उम्र से हर 1-2 "
        "साल में कोलोनोस्कोपी करानी होती है।",
    "Three or more relatives with a Lynch-associated cancer": "तीन या ज़्यादा रिश्तेदारों को लिंच से जुड़ा कैंसर",
    "One is a first-degree relative of the other two": "उनमें से एक बाकी दोनों का नज़दीकी (प्रथम-श्रेणी) रिश्तेदार है",
    "Two or more successive generations affected": "दो या ज़्यादा लगातार पीढ़ियाँ प्रभावित",
    "At least one diagnosed before 50": "कम से कम एक को 50 से पहले पता चला",
    "Colorectal cancer diagnosed before 50": "आँत का कैंसर 50 से पहले पता चला",
    "More than one Lynch-associated cancer in the same person": "एक ही व्यक्ति को एक से ज़्यादा लिंच से जुड़े कैंसर",
    "A first-degree relative with a Lynch-associated cancer, one of them diagnosed before 50":
        "एक नज़दीकी रिश्तेदार को लिंच से जुड़ा कैंसर, और दोनों में से किसी एक को 50 से पहले पता चला",
    "Two or more first- or second-degree relatives with Lynch-associated cancers, any age":
        "दो या ज़्यादा नज़दीकी या दूसरे दर्जे के रिश्तेदारों को लिंच से जुड़ा कैंसर, किसी भी उम्र में",

    # --- heart disease and cholesterol ------------------------------------------------------------------
    "Early heart disease or stroke in a parent or sibling": "माता-पिता या भाई-बहन को कम उम्र में दिल की बीमारी या स्ट्रोक",
    "A first-degree relative had heart disease or stroke at a young age (men before 55, women before 65). Cardiology "
    "guidelines treat this as a 'risk-enhancing factor' that can tip decisions about cholesterol treatment.":
        "एक नज़दीकी रिश्तेदार को कम उम्र में दिल की बीमारी या स्ट्रोक हुआ (पुरुषों में 55 से पहले, महिलाओं में 65 से "
        "पहले)। दिल के डॉक्टरों के दिशानिर्देश इसे 'जोखिम बढ़ाने वाला कारण' मानते हैं, जिससे कोलेस्ट्रॉल के इलाज का "
        "फ़ैसला बदल सकता है।",
    "Combined with an LDL of 160 mg/dL or higher, this is worth discussing soon.":
        "इसके साथ LDL 160 mg/dL या ज़्यादा है, इसलिए इस पर जल्द बात करना ठीक रहेगा।",
    "There's no cholesterol result in your record yet.": "आपके रिकॉर्ड में अभी कोई कोलेस्ट्रॉल नतीजा नहीं है।",
    "Ask your clinician to estimate your 10-year cardiovascular risk with this family history included, check a "
    "lipid panel if you haven't recently, and consider measuring lipoprotein(a) at least once. Lp(a) is largely "
    "inherited and isn't part of a standard panel.":
        "अपने डॉक्टर से कहें कि इस पारिवारिक इतिहास को शामिल करके आपका 10 साल का दिल की बीमारी का जोखिम निकालें। हाल "
        "में नहीं कराया है तो लिपिड प्रोफ़ाइल कराएँ, और कम से कम एक बार लिपोप्रोटीन(a) की जाँच पर विचार करें। Lp(a) "
        "ज़्यादातर विरासत में मिलता है और सामान्य प्रोफ़ाइल में शामिल नहीं होता।",
    "Possible inherited high cholesterol (familial hypercholesterolemia)":
        "संभवतः विरासत में मिला हाई कोलेस्ट्रॉल (फ़ैमिलियल हाइपरकोलेस्टेरोलेमिया)",
    "an LDL of 190 mg/dL or higher": "LDL 190 mg/dL या ज़्यादा है",
    "a relative diagnosed with familial hypercholesterolemia": "एक रिश्तेदार में विरासत वाले हाई कोलेस्ट्रॉल (FH) की पुष्टि हुई है",
    "a parent, sibling or child with an LDL of 190 mg/dL or higher":
        "माता-पिता, भाई-बहन या संतान में से किसी का LDL 190 mg/dL या ज़्यादा है",
    "Your record shows {findings}. Guidelines use this as a signal to look for familial hypercholesterolemia, a "
    "common inherited condition that is very treatable when found early.":
        "आपके रिकॉर्ड में दिखता है कि {findings}। दिशानिर्देश इसे विरासत वाले हाई कोलेस्ट्रॉल (FH) की जाँच का संकेत "
        "मानते हैं। यह एक आम विरासती स्थिति है, और जल्दी पता चलने पर इसका इलाज बहुत अच्छे से हो सकता है।",
    "Discuss evaluation for familial hypercholesterolemia with your clinician. If it is confirmed, your parents, "
    "siblings and children should also have their cholesterol checked.":
        "अपने डॉक्टर से विरासत वाले हाई कोलेस्ट्रॉल (FH) की जाँच के बारे में बात करें। पुष्टि होने पर आपके माता-पिता, "
        "भाई-बहन और बच्चों को भी अपना कोलेस्ट्रॉल जँचवाना चाहिए।",

    # --- diabetes ---------------------------------------------------------------------------------------
    "Type 2 diabetes risk": "टाइप 2 डायबिटीज़ का जोखिम",
    "your most recent HbA1c is in the diabetes range (6.5% or higher); a diagnosis needs a confirming test, so please "
    "follow up with your clinician":
        "आपका सबसे हाल का HbA1c डायबिटीज़ की सीमा में है (6.5% या ज़्यादा); पक्का निदान दूसरे टेस्ट से होता है, इसलिए "
        "अपने डॉक्टर से ज़रूर मिलें",
    "your most recent HbA1c is in the prediabetes range (5.7–6.4%)": "आपका सबसे हाल का HbA1c प्रीडायबिटीज़ की सीमा में है (5.7–6.4%)",
    "your HbA1c has been rising across your recent tests": "आपके हाल के टेस्ट में HbA1c लगातार बढ़ रहा है",
    "a parent or sibling has type 2 diabetes": "माता-पिता या भाई-बहन में से किसी को टाइप 2 डायबिटीज़ है",
    "a parent or sibling has type 2 diabetes, and your BMI is 25 or higher":
        "माता-पिता या भाई-बहन में से किसी को टाइप 2 डायबिटीज़ है, और आपका BMI 25 या ज़्यादा है",
    "Your record shows {findings}.": "आपके रिकॉर्ड में दिखता है कि {findings}।",
    "Ask about diabetes screening (an HbA1c or fasting glucose test). Family history plus overweight is a standard "
    "reason to screen, and prediabetes is often reversible with structured lifestyle programs such as the National "
    "Diabetes Prevention Program.":
        "डायबिटीज़ की जाँच (HbA1c या खाली पेट शुगर) के बारे में पूछें। पारिवारिक इतिहास के साथ ज़्यादा वज़न जाँच का एक "
        "आम कारण है, और प्रीडायबिटीज़ अक्सर खान-पान और व्यायाम के नियमित कार्यक्रम से ठीक हो सकती है।",
    "Indian Diabetes Risk Score: {score} of 100": "Indian Diabetes Risk Score: 100 में से {score}",
    "high (60 or more)": "ज़्यादा (60 या उससे ऊपर)",
    "moderate (30–50)": "मध्यम (30–50)",
    "low (under 30)": "कम (30 से नीचे)",
    "It may be higher: we don't have your {missing} yet.": "यह ज़्यादा हो सकता है: हमारे पास अभी आपका {missing} नहीं है।",
    "Your score is {band}. This score was developed and validated for Indian adults; scores of 60 or more mean "
    "undiagnosed diabetes is much more likely.":
        "आपका स्कोर {band} है। यह स्कोर भारतीय वयस्कों के लिए बनाया और परखा गया है; 60 या ज़्यादा स्कोर का मतलब है कि "
        "बिना पता चली डायबिटीज़ की संभावना काफ़ी ज़्यादा है।",
    "With a score of 60 or more, ask your doctor for a fasting blood sugar, HbA1c or glucose tolerance test.":
        "60 या ज़्यादा स्कोर पर अपने डॉक्टर से खाली पेट शुगर, HbA1c या ग्लूकोज़ टॉलरेंस टेस्ट के लिए कहें।",
    "Keep your weight and waist in check and stay active; re-check your score every year or if anything changes.":
        "वज़न और कमर पर ध्यान रखें और सक्रिय रहें; हर साल, या कुछ बदलने पर, अपना स्कोर फिर से जाँचें।",

    # --- prostate, anaesthesia, blood pressure ------------------------------------------------------------
    "Prostate cancer in close relatives": "क़रीबी रिश्तेदारों में प्रोस्टेट कैंसर",
    "A father, brother or son with prostate cancer (especially before 65) puts you in a higher-risk group for "
    "prostate cancer.":
        "पिता, भाई या बेटे को प्रोस्टेट कैंसर (ख़ासकर 65 से पहले) होने से आप प्रोस्टेट कैंसर के ज़्यादा जोखिम वाले "
        "समूह में आते हैं।",
    "This applies if you have a prostate.": "यह तब लागू है जब आपके शरीर में प्रोस्टेट है।",
    "The American Cancer Society suggests higher-risk men talk with a clinician about PSA screening starting around "
    "age {start}, rather than 50.":
        "American Cancer Society की सलाह है कि ज़्यादा जोखिम वाले पुरुष 50 के बजाय लगभग {start} की उम्र से PSA जाँच के "
        "बारे में डॉक्टर से बात करें।",
    "Tell any surgical or anesthesia team about this family history":
        "किसी भी सर्जरी या बेहोशी देने वाली टीम को यह पारिवारिक इतिहास ज़रूर बताएँ",
    "Malignant hyperthermia is an inherited, potentially life-threatening reaction to some anesthesia drugs. Blood "
    "relatives of someone who had it may carry the same risk.":
        "मैलिग्नेंट हाइपरथर्मिया बेहोशी की कुछ दवाओं से होने वाली विरासती और जानलेवा हो सकने वाली प्रतिक्रिया है। "
        "जिसे यह हुआ हो, उसके ख़ून के रिश्तेदारों को भी यही जोखिम हो सकता है।",
    "Before any procedure that involves anesthesia (including dental surgery), tell the team about this history so "
    "they can use safe alternatives. Ask your clinician whether genetic testing or a medical alert ID is appropriate.":
        "बेहोशी वाली किसी भी प्रक्रिया (दाँतों की सर्जरी सहित) से पहले टीम को यह इतिहास बताएँ, ताकि वे सुरक्षित "
        "विकल्प इस्तेमाल करें। अपने डॉक्टर से पूछें कि जेनेटिक टेस्ट या मेडिकल अलर्ट कार्ड ठीक रहेगा या नहीं।",
    "Blood pressure reading above target": "BP लक्ष्य से ज़्यादा",
    "severely elevated": "बहुत ज़्यादा बढ़ा हुआ",
    "in the stage 2 high blood pressure range": "हाई BP की स्टेज 2 सीमा में",
    "in the stage 1 high blood pressure range": "हाई BP की स्टेज 1 सीमा में",
    "Contact a clinician promptly to recheck it. If you have chest pain, shortness of breath, severe headache, "
    "weakness, or vision or speech changes, seek emergency care.":
        "इसे दोबारा जँचवाने के लिए तुरंत डॉक्टर से संपर्क करें। अगर सीने में दर्द, साँस फूलना, तेज़ सिरदर्द, कमज़ोरी, या "
        "देखने या बोलने में बदलाव हो, तो तुरंत इमरजेंसी में जाएँ।",
    "Ask your clinician about confirming this with repeat or home readings.":
        "अपने डॉक्टर से पूछें कि दोबारा या घर पर नापकर इसकी पुष्टि कैसे करें।",
    "One reading isn't a diagnosis; home monitoring over a few weeks gives a clearer picture.":
        "एक बार की रीडिंग से बीमारी तय नहीं होती; कुछ हफ़्ते घर पर नापने से साफ़ तस्वीर मिलती है।",
    "Your most recent reading ({reading}) is {band} under the 2017 ACC/AHA definitions.":
        "2017 ACC/AHA परिभाषाओं के अनुसार आपकी सबसे हाल की रीडिंग ({reading}) {band} है।",

    # --- the disclaimer under every report (fhg/insights/engine.py) ----------------------------------------
    "These insights are educational and based on simplified summaries of published guidelines. They are not a "
    "diagnosis and do not replace advice from a clinician or genetic counselor who knows your full history. The "
    "absence of an insight does not mean your risk is low; it may mean information is missing.":
        "ये सलाह शैक्षिक हैं और प्रकाशित दिशानिर्देशों के सरल सारांश पर आधारित हैं। ये निदान नहीं हैं और उस डॉक्टर या "
        "जेनेटिक काउंसलर की सलाह की जगह नहीं लेतीं जो आपका पूरा इतिहास जानता हो। कोई सलाह न दिखने का मतलब यह नहीं कि "
        "आपका जोखिम कम है; हो सकता है कुछ जानकारी छूटी हो।",

    # --- questions to ask the family --------------------------------------------------------------------
    "Questions to ask your family": "परिवार से पूछने वाले सवाल",
    "What type of cancer did your {who} have, and at what age?": "आपके/आपकी {who} को किस तरह का कैंसर था, और किस उम्र में?",
    "How old was your {who} when diagnosed with {condition}? Age changes the guidance.":
        "आपके/आपकी {who} को {condition} किस उम्र में पता चला? उम्र से सलाह बदल जाती है।",
    "Can you find out more about your {who}'s '{name}'?": "क्या आप अपने/अपनी {who} की '{name}' के बारे में और पता कर सकते हैं?",
    "Add your mother's health history (even 'no known conditions' helps).":
        "अपनी माँ का स्वास्थ्य इतिहास जोड़ें ('कोई ज्ञात बीमारी नहीं' भी काम का है)।",
    "Add your father's health history (even 'no known conditions' helps).":
        "अपने पिता का स्वास्थ्य इतिहास जोड़ें ('कोई ज्ञात बीमारी नहीं' भी काम का है)।",
    "Add what you know about your grandparents on both sides.": "दोनों तरफ़ के दादा-दादी और नाना-नानी के बारे में जो पता है, जोड़ें।",
    "Add your date of birth and sex so age- and sex-specific guidance can apply.":
        "अपनी जन्म तिथि और लिंग जोड़ें, ताकि उम्र और लिंग के हिसाब से सलाह मिल सके।",
    "Invite a parent or sibling to add their own history. When they share it, your insights update automatically, "
    "and theirs do too.":
        "माता-पिता या भाई-बहन को अपना इतिहास जोड़ने के लिए बुलाएँ। जब वे साझा करेंगे, आपकी और उनकी सलाह अपने आप "
        "अपडेट हो जाएगी।",
    "A few missing details could change your insights. Family gatherings are a good time to ask; relatives can also "
    "be invited to add their own history.":
        "कुछ छूटी हुई बातें आपकी सलाह बदल सकती हैं। परिवार के मिलने-जुलने पर पूछना अच्छा रहता है; रिश्तेदारों को उनका "
        "इतिहास जोड़ने के लिए बुलाया भी जा सकता है।",
    "Fill in what you can; your insights update automatically.": "जो पता है वह भरें; आपकी सलाह अपने आप अपडेट हो जाएगी।",
}
