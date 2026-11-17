import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AppLockProvider } from '../lib/appLock';
import { usePushNotifications } from '../lib/push';
import { SessionProvider, useSession } from '../lib/session';
import { usePalette } from '../lib/theme';

function RootStack() {
  const { ready, token, api } = useSession();
  const c = usePalette();
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
        <Stack.Screen name="insight/[id]" options={{ title: 'Action item' }} />
        <Stack.Screen name="add-history" options={{ title: 'Add family history', presentation: 'modal' }} />
      </Stack.Protected>
      <Stack.Protected guard={!token} redirectTo="/">
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
      </Stack.Protected>
      {/* Reachable signed in or out: invite links open here, and sign-in also links an email. */}
      <Stack.Screen name="invite/[token]" options={{ title: 'Family invitation' }} />
      <Stack.Screen name="sign-in" options={{ title: 'Sign in' }} />
      <Stack.Screen name="clinic/[code]" options={{ title: 'Share with your clinic' }} />
    </Stack>
    </AppLockProvider>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="auto" />
        <RootStack />
      </SessionProvider>
    </SafeAreaProvider>
  );
}
