import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Linking, Platform, Text, View } from 'react-native';

import { Check, Row, Section } from '../components/list';
import { Body, Button, ErrorText, Loading, Screen, styles } from '../components/ui';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import { useLoader } from '../lib/useLoader';

const KIND: Record<string, string> = {
  genetic_counseling: 'Genetic counseling service', genetic_testing: 'Genetic testing company', lab: 'Laboratory',
  specialist: 'Specialist', prevention_program: 'Prevention program', other: 'Health service',
};

function go(url: string) {
  if (Platform.OS === 'web') globalThis.location.assign(url);
  else Linking.openURL(url);
}

/** The consent screen a partner app sends people to ("Connect with Family Health Graph"). */
export default function AuthorizeScreen() {
  const q = useLocalSearchParams<{ client_id: string; redirect_uri: string; scope: string; state?: string;
                                   code_challenge: string; code_challenge_method: string }>();
  const { api } = useSession();
  const c = usePalette();
  const { data, error } = useLoader(() => api.oauthRequest({ client_id: q.client_id, redirect_uri: q.redirect_uri,
                                                             scope: q.scope ?? '' }));
  const [off, setOff] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const chosen = data.scopes.map((s) => s.scope).filter((s) => !off.has(s));
  const host = (() => { try { return new URL(q.redirect_uri).host; } catch { return q.redirect_uri; } })();

  async function decide(allow: boolean) {
    setBusy(true); setActionError(null);
    try {
      const r = allow
        ? await api.oauthApprove({ client_id: q.client_id, redirect_uri: q.redirect_uri, scopes: chosen, state: q.state,
                                   code_challenge: q.code_challenge, code_challenge_method: q.code_challenge_method })
        : await api.oauthDeny({ client_id: q.client_id, redirect_uri: q.redirect_uri, state: q.state });
      go(r.redirect_to);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <Screen>
      <View style={{ gap: 6 }}>
        <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>
          {data.partner.name} wants to read your family history
        </Text>
        <Body muted>{KIND[data.partner.kind] ?? 'Health service'} · returns you to {host}</Body>
      </View>

      <Section title="Choose what to share">
        {data.scopes.map((s, i) => (
          <Row key={s.scope} title={s.description} leading={<Check done={!off.has(s.scope)} />}
               onPress={() => setOff((prev) => { const n = new Set(prev); if (n.has(s.scope)) n.delete(s.scope); else n.add(s.scope); return n; })}
               last={i === data.scopes.length - 1} />
        ))}
      </Section>

      <Body muted style={{ fontSize: 13 }}>
        They can read only what you tick, for up to {Math.round(data.expires_in_days / 30)} months. They never see
        relatives’ names, or anything a linked relative shared with you. You can remove their access any time in
        Settings, and every time they read your record it shows in your activity log.
      </Body>

      <View style={styles.row}>
        <Button title="Allow" variant="primary" busy={busy} disabled={busy || chosen.length === 0} onPress={() => decide(true)} />
        <Button title="Don’t allow" disabled={busy} onPress={() => decide(false)} />
      </View>
      <ErrorText>{actionError}</ErrorText>
    </Screen>
  );
}
