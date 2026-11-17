import { Href, router } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { Badge, Check, Progress, Row, Section } from '../../components/list';
import { Banner, Body, Button, Card, ErrorText, H2, Loading, Screen, styles } from '../../components/ui';
import { shareDoctorSummary } from '../../lib/doctorSummary';
import { REFERRAL_LABEL } from '../../lib/format';
import { pushSupport } from '../../lib/push';
import { useSession } from '../../lib/session';
import { LEVEL_LABEL, usePalette } from '../../lib/theme';
import { useLoader } from '../../lib/useLoader';

const GRANDPARENT = /grand(mother|father)$/;

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

/**
 * Home: a greeting, family alerts, a "next steps" checklist that builds a
 * useful record, and insights as a scannable list of action items that open
 * a detail page. Layout follows Foo Medical's patient-portal home and care-plan
 * patterns.
 */
export default function HomeScreen() {
  const c = usePalette();
  const { api } = useSession();
  const { data, error, refreshing, reload } = useLoader(async () => {
    const [report, notes, own, links, me, push, referrals] = await Promise.all([
      api.insights(), api.notifications(), api.profile(false), api.links(), api.me(), api.pushStatus(),
      api.referrals()]);
    const rels = new Set(own.family.map((m) => m.relationship));
    const steps: { title: string; detail: string; done: boolean; href: Href }[] = [
      { title: 'Add your family’s health history', detail: 'Start with what you know. A sentence or two is fine.',
        done: own.family.length > 0, href: '/add-history' },
      { title: 'Add both parents', detail: 'Parents’ diagnoses, and their ages, matter most.',
        done: rels.has('mother') && rels.has('father'), href: '/add-history' },
      { title: 'Add your grandparents', detail: 'Patterns on one side of the family change screening advice.',
        done: [...rels].some((r) => GRANDPARENT.test(r)), href: '/add-history' },
      { title: 'Add your date of birth and sex', detail: 'So age- and sex-specific guidance applies.',
        done: !!own.birth_date && !!own.sex, href: '/settings' },
      { title: 'Invite a relative', detail: 'Their own history makes both of your insights more accurate.',
        done: links.length > 0, href: '/invite' },
      { title: 'Protect your account', detail: 'Add your email so you can sign in on another phone.',
        done: me.secured, href: { pathname: '/sign-in', params: { mode: 'link' } } },
    ];
    if (pushSupport().ok) {
      steps.push({ title: 'Turn on family alerts', detail: 'Hear when a relative shares something that affects you.',
                   done: push.registered, href: '/settings' });
    }
    return { report, notes: notes.filter((n) => !n.read), steps, referrals };
  });
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { report, notes, steps, referrals } = data;
  const done = steps.filter((s) => s.done).length;
  const todo = steps.filter((s) => !s.done);
  const urgent = report.insights.filter((i) => i.level === 'high').length;

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <View style={{ paddingVertical: 4 }}>
        <Text accessibilityRole="header" style={{ fontSize: 26, fontWeight: '700', color: c.text }}>{greeting()}</Text>
        <Body muted style={{ marginTop: 4 }}>
          {report.insights.length === 0
            ? 'Add some family history to see what’s worth discussing with your clinician.'
            : urgent > 0
              ? `${urgent} ${urgent === 1 ? 'item is' : 'items are'} worth discussing with a clinician soon.`
              : `You have ${report.insights.length} ${report.insights.length === 1 ? 'item' : 'items'} to review.`}
        </Body>
      </View>

      <ErrorText>{error}</ErrorText>

      {notes.map((n) => (
        <Banner key={n.id} tone={n.kind === 'family_cascade' ? 'high' : 'info'}>{n.message}</Banner>
      ))}
      {notes.length > 0 && (
        <View style={{ alignSelf: 'flex-start' }}>
          <Button title="Dismiss" onPress={async () => { await api.markNotificationsRead(); reload(); }} />
        </View>
      )}

      {todo.length > 0 && (
        <Section title="Next steps" right={<Text style={{ color: c.muted }}>{done} of {steps.length} done</Text>}>
          <View style={{ paddingHorizontal: 16, paddingBottom: 4 }}>
            <Progress value={done} total={steps.length} />
          </View>
          {/* Show the next three to keep it light; finished steps drop off. */}
          {todo.slice(0, 3).map((step, i, arr) => (
            <Row key={step.title} title={step.title} detail={step.detail} leading={<Check done={false} />}
                 onPress={() => router.push(step.href)} last={i === arr.length - 1} />
          ))}
        </Section>
      )}

      {report.insights.length > 0 && (
        <Section title="Your action items">
          {report.insights.map((insight, i) => {
            const tone = c.level[insight.level];
            return (
              <Row
                key={insight.rule_id}
                title={insight.title}
                detail={(() => {
                  const r = referrals.find((x) => x.rule_id === insight.rule_id);
                  return r ? `${r.org_name}: ${REFERRAL_LABEL[r.status] ?? r.status}` : insight.evidence[0] ?? insight.summary;
                })()}
                eyebrow={<Badge label={LEVEL_LABEL[insight.level]} fg={tone.fg} bg={tone.bg} />}
                onPress={() => router.push({ pathname: '/insight/[id]', params: { id: insight.rule_id } })}
                last={i === report.insights.length - 1}
              />
            );
          })}
        </Section>
      )}

      {report.insights.length > 0 && (
        <Card>
          <H2>Share with your doctor</H2>
          <Body muted>
            A one-page summary written for clinicians: the items to discuss with the guidelines behind them,
            a family pedigree, and your history. It’s made into a PDF on your phone for you to send or print.
          </Body>
          <View style={styles.row}>
            <Button title="Create PDF summary" variant="primary" busy={pdfBusy} onPress={async () => {
              setPdfBusy(true); setPdfError(null);
              try { await shareDoctorSummary(api); }
              catch (e) { setPdfError(e instanceof Error ? e.message : String(e)); }
              finally { setPdfBusy(false); }
            }} />
            {!summary && (
              <Button title="Plain-language version" busy={summaryBusy} onPress={async () => {
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
