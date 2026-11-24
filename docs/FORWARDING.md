# Forwarding documents by email and WhatsApp

Labs, clinics and telehealth apps in India already send reports as email attachments and WhatsApp messages.
Forwarding them is the lowest-effort way to keep a family's record up to date. Forwarded files go through
the same pipeline as uploads (on-server OCR, rules, opt-in AI fallback) and **wait in "Waiting for your
review"**. Nothing is added to the record until the user checks it.

## Email

Each user gets a private address, `<12-character token>@<FHG_INBOUND_EMAIL_DOMAIN>`, shown under
*Add health information → Forward reports instead*. Plus-addressing works (`token+apollo@…`). *Get a new
address* retires the old one.

Setup (Postmark shown; any provider that POSTs Postmark-style JSON works, and others need a small adapter):
1. Point an MX record for a subdomain (e.g. `in.yourdomain.com`) at the provider's inbound servers.
2. Set the inbound webhook URL to `https://<host>/inbound/email?secret=<FHG_INBOUND_EMAIL_SECRET>`.
3. Set `FHG_INBOUND_EMAIL_DOMAIN=in.yourdomain.com` and `FHG_INBOUND_EMAIL_SECRET=<long random value>`.

Only PDF, JPEG, PNG and WebP attachments are read. Unknown addresses and bad secrets get the same empty
answer, so addresses can't be probed.

## WhatsApp (Business Cloud API)

1. Create a Meta app with the WhatsApp product, and a business phone number.
2. Set the webhook callback to `https://<host>/inbound/whatsapp` with your verify token, and subscribe to `messages`.
3. Set `FHG_WHATSAPP_NUMBER` (shown to users), `FHG_WHATSAPP_VERIFY_TOKEN`, `FHG_WHATSAPP_APP_SECRET` (used to check
   `X-Hub-Signature-256`), `FHG_WHATSAPP_ACCESS_TOKEN` and `FHG_WHATSAPP_PHONE_NUMBER_ID`.

To connect, the user taps *Connect WhatsApp* and sends `LINK 123456` (valid 15 minutes, single use) from their phone.
After that, any photo or PDF they send becomes a document for review. Replies are generic and never contain
health information. Phone numbers are stored as an HMAC (for lookup) and encrypted (for replies). A number can belong to one
account only. Meta's rules for health messaging and opt-in apply; the user starts every conversation.

## The WhatsApp assistant

Once a number is linked, the assistant understands:

| They send | It does |
|---|---|
| A photo or PDF | Reads it (on-server OCR in English, Hindi and Marathi, rules, opt-in AI). Then it replies **1** = save to my record, **2** = my mother's, **3** = my father's. |
| Family history as text, in English, **Hindi or Hinglish** (“mummy ko sugar hai, papa ko 52 mein heart attack hua”) | Kinship words (nani, dadi, chacha, mausi, bua…), condition words (sugar, BP, dil ka daura, lakwa…) and ages are understood. It asks for **1** to save. |
| `HELP` · `SUMMARY` · `LANG hi/bn/ta/te/mr/en` · `STOP` | Options · action items · reply language · disconnect |
| A voice note | Asks for text or a photo (voice is planned) |

- **Languages:** replies are in English, Hindi, Bengali, Tamil, Telugu or Marathi. The language is picked from the
  script the person writes in, or set with `LANG`. The non-English texts in `fhg/i18n.py` are drafts for
  native-speaker review.
- **Privacy:** health details (what was read, action items, the echo of typed history) are only sent when the person
  turns on **WhatsApp summaries** in Settings (consent scope `whatsapp_summaries`). Otherwise replies are short
  confirmations with no health information.
- **OCR languages:** `FHG_OCR_LANGS` (default `eng+hin`, using installed packs only). Add `ben`, `tam`, `tel` or
  `mar` and the matching `tesseract-ocr-*` packages where needed; each extra language slows OCR.

## API

| | |
|---|---|
| `GET /v1/inbound` | The user's address and WhatsApp status |
| `POST /v1/inbound/email/rotate` | A new address |
| `POST /v1/inbound/whatsapp/code` · `DELETE /v1/inbound/whatsapp` | Link code · disconnect |
| `POST /inbound/email` · `GET/POST /inbound/whatsapp` | Provider webhooks |
| `GET /v1/trends[?member_id=]` | Results over time with guideline ranges (yours or a managed relative's) |

Documents carry `source: upload | email | whatsapp`.
