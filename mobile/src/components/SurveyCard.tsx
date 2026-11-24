import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { N, useT } from '../lib/i18n';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import { useLoader } from '../lib/useLoader';
import { Body, Card, H2 } from './ui';

// The pilot's optional questions (fhg/pilot.py). Shown one at a time on Home; answers are only ever counted.
const QUESTION: Record<string, string> = {
  baseline_knowledge: N('Before using the app, how much of your family’s health history did you know?'),
  baseline_discussed: N('Have you ever talked about your family’s health history with a doctor?'),
  followup_action: N('Since joining, has the app led you to have a test or talk to a doctor?'),
  followup_useful: N('How useful has the app been for your family?'),
};
const OPTION: Record<string, string> = {
  most: N('Most of it'), some: N('Some of it'), very_little: N('Very little'), yes: N('Yes'), no: N('No'),
  test: N('Had a test'), doctor: N('Talked to a doctor'), both: N('Both'), not_yet: N('Not yet'),
  very: N('Very useful'), somewhat: N('Somewhat'), not: N('Not useful'),
};

export function SurveyCard() {
  const { t } = useT();
  const { api } = useSession();
  const c = usePalette();
  const { data, reload } = useLoader(() => api.surveys());
  const [busy, setBusy] = useState(false);
  const q = data?.[0];
  if (!q) return null;

  const answer = async (value: string) => {
    setBusy(true);
    try { await api.answerSurvey(q.id, value); reload(); } finally { setBusy(false); }
  };
  return (
    <Card>
      <Body muted style={{ fontSize: 12 }}>{t('Quick question for our pilot · optional')}</Body>
      <H2>{t(QUESTION[q.id] ?? q.text)}</H2>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
        {q.options.map((o) => (
          <Pressable key={o} accessibilityRole="button" disabled={busy} onPress={() => answer(o)}
                     style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18, borderWidth: 1, borderColor: c.accent }}>
            <Text style={{ color: c.accent, fontSize: 15 }}>{t(OPTION[o] ?? o)}</Text>
          </Pressable>
        ))}
        <Pressable accessibilityRole="button" disabled={busy} onPress={() => answer('skipped')} style={{ paddingVertical: 8, paddingHorizontal: 6 }}>
          <Text style={{ color: c.muted, fontSize: 15 }}>{t('Skip')}</Text>
        </Pressable>
      </View>
      <Body muted style={{ fontSize: 12, marginTop: 8 }}>
        {t('Answers are only counted across all families, never shown individually.')}
      </Body>
    </Card>
  );
}
