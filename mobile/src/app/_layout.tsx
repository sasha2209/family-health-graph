import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppLockProvider } from '../lib/appLock';
import { LanguageProvider, useT } from '../lib/i18n';
import { usePushNotifications } from '../lib/push';
import { SessionProvider, useSession } from '../lib/session';
import { usePalette } from '../lib/theme';

function RootStack() {
  const { ready, token, api } = useSession();
  const c = usePalette();
  const { t } = useT();
  usePushNotifications(api, !!token);
  if (!ready) return null; // keep the splash screen up until we know if there's a session

  return (
    <AppLockProvider active={!!token}>
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: c.surface },
        headerTintColor: c.text,
        contentStyle: { backgroundColor: c.bg },
      }}
    >
      <Stack.Protected guard={!!token} redirectTo="/welcome">
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="insight/[id]" options={{ title: t('Action item') }} />
        <Stack.Screen name="add-history" options={{ title: t('Add health information'), presentation: 'modal' }} />
        <Stack.Screen name="document/[id]" options={{ title: t('Document') }} />
        <Stack.Screen name="person/[id]" options={{ title: t('Relative') }} />
        <Stack.Screen name="results" options={{ title: t('Your results') }} />
        <Stack.Screen name="connections" options={{ title: t('Connected records') }} />
        <Stack.Screen name="book" options={{ title: t('Book a test') }} />
        <Stack.Screen name="care" options={{ title: t('Caregiver mode') }} />
        <Stack.Screen name="privacy" options={{ title: t('Your privacy') }} />
        <Stack.Screen name="authorize" options={{ title: t('Share your family history'), headerBackVisible: false }} />
      </Stack.Protected>
      <Stack.Protected guard={!token} redirectTo="/">
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
      </Stack.Protected>
      {/* Reachable signed in or out: invite links open here, and sign-in also links an email. */}
      <Stack.Screen name="invite/[token]" options={{ title: t('Family invitation') }} />
      <Stack.Screen name="sign-in" options={{ title: t('Sign in') }} />
      <Stack.Screen name="clinic/[code]" options={{ title: t('Share with your clinic') }} />
      <Stack.Screen name="care-join/[token]" options={{ title: t('Care circle') }} />
    </Stack>
    </AppLockProvider>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <LanguageProvider>
      <SessionProvider>
        <StatusBar style="auto" />
        <RootStack />
      </SessionProvider>
      </LanguageProvider>
    </SafeAreaProvider>
  );
}
