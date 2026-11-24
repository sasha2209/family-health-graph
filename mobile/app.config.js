// Extends app.json. When EXPO_PUBLIC_LINK_DOMAIN is set at build time (e.g.
// app.example.org), tapped invite links on that domain open the app:
// Universal Links on iOS and verified App Links on Android. The server must
// serve the matching /.well-known files (FHG_IOS_APP_IDS, FHG_ANDROID_*).
//
// Store builds (docs/RELEASE.md) are configured from the environment, so nothing account-specific is committed:
//   APP_ID               bundle identifier / Android package, e.g. in.familyhealthgraph.app
//   EAS_PROJECT_ID       from `eas init` (also what push notifications need)
//   EXPO_OWNER           the Expo account or organisation that owns the project
//   GOOGLE_SERVICES_JSON path to google-services.json for Android push (an EAS "file" environment variable)
module.exports = ({ config }) => {
  // EXPO_BASE_URL=/app when the web build is served under a sub-path (see ../Dockerfile).
  if (process.env.EXPO_BASE_URL) {
    config = { ...config, experiments: { ...config.experiments, baseUrl: process.env.EXPO_BASE_URL } };
  }
  const appId = process.env.APP_ID;
  if (appId) {
    config = { ...config, ios: { ...config.ios, bundleIdentifier: appId }, android: { ...config.android, package: appId } };
  }
  if (process.env.EAS_PROJECT_ID) {
    config = { ...config, extra: { ...config.extra, eas: { projectId: process.env.EAS_PROJECT_ID } } };
  }
  if (process.env.EXPO_OWNER) config = { ...config, owner: process.env.EXPO_OWNER };
  if (process.env.GOOGLE_SERVICES_JSON) {
    config = { ...config, android: { ...config.android, googleServicesFile: process.env.GOOGLE_SERVICES_JSON } };
  }
  const domain = process.env.EXPO_PUBLIC_LINK_DOMAIN;
  if (!domain) return config;
  return {
    ...config,
    ios: { ...config.ios, associatedDomains: [`applinks:${domain}`] },
    android: {
      ...config.android,
      intentFilters: [
        {
          action: 'VIEW',
          autoVerify: true,
          data: [
            { scheme: 'https', host: domain, pathPrefix: '/invite/' },
            { scheme: 'https', host: domain, pathPrefix: '/c/' }, // clinic intake links
          ],
          category: ['BROWSABLE', 'DEFAULT'],
        },
      ],
    },
  };
};
