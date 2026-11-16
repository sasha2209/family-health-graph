import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { Banner, Body, Button, Card, Chips, ErrorText, H2, Loading, Screen, styles } from '../../components/ui';
import { publicApi } from '../../lib/api';
import { ALL_RELATIONSHIPS, label, SHARE_OPTIONS } from '../../lib/format';
import { useSession } from '../../lib/session';
import type { InvitePreview, ShareLevel } from '../../lib/types';

const THEY_SHARE: Record<ShareLevel, string> = {
  none: 'nothing yet',
  conditions: 'their own health conditions',
  conditions_and_tree: "their own health conditions and the family history they've recorded",
};

/** Opened from an invite link (familyhealth://invite/TOKEN or https://<host>/invite/TOKEN). */
export default function AcceptInvite() {
  const { token: inviteToken } = useLocalSearchParams<{ token: string }>();
  const { token, api, signIn } = useSession();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [relationship, setRelationship] = useState('');
  const [editingRel, setEditingRel] = useState(false);
  const [share, setShare] = useState<ShareLevel>('conditions');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!inviteToken) return;
    publicApi.previewInvite(inviteToken)
      .then((p) => { setPreview(p); setRelationship(p.they_are_your); })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, [inviteToken]);

  async function accept() {
    setBusy(true); setError(null);
    try {
      const r = await api.acceptInvite(inviteToken, { share_level: share, relationship });
      setDone(`You're now linked with your ${label(r.they_are_your)}.`);
      if (r.token) await signIn(r.token); // a new account was created for this device
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <Screen>
        <Card>
          <H2>This invitation can’t be used</H2>
          <Body muted>{loadError}. Ask your relative to send a new link.</Body>
        </Card>
      </Screen>
    );
  }
  if (!preview) return <Screen><Loading /></Screen>;

  if (done) {
    return (
      <Screen>
        <Card>
          <H2>{done}</H2>
          <Body muted>Your insights now include what they share. You can change sharing any time on the Family tab.</Body>
          <View style={styles.row}>
            <Button title="Open my family health" variant="primary" onPress={() => router.replace('/')} />
          </View>
        </Card>
      </Screen>
    );
  }

  const who = preview.inviter_name || 'A relative';
  return (
    <Screen>
      <Card>
        <H2>{who}, your {label(preview.they_are_your)}, invited you to share family health history</H2>
        {preview.message ? <Banner>{preview.message}</Banner> : null}
        <Body style={{ marginTop: 10 }}>
          {'•'} They will share {THEY_SHARE[preview.they_will_share]} with you.{'\n'}
          {'•'} You choose what you share, and can change it or unlink at any time.{'\n'}
          {'•'} Shared history is only used for each other’s insights. It is never sold or sent to insurers or employers.
        </Body>
        {editingRel ? (
          <Chips label="They are your" options={ALL_RELATIONSHIPS} value={relationship}
            onChange={(v) => { setRelationship(v); setEditingRel(false); }} />
        ) : (
          <View style={[styles.row, { alignItems: 'center' }]}>
            <Body>They are your <Body style={{ fontWeight: '600' }}>{label(relationship)}</Body></Body>
            <Button title="Change" onPress={() => setEditingRel(true)} />
          </View>
        )}
        <Chips<ShareLevel> label="You'll share with them"
          options={SHARE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          value={share} onChange={setShare} />
        <View style={styles.row}>
          <Button title="Accept and join" variant="primary" onPress={accept} busy={busy} />
          <Button title="No thanks" onPress={async () => {
            await publicApi.declineInvite(inviteToken).catch(() => undefined);
            setLoadError('You declined this invitation');
          }} />
        </View>
        <ErrorText>{error}</ErrorText>
        <Body muted style={{ fontSize: 13, marginTop: 10 }}>
          {token ? "You'll join with your account on this device." : 'A private account will be created on this device.'}
          {' '}Expires {new Date(preview.expires_at).toLocaleDateString()}.
        </Body>
      </Card>
    </Screen>
  );
}
