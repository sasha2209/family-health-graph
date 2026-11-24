import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, Platform, Pressable, Text, View } from 'react-native';

import { Row, Section } from '../../components/list';
import { ScanCard } from '../../components/ScanCard';
import { Body, Button, Card, ErrorText, Field, Loading, Screen, styles } from '../../components/ui';
import { capitalize, DOC_TYPE_LABEL, formatDay, label, sourceLabel } from '../../lib/format';
import { useSession } from '../../lib/session';
import { usePalette } from '../../lib/theme';
import type { Observation } from '../../lib/types';
import { useLoader } from '../../lib/useLoader';
import { N, useT } from '../../lib/i18n';

const OBS_LABEL: Record<string, string> = {
  hba1c: 'HbA1c', fasting_glucose: N('Fasting glucose'), postprandial_glucose: N('Glucose after a meal'),
  ldl_cholesterol: N('LDL cholesterol'), hdl_cholesterol: N('HDL cholesterol'), total_cholesterol: N('Total cholesterol'),
  triglycerides: N('Triglycerides'), lipoprotein_a: 'Lipoprotein(a)', tsh: 'TSH', hemoglobin: N('Hemoglobin'),
  creatinine: N('Creatinine'), egfr: 'eGFR', vitamin_d: N('Vitamin D'), vitamin_b12: N('Vitamin B12'), bmi: 'BMI',
  waist_circumference: N('Waist'), systolic_bp: N('Blood pressure (top)'), diastolic_bp: N('Blood pressure (bottom)'),
};

/** Latest result per test, with how many earlier results there are. */
function latestByCode(obs: Observation[]): { o: Observation; earlier: Observation[] }[] {
  const groups = new Map<string, Observation[]>();
  for (const o of obs) groups.set(o.code, [...(groups.get(o.code) ?? []), o]);
  return [...groups.values()].map((list) => {
    const sorted = [...list].sort((a, b) => (b.effective_date ?? '').localeCompare(a.effective_date ?? ''));
    return { o: sorted[0], earlier: sorted.slice(1) };
  });
}

function confirmRemove(what: string, onOk: () => void, t: (s: string, v?: Record<string, string>) => string) {
  const q = t('Remove {what}?', { what });
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(q)) onOk();
    return;
  }
  Alert.alert(q, undefined, [
    { text: t('Cancel'), style: 'cancel' },
    { text: t('Remove'), style: 'destructive', onPress: onOk },
  ]);
}

