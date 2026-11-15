import { router } from 'expo-router';
import { Alert, Platform, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Card, Chips, ErrorText, H2, Loading, Screen, styles } from '../../components/ui';
import { capitalize, label, SHARE_OPTIONS, SHARE_SHORT, sideOf } from '../../lib/format';
import { useSession } from '../../lib/session';
import { usePalette } from '../../lib/theme';
import type { FamilyMember, ShareLevel } from '../../lib/types';
import { useLoader } from '../../lib/useLoader';

function confirm(title: string, message: string, onOk: () => void) {
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(`${title}\n\n${message}`)) onOk();
    return;
  }
  Alert.alert(title, message, [{ text: 'Cancel', style: 'cancel' }, { text: 'OK', style: 'destructive', onPress: onOk }]);
}

function Person({ m }: { m: FamilyMember }) {
  const c = usePalette();
  return (
    <View style={[s.person, { borderColor: c.border, backgroundColor: c.surface }]}>
      <Text style={[s.side, { color: c.muted }]}>{sideOf(m.relationship).toUpperCase()}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
        <Text style={[s.name, { color: c.text }]}>
          {capitalize(label(m.relationship))}{m.name ? ` · ${m.name}` : ''}{m.deceased ? ' †' : ''}
        </Text>
        {m.linked && <Text style={[s.linked, { color: c.accent, borderColor: c.accent }]}>LINKED</Text>}
      </View>
      {m.conditions.length ? m.conditions.map((cond) => (
        <Text key={cond.id} style={{ color: c.text, fontSize: 14 }}>
          {cond.name}{cond.onset_age != null ? ` (${cond.age_estimated ? '~' : ''}${cond.onset_age})` : ''}
        </Text>
      )) : <Text style={{ color: c.muted, fontSize: 14 }}>No known conditions</Text>}
    </View>
  );
}

export default function FamilyScreen() {
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(async () => {
    const [profile, links] = await Promise.all([api.profile(true), api.links()]);
    return { profile, links };
  });

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { profile, links } = data;

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <ErrorText>{error}</ErrorText>
      <View style={{ alignSelf: 'flex-start' }}>
        <Button title="+ Add family history" variant="primary" onPress={() => router.push('/add-history')} />
      </View>

      {profile.family.length === 0 ? (
        <Body muted>No relatives yet. Add what you know, or invite a relative to add theirs.</Body>
      ) : (
        <View style={s.grid}>{profile.family.map((m) => <Person key={m.id} m={m} />)}</View>
      )}

      <Card>
        <H2>Linked relatives</H2>
        {links.length === 0 && <Body muted>No one yet. Use the Invite tab to invite a relative.</Body>}
        {links.map((l) => (
          <View key={l.link_id} style={{ marginTop: 12 }}>
            <Body style={{ fontWeight: '600' }}>{capitalize(label(l.relationship))}</Body>
            <Body muted>They share: {SHARE_SHORT[l.they_share]}</Body>
            <Chips<ShareLevel>
              label="You share"
              options={SHARE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={l.you_share}
              onChange={async (v) => { await api.setSharing(l.link_id, v); reload(); }}
            />
            <View style={styles.row}>
              <Button
                title="Unlink"
                variant="danger"
                onPress={() => confirm(
                  'Unlink this relative?',
                  "Neither of you will see the other's shared history.",
                  async () => { await api.unlink(l.link_id); reload(); },
                )}
              />
            </View>
          </View>
        ))}
      </Card>
    </Screen>
  );
}

const s = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  person: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 10, padding: 10, flexGrow: 1, flexBasis: 150, gap: 2 },
  side: { fontSize: 10, letterSpacing: 0.5 },
  name: { fontSize: 14, fontWeight: '600' },
  linked: { fontSize: 9, fontWeight: '700', borderWidth: 1, borderRadius: 4, paddingHorizontal: 4 },
});
