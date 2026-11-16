import { useState } from 'react';
import { Share, View } from 'react-native';

import { Body, Button, Card, Chips, ErrorText, Field, H2, Screen, styles } from '../../components/ui';
import { INVITE_RELATIONSHIPS, label, SHARE_OPTIONS } from '../../lib/format';
import { enablePush, pushSupport } from '../../lib/push';
import { useSession } from '../../lib/session';
import type { CreatedInvite, ShareLevel } from '../../lib/types';

export default function InviteScreen() {
  const { api } = useSession();
  const [relationship, setRelationship] = useState('mother');
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const [share, setShare] = useState<ShareLevel>('conditions');
  const [created, setCreated] = useState<CreatedInvite | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alertsOn, setAlertsOn] = useState(false);

  async function shareLink(invite: CreatedInvite) {
    // Android ignores `url`, so the link also goes in the message text.
    try {
      await Share.share({
        title: 'Family Health Graph',
        message: `I'm putting together our family health history. Can you add yours? ${invite.invite_url}`,
        url: invite.invite_url,
      });
    } catch {
      // No share sheet (e.g. some browsers). The link is shown on screen to copy.
    }
  }

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const invite = await api.createInvite({
        relationship,
        inviter_name: name.trim() || undefined,
        message: message.trim() || undefined,
        share_level: share,
      });
      setCreated(invite);
      await shareLink(invite);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Body muted>
        Relatives who join can share their own history, so both of your insights get more accurate.
        Each of you decides what you share, and can change it at any time.
      </Body>
      <Card>
        <Chips label="They are your" options={INVITE_RELATIONSHIPS} value={relationship}
               onChange={(v) => { setRelationship(v); setCreated(null); }} />
        <Field label="Your first name (shown to them)" value={name} onChangeText={setName}
               maxLength={60} placeholder="e.g. Priya" />
        <Field label="Message (optional)" value={message} onChangeText={setMessage} maxLength={500}
               placeholder="Can you add what you know about your side?" />
        <Chips<ShareLevel> label="You'll share with them"
               options={SHARE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
               value={share} onChange={setShare} />
        <View style={styles.row}>
          <Button title="Create and share invite" variant="primary" onPress={create} busy={busy} />
        </View>
        <ErrorText>{error}</ErrorText>
      </Card>

      {created && (
        <Card>
          <H2>Invite ready</H2>
          <Body selectable>{created.invite_url}</Body>
          <Body muted style={{ marginTop: 6 }}>
            Send this to your {label(relationship)}. It works once and expires in 14 days.
          </Body>
          <View style={styles.row}>
            <Button title="Share again" onPress={() => shareLink(created)} />
            {pushSupport().ok && !alertsOn && (
              <Button title="Notify me when they join" onPress={async () => {
                setAlertsOn(await enablePush(api).catch(() => false));
              }} />
            )}
          </View>
          {alertsOn && <Body muted style={{ marginTop: 6 }}>We’ll let you know when they join.</Body>}
        </Card>
      )}
    </Screen>
  );
}
