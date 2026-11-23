import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { Banner, Body, Button, Card, Chips, ErrorText, Field, Screen, styles } from '../components/ui';
import { rupees } from '../lib/format';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';

const SLOTS = [
  { value: 'morning', label: 'Morning (7–11)' },
  { value: 'afternoon', label: 'Afternoon (12–4)' },
  { value: 'evening', label: 'Evening (4–8)' },
] as const;

function nextDays(n: number) {
  const out: { value: string; label: string }[] = [];
  for (let i = 1; i <= n; i++) {
    const d = new Date(); d.setDate(d.getDate() + i);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    out.push({ value: iso, label: d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) });
  }
  return out;
}

/** Book a test with a lab partner, from an action item. */
export default function BookScreen() {
  const q = useLocalSearchParams<{ rule: string; partner: string; partnerName: string; tests: string; testName: string; price?: string }>();
  const { api } = useSession();
  const c = usePalette();
  const days = nextDays(7);
  const [day, setDay] = useState(days[0].value);
  const [slot, setSlot] = useState<string>('morning');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [pincode, setPincode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (done) {
    return (
      <Screen>
        <Banner>Booked. {q.partnerName} will confirm the time; we’ll let you know, and your results will appear in the app.</Banner>
        <View style={styles.row}><Button title="Done" variant="primary" onPress={() => router.back()} /></View>
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={{ gap: 4 }}>
        <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>{q.testName}</Text>
        <Body muted>{[q.partnerName, q.price ? rupees(Number(q.price)) : null].filter(Boolean).join(' · ')}</Body>
      </View>
      <Card>
        <Chips label="Day" options={days} value={day} onChange={setDay} />
        <Chips label="Time" options={[...SLOTS]} value={slot} onChange={setSlot} />
      </Card>
      <Card>
        <Field label="Name" value={name} onChangeText={setName} autoCapitalize="words" />
        <Field label="Phone" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="+91 98xxx xxxxx" />
        <Field label="Address for home collection" value={address} onChangeText={setAddress} multiline />
        <Field label="PIN code" value={pincode} onChangeText={setPincode} keyboardType="number-pad" maxLength={6} />
      </Card>
      <Body muted style={{ fontSize: 13 }}>
        {q.partnerName} receives the test name, your chosen time and these contact details, and nothing else from your
        record. Results come back into your record automatically.
      </Body>
      <View style={styles.row}>
        <Button title="Book" variant="primary" busy={busy} disabled={busy || !name.trim() || phone.replace(/\D/g, '').length < 7}
          onPress={async () => {
            setBusy(true); setError(null);
            try {
              await api.book({ partner_id: q.partner, tests: q.tests.split(','), rule_id: q.rule, preferred_date: day, slot,
                               contact: { name: name.trim(), phone: phone.trim(), address: address.trim() || undefined,
                                          pincode: pincode.trim() || undefined } });
              setDone(true);
            } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
          }} />
      </View>
      <ErrorText>{error}</ErrorText>
    </Screen>
  );
}
