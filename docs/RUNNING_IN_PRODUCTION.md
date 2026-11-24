# Running the pilot in production

What keeps the service healthy once real families use it: background jobs, backups you have actually restored,
error tracking, uptime alerts, and a staging copy for trying changes. Deployment itself is in [DEPLOY.md](DEPLOY.md);
the phone apps are in [RELEASE.md](RELEASE.md).

## The operations console

Open `https://<your-service>/admin` and sign in with the admin key (`FHG_ADMIN_KEY`). The key stays in that browser
tab only. Ten wrong keys lock that address out for 15 minutes. It works on a phone too.

| Tab | What you can do |
|---|---|
| **Overview** | Families, documents, care circles, doses marked this week, clinics, partners, open and overdue privacy concerns, breaches; test bookings by partner and status, with value in ₹ |
| **Pilot report** | Outcomes across all families: building the record (relatives, three generations, documents, weekly use), what it found, follow-through (tests booked and completed, days to result, clinic referrals), caregiving (doses taken over 28 days), and the survey answers. **Download CSV to share**: counts from 1 to 4 show as “<5” |
| **Partners** | Add a lab or counseling partner (its API key and webhook secret are shown once), set its price list (price, home collection, turnaround per test), turn it off or on |
| **Concerns** | Answer privacy concerns before their due date; the answer reaches the person in the app |
| **Breaches** | Record a breach and notify the people affected; record when the Data Protection Board was informed and sent the report |
| **Jobs & backups** | When each background job last ran and how it went; run any of them now |

Everything the console does is also available as `/admin/...` API calls with the `X-Admin-Key` header.

## The pilot report and surveys

`fhg/pilot.py` computes the report (`GET /admin/pilot-report`, or `?format=csv` for the shareable version). Families
see an optional question card on Home, which they can skip:
- at sign-up: how much of their family's health history they knew, and whether they had ever discussed it with a
  doctor;
- after 8 weeks: whether the app led them to a test or a doctor, and how useful it was.

Answers are part of each person's data download and are only reported as counts. The privacy notice lists this use.
Each clinic also has its own referral funnel and report in the clinic portal.

## Background jobs

With `FHG_SCHEDULER=on` (set in `render.yaml`) the web service runs its own jobs; nothing else to deploy.
Times are India time:

| Job | When | What |
|---|---|---|
| `care` | every hour | medicine reminders, missed-dose notices, refill alerts ([CAREGIVER_MODE.md](CAREGIVER_MODE.md)) |
| `reminders` | daily 10:00 | tests still to book, labs that haven't confirmed, results not in ([TEST_BOOKING.md](TEST_BOOKING.md)) |
| `backup` | daily 02:30 (and right after the first deploy) | encrypted database backup |
| `housekeeping` | daily 03:15 | delete expired sign-in codes, tokens, invites and links |

Each job's last run is stored in the database, so a restart neither skips nor repeats a run. After a fresh install
the daily jobs wait for their first scheduled time. Check them with `GET /admin/jobs` (admin key). The same jobs
can be run by hand from the console, or with `POST /admin/jobs/{care|reminders|backup|housekeeping}/run`.

Run exactly **one** instance with the scheduler on.

## Backups

Every night `fhg/backup.py` takes a consistent snapshot of the database while the app keeps running, encrypts the
whole file, and writes it to `FHG_BACKUP_DIR` (`/var/data/backups`), keeping the last `FHG_BACKUP_KEEP` (14).

**Copies on the same disk don't survive losing the disk.** For the pilot, also copy them off-site:

| Variable | Value |
|---|---|
| `FHG_BACKUP_S3_BUCKET` | bucket name |
| `FHG_BACKUP_S3_ENDPOINT` | for S3-compatible services, e.g. Cloudflare R2's account endpoint; leave unset for AWS |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | an access key that can only write to that bucket (secrets) |

Backups are encrypted with `FHG_BACKUP_KEY`, or the app's `FHG_ENCRYPTION_KEY` when that isn't set. **Keep that key
in a password manager outside Render.** Without it no backup can be read.

### Restore drill (do this before the pilot starts, and monthly)

From a Render shell, or locally with a downloaded backup:

```bash
python -m fhg.backup check /var/data/backups/fhg-YYYYMMDD-HHMM.sqlite3.enc
```

This prints row counts per table and runs SQLite's integrity check, without touching the live database. To restore
for real, stop the service (suspend it), then:

```bash
python -m fhg.backup restore /var/data/backups/fhg-YYYYMMDD-HHMM.sqlite3.enc /var/data/fhg.sqlite3
```

The previous database is kept as `fhg.sqlite3.before-restore`. Resume the service and check `/health/ready`.

## Error tracking

Set `FHG_SENTRY_DSN` to a Sentry (or self-hosted GlitchTip) project. Errors are sent with the stack trace only:
`fhg/monitoring.py` removes request bodies, headers, query strings, user details, local variables and breadcrumbs
before anything leaves the server, so no health data reaches the error tracker. `FHG_ENVIRONMENT` tags production
and staging separately.

## Uptime alerts

Point an uptime monitor (UptimeRobot, Better Stack, or similar) at:

- `GET /health`: the process is up.
- `GET /health/ready`: the database takes writes and the background jobs ran on time. It answers `503` with the
  problem (for example `care job overdue` or `backup job failed`) when something needs attention.

Alert by email and SMS to whoever is on call for the pilot.

## Staging

`render.yaml` also creates **family-health-graph-staging**, deployed from the `staging` branch on Render's free
plan. Its data resets on every deploy and its background jobs are off. To try a change, merge it into `staging`
first; the preview phone builds (`eas build --profile preview`) point at staging.

## Before the first family signs up

- [ ] `FHG_ENCRYPTION_KEY` and `FHG_ADMIN_KEY` copied to a password manager.
- [ ] Off-site backup bucket configured; one restore drill done (`check`, then a real restore on staging).
- [ ] `FHG_SENTRY_DSN` set, and a test error seen in the tracker with no request data in it.
- [ ] Uptime monitor on `/health/ready`, alerting a phone.
- [ ] `FHG_PUSH_BACKEND=expo` once the store builds are out ([RELEASE.md](RELEASE.md)).
- [ ] Email sign-in configured (`FHG_EMAIL_BACKEND=smtp`, see [DEPLOY.md](DEPLOY.md)).
