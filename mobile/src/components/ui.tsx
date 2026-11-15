import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { capitalize, label } from '../lib/format';
import { usePalette } from '../lib/theme';

export function Screen({ children, refreshing, onRefresh, edges = ['bottom'] }: {
  children: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  edges?: ('top' | 'bottom')[];
}) {
  const c = usePalette();
  return (
    <SafeAreaView edges={edges} style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={styles.screen}
        keyboardShouldPersistTaps="handled"
        refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} /> : undefined}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const c = usePalette();
  return <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }, style]}>{children}</View>;
}

export function H2({ children }: { children: ReactNode }) {
  const c = usePalette();
  return <Text accessibilityRole="header" style={[styles.h2, { color: c.text }]}>{children}</Text>;
}

export function Body({ children, muted, style, selectable }: {
  children: ReactNode; muted?: boolean; style?: object; selectable?: boolean;
}) {
  const c = usePalette();
  return <Text selectable={selectable} style={[styles.body, { color: muted ? c.muted : c.text }, style]}>{children}</Text>;
}

export function Button({ title, onPress, variant = 'secondary', disabled, busy }: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  busy?: boolean;
}) {
  const c = usePalette();
  const primary = variant === 'primary';
  const fg = primary ? c.accentInk : variant === 'danger' ? c.danger : c.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: primary ? c.accent : c.surface, borderColor: primary ? c.accent : c.border },
        (pressed || disabled) && { opacity: 0.6 },
      ]}
    >
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function Field({ label: fieldLabel, ...props }: TextInputProps & { label: string }) {
  const c = usePalette();
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={[styles.label, { color: c.muted }]}>{fieldLabel}</Text>
      <TextInput
        placeholderTextColor={c.muted}
        accessibilityLabel={fieldLabel}
        {...props}
        style={[styles.input, { color: c.text, borderColor: c.border, backgroundColor: c.bg },
          props.multiline && { minHeight: 110, textAlignVertical: 'top' }]}
      />
    </View>
  );
}

/** A wrapping row of selectable chips (a touch-friendly replacement for <select>). */
export function Chips<T extends string>({ label: chipsLabel, options, value, onChange, format }: {
  label: string;
  options: readonly T[] | { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  format?: (v: T) => string;
}) {
  const c = usePalette();
  const items = (options as (T | { value: T; label: string })[]).map((o) =>
    typeof o === 'string' ? { value: o, label: format ? format(o) : capitalize(label(o)) } : o);
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={[styles.label, { color: c.muted }]}>{chipsLabel}</Text>
      <View style={styles.chips} accessibilityRole="radiogroup" accessibilityLabel={chipsLabel}>
        {items.map((o) => {
          const selected = o.value === value;
          return (
            <Pressable
              key={o.value}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              onPress={() => onChange(o.value)}
              style={[styles.chip, {
                borderColor: selected ? c.accent : c.border,
                backgroundColor: selected ? c.accent : c.surface,
              }]}
            >
              <Text style={{ color: selected ? c.accentInk : c.text, fontSize: 14 }}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function Banner({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'high' }) {
  const c = usePalette();
  const t = c.level[tone];
  return (
    <View style={[styles.banner, { backgroundColor: t.bg, borderLeftColor: t.fg }]}>
      <Text style={[styles.body, { color: c.text }]}>{children}</Text>
    </View>
  );
}

export function ErrorText({ children }: { children: ReactNode }) {
  const c = usePalette();
  if (!children) return null;
  return <Text accessibilityRole="alert" style={[styles.body, { color: c.danger, marginTop: 8 }]}>{children}</Text>;
}

export function Loading() {
  const c = usePalette();
  return <View style={{ padding: 32 }}><ActivityIndicator color={c.accent} /></View>;
}

export const styles = StyleSheet.create({
  screen: { padding: 16, gap: 14, paddingBottom: 40 },
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, padding: 16 },
  h2: { fontSize: 17, fontWeight: '600', marginBottom: 6 },
  body: { fontSize: 15, lineHeight: 21 },
  label: { fontSize: 13, marginBottom: 6 },
  button: { minHeight: 44, paddingHorizontal: 16, borderRadius: 10, borderWidth: 1,
            alignItems: 'center', justifyContent: 'center' },
  buttonText: { fontSize: 15, fontWeight: '600' },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, minHeight: 36,
          justifyContent: 'center' },
  banner: { borderLeftWidth: 4, borderRadius: 10, padding: 12 },
  row: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 14 },
});
