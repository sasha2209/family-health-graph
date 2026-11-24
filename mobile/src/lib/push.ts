import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { AndroidImportance } from 'expo-notifications';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { Platform } from 'react-native';

import type { Api } from './api';
import { N } from './translate';

const native = Platform.OS === 'ios' || Platform.OS === 'android';

if (native) {
  // Show alerts while the app is open too (quietly: no sound).
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false,
    }),
  });
}

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? undefined;
}

/** Whether this install can receive push notifications, and if not, why. */
export function pushSupport(): { ok: true } | { ok: false; reason: string } {
  if (!native) return { ok: false, reason: N('Family alerts by notification are available in the phone app.') };
  if (!Device.isDevice) return { ok: false, reason: N('Push notifications need a physical phone.') };
  if (Platform.OS === 'android' && Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
    return { ok: false, reason: N('Expo Go on Android can’t receive push notifications. Use a development build.') };
  }
  if (!projectId()) {
    return { ok: false, reason: N('Push isn’t set up for this build yet (run “eas init” to add a project ID).') };
  }
  return { ok: true };
}

async function register(api: Api): Promise<void> {
  const { data } = await Notifications.getExpoPushTokenAsync({ projectId: projectId() });
  await api.registerPush(data, Platform.OS as 'ios' | 'android');
}

/** Ask for permission (if needed) and register this phone. Returns false if the user declined. */
export async function enablePush(api: Api): Promise<boolean> {
  if (!pushSupport().ok) return false;
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('family', {
      name: 'Family updates',
      importance: AndroidImportance.DEFAULT,
    });
  }
  let { status } = await Notifications.getPermissionsAsync();
  if (status !== 'granted') status = (await Notifications.requestPermissionsAsync()).status;
  if (status !== 'granted') return false;
  await register(api);
  return true;
}

/**
 * Keep the push registration fresh (tokens can change) without prompting,
 * and open the right screen when a notification is tapped.
 */
export function usePushNotifications(api: Api, signedIn: boolean) {
  useEffect(() => {
    if (!signedIn || !pushSupport().ok) return;
    Notifications.getPermissionsAsync()
      .then(({ status }) => (status === 'granted' ? register(api) : undefined))
      .catch(() => undefined);
  }, [api, signedIn]);

  useEffect(() => {
    if (!native) return;
    const open = (response: Notifications.NotificationResponse | null) => {
      const url = response?.notification.request.content.data?.url;
      if (typeof url === 'string' && url.startsWith('/')) router.push(url as never);
    };
    Notifications.getLastNotificationResponseAsync().then(open).catch(() => undefined); // cold start
    const sub = Notifications.addNotificationResponseReceivedListener(open);
    return () => sub.remove();
  }, []);
}
