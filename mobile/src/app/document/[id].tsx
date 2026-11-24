import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';

import { Check, Row, Section } from '../../components/list';
import { Banner, Body, Button, Card, Chips, ErrorText, Field, Loading, Screen, styles } from '../../components/ui';
import { ALL_RELATIONSHIPS, capitalize, DOC_TYPE_LABEL, formatDay, label } from '../../lib/format';
import { useSession } from '../../lib/session';
import { usePalette } from '../../lib/theme';
import type { DocExtraction, DocType, DocumentDetail } from '../../lib/types';
import { useLoader } from '../../lib/useLoader';
import { useT } from '../../lib/i18n';

const QUICK_SUBJECTS = ['self', 'mother', 'father'] as const;
const DOC_TYPES: DocType[] = ['prescription', 'lab_report', 'discharge_summary', 'other'];

type T = (s: string, v?: Record<string, string | number>) => string;
const subjectLabel = (s: string, t: T) => (s === 'self' ? t('Me') : capitalize(t(label(s))));

function flagText(flag: string | null | undefined, t: T) {
  return flag === 'h' ? ` · ${t('high')}` : flag === 'l' ? ` · ${t('low')}` : '';
}

/** Keys of everything found, all ticked to start with. */
function allKeys(e: DocExtraction): Set<string> {
  return new Set([
    ...e.conditions.map((_, i) => `c${i}`), ...e.medications.map((_, i) => `m${i}`),
    ...e.observations.map((_, i) => `o${i}`),
    ...e.family.flatMap((r, i) => r.conditions.map((_, j) => `f${i}.${j}`)),
  ]);
}

function HowRead({ doc }: { doc: DocumentDetail }) {
  const { t } = useT();
  const how = t(doc.method === 'pdf_text' ? 'Read from the PDF’s text' : doc.method === 'ocr' ? 'Read from the image on our server'
    : doc.method === 'fhir' ? 'Read from a health record file' : 'No text found');
  const ai = doc.ai_used
    ? ` · ${t('AI helped ({n} tokens)', { n: (doc.input_tokens + doc.output_tokens).toLocaleString() })}`
    : ` · ${t('no AI used')}`;
  return <Body muted style={{ fontSize: 13 }}>{how}{ai}</Body>;
}

