# Deploying to Render

One Docker service serves everything:

| Path | What |
|---|---|
| `/` | Patient web dashboard |
| `/app` | The mobile app, as a web app (works in any phone browser) |
| `/portal` | Clinic portal |
| `/c/<code>` | Clinic pre-visit intake links, QR codes and posters |
| `/v1/...`, `/docs` | API (including the partner API) and its interactive docs |

## One-click deploy

1. Open **https://render.com/deploy?repo=https://github.com/sasha2209/family-health-graph** and sign in to Render
   (with GitHub). If the repository is private, give Render access to it when asked.
2. Render reads `render.yaml` and shows one web service, **family-health-graph**, with a 1 GB disk and
   generated secrets. Click **Apply** / **Deploy**. The first build takes about 5 to 10 minutes.
3. When it's live, open `https://<your-service>.onrender.com/health`. It should say `{"status":"ok"}`.
4. **Back up your encryption key now.** In Render: service → *Environment* → copy `FHG_ENCRYPTION_KEY`
   into your password manager. Without it the database can't be read. Also note `FHG_ADMIN_KEY`
   (needed to onboard referral partners).

Every push to `main` redeploys automatically.

For running the pilot (background jobs, backups and restore drills, error tracking, uptime alerts, staging) see
[RUNNING_IN_PRODUCTION.md](RUNNING_IN_PRODUCTION.md). For the phone apps see [RELEASE.md](RELEASE.md).

## Cost and plans

`render.yaml` uses the **Starter** instance with a persistent disk, because the database (SQLite) must
survive restarts and deploys. Check Render's pricing page for current rates.

For a quick free demo, delete the `disk:` block and change `plan: starter` to `plan: free`. Everything works,
but **all data is wiped on every deploy or restart**, and free services sleep when idle (the first request
takes up to a minute). Don't put real patient data on it.

## After the first deploy

| To do | How |
|---|---|
| Real sign-in emails | Set `FHG_EMAIL_BACKEND=smtp` plus `FHG_SMTP_HOST`, `FHG_SMTP_PORT`, `FHG_SMTP_USERNAME`, `FHG_SMTP_PASSWORD` (mark it secret) and `FHG_EMAIL_FROM`. Until then, codes appear in Render's **Logs**. |
| Your own domain | Render → *Settings* → *Custom domains*, then set `FHG_PUBLIC_URL=https://your-domain` so intake and invite links use it. |
| Onboard a referral partner | `curl -X POST https://<host>/admin/partners -H "X-Admin-Key: $FHG_ADMIN_KEY" -H "Content-Type: application/json" -d '{"name":"…","kind":"genetic_counseling","webhook_url":"https://…"}'` (see `PARTNER_API.md`). |
| Push notifications | Set `FHG_PUSH_BACKEND=expo` once the app has an EAS project (see `mobile/README.md`). |
| Phone app pointing at production | Build the app with `EXPO_PUBLIC_API_URL=https://<host>`. |

## Before real patient data

A live URL is not the same as being ready for real health data. Before onboarding real patients:
- confirm your host will sign a **BAA** (needed for HIPAA in the US; check Render's current compliance offering for your plan) or move to one that will, and meet the equivalent obligations in your country (e.g. India's DPDP Act)
- move from SQLite to managed **Postgres** with automated backups
- set up error monitoring, rate limiting and an uptime check
- get a security review
- complete the clinical and regulatory review described in the README
