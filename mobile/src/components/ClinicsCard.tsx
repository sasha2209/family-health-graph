import { useState } from 'react';
import { View } from 'react-native';

import { useSession } from '../lib/session';
import { Body, Button, Card, ErrorText, Field, H2, styles } from './ui';
import { useT } from '../lib/i18n';

type Clinic = { id: string; name: string; connected_at: string };

/** Connect your record to a clinic (with the code they give you), see who has access, disconnect. */
export function ClinicsCard({ clinics, onChange, initialCode, initialName, source = 'code' }: {
  clinics: Clinic[];
  onChange: () => void;
  initialCode?: string;
  initialName?: string; // clinic name already looked up (from an intake link)
  source?: 'code' | 'link';
}) {
  const { t } = useT();
  const { api } = useSession();
  const [code, setCode] = useState(initialCode ?? '');
  const [name, setName] = useState('');
  const [found, setFound] = useState<string | null>(initialName ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }

  return (
    <Card>
      <H2>{t('Your clinics')}</H2>
      <Body muted style={{ fontSize: 13 }}>
        {t('Share your family health record with your care team so they can see what may need follow-up before your visit. They see your history and insights, and you can disconnect at any time.')}
      </Body>
      {clinics.map((c) => (
        <View key={c.id} style={[styles.row, { justifyContent: 'space-between', alignItems: 'center' }]}>
          <Body style={{ flex: 1 }}>{c.name}</Body>
          <Button title={t('Disconnect')} variant="danger" onPress={() => run(async () => {
            await api.disconnectClinic(c.id); onChange();
          })} />
        </View>
      ))}
      {!found ? (
        <>
          <Field label={t('Clinic code')} value={code} onChangeText={setCode} autoCapitalize="characters"
                 autoCorrect={false} placeholder={t('ABCD-2345')} maxLength={20} />
          <View style={styles.row}>
            <Button title={t('Find clinic')} busy={busy} disabled={code.trim().length < 4}
                    onPress={() => run(async () => setFound((await api.lookupClinic(code)).name))} />
          </View>
        </>
      ) : (
        <>
          <Body style={{ marginTop: 12 }}>Connect to <Body style={{ fontWeight: '600' }}>{found}</Body>?</Body>
          <Field label={t('Your name as the clinic knows you')} value={name} onChangeText={setName}
                 placeholder={t('e.g. Priya Shah, DOB 2 May 1984')} maxLength={120} />
          <View style={styles.row}>
            <Button title={t('Connect')} variant="primary" busy={busy} disabled={name.trim().length < 2}
                    onPress={() => run(async () => {
                      await api.connectClinic(code, name, source); setFound(null); setCode(''); setName(''); onChange();
                    })} />
            <Button title={t('Cancel')} onPress={() => { setFound(null); setError(null); }} />
          </View>
        </>
      )}
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
