import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { useT } from '../lib/i18n';
import { useSession } from '../lib/session';
import { useLoader } from '../lib/useLoader';
import { Body, Button, Card, H2, styles } from './ui';

/** Offers the pilot study once, on Home, when it's running (fhg/study.py). "Not now" isn't asked again; the study
 * stays in Settings. */
export function StudyCard() {
  const { t, lang } = useT();
  const { api } = useSession();
  const router = useRouter();
  const { data, reload } = useLoader(() => api.study(lang));
  if (!data || !data.enabled || data.status !== 'not_asked') return null;
  return (
    <Card>
      <Body muted style={{ fontSize: 12 }}>{t('Pilot study · optional')}</Body>
      <H2>{data.title}</H2>
      <Body>{data.summary}</Body>
      <View style={styles.row}>
        <Button title={t('Read and decide')} variant="primary" onPress={() => router.push('/study')} />
        <Button title={data.buttons.decline} onPress={async () => { await api.studyDecline(); reload(); }} />
      </View>
    </Card>
  );
}
