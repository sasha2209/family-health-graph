// Run with: npm test  (Node's built-in test runner; no extra dependencies)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { parseInviteToken } from '../src/lib/api.ts';

const T = 'Abc123_-xyzXYZ0987654321abcdEFGH';

test('parses web, app-scheme and bare invite tokens', () => {
  assert.equal(parseInviteToken(`https://example.org/invite/${T}`), T);
  assert.equal(parseInviteToken(`  http://localhost:8000/invite/${T}  `), T);
  assert.equal(parseInviteToken(`familyhealth://invite/${T}`), T);
  assert.equal(parseInviteToken(`Hey, join me! https://example.org/invite/${T}`), T);
  assert.equal(parseInviteToken(T), T);
});

test('rejects things that are not invites', () => {
  assert.equal(parseInviteToken(''), null);
  assert.equal(parseInviteToken('hello there'), null);
  assert.equal(parseInviteToken('https://example.org/invite/short'), null);
});
