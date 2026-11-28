import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Banner, Body, Button, Card, ErrorText, H2, Loading, Screen, styles } from '../components/ui';
import { formatDay } from '../lib/format';
import { useT } from '../lib/i18n';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import { useLoader } from '../lib/useLoader';

/** The pilot study's information sheet and informed consent (fhg/study.py). The wording comes from the server, in the
 * app's language, so the version the ethics committee approved is what people read and agree to. */
export default function StudyScreen() {
  const { t, lang } = useT();
  const { api } = useSession();
  const c = usePalette();
  const { data, error, reload, refreshing } = useLoader(() => api.study(lang));
  const [ticked, setTicked] = useState<boolean[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const s = data;
  const all = s.statements.every((_, i) => ticked[i]);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setActionError(null);
    try { await fn(); setTicked([]); reload(); } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      {!s.enabled && <Banner>{t('There is no study running at the moment.')}</Banner>}
      {s.status === 'taking_part' && (
        <Banner>{t('You are taking part (since {date}). Thank you.', { date: s.consented_at ? formatDay(s.consented_at) : '' })}</Banner>
      )}
      {s.status === 'withdrew' && <Banner>{t('You stopped taking part. Your care is unchanged, and you are no longer counted.')}</Banner>}
      <ErrorText>{actionError}</ErrorText>
      <Card>
        <H2>{s.title}</H2>
        <Body>{s.summary}</Body>
        {s.sections.map((x) => (
          <View key={x.heading} style={{ marginTop: 14, gap: 4 }}>
            <Text style={{ color: c.text, fontWeight: '700', fontSize: 15 }}>{x.heading}</Text>
            <Body style={{ fontSize: 15 }}>{x.text}</Body>
          </View>
        ))}
        <Text style={{ color: c.text, fontWeight: '700', fontSize: 15, marginTop: 14 }}>{s.contact_heading}</Text>
        {s.contacts.filter((p) => p.name || p.contact).map((p) => (
          <Body key={p.role} style={{ fontSize: 15 }}>{p.role}: {[p.name, p.contact].filter(Boolean).join(', ')}</Body>
        ))}
        <Body muted style={{ fontSize: 12, marginTop: 10 }}>{s.version_label}: {s.version}</Body>
      </Card>

      {s.enabled && s.status !== 'taking_part' && (
        <Card>
          {s.statements.map((text, i) => (
            <Pressable key={text} accessibilityRole="checkbox" accessibilityState={{ checked: !!ticked[i] }}
                       onPress={() => setTicked((prev) => { const next = [...prev]; next[i] = !next[i]; return next; })}
                       style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start', marginBottom: 10 }}>
              <Text style={{ color: c.accent, fontSize: 18 }}>{ticked[i] ? '☑' : '☐'}</Text>
              <Body style={{ flex: 1 }}>{text}</Body>
            </Pressable>
          ))}
          <View style={styles.row}>
            <Button title={s.buttons.agree} variant="primary" disabled={!all || busy}
                    onPress={() => run(() => api.studyConsent(s.version))} />
            {s.status === 'not_asked' && (
              <Button title={s.buttons.decline} disabled={busy} onPress={() => run(() => api.studyDecline())} />
            )}
          </View>
          {!all && <Body muted style={{ fontSize: 12, marginTop: 6 }}>{t('Tick every statement to take part.')}</Body>}
        </Card>
      )}
      {s.status === 'taking_part' && (
        <View style={{ alignSelf: 'flex-start' }}>
          <Button title={s.buttons.withdraw} disabled={busy} onPress={() => run(() => api.studyWithdraw())} />
        </View>
      )}
    </Screen>
  );
}
