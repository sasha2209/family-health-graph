// Pure translation logic (no React Native imports), so tests can use it directly.
import hi from '../locales/hi.ts';

export type Lang = 'en' | 'hi';
export type Vars = Record<string, string | number>;

export const LANGS: { code: Lang; name: string }[] = [
  { code: 'en', name: 'English' },
  { code: 'hi', name: 'हिन्दी' },
];

const TABLES: Record<Lang, Record<string, string>> = { en: {}, hi };

export function translate(lang: Lang, text: string, vars?: Vars): string {
  const out = TABLES[lang][text] ?? text;
  return vars ? out.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : out;
}

/** Marks a string for translation where it's defined but translated later with t() (e.g. lists built ahead). */
export const N = (text: string): string => text;
