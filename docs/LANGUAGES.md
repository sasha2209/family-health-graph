# Languages

The app is in **English and Hindi**. The WhatsApp assistant also replies in Bengali, Tamil, Telugu and Marathi
([fhg/i18n.py](../fhg/i18n.py)).

## How the app's translations work

- UI strings are written in English and wrapped: `t('Add a medicine')`, or with values
  `t('{n} days left', { n })`. The English text is the key; a missing translation falls back to English.
- Hindi lives in `mobile/src/locales/hi.ts`.
- Strings defined ahead of time (tables, lists) are marked with `N('…')` and translated where they are shown.
- `mobile/tests/translations.test.ts` (part of `npm test`, so CI) fails if any wrapped string has no Hindi, or a
  translation drops or renames a `{placeholder}`. It prints the missing strings ready to paste.
- The app starts in the phone's language (Hindi if the phone is set to Hindi) and can be switched in
  **Settings → Language**. The choice is also saved on the server (`PUT /v1/profile/language`).

## What follows the person's language on the server

The server keeps each person's language (`PUT /v1/profile/language`) and uses it for everything it writes to them:

- **Action items.** Title, summary, evidence and what to do, plus the risk page and the disclaimer. The rules in
  `fhg/insights/rules.py` write all their text through `tr("English template {value}", value=...)`, and the
  Hindi is in `fhg/insights/hi.py`. `GET /v1/insights?lang=hi` overrides the stored language. The app sends its
  own.
- **In-app notices** (`fhg/notices.py`, Hindi in `fhg/notices_hi.py`): bookings, results, test reminders,
  referrals, invitations, the care circle, emergency-link openings, family alerts and privacy answers. Each is
  written in the recipient's language, so two siblings can each get their own.
- **Caregiver reminders** (`fhg/care.py`), **lock-screen pushes** (`fhg/push.py`) and **WhatsApp replies**.

`tests/test_insight_language.py` reads every `tr()` and `mark()` template in the rules, risk models and notices. It
fails if any template lacks Hindi, or a placeholder changes. It also checks that a Hindi report contains no English
sentences.

## Deliberately in English

- **The doctor summary, the emergency summary, and anything partners or clinics receive.** Clinicians read these,
  and the language context defaults to English, so they stay English automatically.
- **Breach notices** are written by the privacy officer in the console.
- **The AI plain-language summary** (an optional feature).

## Adding a language

1. Copy `mobile/src/locales/hi.ts` to `<code>.ts` and translate the values.
2. Add the language to `LANGS` and `TABLES` in `mobile/src/lib/translate.ts`.
3. Add a column to the coverage test.
4. Add push texts to `PUSH_TEXT_I18N` in `fhg/push.py` and alert texts to `ALERT_TEXT` in `fhg/care.py`.

Every translation needs review by a native speaker before families see it. The Hindi here was written for the
pilot and hasn't had that review yet.
