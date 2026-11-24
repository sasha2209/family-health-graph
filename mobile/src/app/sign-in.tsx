import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { AppleSignIn } from '../components/AppleSignIn';
import { Body, Button, Card, ErrorText, Field, H2, Screen, styles } from '../components/ui';
import { publicApi } from '../lib/api';
import { useSession } from '../lib/session';
import type { SignInResult } from '../lib/types';
import { useT } from '../lib/i18n';

const RESEND_SECONDS = 30;

/**
 * Email sign-in with a one-time code. Signed out, it signs in (or creates an
 * account). Signed in (mode=link), it adds the email to the current account so
 * it can be recovered and used on other devices.
 */
export default function SignIn() {
  const { t } = useT();
  const { mode } = useLocalSearchParams<{ mode?: string }>();
  const { token, api, signIn } = useSession();
  const linking = mode === 'link' && !!token;

  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function sendCode() {
    setBusy(true); setError(null);
    try {
      await publicApi.emailStart(email.trim());
      setStep('code'); setCode(''); setCooldown(RESEND_SECONDS);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function finish(result: SignInResult) {
    if (result.token) {
      await signIn(result.token);
      router.replace('/');
    } else {
      router.back(); // linked to the current account; Settings refreshes on focus
    }
  }

  async function verify(value = code) {
    setBusy(true); setError(null);
    try {
      await finish(await api.emailVerify(email.trim(), value));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card>
        <H2>{t(linking ? 'Protect your account' : 'Sign in or create an account')}</H2>
        <Body muted>
          {linking
            ? t('Add your email so you can sign in on another phone and get your data back if you lose this one.')
            : t('We’ll email you a 6-digit code. No password needed.')}
        </Body>

        {step === 'email' ? (
          <>
            <Field
              label={t('Email')}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              keyboardType="email-address"
              textContentType="emailAddress"
              returnKeyType="send"
              onSubmitEditing={() => email.trim() && sendCode()}
              placeholder={t('you@example.com')}
            />
            <View style={styles.row}>
              <Button title={t('Send code')} variant="primary" onPress={sendCode} busy={busy} disabled={!email.trim()} />
            </View>
          </>
        ) : (
          <>
            <Body style={{ marginTop: 12 }}>Enter the code we sent to {email.trim()}.</Body>
            <Field
              label={t('6-digit code')}
              value={code}
              onChangeText={(v) => {
                const digits = v.replace(/\D/g, '').slice(0, 6);
                setCode(digits);
                if (digits.length === 6) verify(digits);
              }}
              keyboardType="number-pad"
              textContentType="oneTimeCode"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="123456"
            />
            <View style={styles.row}>
              <Button title={linking ? 'Add email' : 'Sign in'} variant="primary" onPress={() => verify()}
                busy={busy} disabled={code.length !== 6} />
              <Button title={cooldown > 0 ? t('Resend in {n}s', { n: cooldown }) : t('Resend code')} onPress={sendCode}
                disabled={cooldown > 0 || busy} />
              <Button title={t('Change email')} onPress={() => { setStep('email'); setError(null); }} />
            </View>
          </>
        )}
        <ErrorText>{error}</ErrorText>
      </Card>

      <View style={{ gap: 8 }}>
        <AppleSignIn link={linking} onDone={finish} onError={setError} />
      </View>
    </Screen>
  );
}
