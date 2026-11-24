import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Row, Section } from '../components/list';
import { ForwardCard } from '../components/ForwardCard';
import { ScanCard } from '../components/ScanCard';
import { Body, Button, Card, ErrorText, Field, H2, Screen, styles } from '../components/ui';
import { publicApi } from '../lib/api';
import { capitalize, DOC_TYPE_LABEL, formatDay, label, VIA_LABEL } from '../lib/format';
import { useSession } from '../lib/session';
import type { Profile } from '../lib/types';
import { useLoader } from '../lib/useLoader';
import { useT } from '../lib/i18n';

function describe(parsed: Profile): string[] {
  const lines = parsed.family.map((m) =>
    `${capitalize(label(m.relationship))}: ${m.conditions.map((c) =>
      c.name + (c.onset_age != null ? ` (${c.age_estimated ? '~' : ''}${c.onset_age})` : '')).join(', ')}`);
  if (parsed.conditions.length) lines.push(`You: ${parsed.conditions.map((c) => c.name).join(', ')}`);
  return lines;
}

// Return to wherever the user came from, or Home if this screen was opened
// directly (e.g. right after connecting from a clinic's intake link).
function done() {
  if (router.canGoBack()) router.back();
  else router.replace('/');
}

export default function AddHistory() {
  const { t } = useT();
  const { api } = useSession();
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: documents } = useLoader(() => api.documents());

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  return (
    <Screen>
      <ScanCard />
      <ForwardCard />

      <Card>
        <H2>{t('Records from hospitals')}</H2>
        <Body muted>
          {t('Connect a hospital’s patient portal to import your records, or upload a health record file (.json) exported from the ABHA app or a hospital. It goes through the same check before anything is saved.')}
        </Body>
        <View style={styles.row}>
          <Button title={t('Connected records')} onPress={() => router.push('/connections')} />
        </View>
      </Card>

      <Card>
        <H2>{t('Or describe it')}</H2>
        <Field
          label={t('Describe your family\'s health')}
          value={text}
          onChangeText={(t) => { setText(t); setPreview(null); }}
          multiline
          placeholder={t("My mom had breast cancer at 46.\nDad had a heart attack at 51.")}
        />
        <Body muted style={{ fontSize: 13, marginTop: 6 }}>
          {t('Include who, what and the age at diagnosis if you know it. “In her 50s” is fine too.')}
        </Body>
        <View style={styles.row}>
          <Button title={t('Check')} disabled={!text.trim()} busy={busy && !preview} onPress={() => run(async () => {
            const r = await api.ingestText(text, true);
            const lines = r.parsed ? describe(r.parsed) : [];
            setPreview(lines.length ? lines : r.warnings);
          })} />
          <Button title={t('Save')} variant="primary" disabled={!text.trim()} busy={busy && !!preview} onPress={() => run(async () => {
            const r = await api.ingestText(text);
            if (r.warnings.length && !r.merged?.relatives_added && !r.merged?.relative_conditions) {
              setPreview(r.warnings);
              return;
            }
            done();
          })} />
        </View>
        <ErrorText>{error}</ErrorText>
      </Card>

      {preview && (
        <Card>
          <H2>{t('We understood')}</H2>
          {preview.map((l) => <Body key={l}>{'•'} {l}</Body>)}
        </Card>
      )}

      {documents && documents.length > 0 && (
        <Section title={t('Your documents')}>
          {documents.map((d, i) => (
            <Row key={d.id} title={`${DOC_TYPE_LABEL[d.doc_type]}${d.subject !== 'self' ? ` · ${label(d.subject)}` : ''}`}
                 detail={[formatDay(d.doc_date), d.source ? VIA_LABEL[d.source] : '', d.status === 'review' ? 'waiting for your review' : '']
                   .filter(Boolean).join(' · ')}
                 onPress={() => router.push({ pathname: '/document/[id]', params: { id: d.id } })}
                 last={i === documents.length - 1} />
          ))}
        </Section>
      )}

      <Card>
        <H2>{t('Just exploring?')}</H2>
        <Body muted>{t('Load a sample record to see what the app does with a full history.')}</Body>
        <View style={styles.row}>
          <Button title={t('Load sample record')} onPress={() => run(async () => {
            await api.ingestFhir(await publicApi.sampleRecord());
            done();
          })} />
        </View>
      </Card>
    </Screen>
  );
}
