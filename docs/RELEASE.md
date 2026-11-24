# Getting the app onto pilot families' phones

The app is built with Expo and EAS (Expo's build service): no Mac or Android Studio needed. Pilot families install
it from **TestFlight** (iPhone) and **Google Play internal testing** (Android), which keeps the pilot private and
skips full store review until you're ready to launch publicly.

## One-time setup (about a day, mostly waiting for accounts)

1. **Accounts:**
   - an Expo account (free to start);
   - an Apple Developer Program membership, for TestFlight;
   - a Google Play Console account.
2. **Choose the app's ID**, for example `in.familyhealthgraph.app`. It can't change after the first store upload.
3. **Create the EAS project.** In `mobile/`, run:

   ```bash
   npx eas-cli@latest init
   ```

   Note the project ID it prints.
4. **GitHub settings.** In the repository's *Settings → Secrets and variables → Actions*, add:
   - the secret `EXPO_TOKEN`, a token from expo.dev → Account settings → Access tokens;
   - the variable `APP_ID` (the ID from step 2);
   - the variable `EAS_PROJECT_ID` (from step 3);
   - the variable `EXPO_OWNER` (your Expo account or organisation).

   On expo.dev, add the same `APP_ID`, `EAS_PROJECT_ID` and `EXPO_OWNER` as EAS environment variables, so builds
   started there use them too.
5. **Android push (Firebase Cloud Messaging):**
   1. Create a Firebase project and add an Android app with the `APP_ID`.
   2. Download `google-services.json` and upload it to EAS as a *file* environment variable named
      `GOOGLE_SERVICES_JSON`. Don't commit it.
   3. Upload the FCM v1 service-account key in expo.dev → your project → Credentials → Android.
6. **iOS push.** The first iOS build asks to create the push key; let EAS manage it.
7. **Server URLs.** Check the server URLs in `mobile/eas.json`: `preview` points at staging and `pilot` at
   production. Change them if your Render services have other names.

## Building

From GitHub, go to *Actions → Mobile builds → Run workflow* and choose:

| Profile | What you get | Who it's for |
|---|---|---|
| `preview` | An Android APK link and an iOS ad-hoc build, both on staging | The team, before each pilot release |
| `pilot` | Store builds on production. Tick *submit* to send them to TestFlight and Play internal testing | Pilot families |

You can also build from a laptop, in `mobile/`:

```bash
npx eas-cli@latest build --profile pilot --platform all
```

## Inviting pilot families

- **iPhone:** in App Store Connect → TestFlight, add testers by email or share a public link. Families install the
  TestFlight app first.
- **Android:** in the Play Console → Internal testing, add testers by email (up to 100), then share the opt-in link.
- Put both links on the clinic's QR poster or in the welcome message. The web app at `/app` stays available for
  anyone who can't install.

## Turn on push

Once a store build is installed:
1. Set `FHG_PUSH_BACKEND=expo` on the production service.
2. On a phone, go to Settings → *Turn on family alerts* and allow notifications.
3. Trigger something, such as a care reminder from `POST /admin/tasks/care` at a dose time, and check the phone.

Push texts never contain health details, because they show on the lock screen. Tapping one opens the right screen.

## Store listings (needed for TestFlight external testing and public launch)

- A privacy policy URL. The privacy notice at `/v1/privacy/notice` is the basis.
- Apple App Privacy answers: health data and contact info, used for app functionality, not tracking.
- Google Play Data safety form and the Health apps declaration.
- A short medical disclaimer in the description: guidance, not diagnosis.
- Demo account details for reviewers.
