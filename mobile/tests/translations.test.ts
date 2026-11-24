// Every English UI string the app translates must have a Hindi and a Marathi entry. Run with: npm test
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';

import * as format from '../src/lib/format.ts';
import hi from '../src/locales/hi.ts';
import mr from '../src/locales/mr.ts';
import { translate } from '../src/lib/translate.ts';

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? files(p) : /\.(tsx?|ts)$/.test(f) ? [p] : [];
  });
}

const CALL = /\b(?:t|tr|N)\(/g;
const LITERAL = /'((?:\\.|[^'\\])*)'|"((?:\\.|[^"\\])*)"/g;
const unescape = (s: string) => s.replace(/\\(.)/g, (_, c: string) => (c === 'n' ? '\n' : c));

/** The first argument of each t()/N() call (up to a top-level comma or the closing paren). */
function firstArgs(src: string): string[] {
  const out: string[] = [];
  for (const m of src.matchAll(CALL)) {
    let depth = 0, quote = '', i = m.index! + m[0].length, start = i;
    for (; i < src.length; i++) {
      const ch = src[i];
      if (quote) { if (ch === '\\') i++; else if (ch === quote) quote = ''; continue; }
      if (ch === "'" || ch === '"' || ch === '`') quote = ch;
      else if ('([{'.includes(ch)) depth++;
      else if (')]}'.includes(ch)) { if (depth === 0) break; depth--; }
      else if (ch === ',' && depth === 0) break;
    }
    out.push(src.slice(start, i));
  }
  return out;
}

/** English strings used through t()/N() in the source, plus the label tables translated at their use sites. */
export function uiStrings(): Set<string> {
  const out = new Set<string>();
  for (const f of files('src')) {
    if (f.includes('locales')) continue;
    for (const arg of firstArgs(readFileSync(f, 'utf8'))) {
      // Every plain string literal in the argument: both branches of a ternary count.
      if (/^\s*[A-Z_]+\[/.test(arg) || /^\s*[a-z][\w.]*(\[|\(|\s*$)/.test(arg) && !arg.includes('?')) continue;
      for (const lit of arg.matchAll(LITERAL)) {
        if (/[!=]==\s*$/.test(arg.slice(0, lit.index))) continue;   // a value being compared, not shown
        out.add(unescape(lit[1] ?? lit[2]));
      }
    }
  }
  for (const table of [format.SHARE_SHORT, format.REFERRAL_LABEL, format.DOC_TYPE_LABEL, format.BOOKING_LABEL,
    format.VIA_LABEL]) Object.values(table).filter(Boolean).forEach((v) => out.add(v));
  format.SHARE_OPTIONS.forEach((o) => out.add(o.label));
  format.ALL_RELATIONSHIPS.forEach((r) => out.add(format.label(r)));
  ['Immediate family', 'Maternal side', 'Paternal side', 'Extended side'].forEach((s) => out.add(s));
  ['From a document', 'Shared by them', 'Imported record', 'Added by you'].forEach((s) => out.add(s));
  ['Discuss soon', 'Next visit', 'Good to know'].forEach((s) => out.add(s));                 // LEVEL_LABEL (theme.ts)
  ['morning', 'afternoon', 'night', 'after food', 'before food', 'empty stomach', 'you'].forEach((s) => out.add(s));
  ['iPhone', 'Android phone', 'Web browser'].forEach((s) => out.add(s));                        // DEVICE_NAME
  ['denied', 'revoked', 'expired'].forEach((s) => out.add(`Request ${s}. Disconnect and start again.`));
  ['Female', 'Male', 'Other'].forEach((s) => out.add(s));
  return out;
}

for (const [code, table] of Object.entries({ hi, mr })) {
  test(`every UI string has a translation (${code})`, () => {
    const missing = [...uiStrings()].filter((s) => !(s in table) && !/^[\d\s+x·.,()–-]*$/.test(s));
    assert.deepEqual(missing, [], `Add these to src/locales/${code}.ts:\n${missing.map((s) => JSON.stringify(s)).join(',\n')}`);
  });

  test(`placeholders survive translation (${code})`, () => {
    for (const [en, h] of Object.entries(table)) {
      const want = (en.match(/\{\w+\}/g) ?? []).sort().join(',');
      const got = (h.match(/\{\w+\}/g) ?? []).sort().join(',');
      assert.equal(got, want, `Placeholders differ for ${JSON.stringify(en)}`);
    }
  });
}

test('translate fills placeholders and falls back to English', () => {
  assert.equal(translate('en', '{n} to mark', { n: 2 }), '2 to mark');
  assert.equal(translate('hi', 'A string nobody translated'), 'A string nobody translated');
  assert.equal(translate('mr', '{n} days left', { n: 3 }), '3 दिवस उरले');
});
