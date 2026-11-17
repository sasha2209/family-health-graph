import { Stack, useLocalSearchParams } from 'expo-router';
import { Linking, Text, View } from 'react-native';

import { Badge, Row, Section } from '../../components/list';
import { Body, ErrorText, Loading, Screen } from '../../components/ui';
import { useSession } from '../../lib/session';
import { LEVEL_LABEL, usePalette } from '../../lib/theme';
import { useLoader } from '../../lib/useLoader';

const WHEN: Record<string, string> = {
  high: 'Worth raising with a clinician soon.',
  moderate: 'Bring this up at your next routine visit.',
  info: 'Good to know. No appointment needed for this alone.',
};

/** Detail page for one action item: why it was flagged, what to do, and the source guidance. */
export default function InsightDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const c = usePalette();
  const { api } = useSession();
  const { data, error } = useLoader(async () => {
    const report = await api.insights();
    return { insight: report.insights.find((i) => i.rule_id === id) ?? null, disclaimer: report.disclaimer };
  });

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { insight, disclaimer } = data;
  if (!insight) {
    return <Screen><Body muted>This item no longer applies. Your record may have changed.</Body></Screen>;
  }
  const tone = c.level[insight.level];

  return (
    <Screen>
      <Stack.Screen options={{ title: LEVEL_LABEL[insight.level] }} />
      <View style={{ gap: 8 }}>
        <View style={{ alignSelf: 'flex-start' }}>
          <Badge label={LEVEL_LABEL[insight.level]} fg={tone.fg} bg={tone.bg} />
        </View>
        <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>{insight.title}</Text>
        <Body muted>{WHEN[insight.level]}</Body>
      </View>

      <Body>{insight.summary}</Body>

      {insight.evidence.length > 0 && (
        <Section title="Why this was flagged">
          {insight.evidence.map((e, i) => (
            <Row key={e} title={e} last={i === insight.evidence.length - 1} />
          ))}
        </Section>
      )}

      <Section title="What you can do">
        <View style={{ padding: 16 }}><Body>{insight.recommendation}</Body></View>
      </Section>

      {insight.references.length > 0 && (
        <Section title="Based on">
          {insight.references.map((r, i) => (
            <Row key={r.url} title={r.title} onPress={() => Linking.openURL(r.url)}
                 last={i === insight.references.length - 1} />
          ))}
        </Section>
      )}

      <Body muted style={{ fontSize: 12 }}>{disclaimer}</Body>
    </Screen>
  );
}
