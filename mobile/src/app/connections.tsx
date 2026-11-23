import { useState } from 'react';
import { Linking, Platform, View } from 'react-native';

import { Row, Section } from '../components/list';
import { Banner, Body, Button, Card, ErrorText, H2, Loading, Screen, styles } from '../components/ui';
import { formatDay } from '../lib/format';
import { useSession } from '../lib/session';
import { useLoader } from '../lib/useLoader';

function summary(c: { last_sync_at: string | null; last_sync_summary: { merged: Record<string, number> } | null }) {
  if (!c.last_sync_at) return 'Not synced yet';
  const m = c.last_sync_summary?.merged ?? {};
  const added = (m.conditions ?? 0) + (m.medications ?? 0) + (m.observations ?? 0) + (m.relative_conditions ?? 0);
  return `Synced ${formatDay(c.last_sync_at)} · ${added} new item${added === 1 ? '' : 's'}`;
}

/** Patient portals connected over SMART on FHIR, and portals this server can connect to. */
export default function ConnectionsScreen() {
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(() => api.connections());
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key); setActionError(null); setNote(null);
    try { await fn(); } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  }

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const connected = new Set(data.connections.map((c) => c.provider));

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      {note && <Banner>{note}</Banner>}
      {data.connections.length > 0 && (
        <Section title="Connected">
          {data.connections.map((c, i) => (
            <View key={c.id}>
              <Row title={c.display_name} detail={c.status === 'error' ? 'Needs attention: sync again or reconnect' : summary(c)}
 />
              <View style={[styles.row, { paddingHorizontal: 16, paddingBottom: 12, marginTop: 0 }]}>
                <Button title="Sync now" busy={busy === `sync-${c.id}`} disabled={!!busy} onPress={() => run(`sync-${c.id}`, async () => {
                  const r = await api.syncConnection(c.id);
                  const m = r.merged;
                  setNote(`Synced. ${m ? `${m.conditions + m.relative_conditions} new diagnoses.` : ''}`.trim());
                  reload();
                })} />
                <Button title="Disconnect" variant="danger" disabled={!!busy} onPress={() => run(`del-${c.id}`, async () => {
                  await api.deleteConnection(c.id); setNote(`Disconnected ${c.display_name}. Records already imported stay.`); reload();
                })} />
              </View>
            </View>
          ))}
        </Section>
      )}

      <Card>
        <H2>Connect a patient portal</H2>
        {data.available.length === 0 ? (
          <Body muted>No hospital portals are set up on this server yet. You can still upload a record file from Add health information.</Body>
        ) : (
          <>
            <Body muted>You’ll sign in at the hospital’s own site and choose what to share. We only read your records.</Body>
            {data.available.every((p) => connected.has(p.id)) && (
              <Body muted style={{ marginTop: 8 }}>All available portals are connected.</Body>
            )}
            {data.available.filter((p) => !connected.has(p.id)).map((p) => (
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
        <H2>India: ABHA and hospital records</H2>
        <Body muted>
          Download a record from the ABHA app or your hospital (a .json health record file, or the PDF), then add it from
          Add health information → Choose file. Connecting your ABHA directly is coming once our ABDM certification is complete.
        </Body>
      </Card>
      <ErrorText>{actionError}</ErrorText>
    </Screen>
  );
}
