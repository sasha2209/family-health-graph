import { router } from 'expo-router';
import { useState } from 'react';
import { Platform, View } from 'react-native';

import { useSession } from '../lib/session';
import { chooseFile, choosePhoto, type Picked, takePhoto } from '../lib/pickDocument';
import { Body, Button, Card, ErrorText, H2, styles } from './ui';

/** "Snap a prescription or lab report": the fastest way to fill a record with real data. */
export function ScanCard({ replace = false, subject, memberId, title }: {
  replace?: boolean; subject?: string; memberId?: string; title?: string;
}) {
  const { api } = useSession();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function go(kind: string, pick: () => Promise<Picked | null>) {
    setError(null);
    try {
      const file = await pick();
      if (!file) return;
      setBusy(kind);
      const doc = await api.uploadDocument(file.base64, file.filename);
      const href = { pathname: '/document/[id]' as const,
                     params: { id: doc.id, ...(subject ? { subject } : {}), ...(memberId ? { member: memberId } : {}) } };
      if (replace) router.replace(href);
      else router.push(href);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <H2>{title ?? 'Add a prescription or lab report'}</H2>
      <Body muted>
        Take a photo or upload a PDF. We read it, you check what we found, and only what you keep is added.
        Works for your family’s documents too.
      </Body>
      <View style={styles.row}>
        {Platform.OS !== 'web' && (
          <Button title="Take photo" variant="primary" busy={busy === 'camera'} disabled={!!busy}
                  onPress={() => go('camera', takePhoto)} />
        )}
        <Button title={Platform.OS === 'web' ? 'Upload photo or PDF' : 'Choose file'}
                variant={Platform.OS === 'web' ? 'primary' : 'secondary'}
                busy={busy === 'file'} disabled={!!busy} onPress={() => go('file', chooseFile)} />
        {Platform.OS !== 'web' && (
          <Button title="From photos" busy={busy === 'library'} disabled={!!busy}
                  onPress={() => go('library', choosePhoto)} />
        )}
      </View>
      {busy && <Body muted style={{ fontSize: 13, marginTop: 8 }}>Reading your document…</Body>}
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
