import { useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { LEVEL_LABEL, usePalette } from '../lib/theme';
import type { Insight } from '../lib/types';

export function InsightCard({ insight }: { insight: Insight }) {
  const c = usePalette();
  const tone = c.level[insight.level];
  const [showSources, setShowSources] = useState(false);
  return (
    <View
      style={[s.card, { backgroundColor: tone.bg, borderLeftColor: tone.fg }]}
      accessible={false}
    >
      <Text style={[s.badge, { color: tone.fg }]}>{LEVEL_LABEL[insight.level].toUpperCase()}</Text>
      <Text accessibilityRole="header" style={[s.title, { color: c.text }]}>{insight.title}</Text>
      <Text style={[s.body, { color: c.text }]}>{insight.summary}</Text>
      {insight.evidence.length > 0 && (
        <View style={{ marginTop: 8, gap: 2 }}>
          {insight.evidence.map((e) => (
            <Text key={e} style={[s.body, { color: c.text }]}>{'•'} {e}</Text>
          ))}
        </View>
      )}
      <Text style={[s.body, { color: c.text, marginTop: 8 }]}>
        <Text style={{ fontWeight: '600' }}>What you can do: </Text>
        {insight.recommendation}
      </Text>
      {insight.references.length > 0 && (
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: showSources }}
          onPress={() => setShowSources((v) => !v)}
          hitSlop={8}
          style={{ marginTop: 10 }}
        >
          <Text style={[s.small, { color: c.muted }]}>{showSources ? '▾' : '▸'} Sources</Text>
        </Pressable>
      )}
      {showSources && insight.references.map((r) => (
        <Text
          key={r.url}
          accessibilityRole="link"
          onPress={() => Linking.openURL(r.url)}
          style={[s.small, { color: c.text, textDecorationLine: 'underline', marginTop: 6 }]}
        >
          {r.title}
        </Text>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  card: { borderLeftWidth: 4, borderRadius: 12, padding: 14 },
  badge: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  title: { fontSize: 16, fontWeight: '600', marginTop: 4, marginBottom: 4 },
  body: { fontSize: 15, lineHeight: 21 },
  small: { fontSize: 13 },
});
