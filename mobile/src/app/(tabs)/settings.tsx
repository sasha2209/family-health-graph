import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Platform, Share, Switch, View } from 'react-native';

import { AppleSignIn } from '../../components/AppleSignIn';
import { ClinicsCard } from '../../components/ClinicsCard';
import { Banner, Body, Button, Card, Chips, ErrorText, Field, H2, Loading, Screen, styles } from '../../components/ui';
import { API_URL } from '../../lib/api';
import { useAppLock } from '../../lib/appLock';
import { enablePush, pushSupport } from '../../lib/push';
import { useSession } from '../../lib/session';
import { usePalette } from '../../lib/theme';
import type { Activity, Sex } from '../../lib/types';
import { useLoader } from '../../lib/useLoader';

const AI_SCOPE = 'ai_summary';
const AI_DOCS_SCOPE = 'ai_document_reading';
const WA_SCOPE = 'whatsapp_summaries';

function confirmDestructive(title: string, message: string, onOk: () => void, okText = 'Delete') {
  if (Platform.OS === 'web') {
    if (globalThis.confirm?.(`${title}\n\n${message}`)) onOk();
    return;
  }
  Alert.alert(title, message, [
    { text: 'Cancel', style: 'cancel' },
    { text: okText, style: 'destructive', onPress: onOk },
  ]);
}

const PROVIDER_LABEL = { email: 'Email', apple: 'Apple', google: 'Google' } as const;

