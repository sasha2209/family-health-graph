import { router } from 'expo-router';
import { Alert, Platform, Text, View } from 'react-native';

import { Badge, Row, Section } from '../../components/list';

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

const SIDES = ['Immediate', 'Maternal', 'Paternal', 'Extended'] as const;

function conditionSummary(m: FamilyMember): string {
  if (!m.conditions.length) return 'No known conditions';
  return m.conditions.map((cond) =>
    cond.name + (cond.onset_age != null ? ` (${cond.age_estimated ? '~' : ''}${cond.onset_age})` : '')).join(', ');
}

export default function FamilyScreen() {
  const c = usePalette();
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
        SIDES.map((side) => {
          const members = profile.family.filter((m) => sideOf(m.relationship) === side);
          if (!members.length) return null;
          return (
            <Section key={side} title={`${side === 'Immediate' ? 'Immediate family' : `${side} side`}`}
                     right={<Text style={{ color: c.muted }}>{members.length}</Text>}>
              {members.map((m, i) => (
                <Row
                  key={m.id}
                  title={`${capitalize(label(m.relationship))}${m.name ? ` · ${m.name}` : ''}${m.deceased ? ' †' : ''}`}
                  detail={conditionSummary(m)}
                  badge={m.linked ? <Badge label="Linked" fg={c.accent} bg={c.bg} /> : undefined}
                  last={i === members.length - 1}
                />
              ))}
            </Section>
          );
        })
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
