// Pure translation logic (no React Native imports), so tests can use it directly.
import hi from '../locales/hi.ts';
import mr from '../locales/mr.ts';

export type Lang = 'en' | 'hi' | 'mr';
export type Vars = Record<string, string | number>;

export const LANGS: { code: Lang; name: string }[] = [
  { code: 'en', name: 'English' },
  { code: 'hi', name: 'हिन्दी' },
  { code: 'mr', name: 'मराठी' },
];

export const isLang = (x: unknown): x is Lang => LANGS.some((l) => l.code === x);

/** For dates and numbers (toLocaleDateString). */
export const LOCALE: Record<Lang, string> = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' };

const TABLES: Record<Lang, Record<string, string>> = { en: {}, hi, mr };

export function translate(lang: Lang, text: string, vars?: Vars): string {
  const out = TABLES[lang][text] ?? text;
  return vars ? out.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : out;
}

/** Marks a string for translation where it's defined but translated later with t() (e.g. lists built ahead). */
export const N = (text: string): string => text;