function ago(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

export default function SettingsScreen() {
  const c = usePalette();
  const { api, signOut } = useSession();
  const lock = useAppLock();
  const { data, error, reload } = useLoader(async () => {
    const [profile, consents, me, sessions, pushState, clinics, grants] = await Promise.all([
      api.profile(false), api.consents(), api.me(), api.sessions(), api.pushStatus(), api.clinics(), api.grants()]);
    return { profile, me, sessions, clinics, grants, push: pushState.registered,
             ai: consents.consents.some((x) => x.scope === AI_SCOPE && x.active),
             aiDocs: consents.consents.some((x) => x.scope === AI_DOCS_SCOPE && x.active),
             wa: consents.consents.some((x) => x.scope === WA_SCOPE && x.active) };
  });
  const [birth, setBirth] = useState<string | null>(null);
  const [waist, setWaist] = useState('');
  const [riskMsg, setRiskMsg] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { profile, ai, aiDocs, wa, me, sessions, push, clinics, grants } = data;
  const support = pushSupport();
  const birthValue = birth ?? profile.birth_date ?? '';

  return (
    <Screen>
      <Card>
        <H2>Account</H2>
        {me.secured ? (
          me.identities.map((i) => (
            <Body key={i.provider + (i.email ?? '')}>
              Signed in with {PROVIDER_LABEL[i.provider]}{i.email ? `: ${i.email}` : ''}
            </Body>
          ))
        ) : (
          <Banner tone="high">
            Your account isn’t protected yet. If you lose this phone, your data can’t be recovered.
            Add your email to sign in on other devices.
          </Banner>
        )}
        <View style={[styles.row, { flexDirection: 'column', alignItems: 'stretch' }]}>
          {!me.identities.some((i) => i.provider === 'email') && (
            <Button title="Add your email" variant={me.secured ? 'secondary' : 'primary'}
              onPress={() => router.push({ pathname: '/sign-in', params: { mode: 'link' } })} />
          )}
          {!me.identities.some((i) => i.provider === 'apple') && (
            <AppleSignIn link onDone={() => reload()} onError={setMsg} />
          )}
        </View>
      </Card>

      <ClinicsCard clinics={clinics} onChange={reload} />

      <Card>
        <H2>Signed-in devices</H2>
        {sessions.map((d) => (
          <View key={d.id} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                                    gap: 8, marginTop: 10 }}>
            <View style={{ flex: 1 }}>
              <Body>{d.device ?? 'Unknown device'}{d.current ? ' (this device)' : ''}</Body>
              <Body muted style={{ fontSize: 13 }}>Last active {ago(d.last_used_at)}</Body>
            </View>
            {!d.current && (
              <Button title="Sign out" onPress={async () => { await api.revokeSession(d.id); reload(); }} />
            )}
          </View>
        ))}
      </Card>

      <Card>
        <H2>Notifications</H2>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Body>Family alerts</Body>
            <Body muted style={{ fontSize: 13 }}>
              {support.ok
                ? 'When a relative joins or shares a result that runs in families. Notifications never show health details.'
                : support.reason}
            </Body>
          </View>
          <Switch
            accessibilityLabel="Family alerts"
            value={push}
            disabled={!support.ok}
            trackColor={{ true: c.accent, false: c.border }}
            onValueChange={async (on) => {
              if (on) {
                const ok = await enablePush(api).catch(() => false);
                if (!ok) setMsg('Notifications are turned off for this app in your phone’s settings.');
              } else {
                await api.unregisterPush();
              }
              reload();
            }}
          />
        </View>
      </Card>

      {lock.available && (
        <Card>
          <H2>App lock</H2>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <View style={{ flex: 1 }}>
              <Body>Require Face ID or fingerprint</Body>
              <Body muted style={{ fontSize: 13 }}>
                When you open the app, and after 30 seconds away.
              </Body>
            </View>
            <Switch
              accessibilityLabel="Require Face ID or fingerprint"
              value={lock.enabled}
              trackColor={{ true: c.accent, false: c.border }}
              onValueChange={(on) => { lock.setEnabled(on); }}
            />
          </View>
        </Card>
      )}

      <Card>
        <H2>About you</H2>
        <Body muted>Used for age- and sex-specific guidance.</Body>
        <Chips<Sex> label="Sex" options={['female', 'male', 'other']} value={(profile.sex ?? '') as Sex}
          onChange={async (sex) => { await api.setDemographics({ sex }); reload(); }} />
        <Field label="Date of birth (YYYY-MM-DD)" value={birthValue} onChangeText={setBirth}
          keyboardType="numbers-and-punctuation" placeholder="1984-05-02" maxLength={10} />
        <View style={styles.row}>
          <Button title="Save" disabled={!/^\d{4}-\d{2}-\d{2}$/.test(birthValue)} onPress={async () => {
            try { await api.setDemographics({ birth_date: birthValue }); setMsg('Saved.'); reload(); }
            catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
          }} />
        </View>
        {msg && <Body muted style={{ marginTop: 6 }}>{msg}</Body>}
      </Card>

      <Card>
        <H2>Diabetes risk check</H2>
        <Body muted>
          Two questions for the Indian Diabetes Risk Score, a check developed for Indian adults. It also uses your age
          and whether your parents have diabetes.
        </Body>
        <Chips<Activity> label="Physical activity" value={(profile.activity ?? '') as Activity}
          options={[
            { value: 'exercise_and_active_work', label: 'Exercise and an active day' },
            { value: 'exercise_or_active_work', label: 'One of the two' },
            { value: 'sedentary', label: 'Neither: mostly sitting' },
          ]}
          onChange={async (activity) => { await api.setLifestyle({ activity }); setRiskMsg('Saved.'); reload(); }} />
        <Field label="Waist, measured at the navel (cm)" value={waist} onChangeText={setWaist} keyboardType="decimal-pad"
               placeholder="e.g. 88" maxLength={5} />
        <View style={styles.row}>
          <Button title="Save waist" disabled={!/^\d{2,3}(\.\d)?$/.test(waist)} onPress={async () => {
            try { await api.setLifestyle({ waist_cm: Number(waist) }); setWaist(''); setRiskMsg('Saved. Your score is on Home.'); reload(); }
            catch (e) { setRiskMsg(e instanceof Error ? e.message : String(e)); }
          }} />
        </View>
        {riskMsg && <Body muted style={{ marginTop: 6 }}>{riskMsg}</Body>}
      </Card>

      <Card>
        <H2>Apps with access</H2>
        {grants.length === 0 ? (
          <Body muted>No apps can read your record. When a service asks to connect, you choose what it can see.</Body>
        ) : grants.map((g) => (
          <View key={g.id} style={{ marginTop: 12, gap: 4 }}>
            <Body style={{ fontWeight: '600' }}>{g.partner.name}</Body>
            <Body muted style={{ fontSize: 13 }}>
              Can read: {g.scopes.map((x) => x.scope.replace('.read', '').replace('_', ' ')).join(', ')}
              {' · '}{g.last_used_at ? `last read ${new Date(g.last_used_at).toLocaleDateString()}` : 'not used yet'}
            </Body>
            <View style={styles.row}>
              <Button title="Remove access" variant="danger" onPress={() => confirmDestructive(
                `Remove ${g.partner.name}’s access?`, 'They will no longer be able to read your record.',
                async () => { await api.revokeGrant(g.id); reload(); }, 'Remove')} />
            </View>
          </View>
        ))}
      </Card>

      <Card>
        <H2>Privacy</H2>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Body>AI plain-language summaries</Body>
            <Body muted style={{ fontSize: 13 }}>
              Sends only your computed insights (no names or raw records) to an AI model.
            </Body>
          </View>
          <Switch
            accessibilityLabel="AI plain-language summaries"
            value={ai}
            trackColor={{ true: c.accent, false: c.border }}
            onValueChange={async (v) => { await api.setConsent(AI_SCOPE, v); reload(); }}
          />
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 14 }}>
          <View style={{ flex: 1 }}>
            <Body>AI reading for hard-to-read documents</Body>
            <Body muted style={{ fontSize: 13 }}>
              Documents are read on our server first. Only when that fails (handwriting, a blurry photo) is the
              text, or one reduced image, sent to an AI model. You always review the result.
            </Body>
          </View>
          <Switch
            accessibilityLabel="AI reading for hard-to-read documents"
            value={aiDocs}
            trackColor={{ true: c.accent, false: c.border }}
            onValueChange={async (v) => { await api.setConsent(AI_DOCS_SCOPE, v); reload(); }}
          />
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 14 }}>
          <View style={{ flex: 1 }}>
            <Body>WhatsApp summaries</Body>
            <Body muted style={{ fontSize: 13 }}>
              Let the WhatsApp assistant tell you what it read and your action items. Off: it only sends short
              confirmations, with no health details.
            </Body>
          </View>
          <Switch
            accessibilityLabel="WhatsApp summaries"
            value={wa}
            trackColor={{ true: c.accent, false: c.border }}
            onValueChange={async (v) => { await api.setConsent(WA_SCOPE, v); reload(); }}
          />
        </View>
        <View style={styles.row}>
          <Button title="Your privacy rights" variant="primary" onPress={() => router.push('/privacy')} />
          <Button title="Export my data (FHIR)" onPress={async () => {
            const bundle = await api.exportFhir();
            await Share.share({ title: 'My health record (FHIR)', message: JSON.stringify(bundle, null, 2) });
          }} />
        </View>
      </Card>

      <Card>
        <H2>Account</H2>
        <Body muted style={{ fontSize: 13 }}>Server: {API_URL}</Body>
        <View style={styles.row}>
          <Button title="Sign out of this device" onPress={() => confirmDestructive(
            'Sign out?',
            me.secured
              ? 'You can sign back in with your email or Apple ID.'
              : 'Your account has no email or Apple ID, so you won’t be able to sign back in. Add your email first to keep your data.',
            () => signOut(),
            'Sign out',
          )} />
          <Button title="Delete all my data" variant="danger" onPress={() => confirmDestructive(
            'Delete everything?',
            'Your record, linked relatives and history will be permanently deleted. This cannot be undone.',
            async () => { await api.deleteAccount(); await signOut({ revoke: false }); },
          )} />
        </View>
      </Card>
    </Screen>
  );
}
