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

const OBS_LABEL: Record<string, string> = {
  hba1c: 'HbA1c', fasting_glucose: 'Fasting glucose', postprandial_glucose: 'Glucose after a meal',
  ldl_cholesterol: 'LDL cholesterol', hdl_cholesterol: 'HDL cholesterol', total_cholesterol: 'Total cholesterol',
  triglycerides: 'Triglycerides', lipoprotein_a: 'Lipoprotein(a)', tsh: 'TSH', hemoglobin: 'Hemoglobin',
  creatinine: 'Creatinine', egfr: 'eGFR', vitamin_d: 'Vitamin D', vitamin_b12: 'Vitamin B12', bmi: 'BMI',
  waist_circumference: 'Waist', systolic_bp: 'Blood pressure (top)', diastolic_bp: 'Blood pressure (bottom)',
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

function confirmRemove(what: string, onOk: () => void) {
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(`Remove ${what}?`)) onOk();
    return;
  }
  Alert.alert(`Remove ${what}?`, undefined, [
    { text: 'Cancel', style: 'cancel' },
    { text: 'Remove', style: 'destructive', onPress: onOk },
  ]);
}

/** A relative's managed profile: what you know about them, built from their own documents. */
export default function PersonScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useSession();
  const c = usePalette();
  const { data: m, error, refreshing, reload } = useLoader(() => api.familyMember(id));
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [age, setAge] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);

  if (!m) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const who = capitalize(label(m.relationship));
  const meds = m.medications ?? [];
  const results = latestByCode(m.observations ?? []);
  const remove = (itemId: string, what: string) =>
    confirmRemove(what, async () => { await api.deleteFamilyItem(m.id, itemId); reload(); });

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <Stack.Screen options={{ title: m.name ? `${who} · ${m.name}` : who }} />
      <View style={{ gap: 4 }}>
        <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>
          {m.name ?? who}{m.deceased ? ' †' : ''}
        </Text>
        <Body muted>
          {[m.name ? who : null, m.age != null ? `${m.age} years` : 'Age not recorded',
            m.linked ? 'Shares their own history with you' : null].filter(Boolean).join(' · ')}
        </Body>
        {!editing && (
          <Pressable accessibilityRole="button" onPress={() => { setName(m.name ?? ''); setAge(m.age != null ? String(m.age) : ''); setEditing(true); }}>
            <Text style={{ color: c.accent, fontSize: 14, marginTop: 4 }}>Edit name and age</Text>
          </Pressable>
        )}
      </View>

      {editing && (
        <Card>
          <Field label="Name (optional)" value={name} onChangeText={setName} autoCapitalize="words" />
          <Field label="Age" value={age} onChangeText={setAge} keyboardType="number-pad" />
          <View style={styles.row}>
            <Button title="Save" variant="primary" onPress={async () => {
              setSaveError(null);
              try {
                await api.updateFamilyMember(m.id, { name: name.trim() || null, age: age ? Number(age) : null });
                setEditing(false); reload();
              } catch (e) { setSaveError(e instanceof Error ? e.message : String(e)); }
            }} />
            <Button title="Cancel" onPress={() => setEditing(false)} />
          </View>
          <ErrorText>{saveError}</ErrorText>
        </Card>
      )}

      <Section title="Diagnoses">
        {m.conditions.length === 0 && <View style={{ padding: 16 }}><Body muted>None recorded yet.</Body></View>}
        {m.conditions.map((x, i) => (
          <Row key={x.id} title={x.name}
               detail={[x.onset_age != null ? `Diagnosed at ${x.age_estimated ? 'about ' : ''}${x.onset_age}` : null,
                        sourceLabel(x.source)].filter(Boolean).join(' · ') || undefined}
               last={i === m.conditions.length - 1} />
        ))}
      </Section>

      {meds.length > 0 && (
        <Section title="Medicines">
          {meds.map((x, i) => (
            <Row key={x.id} title={x.name}
                 detail={[x.generic && !x.name.toLowerCase().includes(x.generic.split(' ')[0]) ? x.generic : null, x.dosage,
                          x.prescribed_on ? `prescribed ${formatDay(x.prescribed_on)}` : null].filter(Boolean).join(' · ')}
                 onPress={() => remove(x.id, x.name)} last={i === meds.length - 1} />
          ))}
        </Section>
      )}
      {meds.length > 0 && (
        <Body muted style={{ fontSize: 12, marginTop: -6 }}>Tap a medicine to remove it if they no longer take it.</Body>
      )}

      {results.length > 0 && (
        <Section title="Test results" right={
          <Pressable accessibilityRole="link" onPress={() => router.push({ pathname: '/results', params: { member: m.id, who: m.relationship } })}>
            <Text style={{ color: c.accent, fontSize: 14 }}>Over time ›</Text>
          </Pressable>}>
          {results.map(({ o, earlier }, i) => (
            <Row key={o.id} title={`${OBS_LABEL[o.code] ?? label(o.code)}: ${o.value} ${o.unit}`.trim()}
                 detail={`${formatDay(o.effective_date)}${earlier.length
                   ? ` · before: ${earlier.slice(0, 2).map((e) => `${e.value} (${formatDay(e.effective_date)})`).join(', ')}` : ''}`}
                 last={i === results.length - 1} />
          ))}
        </Section>
      )}

      <ScanCard title={`Add ${who.toLowerCase()}’s prescription or report`} subject={m.relationship} memberId={m.id} />

      {m.documents.length > 0 && (
        <Section title="Documents">
          {m.documents.map((d, i) => (
            <Row key={d.id} title={DOC_TYPE_LABEL[d.doc_type]} detail={formatDay(d.doc_date)}
                 onPress={() => router.push({ pathname: '/document/[id]', params: { id: d.id } })}
                 last={i === m.documents.length - 1} />
          ))}
        </Section>
      )}

      <Body muted style={{ fontSize: 12 }}>
        Only you can see {who.toLowerCase()}’s medicines, results and documents. Relatives you link with see
        diagnoses only, and only if you choose to share your family tree.
      </Body>
    </Screen>
  );
}
