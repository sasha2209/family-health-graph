import { Href, router } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { Badge, Check, Progress, Row, Section } from '../../components/list';
import { SurveyCard } from '../../components/SurveyCard';
import { Banner, Body, Button, Card, ErrorText, H2, Loading, Screen, styles } from '../../components/ui';
import { shareDoctorSummary } from '../../lib/doctorSummary';
import { BOOKING_LABEL, capitalize, DOC_TYPE_LABEL, formatDay, label, REFERRAL_LABEL, VIA_LABEL } from '../../lib/format';
import { pushSupport } from '../../lib/push';
import { N, useT } from '../../lib/i18n';
import { useSession } from '../../lib/session';
import { LEVEL_LABEL, usePalette } from '../../lib/theme';
import { useLoader } from '../../lib/useLoader';

const GRANDPARENT = /grand(mother|father)$/;

function greeting(t: (s: string) => string): string {
  const h = new Date().getHours();
  return t(h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening');
}

/**
 * Home: a greeting, family alerts, a "next steps" checklist that builds a
 * useful record, and insights as a scannable list of action items that open
 * a detail page. Layout follows Foo Medical's patient-portal home and care-plan
 * patterns.
 */
export default function HomeScreen() {
  const c = usePalette();
  const { t, lang } = useT();
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(async () => {
    const [report, notes, own, links, me, push, referrals, documents, myBookings, caring] = await Promise.all([
      api.insights(lang), api.notifications(), api.profile(false), api.links(), api.me(), api.pushStatus(),
      api.referrals(), api.documents(), api.bookings(), api.care()]);
    const rels = new Set(own.family.map((m) => m.relationship));
    const steps: { title: string; detail: string; done: boolean; href: Href }[] = [
      { title: N('Add your family’s health history'), detail: N('Start with what you know. A sentence or two is fine.'),
        done: own.family.length > 0, href: '/add-history' },
      { title: N('Add a lab report or prescription'), detail: N('Snap a photo. Real results make insights sharper.'),
        done: documents.some((d) => d.status === 'saved'), href: '/add-history' },
      { title: N('Add both parents'), detail: N('Parents’ diagnoses, and their ages, matter most.'),
        done: rels.has('mother') && rels.has('father'), href: '/add-history' },
      { title: N('Add your grandparents'), detail: N('Patterns on one side of the family change screening advice.'),
        done: [...rels].some((r) => GRANDPARENT.test(r)), href: '/add-history' },
      { title: N('Check your diabetes risk'), detail: N('Two quick questions for the Indian Diabetes Risk Score.'),
        done: !!own.activity && (own.observations ?? []).some((o) => o.code === 'waist_circumference'), href: '/settings' },
      { title: N('Add your date of birth and sex'), detail: N('So age- and sex-specific guidance applies.'),
        done: !!own.birth_date && !!own.sex, href: '/settings' },
      { title: N('Invite a relative'), detail: N('Their own history makes both of your insights more accurate.'),
        done: links.length > 0, href: '/invite' },
      { title: N('Protect your account'), detail: N('Add your email so you can sign in on another phone.'),
        done: me.secured, href: { pathname: '/sign-in', params: { mode: 'link' } } },
    ];
    if (pushSupport().ok) {
      steps.push({ title: N('Turn on family alerts'), detail: N('Hear when a relative shares something that affects you.'),
                   done: push.registered, href: '/settings' });
    }
    const pending = documents.filter((d) => d.status === 'review');
    const testCount = new Set((own.observations ?? []).map((o) => o.code)).size;
    const activeBookings = myBookings.filter((b) => ['requested', 'scheduled', 'sample_collected'].includes(b.status));
    return { report, notes: notes.filter((n) => !n.read), steps, referrals, pending, testCount, activeBookings,
             caring: caring.filter((p) => p.today.length > 0 || p.refills_due > 0 || p.role === 'caregiver') };
  });
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { report, notes, steps, referrals, pending, testCount, activeBookings, caring } = data;
  const done = steps.filter((s) => s.done).length;
  const todo = steps.filter((s) => !s.done);
  const urgent = report.insights.filter((i) => i.level === 'high').length;

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <View style={{ paddingVertical: 4 }}>
        <Text accessibilityRole="header" style={{ fontSize: 26, fontWeight: '700', color: c.text }}>{greeting(t)}</Text>
        <Body muted style={{ marginTop: 4 }}>
          {report.insights.length === 0
            ? t('Add some family history to see what’s worth discussing with your clinician.')
            : urgent > 0
              ? t(urgent === 1 ? '1 item is worth discussing with a clinician soon.' : '{n} items are worth discussing with a clinician soon.', { n: urgent })
              : t(report.insights.length === 1 ? 'You have 1 item to review.' : 'You have {n} items to review.', { n: report.insights.length })}
        </Body>
      </View>

      <ErrorText>{error}</ErrorText>

      {notes.map((n) => (
        <Banner key={n.id} tone={n.kind === 'family_cascade' ? 'high' : 'info'}>{n.message}</Banner>
      ))}
      {notes.length > 0 && (
        <View style={{ alignSelf: 'flex-start' }}>
          <Button title={t('Dismiss')} onPress={async () => { await api.markNotificationsRead(); reload(); }} />
        </View>
      )}

      <SurveyCard />

      {pending.length > 0 && (
        <Section title={t('Waiting for your review')} right={<Text style={{ color: c.muted }}>{pending.length}</Text>}>
          {pending.map((d, i) => (
            <Row key={d.id} title={t(DOC_TYPE_LABEL[d.doc_type])}
                 detail={[formatDay(d.doc_date), d.source && VIA_LABEL[d.source] ? t(VIA_LABEL[d.source]) : ''].filter(Boolean).join(' · ')}
                 onPress={() => router.push({ pathname: '/document/[id]', params: { id: d.id } })}
                 last={i === pending.length - 1} />
          ))}
        </Section>
      )}

      {caring.length > 0 && (
        <Section title={t('Caring for')}>
          {caring.map((p, i) => {
            const open = p.today.filter((d) => d.status === 'due' || d.status === 'missed').length;
            const taken = p.today.filter((d) => d.status === 'taken').length;
            return (
              <Row key={p.care_id} title={p.has_name ? p.name : capitalize(t(label(p.relationship_code)))}
                   detail={[p.today.length ? t('{taken} of {total} doses taken today', { taken, total: p.today.length }) : null,
                            open ? t('{n} to mark', { n: open }) : null,
                            p.refills_due ? t('{n} to reorder', { n: p.refills_due }) : null].filter(Boolean).join(' · ') || t('Medicines and emergency details')}
                   onPress={() => router.push({ pathname: '/care', params: { id: p.care_id } })}
                   last={i === caring.length - 1} />
            );
          })}
        </Section>
      )}

      {activeBookings.length > 0 && (
        <Section title={t('Your tests')}>
          {activeBookings.map((b, i) => (
            <Row key={b.id} title={`${b.test_names.join(', ')} · ${b.partner_name}`}
                 detail={[t(BOOKING_LABEL[b.status]), b.scheduled_for ? formatDay(b.scheduled_for) : null].filter(Boolean).join(' · ')}
                 onPress={b.rule_id ? () => router.push({ pathname: '/insight/[id]', params: { id: b.rule_id as string } }) : undefined}
                 last={i === activeBookings.length - 1} />
          ))}
        </Section>
      )}

      {testCount > 0 && (
        <Section title={t('Your results')}>
          <Row title={t('Results over time')} detail={t(testCount > 1 ? '{n} tests, with healthy ranges' : '1 test, with healthy ranges', { n: testCount })}
               onPress={() => router.push('/results')} last />
        </Section>
      )}

      {todo.length > 0 && (
        <Section title={t('Next steps')} right={<Text style={{ color: c.muted }}>{t('{done} of {total} done', { done, total: steps.length })}</Text>}>
          <View style={{ paddingHorizontal: 16, paddingBottom: 4 }}>
            <Progress value={done} total={steps.length} />
          </View>
          {/* Show the next three to keep it light; finished steps drop off. */}
          {todo.slice(0, 3).map((step, i, arr) => (
            <Row key={step.title} title={t(step.title)} detail={t(step.detail)} leading={<Check done={false} />}
                 onPress={() => router.push(step.href)} last={i === arr.length - 1} />
          ))}
        </Section>
      )}

      {report.insights.length > 0 && (
        <Section title={t('Your action items')}>
          {report.insights.map((insight, i) => {
            const tone = c.level[insight.level];
            return (
              <Row
                key={insight.rule_id}
                title={t(insight.title)}
                detail={(() => {
                  const r = referrals.find((x) => x.rule_id === insight.rule_id);
                  return r ? `${r.org_name}: ${t(REFERRAL_LABEL[r.status] ?? r.status)}` : insight.evidence[0] ?? insight.summary;
                })()}
                eyebrow={<Badge label={t(LEVEL_LABEL[insight.level])} fg={tone.fg} bg={tone.bg} />}
                onPress={() => router.push({ pathname: '/insight/[id]', params: { id: insight.rule_id } })}
                last={i === report.insights.length - 1}
              />
            );
          })}
        </Section>
      )}

      {report.insights.length > 0 && (
        <Card>
          <H2>{t('Share with your doctor')}</H2>
          <Body muted>
            {t('A one-page summary written for clinicians: the items to discuss with the guidelines behind them, a family pedigree, and your history. It’s made into a PDF on your phone for you to send or print.')}
          </Body>
          <View style={styles.row}>
            <Button title={t('Create PDF summary')} variant="primary" busy={pdfBusy} onPress={async () => {
              setPdfBusy(true); setPdfError(null);
              try { await shareDoctorSummary(api); }
              catch (e) { setPdfError(e instanceof Error ? e.message : String(e)); }
              finally { setPdfBusy(false); }
            }} />
            {!summary && (
              <Button title={t('Plain-language version')} busy={summaryBusy} onPress={async () => {
                setSummaryBusy(true);
                try { setSummary((await api.summary()).text); } finally { setSummaryBusy(false); }
              }} />
            )}
          </View>
          <ErrorText>{pdfError}</ErrorText>
          {summary && <Body style={{ marginTop: 10 }}>{summary}</Body>}
        </Card>
      )}

      <Body muted style={{ fontSize: 12 }}>{report.disclaimer}</Body>
    </Screen>
  );
}
