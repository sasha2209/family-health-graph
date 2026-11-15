import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';

const require = createRequire(import.meta.url);
const appConfig = require('../app.config.js');
const base = { name: 'x', ios: { bundleIdentifier: 'com.example.app' }, android: { package: 'com.example.app' } };

test('no link domain: config is unchanged', () => {
  delete process.env.EXPO_PUBLIC_LINK_DOMAIN;
  assert.deepEqual(appConfig({ config: base }), base);
});

test('link domain adds iOS associated domains and a verified Android intent filter', () => {
  process.env.EXPO_PUBLIC_LINK_DOMAIN = 'app.example.org';
  const out = appConfig({ config: base });
  assert.deepEqual(out.ios.associatedDomains, ['applinks:app.example.org']);
  assert.equal(out.ios.bundleIdentifier, 'com.example.app');
  const filter = out.android.intentFilters[0];
  assert.equal(filter.autoVerify, true);
  assert.deepEqual(filter.data, [{ scheme: 'https', host: 'app.example.org', pathPrefix: '/invite/' }]);
  delete process.env.EXPO_PUBLIC_LINK_DOMAIN;
});