/** A relative's managed profile: what you know about them, built from their own documents. */
export default function PersonScreen() {
  const { t } = useT();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useSession();
  const c = usePalette();
  const { data: m, error, refreshing, reload } = useLoader(() => api.familyMember(id));
  const { data: me } = useLoader(() => api.me());
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);

  if (!m) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const who = capitalize(t(label(m.relationship)));
  const meds = m.medications ?? [];
  const results = latestByCode(m.observations ?? []);
  const remove = (itemId: string, what: string) =>
    confirmRemove(what, async () => { await api.deleteFamilyItem(m.id, itemId); reload(); }, t);

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <Stack.Screen options={{ title: m.name ? `${who} · ${m.name}` : who }} />
      <View style={{ gap: 4 }}>
        <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>
          {m.name ?? who}{m.deceased ? ' †' : ''}
        </Text>
        <Body muted>
          {[m.name ? who : null, m.age != null ? t('{n} years', { n: m.age }) : t('Age not recorded'),
            m.linked ? t('Shares their own history with you') : null].filter(Boolean).join(' · ')}
        </Body>
        {!editing && (
          <Pressable accessibilityRole="button" onPress={() => { setName(m.name ?? ''); setAge(m.age != null ? String(m.age) : ''); setEditing(true); }}>
            <Text style={{ color: c.accent, fontSize: 14, marginTop: 4 }}>{t('Edit name and age')}</Text>
          </Pressable>
        )}
      </View>

      {editing && (
        <Card>
          <Field label={t('Name (optional)')} value={name} onChangeText={setName} autoCapitalize="words" />
          <Field label={t('Age')} value={age} onChangeText={setAge} keyboardType="number-pad" />
          <View style={styles.row}>
            <Button title={t('Save')} variant="primary" onPress={async () => {
              setSaveError(null);
              try {
                await api.updateFamilyMember(m.id, { name: name.trim() || null, age: age ? Number(age) : null });
                setEditing(false); reload();
              } catch (e) { setSaveError(e instanceof Error ? e.message : String(e)); }
            }} />
            <Button title={t('Cancel')} onPress={() => setEditing(false)} />
          </View>
          <ErrorText>{saveError}</ErrorText>
        </Card>
      )}

      {!m.deceased && me && (
        <Section title={t('Caregiver mode')}>
          <Row title={m.name ? t('Help {name} with medicines', { name: m.name }) : t('Help them with medicines')}
               detail={t('Daily reminders, refill alerts, an emergency summary, and siblings can help')}
               onPress={() => router.push({ pathname: '/care', params: { id: `${me.user_id}.${m.id}` } })} last />
        </Section>
      )}

      <Section title={t('Diagnoses')}>
        {m.conditions.length === 0 && <View style={{ padding: 16 }}><Body muted>{t('None recorded yet.')}</Body></View>}
        {m.conditions.map((x, i) => (
          <Row key={x.id} title={x.name}
               detail={[x.onset_age != null ? t(x.age_estimated ? 'Diagnosed at about {n}' : 'Diagnosed at {n}', { n: x.onset_age }) : null,
                        sourceLabel(x.source) ? t(sourceLabel(x.source)!) : null].filter(Boolean).join(' · ') || undefined}
               last={i === m.conditions.length - 1} />
        ))}
      </Section>

      {meds.length > 0 && (
        <Section title={t('Medicines')}>
          {meds.map((x, i) => (
            <Row key={x.id} title={x.name}
                 detail={[x.generic && !x.name.toLowerCase().includes(x.generic.split(' ')[0]) ? x.generic : null, x.dosage,
                          x.prescribed_on ? t('prescribed {date}', { date: formatDay(x.prescribed_on) }) : null].filter(Boolean).join(' · ')}
                 onPress={() => remove(x.id, x.name)} last={i === meds.length - 1} />
          ))}
        </Section>
      )}
      {meds.length > 0 && (
        <Body muted style={{ fontSize: 12, marginTop: -6 }}>{t('Tap a medicine to remove it if they no longer take it.')}</Body>
      )}

      {results.length > 0 && (
        <Section title={t('Test results')} right={
          <Pressable accessibilityRole="link" onPress={() => router.push({ pathname: '/results', params: { member: m.id, who: m.relationship } })}>
            <Text style={{ color: c.accent, fontSize: 14 }}>{t('Over time ›')}</Text>
          </Pressable>}>
          {results.map(({ o, earlier }, i) => (
            <Row key={o.id} title={`${OBS_LABEL[o.code] ? t(OBS_LABEL[o.code]) : label(o.code)}: ${o.value} ${o.unit}`.trim()}
                 detail={`${formatDay(o.effective_date)}${earlier.length
                   ? ` · ${t('before:')} ${earlier.slice(0, 2).map((e) => `${e.value} (${formatDay(e.effective_date)})`).join(', ')}` : ''}`}
                 last={i === results.length - 1} />
          ))}
        </Section>
      )}

      <ScanCard title={t('Add {who}’s prescription or report', { who: who.toLowerCase() })} subject={m.relationship} memberId={m.id} />

      {m.documents.length > 0 && (
        <Section title={t('Documents')}>
          {m.documents.map((d, i) => (
            <Row key={d.id} title={t(DOC_TYPE_LABEL[d.doc_type])} detail={formatDay(d.doc_date)}
                 onPress={() => router.push({ pathname: '/document/[id]', params: { id: d.id } })}
                 last={i === m.documents.length - 1} />
          ))}
        </Section>
      )}

      <Body muted style={{ fontSize: 12 }}>
        {t('Only you can see {who}’s medicines, results and documents. Relatives you link with see diagnoses only, and only if you choose to share your family tree.', { who: who.toLowerCase() })}
      </Body>
    </Screen>
  );
}
