import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { AppState, Platform, StyleSheet, Text, View } from 'react-native';

import { Button } from '../components/ui';
import { usePalette } from './theme';

const PREF_KEY = 'fhg_app_lock';
const LOCK_AFTER_MS = 30_000; // re-lock after 30 s in the background
const native = Platform.OS === 'ios' || Platform.OS === 'android';

interface AppLock {
  /** Device has Face ID / Touch ID / fingerprint set up. */
  available: boolean;
  enabled: boolean;
  setEnabled: (on: boolean) => Promise<boolean>;
}

const AppLockContext = createContext<AppLock>({ available: false, enabled: false, setEnabled: async () => false });

export const useAppLock = () => useContext(AppLockContext);

async function authenticate(): Promise<boolean> {
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Unlock Family Health Graph',
    cancelLabel: 'Cancel',
  }); // falls back to the device passcode if biometrics fail
  return result.success;
}

/**
 * Optional biometric lock plus a privacy cover: whenever the app isn't in the
 * foreground its content is hidden, so health information doesn't show in the
 * app switcher. `active` should be true only while someone is signed in.
 */
export function AppLockProvider({ children, active }: { children: ReactNode; active: boolean }) {
  const c = usePalette();
  const [available, setAvailable] = useState(false);
  const [enabled, setEnabledState] = useState(false);
  const [locked, setLocked] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const backgroundedAt = useRef<number | null>(null);
  const activeRef = useRef(active);
  useEffect(() => { activeRef.current = active; });

  const unlock = useCallback(async () => {
    if (await authenticate().catch(() => false)) setLocked(false);
  }, []);

  // Lock, and prompt right away if someone is signed in.
  const lockNow = useCallback(() => {
    setLocked(true);
    if (activeRef.current) unlock();
  }, [unlock]);

  useEffect(() => {
    if (!native) return;
    Promise.all([LocalAuthentication.hasHardwareAsync(), LocalAuthentication.isEnrolledAsync(),
                 SecureStore.getItemAsync(PREF_KEY)])
      .then(([hw, enrolled, pref]) => {
        const ok = hw && enrolled;
        setAvailable(ok);
        setEnabledState(ok && pref === '1');
        if (ok && pref === '1') lockNow(); // cold start
      })
      .catch(() => setAvailable(false));
  }, [lockNow]);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      setForeground(state === 'active');
      if (state === 'background') backgroundedAt.current = Date.now();
      if (state === 'active' && backgroundedAt.current !== null) {
        if (enabled && Date.now() - backgroundedAt.current > LOCK_AFTER_MS) lockNow();
        backgroundedAt.current = null;
      }
    });
    return () => sub.remove();
  }, [enabled, lockNow]);

  const setEnabled = useCallback(async (on: boolean) => {
    if (on && !(await authenticate().catch(() => false))) return false; // prove it works first
    await SecureStore.setItemAsync(PREF_KEY, on ? '1' : '0');
    setEnabledState(on);
    return true;
  }, []);

  const hideContent = active && native && (!foreground || (enabled && locked));

  return (
    <AppLockContext.Provider value={{ available, enabled, setEnabled }}>
      {children}
      {hideContent && (
        <View style={[StyleSheet.absoluteFill, s.cover, { backgroundColor: c.bg }]}
              accessibilityViewIsModal>
          <Text style={[s.title, { color: c.text }]}>Family Health Graph</Text>
          {locked && foreground && (
            <>
              <Text style={{ color: c.muted, marginBottom: 16 }}>Locked to protect your health information.</Text>
              <Button title="Unlock" variant="primary" onPress={unlock} />
            </>
          )}
        </View>
      )}
    </AppLockContext.Provider>
  );
}

const s = StyleSheet.create({
  cover: { alignItems: 'center', justifyContent: 'center', padding: 24, zIndex: 1000 },
  title: { fontSize: 22, fontWeight: '700', marginBottom: 8 },
});
