import { useState } from 'react';
import { Platform, Pressable, Share, Text, View } from 'react-native';

import { Row, Section } from '../components/list';
import { Banner, Body, Button, Card, Chips, ErrorText, Field, H2, Loading, Screen, styles } from '../components/ui';
import { formatDay } from '../lib/format';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import { useLoader } from '../lib/useLoader';
import { LANGS, useT, type Lang } from '../lib/i18n';

const READ_IN: Record<Lang, string> = { en: 'Read in English', hi: 'हिंदी में पढ़ें', mr: 'मराठीत वाचा' };

const CATEGORIES = ['access', 'correction', 'erasure', 'consent', 'sharing', 'security', 'other'] as const;
type Category = (typeof CATEGORIES)[number];

/** Your rights under India's data protection law: notice, what we hold, who has it, nominee, concerns, download. */
export default function PrivacyScreen() {
  const { t } = useT();
  const { api } = useSession();
  const c = usePalette();
  const { lang: appLang } = useT();
  const [lang, setLang] = useState<Lang>(appLang);
  const { data, error, refreshing, reload } = useLoader(async () => {
    const [summary, ...notices] = await Promise.all([api.privacy(), ...LANGS.map((l) => api.privacyNotice(l.code))]);
    return { summary, notices: Object.fromEntries(LANGS.map((l, i) => [l.code, notices[i]])) as Record<Lang, (typeof notices)[number]> };
  });
  const [showNotice, setShowNotice] = useState(false);
  const [nominee, setNominee] = useState<{ name: string; relationship: string; phone: string } | null>(null);
  const [concern, setConcern] = useState<{ category: Category; message: string } | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setActionError(null);
    try { await fn(); } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); }
  };

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const { summary: s } = data;
  const notice = data.notices[lang];

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      {note && <Banner>{note}</Banner>}
      <ErrorText>{actionError}</ErrorText>
      {s.minor && (
        <Banner tone="high">
          {t('Because you’re under 18, sharing with apps, labs, research and AI features stay off until a parent gives verified consent.')}
        </Banner>
      )}

      <Card>
        <H2>{notice.title}</H2>
        <Body>{notice.summary}</Body>
        <View style={styles.row}>
          <Button title={t(showNotice ? 'Hide the full notice' : 'Read the full notice')} onPress={() => setShowNotice(!showNotice)} />
          {LANGS.filter((l) => l.code !== lang).map((l) => (
            <Button key={l.code} title={READ_IN[l.code]} onPress={() => { setLang(l.code); setShowNotice(true); }} />
          ))}
        </View>
        {showNotice && notice.sections.map((sec) => (
          <View key={sec.heading} style={{ marginTop: 14, gap: 4 }}>
            <Text style={{ color: c.text, fontWeight: '700', fontSize: 15 }}>{sec.heading}</Text>
            {sec.items.map((it) => (
              <Body key={it.title} style={{ fontSize: 14 }}>
                • {it.title}{it.detail ? <Text style={{ color: c.muted }}>: {it.detail}</Text> : null}
              </Body>
            ))}
          </View>
        ))}
      </Card>

      <Section title={t('What we hold')}>
        {s.held.map((h, i) => <Row key={h.category} title={h.category} detail={h.detail} last={i === s.held.length - 1} />)}
      </Section>

      <Section title={t('Who has it')}>
        {s.shared_with.length === 0 && <View style={{ padding: 16 }}><Body muted>{t('No one. Nothing has been shared.')}</Body></View>}
        {s.shared_with.map((x, i) => (
          <Row key={`${x.with}-${i}`} title={x.with}
               detail={`${x.what} · since ${formatDay(x.since)}${x.until ? ` · until ${formatDay(x.until)}` : ''}`}
               last={i === s.shared_with.length - 1} />
        ))}
      </Section>
      <Body muted style={{ fontSize: 12, marginTop: -6 }}>
        {t('Change any of these from Settings (apps, clinics, linked relatives) or the item itself.')}
      </Body>

      <Section title={t('Your nominee')}>
        {nominee ? (
          <View style={{ padding: 16, gap: 10 }}>
            <Body muted>{t('Someone who can use these rights for you if you die or can’t.')}</Body>
            <Field label={t('Name')} value={nominee.name} onChangeText={(v) => setNominee({ ...nominee, name: v })} />
            <Field label={t('Relationship')} value={nominee.relationship} placeholder={t('brother')}
                   onChangeText={(v) => setNominee({ ...nominee, relationship: v })} />
            <Field label={t('Phone')} value={nominee.phone} keyboardType="phone-pad" onChangeText={(v) => setNominee({ ...nominee, phone: v })} />
            <Button title={t('Save nominee')} variant="primary" disabled={!nominee.name.trim() || !nominee.relationship.trim()}
                    onPress={() => run(async () => {
                      await api.setNominee({ name: nominee.name.trim(), relationship: nominee.relationship.trim(),
                                             phone: nominee.phone.trim() || null, email: null });
                      setNominee(null); reload();
                    })} />
          </View>
        ) : s.nominee ? (
          <>
            <Row title={`${s.nominee.name} (${s.nominee.relationship})`} detail={s.nominee.phone ?? undefined}
                 onPress={() => setNominee({ name: s.nominee!.name, relationship: s.nominee!.relationship, phone: s.nominee!.phone ?? '' })} />
            <Row title={t('Remove nominee')} onPress={() => run(async () => { await api.removeNominee(); reload(); })} last />
          </>
        ) : (
          <Row title={t('Add a nominee')} detail={t('Someone who can use these rights for you if you die or can\'t')}
               onPress={() => setNominee({ name: '', relationship: '', phone: '' })} last />
        )}
      </Section>

      <Section title={t('Concerns')}>
        {s.grievances.map((g) => (
          <Row key={g.id} title={`${g.category}: ${g.status === 'open' ? `answer due by ${formatDay(g.due_at)}` : 'answered'}`}
               detail={g.response ?? g.message} />
        ))}
        {concern ? (
          <View style={{ padding: 16, gap: 10 }}>
            <Chips label={t('About')} options={CATEGORIES} value={concern.category}
                   onChange={(v) => setConcern({ ...concern, category: v })} />
            <Field label={t('What\'s the concern?')} value={concern.message} multiline
                   onChangeText={(v) => setConcern({ ...concern, message: v })} />
            <Button title={t('Send')} variant="primary" disabled={concern.message.trim().length < 5}
                    onPress={() => run(async () => {
                      const r = await api.raiseGrievance(concern.category, concern.message.trim());
                      setConcern(null); setNote(r.message); reload();
                    })} />
          </View>
        ) : (
          <Row title={t('Raise a concern')} detail={`Answered within ${s.contact.response_days} days${s.contact.email ? ` · ${s.contact.email}` : ''}`}
               onPress={() => setConcern({ category: 'access', message: '' })} last />
        )}
      </Section>
      <Body muted style={{ fontSize: 12, marginTop: -6 }}>
        {t('If you’re not satisfied with our answer, you can complain to the Data Protection Board of India.')}
      </Body>

      <Card>
        <H2>{t('Download everything')}</H2>
        <Body muted>{t('Your record, documents list, consents, sharing, bookings and the log of who accessed it, as one file.')}</Body>
        <View style={styles.row}>
          <Pressable accessibilityRole="button" onPress={() => run(async () => {
            const json = await api.privacyExport();
            if (Platform.OS === 'web') {
              const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
              const a = document.createElement('a');
              a.href = url; a.download = 'my-family-health-graph-data.json'; a.click(); URL.revokeObjectURL(url);
            } else {
              await Share.share({ title: t('My Family Health Graph data'), message: json });
            }
          })}>
            <Text style={{ color: c.accent, fontSize: 16, fontWeight: '600' }}>{t('Download my data')}</Text>
          </Pressable>
        </View>
      </Card>
    </Screen>
  );
}
