import { useState } from 'react';
import { Linking, Platform, Pressable, Share, Text, View } from 'react-native';

import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import { useLoader } from '../lib/useLoader';
import { Body, Button, Card, ErrorText, H2, styles } from './ui';

async function copyOrShare(text: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try { await navigator.clipboard.writeText(text); return 'Copied'; } catch { return 'Select the address to copy it'; }
  }
  await Share.share({ message: text });
  return null;
}

/** Forward lab reports and prescriptions by email or WhatsApp instead of uploading them one by one. */
export function ForwardCard() {
  const { api } = useSession();
  const c = usePalette();
  const { data, error, reload } = useLoader(() => api.inbound());
  const [code, setCode] = useState<{ message: string; number: string; minutes: number } | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!data || (!data.email.available && !data.whatsapp.available)) return error ? <ErrorText>{error}</ErrorText> : null;

  async function run(fn: () => Promise<void>) {
    setBusy(true); setActionError(null);
    try { await fn(); } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  const waDigits = (code?.number ?? data.whatsapp.number ?? '').replace(/\D/g, '');

  return (
    <Card>
      <H2>Forward reports instead</H2>
      <Body muted>Labs and doctors already send reports by email and WhatsApp. Forward them here and they wait for you to check.</Body>

      {data.email.available && data.email.address && (
        <View style={{ marginTop: 14, gap: 6 }}>
          <Text style={[styles.label, { color: c.muted }]}>Your private email address</Text>
          <Text selectable accessibilityLabel={`Forwarding address ${data.email.address}`}
                style={{ color: c.text, fontSize: 15, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' }}>
            {data.email.address}
          </Text>
          <View style={styles.row}>
            <Button title={Platform.OS === 'web' ? 'Copy address' : 'Share address'}
                    onPress={async () => setNote(await copyOrShare(data.email.address!))} />
            <Button title="Get a new address" disabled={busy} onPress={() => run(async () => {
              await api.rotateInboundEmail(); setNote('New address ready. The old one no longer works.'); reload();
            })} />
          </View>
          <Body muted style={{ fontSize: 12 }}>Anyone with this address can send you documents, so share it only with your labs and doctors.</Body>
        </View>
      )}

      {data.whatsapp.available && (
        <View style={{ marginTop: 16, gap: 6 }}>
          <Text style={[styles.label, { color: c.muted }]}>WhatsApp</Text>
          {data.whatsapp.linked ? (
            <>
              <Body>Connected. Send photos or PDFs to {data.whatsapp.number}.</Body>
              <View style={styles.row}>
                <Button title="Disconnect WhatsApp" variant="danger" disabled={busy}
                        onPress={() => run(async () => { await api.unlinkWhatsapp(); reload(); })} />
              </View>
            </>
          ) : code ? (
            <>
              <Body>Send this message from your WhatsApp to {code.number} within {code.minutes} minutes:</Body>
              <Text selectable style={{ color: c.text, fontSize: 22, fontWeight: '700', letterSpacing: 1 }}>{code.message}</Text>
              <View style={styles.row}>
                <Button title="Open WhatsApp" variant="primary"
                        onPress={() => Linking.openURL(`https://wa.me/${waDigits}?text=${encodeURIComponent(code.message)}`)} />
                <Button title="I’ve sent it" onPress={() => { setCode(null); reload(); }} />
              </View>
            </>
          ) : (
            <View style={styles.row}>
              <Button title="Connect WhatsApp" variant="primary" disabled={busy} onPress={() => run(async () => {
                const r = await api.whatsappCode();
                setCode({ message: r.message, number: r.number, minutes: r.expires_in_minutes });
              })} />
            </View>
          )}
        </View>
      )}
      {note && (
        <Pressable onPress={() => setNote(null)}><Body muted style={{ fontSize: 13, marginTop: 8 }}>{note}</Body></Pressable>
      )}
      <ErrorText>{actionError}</ErrorText>
    </Card>
  );
}
