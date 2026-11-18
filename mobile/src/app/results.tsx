import { router, Stack, useLocalSearchParams } from 'expo-router';
import { Text, View } from 'react-native';

import { Badge, Section } from '../components/list';
import { TrendChart } from '../components/TrendChart';
import { Body, Button, ErrorText, Loading, Screen } from '../components/ui';
import { capitalize, label, monthYear } from '../lib/format';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import type { Tone } from '../lib/types';
import { useLoader } from '../lib/useLoader';

/** Results over time, for you or (with ?member=&who=) a relative whose reports you manage. */
export default function ResultsScreen() {
  const { member, who } = useLocalSearchParams<{ member?: string; who?: string }>();
  const { api } = useSession();
  const c = usePalette();
  const { data, error, refreshing, reload } = useLoader(() => api.trends(member));
  const tone = (t: Tone) => (t === 'good' ? { fg: c.accent, bg: c.bg } : t === 'watch' ? c.level.moderate : c.level.high);
  const title = who ? `${capitalize(label(who))}’s results` : 'Your results';

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <Stack.Screen options={{ title }} />
      {data.tests.length === 0 ? (
        <View style={{ gap: 12 }}>
          <Body muted>No test results yet. Add a lab report and each test will show up here, building a timeline as you add more.</Body>
          <View style={{ alignSelf: 'flex-start' }}>
            <Button title="Add a lab report" variant="primary" onPress={() => router.push('/add-history')} />
          </View>
        </View>
      ) : (
        data.tests.map((test) => {
          const band = test.latest_band;
          const series = test.points.map((p) => `${p.value} (${monthYear(p.date)})`).join(' → ');
          return (
            <Section key={test.code} title={test.display}
                     right={band ? <Badge label={band.label} fg={tone(band.tone).fg} bg={tone(band.tone).bg} /> : undefined}>
              <View style={{ padding: 16, gap: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={{ color: c.text, fontSize: 24, fontWeight: '700', fontVariant: ['tabular-nums'] }}>
                    {test.latest.value}
                  </Text>
                  <Text style={{ color: c.muted, fontSize: 14 }}>{test.unit}</Text>
                  {test.change != null && test.change !== 0 && (
                    <Text style={{ color: c.muted, fontSize: 13, fontVariant: ['tabular-nums'] }}>
                      {test.change > 0 ? '▲' : '▼'} {Math.abs(test.change)} since the previous test
                    </Text>
                  )}
                </View>
                {test.points.filter((p) => p.date).length > 1 ? <TrendChart test={test} /> : null}
                <Body muted style={{ fontSize: 13 }}>{series}</Body>
                {test.bands_source && (
                  <Body muted style={{ fontSize: 12 }}>
                    Shaded: outside the healthy range ({test.bands_source}). Your lab’s own range may differ slightly.
                  </Body>
                )}
              </View>
            </Section>
          );
        })
      )}
      <Body muted style={{ fontSize: 12 }}>
        Ranges are general guidance for adults, not a diagnosis. Talk to your doctor about what your results mean for you.
      </Body>
    </Screen>
  );
}
