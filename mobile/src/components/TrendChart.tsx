import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { formatDay } from '../lib/format';
import { type Palette, usePalette } from '../lib/theme';
import type { Tone, TrendTest } from '../lib/types';

const H = 132;            // plot height
const PAD_X = 14;         // keeps the end markers inside the plot
const PAD_TOP = 22;       // room for the latest-value label
const PAD_BOTTOM = 8;

function toneBg(c: Palette, tone: Tone): string {
  return tone === 'good' ? 'transparent' : tone === 'watch' ? c.level.moderate.bg : c.level.high.bg;
}

/**
 * One test over time: a 2px line with 8px markers, the guideline ranges as recessive tinted bands
 * behind it, and the latest value labelled. Tap a marker to read its value and date.
 * Points are placed by date, so uneven gaps between tests show as uneven spacing.
 */
export function TrendChart({ test }: { test: TrendTest }) {
  const c = usePalette();
  const [width, setWidth] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const pts = test.points.filter((p) => p.date);
  if (pts.length === 0) return null;

  // Value domain: the data, padded, extended to any band edge just outside it so the context shows.
  const values = pts.map((p) => p.value);
  let lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || Math.max(Math.abs(hi) * 0.2, 1);
  lo -= span * 0.35; hi += span * 0.35;
  for (const b of test.bands) {
    for (const edge of [b.from, b.to]) {
      if (edge == null) continue;
      if (edge < lo && edge > lo - span) lo = edge - span * 0.1;
      if (edge > hi && edge < hi + span) hi = edge + span * 0.1;
    }
  }
  lo = Math.max(lo, 0);
  const t = pts.map((p) => new Date(p.date as string).getTime());
  const t0 = Math.min(...t), t1 = Math.max(...t);
  const plotW = Math.max(width - PAD_X * 2, 1);
  const plotH = H - PAD_TOP - PAD_BOTTOM;
  const x = (ms: number) => PAD_X + (t1 === t0 ? plotW / 2 : ((ms - t0) / (t1 - t0)) * plotW);
  const y = (v: number) => PAD_TOP + (1 - (v - lo) / (hi - lo)) * plotH;
  const coords = pts.map((p, i) => ({ x: x(t[i]), y: y(p.value), p }));
  const last = coords[coords.length - 1];
  const shown = picked != null ? coords[picked] : null;

  return (
    <View>
      <View onLayout={(e) => setWidth(e.nativeEvent.layout.width)} style={{ height: H, position: 'relative', overflow: 'hidden' }}
            accessibilityRole="image"
            accessibilityLabel={`${test.display}: ${pts.map((p) => `${p.value} on ${formatDay(p.date)}`).join(', ')}`}>
        {width > 0 && (
          <>
            {/* guideline ranges */}
            {test.bands.map((b) => {
              const top = y(Math.min(b.to ?? hi, hi));
              const bottom = y(Math.max(b.from ?? lo, lo));
              if (bottom <= top || b.tone === 'good') return null;
              return <View key={b.label} style={{ position: 'absolute', left: 0, right: 0, top, height: bottom - top,
                                                   backgroundColor: toneBg(c, b.tone) }} />;
            })}
            {test.bands.filter((b) => b.to != null && b.to > lo && b.to < hi).map((b) => (
              <View key={`edge-${b.label}`} style={{ position: 'absolute', left: 0, right: 0, top: y(b.to as number),
                                                     height: 1, backgroundColor: c.border }} />
            ))}
            {/* line */}
            {coords.slice(1).map((b, i) => {
              const a = coords[i];
              const len = Math.hypot(b.x - a.x, b.y - a.y);
              const angle = Math.atan2(b.y - a.y, b.x - a.x);
              return <View key={`seg-${i}`} style={{ position: 'absolute', width: len, height: 2, backgroundColor: c.accent,
                left: (a.x + b.x) / 2 - len / 2, top: (a.y + b.y) / 2 - 1, transform: [{ rotate: `${angle}rad` }] }} />;
            })}
            {/* markers, with hit areas larger than the mark */}
            {coords.map((pt, i) => {
              const isLast = i === coords.length - 1;
              const size = isLast ? 10 : 8;
              return (
                <Pressable key={`pt-${i}`} accessibilityRole="button"
                           accessibilityLabel={`${pt.p.value} ${test.unit}, ${formatDay(pt.p.date)}`}
                           onPress={() => setPicked(picked === i ? null : i)}
                           style={{ position: 'absolute', left: pt.x - 16, top: pt.y - 16, width: 32, height: 32,
                                    alignItems: 'center', justifyContent: 'center' }}>
                  <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: c.accent,
                                 borderWidth: 2, borderColor: c.surface }} />
                </Pressable>
              );
            })}
            {/* direct label on the latest value only */}
            {!shown && (
              <Text style={{ position: 'absolute', top: Math.max(last.y - 22, 0), right: width - last.x > 60 ? undefined : 2,
                             left: width - last.x > 60 ? last.x - 20 : undefined,
                             color: c.text, fontSize: 12, fontWeight: '600', fontVariant: ['tabular-nums'] }}>
                {last.p.value}
              </Text>
            )}
            {shown && (
              <View style={{ position: 'absolute', top: 0, left: Math.min(Math.max(shown.x - 60, 0), width - 120), width: 120,
                             backgroundColor: c.surface, borderColor: c.border, borderWidth: 1, borderRadius: 6,
                             paddingHorizontal: 8, paddingVertical: 3 }}>
                <Text style={{ color: c.text, fontSize: 12, fontWeight: '600', fontVariant: ['tabular-nums'] }}>
                  {shown.p.value} {test.unit}
                </Text>
                <Text style={{ color: c.muted, fontSize: 11 }}>{formatDay(shown.p.date)}</Text>
              </View>
            )}
          </>
        )}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 2 }}>
        <Text style={{ color: c.muted, fontSize: 11 }}>{formatDay(pts[0].date)}</Text>
        {pts.length > 1 && <Text style={{ color: c.muted, fontSize: 11 }}>{formatDay(pts[pts.length - 1].date)}</Text>}
      </View>
    </View>
  );
}
