import { router } from 'expo-router';
import { Alert, Platform, Text, View } from 'react-native';

import { Badge, Row, Section } from '../../components/list';

import { Body, Button, Card, Chips, ErrorText, H2, Loading, Screen, styles } from '../../components/ui';
import { capitalize, label, SHARE_OPTIONS, SHARE_SHORT, sideOf } from '../../lib/format';
import { useT } from '../../lib/i18n';
import { useSession } from '../../lib/session';
import { usePalette } from '../../lib/theme';
import type { FamilyMember, ShareLevel } from '../../lib/types';
import { useLoader } from '../../lib/useLoader';

function confirm(title: string, message: string, onOk: () => void, t: (s: string) => string) {
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(`${title}\n\n${message}`)) onOk();
    return;
  }
  Alert.alert(title, message, [{ text: t('Cancel'), style: 'cancel' }, { text: t('OK'), style: 'destructive', onPress: onOk }]);
}

const SIDES = ['Immediate', 'Maternal', 'Paternal', 'Extended'] as const;

function conditionSummary(m: FamilyMember, t: (s: string, v?: Record<string, number>) => string): string {
  const parts = m.conditions.map((cond) =>
    cond.name + (cond.onset_age != null ? ` (${cond.age_estimated ? '~' : ''}${cond.onset_age})` : ''));
  const meds = m.medications?.length ?? 0;
  const results = new Set((m.observations ?? []).map((o) => o.code)).size;
  const extra = [meds ? t(meds > 1 ? '{n} medicines' : '1 medicine', { n: meds }) : '',
                 results ? t(results > 1 ? '{n} test results' : '1 test result', { n: results }) : '']
    .filter(Boolean).join(', ');
  return [parts.join(', ') || t('No known conditions'), extra].filter(Boolean).join(' · ');
}

export default function FamilyScreen() {
  const c = usePalette();
  const { t } = useT();
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(async () => {
    const [profile, own, links] = await Promise.all([api.profile(true), api.profile(false), api.links()]);
    // Relatives on your own record open their profile; ones only shared by a linked relative don't have one.
    return { profile, links, ownIds: new Set(own.family.map((m) => m.id)) };
  });

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { profile, links, ownIds } = data;

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <ErrorText>{error}</ErrorText>
      <View style={{ alignSelf: 'flex-start' }}>
        <Button title={t('+ Add family history')} variant="primary" onPress={() => router.push('/add-history')} />
      </View>

      {profile.family.length === 0 ? (
        <Body muted>{t('No relatives yet. Add what you know, or invite a relative to add theirs.')}</Body>
      ) : (
        SIDES.map((side) => {
          const members = profile.family.filter((m) => sideOf(m.relationship) === side);
          if (!members.length) return null;
          return (
            <Section key={side} title={t(side === 'Immediate' ? 'Immediate family' : `${side} side`)}
                     right={<Text style={{ color: c.muted }}>{members.length}</Text>}>
              {members.map((m, i) => (
                <Row
                  key={m.id}
                  title={`${capitalize(t(label(m.relationship)))}${m.name ? ` · ${m.name}` : ''}${m.deceased ? ' †' : ''}`}
                  detail={conditionSummary(m, t)}
                  badge={m.linked ? <Badge label={t('Linked')} fg={c.accent} bg={c.bg} /> : undefined}
                  onPress={ownIds.has(m.id) ? () => router.push({ pathname: '/person/[id]', params: { id: m.id } }) : undefined}
                  last={i === members.length - 1}
                />
              ))}
            </Section>
          );
        })
      )}

      <Card>
        <H2>{t('Linked relatives')}</H2>
        {links.length === 0 && <Body muted>{t('No one yet. Use the Invite tab to invite a relative.')}</Body>}
        {links.map((l) => (
          <View key={l.link_id} style={{ marginTop: 12 }}>
            <Body style={{ fontWeight: '600' }}>{capitalize(t(label(l.relationship)))}</Body>
            <Body muted>{t('They share: {what}', { what: t(SHARE_SHORT[l.they_share]) })}</Body>
            <Chips<ShareLevel>
              label={t('You share')}
              options={SHARE_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
              value={l.you_share}
              onChange={async (v) => { await api.setSharing(l.link_id, v); reload(); }}
            />
            <View style={styles.row}>
              <Button
                title={t('Unlink')}
                variant="danger"
                onPress={() => confirm(
                  t('Unlink this relative?'),
                  t("Neither of you will see the other's shared history."),
                  async () => { await api.unlink(l.link_id); reload(); },
                  t,
                )}
              />
            </View>
          </View>
        ))}
      </Card>
    </Screen>
  );
}
