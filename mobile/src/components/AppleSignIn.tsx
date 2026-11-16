import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import { useEffect, useState } from 'react';
import { Platform, useColorScheme } from 'react-native';

import { publicApi } from '../lib/api';
import { useSession } from '../lib/session';
import type { SignInResult } from '../lib/types';

/**
 * Sign in with Apple. Renders nothing unless we're on iOS, the device supports
 * it, and the server has Apple sign-in configured (FHG_APPLE_AUDIENCES).
 * With a signed-in session it links Apple to the current account instead.
 */
export function AppleSignIn({ onDone, onError, link = false }: {
  onDone: (result: SignInResult) => void;
  onError: (message: string) => void;
  link?: boolean;
}) {
  const { api } = useSession();
  const scheme = useColorScheme();
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'ios') return;
    Promise.all([AppleAuthentication.isAvailableAsync(), publicApi.authConfig()])
      .then(([device, config]) => setAvailable(device && config.apple))
      .catch(() => setAvailable(false));
  }, []);

  if (!available) return null;

  async function onPress() {
    try {
      // The server checks this nonce against the token, which prevents replaying a stolen token.
      const nonce = Crypto.randomUUID();
      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [AppleAuthentication.AppleAuthenticationScope.EMAIL],
        nonce,
      });
      if (!credential.identityToken) throw new Error('Apple did not return a sign-in token');
      onDone(await api.appleSignIn(credential.identityToken, nonce));
    } catch (e) {
      if ((e as { code?: string }).code === 'ERR_REQUEST_CANCELED') return; // user closed the sheet
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <AppleAuthentication.AppleAuthenticationButton
      buttonType={link ? AppleAuthentication.AppleAuthenticationButtonType.CONTINUE
        : AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
      buttonStyle={scheme === 'dark' ? AppleAuthentication.AppleAuthenticationButtonStyle.WHITE
        : AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
      cornerRadius={10}
      style={{ height: 46, width: '100%' }}
      onPress={onPress}
    />
  );
}
