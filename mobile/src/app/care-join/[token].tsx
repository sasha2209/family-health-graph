import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';

import { Body, Button, Card, ErrorText, Field, H2, Screen } from '../../components/ui';
import { createApi, publicApi } from '../../lib/api';
import { useSession } from '../../lib/session';
import { useT } from '../../lib/i18n';

/** Opened from a care-circle invite (https://<host>/app/care-join/TOKEN): help a sibling look after a parent. */
export default function JoinCareCircle() {
  const { t } = useT();
  const { token: inviteToken } = useLocalSearchParams<{ token: string }>();
  const { token, signIn } = useSession();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function join() {
    setBusy(true); setError(null);
    try {
      let t = token;
      if (!t) {
        t = (await publicApi.createAccount()).token;     // a new account for this phone
        await signIn(t);
      }
      const care = await createApi(t).careJoin(inviteToken, name.trim() || undefined);
      router.replace({ pathname: '/care', params: { id: care.care_id } });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <Card>
        <H2>{t('Help look after a family member')}</H2>
        <Body muted>
          {t('You’ll see their medicines and today’s doses, can mark doses as taken, keep their emergency details, and get the same reminders as the rest of the family. Their record stays with the person who invited you.')}
        </Body>
        <Field label={t('Your name (so the family knows who marked a dose)')} value={name} onChangeText={setName} placeholder={t('Rahul')} />
        <Button title={t('Join the care circle')} variant="primary" busy={busy} onPress={join} />
        <ErrorText>{error}</ErrorText>
      </Card>
    </Screen>
  );
}
