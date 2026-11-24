import { getLocales } from 'expo-localization';
import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import { isLang, translate, type Lang, type Vars } from './translate';

export { isLang, LANGS, LOCALE, N, translate, type Lang } from './translate';

const KEY = 'fhg_lang';

const prefStore = {
  async get(): Promise<string | null> {
    if (Platform.OS === 'web') {
      try { return globalThis.localStorage?.getItem(KEY) ?? null; } catch { return null; }
    }
    return SecureStore.getItemAsync(KEY);
  },
  async set(value: string): Promise<void> {
    if (Platform.OS === 'web') {
      try { globalThis.localStorage?.setItem(KEY, value); } catch { /* private mode */ }
      return;
    }
    await SecureStore.setItemAsync(KEY, value);
  },
};

/** The phone's language, if we have it; otherwise English. */
function deviceLang(): Lang {
  try {
    const found = getLocales().map((l) => l.languageCode).find(isLang);
    return found ?? 'en';
  } catch {
    return 'en';
  }
}

interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => Promise<void>;
  /** Translate an English UI string; `{name}` placeholders are filled from `vars`. Missing → English. */
  t: (text: string, vars?: Vars) => string;
}

const I18nContext = createContext<I18n>({ lang: 'en', setLang: async () => undefined, t: (s, v) => translate('en', s, v) });

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(deviceLang);
  useEffect(() => {
    prefStore.get().then((saved) => { if (isLang(saved)) setLangState(saved); }).catch(() => undefined);
  }, []);
  const setLang = useCallback(async (next: Lang) => {
    setLangState(next);
    await prefStore.set(next).catch(() => undefined);
  }, []);
  const t = useCallback((text: string, vars?: Vars) => translate(lang, text, vars), [lang]);
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): I18n {
  return useContext(I18nContext);
}
