import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';

import { Badge, Row, Section } from '../../components/list';
import { Body, ErrorText, Loading, Screen } from '../../components/ui';
import { shareCanRiskFile } from '../../lib/canrisk';
import { BOOKING_LABEL, formatDay, REFERRAL_LABEL, rupees } from '../../lib/format';
import { useSession } from '../../lib/session';
import { LEVEL_LABEL, usePalette } from '../../lib/theme';
import { useLoader } from '../../lib/useLoader';

/** Action items where the family tree feeds a hereditary-risk model or calculator. */
const TREE_MODELS = new Set(['hboc_family_pattern', 'colorectal_family_history', 'lynch_criteria']);

const WHEN: Record<string, string> = {
  high: 'Worth raising with a clinician soon.',
  moderate: 'Bring this up at your next routine visit.',
  info: 'Good to know. No appointment needed for this alone.',
};

/** Detail page for one action item: why it was flagged, what to do, and the source guidance. */
export default function InsightDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const c = usePalette();
  const { api } = useSession();
  const { data, error, reload } = useLoader(async () => {
    const [report, referrals, tests, risk] = await Promise.all([
      api.insights(), api.referrals(), api.insightTests(id), TREE_MODELS.has(id) ? api.risk() : Promise.resolve(null)]);
    return { insight: report.insights.find((i) => i.rule_id === id) ?? null, disclaimer: report.disclaimer,
             referrals: referrals.filter((r) => r.rule_id === id), tests, risk };
  });
  const [shareError, setShareError] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { insight, disclaimer, referrals, tests, risk } = data;
  const active = tests.bookings.filter((b) => ['requested', 'scheduled', 'sample_collected'].includes(b.status));
  if (!insight) {
    return <Screen><Body muted>This item no longer applies. Your record may have changed.</Body></Screen>;
  }
  const tone = c.level[insight.level];

  return (
    <Screen>
      <Stack.Screen options={{ title: LEVEL_LABEL[insight.level] }} />
      <View style={{ gap: 8 }}>
        <View style={{ alignSelf: 'flex-start' }}>
          <Badge label={LEVEL_LABEL[insight.level]} fg={tone.fg} bg={tone.bg} />
        </View>
        <Text accessibilityRole="header" style={{ fontSize: 22, fontWeight: '700', color: c.text }}>{insight.title}</Text>
        <Body muted>{WHEN[insight.level]}</Body>
      </View>

      <Body>{insight.summary}</Body>

      {insight.evidence.length > 0 && (
        <Section title="Why this was flagged">
          {insight.evidence.map((e, i) => (
            <Row key={e} title={e} last={i === insight.evidence.length - 1} />
          ))}
        </Section>
      )}

      {referrals.length > 0 && (
        <Section title="From your care team">
          {referrals.map((r, i) => (
            <Row key={r.org_id} title={`${r.org_name}: ${REFERRAL_LABEL[r.status] ?? r.status}`}
                 detail={`${r.program}${r.partner_name ? ` · with ${r.partner_name}` : ''} · updated ${new Date(r.updated_at).toLocaleDateString()}`}
                 last={i === referrals.length - 1} />
          ))}
        </Section>
      )}

      <Section title="What you can do">
        <View style={{ padding: 16 }}><Body>{insight.recommendation}</Body></View>
      </Section>

      {risk && risk.assessments.length > 0 && (
        <Section title="Your counselor's risk figures">
          {risk.assessments.flatMap((a) => a.predictions.map((pr, i) => (
            <Row key={`${a.id}-${i}`} title={`${pr.outcome}: ${pr.probability_percent}% ${pr.horizon}`}
                 detail={[pr.population_percent != null ? `population ${pr.population_percent}%` : null,
                          `${a.model} · ${a.partner_name} · ${new Date(a.created_at).toLocaleDateString()}`]
                   .filter(Boolean).join(' · ')} />
          )))}
        </Section>
      )}

      {risk && TREE_MODELS.has(insight.rule_id) && (
        <Section title="For your genetic counselor">
          <View style={{ padding: 16, gap: 8 }}>
            <Body>
              Counselors calculate breast and ovarian cancer risk with BOADICEA in CanRisk. Your family tree can be
              exported as a CanRisk file, with no names in it.
            </Body>
            {risk.needs ? <Body muted>{risk.needs}</Body> : (
              <Pressable accessibilityRole="button" onPress={() => {
                setShareError(null);
                shareCanRiskFile(api).catch((e) => setShareError(e instanceof Error ? e.message : String(e)));
              }}>
                <Text style={{ color: c.accent, fontSize: 16, fontWeight: '600' }}>Share the CanRisk file</Text>
              </Pressable>
            )}
            {risk.pedigree && risk.pedigree.not_placed.length > 0 && (
              <Body muted style={{ fontSize: 13 }}>Not included: {risk.pedigree.not_placed.join('; ')}.</Body>
            )}
            {shareError && <ErrorText>{shareError}</ErrorText>}
          </View>
        </Section>
      )}

      {tests.bookings.length > 0 && (
        <Section title="Your bookings">
          {tests.bookings.map((b, i) => (
            <View key={b.id}>
              <Row title={`${b.test_names.join(', ')} · ${b.partner_name}`}
                   detail={[BOOKING_LABEL[b.status], b.scheduled_for ? formatDay(b.scheduled_for) : null].filter(Boolean).join(' · ')}
                   last={i === tests.bookings.length - 1 && !active.includes(b)} />
              {active.includes(b) && (
                <View style={{ flexDirection: 'row', gap: 16, paddingHorizontal: 16, paddingBottom: 12 }}>
                  <Pressable accessibilityRole="button" onPress={async () => { await api.cancelBooking(b.id); reload(); }}>
                    <Text style={{ color: c.danger, fontSize: 14 }}>Cancel booking</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" onPress={async () => { await api.bookingDoneElsewhere(b.id); reload(); }}>
                    <Text style={{ color: c.accent, fontSize: 14 }}>I had it done elsewhere</Text>
                  </Pressable>
                </View>
              )}
            </View>
          ))}
        </Section>
      )}

      {tests.tests.length > 0 && active.length === 0 && (
        <Section title="Get tested">
          {tests.tests.map((t) => (
            <View key={t.test}>
              <View style={{ paddingHorizontal: 16, paddingTop: 14, gap: 2 }}>
                <Text style={{ color: c.text, fontSize: 16, fontWeight: '600' }}>{t.name}</Text>
                <Body muted style={{ fontSize: 13 }}>{t.prep}</Body>
              </View>
              {t.offers.length === 0 ? (
                <View style={{ paddingHorizontal: 16, paddingVertical: 10 }}>
                  <Body muted style={{ fontSize: 13 }}>No partner offers this yet. Your doctor or any lab can do it.</Body>
                </View>
              ) : t.offers.map((o) => (
                <Row key={o.partner_id} title={o.partner_name}
                     detail={[rupees(o.price_inr), o.home_collection ? 'home collection' : null,
                              o.turnaround_days != null ? `results in ${o.turnaround_days} day${o.turnaround_days === 1 ? '' : 's'}` : null]
                       .filter(Boolean).join(' · ')}
                     onPress={() => router.push({ pathname: '/book', params: {
                       rule: insight.rule_id, partner: o.partner_id, partnerName: o.partner_name, tests: t.test,
                       testName: t.name, price: o.price_inr != null ? String(o.price_inr) : '' } })} />
              ))}
            </View>
          ))}
        </Section>
      )}

      {insight.references.length > 0 && (
        <Section title="Based on">
          {insight.references.map((r, i) => (
            <Row key={r.url} title={r.title} onPress={() => Linking.openURL(r.url)}
                 last={i === insight.references.length - 1} />
          ))}
        </Section>
      )}

      <Body muted style={{ fontSize: 12 }}>{disclaimer}</Body>
    </Screen>
  );
}
