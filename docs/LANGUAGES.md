# Languages

The app is in **English, Hindi and Marathi** (Marathi for the Pune pilot). The WhatsApp assistant also replies in
Bengali, Tamil and Telugu ([fhg/i18n.py](../fhg/i18n.py)).

## How the app's translations work

- UI strings are written in English and wrapped: `t('Add a medicine')`, or with values
  `t('{n} days left', { n })`. The English text is the key; a missing translation falls back to English.
- Hindi lives in `mobile/src/locales/hi.ts`, Marathi in `mobile/src/locales/mr.ts`.
- Strings defined ahead of time (tables, lists) are marked with `N('…')` and translated where they are shown.
- `mobile/tests/translations.test.ts` (part of `npm test`, so CI) fails if any wrapped string has no Hindi or no
  Marathi, or a translation drops or renames a `{placeholder}`. It prints the missing strings ready to paste.
- The app starts in the phone's language (Hindi or Marathi if the phone is set to one) and can be switched in
  **Settings → Language**. The choice is also saved on the server (`PUT /v1/profile/language`).

## What follows the person's language on the server

The server keeps each person's language (`PUT /v1/profile/language`) and uses it for everything it writes to them:

- **Action items.** Title, summary, evidence and what to do, plus the risk page and the disclaimer. The rules in
  `fhg/insights/rules.py` write all their text through `tr("English template {value}", value=...)`, and the
  translations are in `fhg/insights/hi.py` and `fhg/insights/mr.py`. `GET /v1/insights?lang=mr` overrides the
  stored language. The app sends its own.
- **In-app notices** (`fhg/notices.py`, translations in `fhg/notices_hi.py` and `fhg/notices_mr.py`): bookings, results, test reminders,
  referrals, invitations, the care circle, emergency-link openings, family alerts and privacy answers. Each is
  written in the recipient's language, so two siblings can each get their own.
- **Caregiver reminders** (`fhg/care.py`), **lock-screen pushes** (`fhg/push.py`) and **WhatsApp replies**.

`tests/test_insight_language.py` reads every `tr()` and `mark()` template in the rules, risk models and notices. It
fails if any template lacks a translation in any language, or a placeholder changes. It also checks that Hindi and
Marathi reports contain no English sentences.

## Marathi for Pune

- **Family history typed in Marathi** is understood, in Devanagari ("माझ्या आईला 46 व्या वर्षी स्तनाचा कर्करोग
  झाला") and in Latin letters ("aaila 46 vya varshi breast cancer zala"). See `normalize_family_text` in
  `fhg/i18n.py`. Marathi uses the same script as Hindi; Marathi words (आहे, झाला, वर्षी, आणि…) tell them apart, and
  the WhatsApp assistant then replies in Marathi.
- **Clinic language.** A clinic's admin picks Hindi or Marathi in the portal (next to the intake link;
  `PUT /v1/orgs/{id}/language`). The poster and staff guide then print English plus that language, and the intake
  page offers it right after English. The intake page always offers all three.
- **Documents.** OCR reads Marathi with `FHG_OCR_LANGS=eng+hin+mar` (set in `render.yaml`; the Docker image has the
  Marathi data).
- **WhatsApp reminders for parents** need the Marathi versions of the two templates approved by Meta
  ([CAREGIVER_MODE.md](CAREGIVER_MODE.md#templates-to-submit-to-meta-whatsapp-manager--message-templates-category-utility)).

## Deliberately in English

- **The doctor summary, the emergency summary, and anything partners or clinics receive.** Clinicians read these,
  and the language context defaults to English, so they stay English automatically.
- **Breach notices** are written by the privacy officer in the console.
- **The AI plain-language summary** (an optional feature).

## Adding a language

1. App: copy `mobile/src/locales/mr.ts` to `<code>.ts` and translate the values. Add the language to `Lang`,
   `LANGS`, `LOCALE` and `TABLES` in `mobile/src/lib/translate.ts`, and to the tables in
   `mobile/tests/translations.test.ts`.
2. Server: copy `fhg/insights/mr.py` and `fhg/notices_mr.py`, add them to `TABLES` in `fhg/insights/lang.py` (the
   coverage tests pick it up from there).
3. Add the language to `PUSH_TEXT_I18N` (`fhg/push.py`), `ALERT_TEXT`, `WA_TEXT` and `WA_SLOT` (`fhg/care.py`),
   the privacy notice (`fhg/privacy.py`), and the language patterns in `fhg/api.py` (`CareWhatsAppIn`,
   `OrgLanguageIn`).
4. Clinic pages: `TEXT` in `fhg/static/intake.html`, and a `lang` span for each line of the poster and staff guide.

Every translation needs review by a native speaker before families see it. The Hindi and Marathi here were written
for the pilot and haven't had that review yet. Health terms especially (कर्करोग, मधुमेह, रक्तदाब) should be checked
with a clinician who sees Pune patients.
