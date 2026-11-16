import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Body, Button, Card, ErrorText, Field, H2, Screen, styles } from '../components/ui';
import { publicApi } from '../lib/api';
import { capitalize, label } from '../lib/format';
import { useSession } from '../lib/session';
import type { Profile } from '../lib/types';

function describe(parsed: Profile): string[] {
  const lines = parsed.family.map((m) =>
    `${capitalize(label(m.relationship))}: ${m.conditions.map((c) =>
      c.name + (c.onset_age != null ? ` (${c.age_estimated ? '~' : ''}${c.onset_age})` : '')).join(', ')}`);
  if (parsed.conditions.length) lines.push(`You: ${parsed.conditions.map((c) => c.name).join(', ')}`);
  return lines;
}

export default function AddHistory() {
  const { api } = useSession();
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  return (
    <Screen>
      <Card>
        <Field
          label="Describe your family's health"
          value={text}
          onChangeText={(t) => { setText(t); setPreview(null); }}
          multiline
          placeholder={"My mom had breast cancer at 46.\nDad had a heart attack at 51."}
        />
        <Body muted style={{ fontSize: 13, marginTop: 6 }}>
          Include who, what and the age at diagnosis if you know it. “In her 50s” is fine too.
        </Body>
        <View style={styles.row}>
          <Button title="Check" disabled={!text.trim()} busy={busy && !preview} onPress={() => run(async () => {
            const r = await api.ingestText(text, true);
            const lines = r.parsed ? describe(r.parsed) : [];
            setPreview(lines.length ? lines : r.warnings);
          })} />
          <Button title="Save" variant="primary" disabled={!text.trim()} busy={busy && !!preview} onPress={() => run(async () => {
            const r = await api.ingestText(text);
            if (r.warnings.length && !r.merged?.relatives_added && !r.merged?.relative_conditions) {
              setPreview(r.warnings);
              return;
            }
            router.back();
          })} />
        </View>
        <ErrorText>{error}</ErrorText>
      </Card>

      {preview && (
        <Card>
          <H2>We understood</H2>
          {preview.map((l) => <Body key={l}>{'•'} {l}</Body>)}
        </Card>
      )}

      <Card>
        <H2>Have health records?</H2>
        <Body muted>
          Importing from Apple Health or your patient portal is coming. For now you can load a sample
          record to explore the app.
        </Body>
        <View style={styles.row}>
          <Button title="Load sample record" onPress={() => run(async () => {
            await api.ingestFhir(await publicApi.sampleRecord());
            router.back();
          })} />
        </View>
      </Card>
    </Screen>
  );
}
