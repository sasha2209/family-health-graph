import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import { createApi, type Api } from './api';

const KEY = 'fhg_token';

// The API token lives in the iOS Keychain / Android Keystore. expo-secure-store
// has no web implementation, so the browser preview falls back to localStorage.
const tokenStore = {
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
    // THIS_DEVICE_ONLY: the token is not copied into device backups.
    await SecureStore.setItemAsync(KEY, value, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  },
  async clear(): Promise<void> {
    if (Platform.OS === 'web') {
      try { globalThis.localStorage?.removeItem(KEY); } catch { /* ignore */ }
      return;
    }
    await SecureStore.deleteItemAsync(KEY);
  },
};

interface Session {
  ready: boolean;
  token: string | null;
  api: Api;
  signIn: (token: string) => Promise<void>;
  /** Sign out of this device. Revokes the session on the server unless it's already invalid. */
  signOut: (options?: { revoke?: boolean }) => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    tokenStore.get().then((t) => { setToken(t); setReady(true); });
  }, []);

  const signIn = useCallback(async (t: string) => { await tokenStore.set(t); setToken(t); }, []);
  const signOut = useCallback(async ({ revoke = true }: { revoke?: boolean } = {}) => {
    if (revoke && token) await createApi(token).logout().catch(() => undefined);
    await tokenStore.clear();
    setToken(null);
  }, [token]);
  const api = useMemo(() => createApi(token), [token]);

  const value = useMemo(() => ({ ready, token, api, signIn, signOut }), [ready, token, api, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>');
  return ctx;
}
