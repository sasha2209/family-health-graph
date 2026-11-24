import { useState } from 'react';
import { Linking, Platform, View } from 'react-native';

import { Row, Section } from '../components/list';
import { Banner, Body, Button, Card, ErrorText, Field, H2, Loading, Screen, styles } from '../components/ui';
import { formatDay } from '../lib/format';
import { useSession } from '../lib/session';
import type { Connection } from '../lib/types';
import { useLoader } from '../lib/useLoader';
import { useT } from '../lib/i18n';

function summary(c: Connection, t: (s: string, v?: Record<string, string | number>) => string) {
  if (c.status === 'pending') return t(c.last_sync_summary?.waiting ?? 'Waiting for you to approve the request in your ABHA app');
  if (c.status === 'denied' || c.status === 'revoked' || c.status === 'expired') return t(`Request ${c.status}. Disconnect and start again.`);
  if (!c.last_sync_at) return t('Not synced yet');
  const m = c.last_sync_summary?.merged ?? {};
  const added = (m.conditions ?? 0) + (m.medications ?? 0) + (m.observations ?? 0) + (m.relative_conditions ?? 0);
  return t(added === 1 ? 'Synced {date} · 1 new item' : 'Synced {date} · {n} new items', { date: formatDay(c.last_sync_at), n: added });
}

/** Patient portals connected over SMART on FHIR, and portals this server can connect to. */
export default function ConnectionsScreen() {
  const { t } = useT();
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(() => api.connections());
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [abha, setAbha] = useState('');

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key); setActionError(null); setNote(null);
    try { await fn(); } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  }

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const connected = new Set(data.connections.map((c) => c.provider));
  const portals = data.available.filter((p) => p.kind === 'smart');

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      {note && <Banner>{note}</Banner>}
      {data.connections.length > 0 && (
        <Section title={t('Connected')}>
          {data.connections.map((c, i) => (
            <View key={c.id}>
              <Row title={c.display_name} detail={c.status === 'error' ? 'Needs attention: sync again or reconnect' : summary(c, t)}
 />
              <View style={[styles.row, { paddingHorizontal: 16, paddingBottom: 12, marginTop: 0 }]}>
                <Button title={t('Sync now')} busy={busy === `sync-${c.id}`} disabled={!!busy} onPress={() => run(`sync-${c.id}`, async () => {
                  const r = await api.syncConnection(c.id);
                  const m = r.merged;
                  setNote(r.message ? t(r.message) : m ? t('Synced. {n} new diagnoses.', { n: (m.conditions ?? 0) + (m.relative_conditions ?? 0) }) : t('Synced.'));
                  reload();
                })} />
                <Button title={t('Disconnect')} variant="danger" disabled={!!busy} onPress={() => run(`del-${c.id}`, async () => {
                  await api.deleteConnection(c.id); setNote(t('Disconnected {name}. Records already imported stay.', { name: c.display_name })); reload();
                })} />
              </View>
            </View>
          ))}
        </Section>
      )}

      <Card>
        <H2>{t('Connect a patient portal')}</H2>
        {portals.length === 0 ? (
          <Body muted>{t('No hospital portals are set up on this server yet. You can still upload a record file from Add health information.')}</Body>
        ) : (
          <>
            <Body muted>{t('You’ll sign in at the hospital’s own site and choose what to share. We only read your records.')}</Body>
            {portals.every((p) => connected.has(p.id)) && (
              <Body muted style={{ marginTop: 8 }}>{t('All available portals are connected.')}</Body>
            )}
            {portals.filter((p) => !connected.has(p.id)).map((p) => (
              <View key={p.id} style={styles.row}>
                <Button title={`Connect ${p.name}`} variant="primary" busy={busy === p.id} disabled={!!busy}
                        onPress={() => run(p.id, async () => {
                          const { authorize_url } = await api.connectSmart(p.id, Platform.OS === 'web' ? '/app/connections' : undefined);
                          if (Platform.OS === 'web') globalThis.location.assign(authorize_url);
                          else await Linking.openURL(authorize_url);
                        })} />
              </View>
            ))}
          </>
        )}
      </Card>

      <Card>
        <H2>{t('India: link your ABHA')}</H2>
        {data.available.some((p) => p.kind === 'abdm') ? (
          <>
            <Body muted>
              {t('Bring in records from hospitals and labs linked to ABDM. We send a request to your ABHA address; you see exactly what’s asked for and approve it in your ABHA app. You can withdraw it there at any time.')}
            </Body>
            <Field label={t('ABHA address')} value={abha} onChangeText={setAbha} placeholder={t('name@abdm')}
                   autoCapitalize="none" autoCorrect={false} />
            <View style={styles.row}>
              <Button title={t('Send request')} variant="primary" busy={busy === 'abha'} disabled={!!busy || !abha.includes('@')}
                      onPress={() => run('abha', async () => {
                        const r = await api.connectAbha(abha.trim());
                        setNote(r.message); setAbha(''); reload();
                      })} />
            </View>
          </>
        ) : (
          <Body muted>
            {t('Download a record from the ABHA app or your hospital (a .json health record file, or the PDF), then add it from Add health information → Choose file. Linking your ABHA directly needs this server to be connected to ABDM.')}
          </Body>
        )}
      </Card>
      <ErrorText>{actionError}</ErrorText>
    </Screen>
  );
}
