// List building blocks, modelled on the UX patterns of Medplum's Foo Medical
// patient portal (titled sections, scannable rows that open a detail page,
// status badges, a progress checklist). Written for React Native; no code copied.
import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { usePalette } from '../lib/theme';

/** A titled card that groups related rows ("Your action items", "Maternal side"). */
export function Section({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  const c = usePalette();
  return (
    <View style={[s.section, { backgroundColor: c.surface, borderColor: c.border }]}>
      <View style={[s.sectionHead, { borderBottomColor: c.border }]}>
        <Text accessibilityRole="header" style={[s.sectionTitle, { color: c.text }]}>{title}</Text>
        {right}
      </View>
      {children}
    </View>
  );
}

/** One tappable line: optional eyebrow (e.g. a status badge), title, detail line, trailing badge, chevron. */
export function Row({ title, detail, eyebrow, badge, leading, onPress, last }: {
  title: string;
  detail?: string;
  eyebrow?: ReactNode;
  badge?: ReactNode;
  leading?: ReactNode;
  onPress?: () => void;
  last?: boolean;
}) {
  const c = usePalette();
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={[title, detail].filter(Boolean).join('. ')}
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [s.row, !last && { borderBottomColor: c.border, borderBottomWidth: StyleSheet.hairlineWidth },
        pressed && { backgroundColor: c.bg }]}
    >
      {leading}
      <View style={{ flex: 1, gap: 2 }}>
        {eyebrow ? <View style={{ alignSelf: 'flex-start', marginBottom: 4 }}>{eyebrow}</View> : null}
        <Text style={[s.rowTitle, { color: c.text }]}>{title}</Text>
        {detail ? <Text style={{ color: c.muted, fontSize: 14, lineHeight: 19 }} numberOfLines={2}>{detail}</Text> : null}
      </View>
      {badge}
      {onPress && <Text style={{ color: c.muted, fontSize: 20 }} accessibilityElementsHidden>{'›'}</Text>}
    </Pressable>
  );
}

export function Badge({ label, fg, bg }: { label: string; fg: string; bg: string }) {
  return (
    <View style={[s.badge, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 11, fontWeight: '700', letterSpacing: 0.3 }}>{label.toUpperCase()}</Text>
    </View>
  );
}

/** A round tick for checklist rows. */
export function Check({ done }: { done: boolean }) {
  const c = usePalette();
  return (
    <View
      accessibilityLabel={done ? 'Done' : 'Not done'}
      style={[s.check, { borderColor: done ? c.accent : c.border, backgroundColor: done ? c.accent : 'transparent' }]}
    >
      {done && <Text style={{ color: c.accentInk, fontSize: 13, fontWeight: '700' }}>{'✓'}</Text>}
    </View>
  );
}

export function Progress({ value, total }: { value: number; total: number }) {
  const c = usePalette();
  return (
    <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: total, now: value }}
          style={[s.track, { backgroundColor: c.border }]}>
      <View style={{ width: `${(value / Math.max(total, 1)) * 100}%`, backgroundColor: c.accent, height: '100%',
                     borderRadius: 999 }} />
    </View>
  );
}

const s = StyleSheet.create({
  section: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, overflow: 'hidden' },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8,
                 paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  sectionTitle: { fontSize: 16, fontWeight: '600' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12, minHeight: 52 },
  rowTitle: { fontSize: 15, fontWeight: '500' },
  badge: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 },
  check: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  track: { height: 6, borderRadius: 999, overflow: 'hidden', marginTop: 8 },
});
