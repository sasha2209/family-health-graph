// Extends app.json. When EXPO_PUBLIC_LINK_DOMAIN is set at build time (e.g.
// app.example.org), tapped invite links on that domain open the app:
// Universal Links on iOS and verified App Links on Android. The server must
// serve the matching /.well-known files (FHG_IOS_APP_IDS, FHG_ANDROID_*).
module.exports = ({ config }) => {
  // EXPO_BASE_URL=/app when the web build is served under a sub-path (see ../Dockerfile).
  if (process.env.EXPO_BASE_URL) {
    config = { ...config, experiments: { ...config.experiments, baseUrl: process.env.EXPO_BASE_URL } };
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
