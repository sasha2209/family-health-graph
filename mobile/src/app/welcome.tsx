import { router } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { AppleSignIn } from '../components/AppleSignIn';
import { Body, Button, Card, ErrorText, Field, Screen, styles } from '../components/ui';
import { parseInviteToken, publicApi } from '../lib/api';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';

export default function Welcome() {
  const c = usePalette();
  const { signIn } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inviteText, setInviteText] = useState('');

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const { token } = await publicApi.createAccount();
      await signIn(token); // the route guard moves us into the app
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function openInvite() {
    const t = parseInviteToken(inviteText);
    if (!t) { setError("That doesn't look like an invite link."); return; }
    router.push({ pathname: '/invite/[token]', params: { token: t } });
  }

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={{ paddingVertical: 24 }}>
        <Text accessibilityRole="header" style={{ fontSize: 28, fontWeight: '700', color: c.text }}>
          Family Health Graph
        </Text>
        <Body muted style={{ marginTop: 8 }}>
          Bring together your health records and your family’s history to see what’s worth
          discussing with your clinician.
        </Body>
      </View>

      <Card>
        <Body>
          {'•'} Explainable insights based on published screening guidelines{'\n'}
          {'•'} Invite relatives so your family’s history builds itself{'\n'}
          {'•'} You control what’s shared, and can delete everything at any time
        </Body>
        <View style={[styles.row, { flexDirection: 'column', alignItems: 'stretch' }]}>
          <Button title="Continue with email" variant="primary" onPress={() => router.push('/sign-in')} />
          <AppleSignIn
            onDone={async (r) => { if (r.token) await signIn(r.token); }}
            onError={setError}
          />
          <Button title="Try it without an account" onPress={start} busy={busy} />
        </View>
        <Body muted style={{ fontSize: 13, marginTop: 8 }}>
          Without an account, only this phone can open your data. You can add an email any time.
        </Body>
      </Card>

      <Card>
        <Body>Did a relative send you an invite?</Body>
        <Field
          label="Paste the invite link"
          value={inviteText}
          onChangeText={setInviteText}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="https://…/invite/…"
        />
        <View style={styles.row}>
          <Button title="Open invite" onPress={openInvite} disabled={!inviteText.trim()} />
        </View>
      </Card>

      <ErrorText>{error}</ErrorText>
      <Body muted style={{ fontSize: 12 }}>
        Educational information based on simplified summaries of published guidelines. Not a diagnosis
        and not a replacement for advice from a clinician.
      </Body>
    </Screen>
  );
}
