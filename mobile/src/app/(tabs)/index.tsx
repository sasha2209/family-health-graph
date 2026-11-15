import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { InsightCard } from '../../components/InsightCard';
import { Banner, Body, Button, Card, ErrorText, H2, Loading, Screen, styles } from '../../components/ui';
import { useSession } from '../../lib/session';
import { useLoader } from '../../lib/useLoader';

export default function InsightsScreen() {
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(async () => {
    const [report, notes, own] = await Promise.all([api.insights(), api.notifications(), api.profile(false)]);
    // Prompt based on the user's *own* record: someone who just joined through an
    // invite already sees their linked relative, but hasn't added anything yet.
    const hasOwnHistory = own.family.length > 0 || own.conditions.length > 0;
    return { report, notes: notes.filter((n) => !n.read), hasOwnHistory };
  });
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryBusy, setSummaryBusy] = useState(false);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { report, notes, hasOwnHistory } = data;

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <ErrorText>{error}</ErrorText>

      {notes.map((n) => (
        <Banner key={n.id} tone={n.kind === 'family_cascade' ? 'high' : 'info'}>{n.message}</Banner>
      ))}
      {notes.length > 0 && (
        <View style={{ alignSelf: 'flex-start' }}>
          <Button title="Dismiss" onPress={async () => { await api.markNotificationsRead(); reload(); }} />
        </View>
      )}

      {!hasOwnHistory && (
        <Card>
          <H2>Start with what you know</H2>
          <Body muted>
            Type a few sentences about your family’s health, like “My mom had breast cancer at 46”.
          </Body>
          <View style={styles.row}>
            <Button title="Add family history" variant="primary" onPress={() => router.push('/add-history')} />
          </View>
        </Card>
      )}

      {report.insights.map((i) => <InsightCard key={i.rule_id} insight={i} />)}

      {report.insights.length > 0 && (
        <Card>
          <H2>Plain-language summary</H2>
          {summary ? <Body>{summary}</Body> : (
            <Body muted>A short summary you can show your clinician.</Body>
          )}
          {!summary && (
            <View style={styles.row}>
              <Button
                title="Summarize"
                busy={summaryBusy}
                onPress={async () => {
                  setSummaryBusy(true);
                  try { setSummary((await api.summary()).text); } finally { setSummaryBusy(false); }
                }}
              />
            </View>
          )}
        </Card>
      )}

      <Body muted style={{ fontSize: 12 }}>{report.disclaimer}</Body>
    </Screen>
  );
}
