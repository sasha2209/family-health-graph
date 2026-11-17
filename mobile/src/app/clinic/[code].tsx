import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { ClinicsCard } from '../../components/ClinicsCard';
import { Body, Button, Card, H2, Loading, Screen, styles } from '../../components/ui';
import { publicApi } from '../../lib/api';
import { useSession } from '../../lib/session';

/**
 * Opened from a clinic's pre-visit intake link (familyhealth://clinic/CODE or
 * https://<domain>/c/CODE). Works signed in or out: newcomers get a private
 * account first, then confirm and connect with the code already filled in.
 */
export default function ClinicIntake() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const { token, api, signIn } = useSession();
  const [clinic, setClinic] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!code) return;
    publicApi.clinicByCode(code).then((c) => setClinic(c.name))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [code]);

  if (error) {
    return <Screen><Card><H2>This link isn’t working</H2><Body muted>{error}. Ask your clinic for a new link.</Body></Card></Screen>;
  }
  if (!clinic) return <Screen><Loading /></Screen>;

  if (connected) {
    return (
      <Screen>
        <Card>
          <H2>Shared with {clinic}</H2>
          <Body muted>Your care team will see your family history and insights before your visit. Add more any time; they’ll see updates.</Body>
          <View style={styles.row}>
            <Button title="Add family history" variant="primary" onPress={() => router.replace('/add-history')} />
            <Button title="Go to Home" onPress={() => router.replace('/')} />
          </View>
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <Card>
        <H2>{clinic} asks you to share your family health history</H2>
        <Body muted>
          It helps your care team spot what may need follow-up, such as earlier screening. Your record is encrypted,
          never sold, and you can disconnect at any time.
        </Body>
        {!token && (
          <View style={styles.row}>
            <Button title="Get started" variant="primary" busy={busy} onPress={async () => {
              setBusy(true);
              try { await signIn((await publicApi.createAccount()).token); }
              catch (e) { setError(e instanceof Error ? e.message : String(e)); }
              finally { setBusy(false); }
            }} />
          </View>
        )}
      </Card>
      {token && (
        <ClinicsCard clinics={[]} initialCode={code} initialName={clinic} source="link"
                     onChange={async () => { await api.clinics(); setConnected(true); }} />
      )}
    </Screen>
  );
}