export default function DocumentReview() {
  const { t } = useT();
  const { id, subject: presetSubject, member } = useLocalSearchParams<{ id: string; subject?: string; member?: string }>();
  const { api } = useSession();
  const c = usePalette();
  const { data: doc, error, reload } = useLoader(() => api.document(id));

  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [subject, setSubject] = useState(presetSubject ?? 'self');
  const [moreSubjects, setMoreSubjects] = useState(!!presetSubject && !QUICK_SUBJECTS.includes(presetSubject as never));
  const [docType, setDocType] = useState<DocType | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [age, setAge] = useState<string | null>(null);
  const [showText, setShowText] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [result, setResult] = useState<string[] | null>(null);

  if (!doc) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const e = doc.extraction;
  const keys = picked ?? allKeys(e);
  const type = docType ?? e.doc_type;
  const dateValue = date ?? e.doc_date ?? '';
  const ageValue = age ?? (e.patient.age != null ? String(e.patient.age) : '');
  const self = subject === 'self';
  const toggle = (k: string) => {
    const next = new Set(keys);
    if (next.has(k)) next.delete(k); else next.add(k);
    setPicked(next);
  };
  const tick = (k: string) => <Check done={keys.has(k)} />;
  const count = keys.size;
  const nothing = e.conditions.length + e.medications.length + e.observations.length + e.family.length === 0;

  async function save() {
    setBusy(true); setSaveError(null);
    try {
      if (dateValue && !/^\d{4}-\d{2}-\d{2}$/.test(dateValue)) throw new Error(t('Use the date format YYYY-MM-DD.'));
      const r = await api.saveDocument(id, {
        subject, doc_type: type, doc_date: dateValue || null,
        relative_age: !self && ageValue ? Number(ageValue) : null,
        member_id: !self && member && subject === presetSubject ? member : null,
        conditions: e.conditions.filter((_, i) => keys.has(`c${i}`)),
        medications: e.medications.filter((_, i) => keys.has(`m${i}`)),
        observations: e.observations.filter((_, i) => keys.has(`o${i}`)),
        family: e.family.map((rel, i) => ({ ...rel, conditions: rel.conditions.filter((_, j) => keys.has(`f${i}.${j}`)) }))
          .filter((rel) => rel.conditions.length),
      });
      setResult(r.warnings);
      reload();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    setBusy(true);
    try {
      await api.deleteDocument(id);
      if (router.canGoBack()) router.back(); else router.replace('/');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  const header = (
    <View style={{ gap: 4 }}>
      <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>
        {DOC_TYPE_LABEL[type]}
      </Text>
      <Body muted>{[formatDay(e.doc_date), e.facility, e.doctor].filter(Boolean).join(' · ')}</Body>
      <HowRead doc={doc} />
    </View>
  );

  if (doc.status === 'saved') {
    return (
      <Screen>
        <Stack.Screen options={{ title: DOC_TYPE_LABEL[doc.doc_type] }} />
        {header}
        <Banner>{doc.subject === 'self' ? t('Added to your record.') : t('Added to your {who}’s record.', { who: t(label(doc.subject)) })}</Banner>
        {result?.map((w) => <Body muted key={w}>{w}</Body>)}
        <View style={styles.row}>
          <Button title={t('Done')} variant="primary"
                  onPress={() => (presetSubject && router.canGoBack() ? router.back() : router.replace('/'))} />
          <Button title={t('Add another')} onPress={() => (router.canGoBack() ? router.back() : router.replace('/add-history'))} />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <Stack.Screen options={{ title: t('Check what we found') }} />
      {header}
      {doc.warnings?.map((w) => <Banner key={w} tone="high">{w}</Banner>)}

      <Card>
        <Chips label={t('Whose document is this?')}
               options={(moreSubjects ? ['self', ...ALL_RELATIONSHIPS.filter((r) => r !== 'other')] : [...QUICK_SUBJECTS])
                 .map((v) => ({ value: v, label: subjectLabel(v, t) }))}
               value={subject} onChange={setSubject} />
        {!moreSubjects && (
          <Pressable accessibilityRole="button" onPress={() => setMoreSubjects(true)} style={{ marginTop: 8 }}>
            <Text style={{ color: c.accent, fontSize: 14 }}>{t('Someone else in the family…')}</Text>
          </Pressable>
        )}
        {e.patient.name && (
          <Body muted style={{ fontSize: 13, marginTop: 8 }}>
            {t('Name on the document: {name}', { name: e.patient.name ?? '' })}{e.patient.age != null ? `, ${e.patient.age}` : ''}
          </Body>
        )}
        {!self && (
          <Field label={t('{who}’s age (optional)', { who: capitalize(t(label(subject))) })} value={ageValue} onChangeText={setAge}
                 keyboardType="number-pad" />
        )}
      </Card>

      {nothing && (
        <Banner tone="high">
          {t('We couldn’t find diagnoses, medicines or test results in this document. You can type them in instead.')}
        </Banner>
      )}

      {e.conditions.length > 0 && (
        <Section title={self ? t('Diagnoses') : t('{who}’s diagnoses', { who: capitalize(t(label(subject))) })}>
          {e.conditions.map((x, i) => (
            <Row key={`c${i}`} title={x.name} detail={x.evidence} leading={tick(`c${i}`)}
                 onPress={() => toggle(`c${i}`)} last={i === e.conditions.length - 1} />
          ))}
        </Section>
      )}

      {e.observations.length > 0 && (
        <Section title={self ? t('Test results') : t('{who}’s test results', { who: capitalize(t(label(subject))) })}>
          {e.observations.map((o, i) => (
            <Row key={`o${i}`} title={`${o.display || label(o.code)}: ${o.value} ${o.unit}`.trim()}
                 detail={`${formatDay(dateValue || null)}${flagText(o.flag, t)}`} leading={tick(`o${i}`)}
                 onPress={() => toggle(`o${i}`)} last={i === e.observations.length - 1} />
          ))}
        </Section>
      )}

      {e.medications.length > 0 && (
        <Section title={self ? t('Medicines') : t('{who}’s medicines', { who: capitalize(t(label(subject))) })}>
          {e.medications.map((m, i) => (
            <Row key={`m${i}`} title={m.name}
                 detail={[m.generic && !m.name.toLowerCase().includes(m.generic.split(' ')[0]) ? m.generic : null, m.dosage]
                   .filter(Boolean).join(' · ') || undefined} leading={tick(`m${i}`)}
                 onPress={() => toggle(`m${i}`)} last={i === e.medications.length - 1} />
          ))}
        </Section>
      )}

      {e.family.length > 0 && (
        <Section title={self ? t('Family history') : t('{who}’s family history', { who: capitalize(t(label(subject))) })}>
          {e.family.flatMap((rel, i) => rel.conditions.map((x, j) => (
            <Row key={`f${i}.${j}`} title={`${capitalize(t(label(rel.relationship)))}: ${x.name}`}
                 detail={x.onset_age != null ? t('Diagnosed at {n}', { n: x.onset_age }) : undefined}
                 leading={tick(`f${i}.${j}`)} onPress={() => toggle(`f${i}.${j}`)} />
          )))}
        </Section>
      )}

      <Card>
        <Chips label={t('Document type')} options={DOC_TYPES.map((v) => ({ value: v, label: t(DOC_TYPE_LABEL[v]) }))}
               value={type} onChange={setDocType} />
        <Field label={t('Date on the document (YYYY-MM-DD)')} value={dateValue} onChangeText={setDate}
               autoCapitalize="none" inputMode={Platform.OS === 'web' ? 'numeric' : undefined} />
      </Card>

      <View style={styles.row}>
        <Button title={t(self ? 'Add {n} to my record' : 'Add {n} to their record', { n: count })} variant="primary" busy={busy}
                disabled={busy || count === 0} onPress={save} />
        <Button title={t('Discard')} disabled={busy} onPress={discard} />
      </View>
      <ErrorText>{saveError}</ErrorText>

      <Pressable accessibilityRole="button" onPress={() => setShowText(!showText)}>
        <Text style={{ color: c.accent, fontSize: 14 }}>{t(showText ? 'Hide the text we read' : 'Show the text we read')}</Text>
      </Pressable>
      {showText && (
        <Card><Body selectable style={{ fontSize: 13, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' }}>
          {doc.text_preview || '(no text)'}
        </Body></Card>
      )}
    </Screen>
  );
}
