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

- Lock-screen push texts (`fhg/push.py`).
- Caregiver reminders, missed-dose notices and refill alerts (`fhg/care.py`), each in the recipient's own
  language, so siblings in one care circle can use different languages.
- WhatsApp replies.

## Still in English

These are the next pieces to translate:
- **Action item details.** The titles are translated, but the explanations, evidence and recommendations come from
  the rules in `fhg/insights/rules.py`, which build sentences in English.
- **Other in-app notices** from the server: bookings, referrals, the care circle, privacy answers.
- **The privacy notice** is in English and Hindi already (`fhg/privacy.py`).
- **The doctor summary and emergency summary.** These are kept in English on purpose, since clinicians read them.

## Adding a language

1. Copy `mobile/src/locales/hi.ts` to `<code>.ts` and translate the values.
2. Add the language to `LANGS` and `TABLES` in `mobile/src/lib/translate.ts`.
3. Add a column to the coverage test.
4. Add push texts to `PUSH_TEXT_I18N` in `fhg/push.py` and alert texts to `ALERT_TEXT` in `fhg/care.py`.

Every translation needs review by a native speaker before families see it. The Hindi here was written for the
pilot and hasn't had that review yet.
