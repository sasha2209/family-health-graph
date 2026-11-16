import { Alert, Platform, Share, Switch, View } from 'react-native';
import { useState } from 'react';

import { Body, Button, Card, Chips, ErrorText, Field, H2, Loading, Screen, styles } from '../../components/ui';
import { API_URL } from '../../lib/api';
import { useSession } from '../../lib/session';
import { usePalette } from '../../lib/theme';
import type { Sex } from '../../lib/types';
import { useLoader } from '../../lib/useLoader';

const AI_SCOPE = 'ai_summary';

function confirmDestructive(title: string, message: string, onOk: () => void) {
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(`${title}\n\n${message}`)) onOk();
    return;
  }
  Alert.alert(title, message, [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Delete', style: 'destructive', onPress: onOk },
  ]);
}

export default function SettingsScreen() {
  const c = usePalette();
  const { api, signOut } = useSession();
  const { data, error, reload } = useLoader(async () => {
    const [profile, consents] = await Promise.all([api.profile(false), api.consents()]);
    return { profile, ai: consents.consents.some((x) => x.scope === AI_SCOPE && x.active) };
  });
  const [birth, setBirth] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { profile, ai } = data;
  const birthValue = birth ?? profile.birth_date ?? '';

  return (
    <Screen>
      <Card>
        <H2>About you</H2>
        <Body muted>Used for age- and sex-specific guidance.</Body>
        <Chips<Sex> label="Sex" options={['female', 'male', 'other']} value={(profile.sex ?? '') as Sex}
          onChange={async (sex) => { await api.setDemographics({ sex }); reload(); }} />
        <Field label="Date of birth (YYYY-MM-DD)" value={birthValue} onChangeText={setBirth}
          keyboardType="numbers-and-punctuation" placeholder="1984-05-02" maxLength={10} />
        <View style={styles.row}>
          <Button title="Save" disabled={!/^\d{4}-\d{2}-\d{2}$/.test(birthValue)} onPress={async () => {
            try { await api.setDemographics({ birth_date: birthValue }); setMsg('Saved.'); reload(); }
            catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
          }} />
        </View>
        {msg && <Body muted style={{ marginTop: 6 }}>{msg}</Body>}
      </Card>

      <Card>
        <H2>Privacy</H2>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Body>AI plain-language summaries</Body>
            <Body muted style={{ fontSize: 13 }}>
              Sends only your computed insights (no names or raw records) to an AI model.
            </Body>
          </View>
          <Switch
            accessibilityLabel="AI plain-language summaries"
            value={ai}
            trackColor={{ true: c.accent, false: c.border }}
            onValueChange={async (v) => { await api.setConsent(AI_SCOPE, v); reload(); }}
          />
        </View>
        <View style={styles.row}>
          <Button title="Export my data (FHIR)" onPress={async () => {
            const bundle = await api.exportFhir();
            await Share.share({ title: 'My health record (FHIR)', message: JSON.stringify(bundle, null, 2) });
          }} />
        </View>
      </Card>

      <Card>
        <H2>Account</H2>
        <Body muted style={{ fontSize: 13 }}>Server: {API_URL}</Body>
        <View style={styles.row}>
          <Button title="Sign out of this device" onPress={() => confirmDestructive(
            'Sign out?',
            'This device has no other copy of your sign-in. Until account recovery is added, signing out means you lose access to this account.',
            signOut,
          )} />
          <Button title="Delete all my data" variant="danger" onPress={() => confirmDestructive(
            'Delete everything?',
            'Your record, linked relatives and history will be permanently deleted. This cannot be undone.',
            async () => { await api.deleteAccount(); await signOut(); },
          )} />
        </View>
      </Card>
    </Screen>
  );
}
