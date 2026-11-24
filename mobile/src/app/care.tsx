import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, Share, Text, View } from 'react-native';

import { Badge, Row, Section } from '../components/list';
import { Body, Button, Card, Chips, ErrorText, Field, H2, Loading, Screen, styles } from '../components/ui';
import { shareHtmlAsPdf } from '../lib/doctorSummary';
import { capitalize, formatDay, label } from '../lib/format';
import { useSession } from '../lib/session';
import { usePalette } from '../lib/theme';
import type { CareDetail, CareInfo, Dose, Slot } from '../lib/types';
import { useLoader } from '../lib/useLoader';
import { N, useT } from '../lib/i18n';

const SLOT_LABEL: Record<Slot, string> = { morning: N('Morning · 8 am'), afternoon: N('Afternoon · 2 pm'), night: N('Night · 9 pm') };
const STATUS_LABEL: Record<Dose['status'], string> = {
  taken: N('Taken'), skipped: N('Skipped'), missed: N('Not marked'), due: N('Due now'), upcoming: N('Later'),
};
const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'] as const;

function amount(n: number, t: (s: string, v?: Record<string, number>) => string): string {
  return n === 0.5 ? t('½ tablet') : t(n === 1 ? '1 tablet' : '{n} tablets', { n });
}

/** Caregiver mode for one relative: today's medicines, refills, the care circle, and the emergency summary. */
export default function CareScreen() {
  const { t, lang } = useT();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { api } = useSession();
  const c = usePalette();
  const { data, error, refreshing, reload, setData } = useLoader(() => api.careDetail(id));
  const [actionError, setActionError] = useState<string | null>(null);
  const [newMed, setNewMed] = useState({ name: '', dosage: '', stock: '' });
  const [adding, setAdding] = useState(false);
  const [editingInfo, setEditingInfo] = useState(false);
  const [info, setInfo] = useState<CareInfo | null>(null);
  const [allergies, setAllergies] = useState('');
  const [stockFor, setStockFor] = useState<{ id: string; value: string } | null>(null);
  const [shown, setShown] = useState<string | null>(null);

  if (!data) return <Screen>{error ? <ErrorText>{error}</ErrorText> : <Loading />}</Screen>;
  const d: CareDetail = { ...data, name: data.has_name ? data.name : capitalize(t(label(data.relationship_code))) };
  const run = async (fn: () => Promise<CareDetail | void>) => {
    setActionError(null);
    try {
      const out = await fn();
      if (out) setData(out); else reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };
  // No share sheet (some browsers): show the text on screen to copy instead.
  const shareOrShow = async (message: string) => {
    try { await Share.share({ message }); } catch { setShown(message); }
  };
  const slots = (['morning', 'afternoon', 'night'] as Slot[]).filter((s) => d.today.some((x) => x.slot === s));
  const refills = d.medications.filter((m) => m.refill?.due);
  const tone = (s: Dose['status']) =>
    s === 'taken' ? c.level.info : s === 'missed' ? c.level.high : s === 'due' ? c.level.moderate : { fg: c.muted, bg: c.bg };

  return (
    <Screen refreshing={refreshing} onRefresh={reload}>
      <Stack.Screen options={{ title: t('Caring for {name}', { name: d.name }) }} />
      <ErrorText>{actionError}</ErrorText>
      {shown && (
        <Card>
          <Body muted>{t('Copy this and send it:')}</Body>
          <Body selectable>{shown}</Body>
          <View style={styles.row}><Button title={t('Done')} onPress={() => setShown(null)} /></View>
        </Card>
      )}

      <Section title={t('Today')}>
        {slots.length === 0 && (
          <View style={{ padding: 16 }}>
            <Body muted>{t('No medicine reminders yet. Add a medicine below, or turn reminders on for one.')}</Body>
          </View>
        )}
        {slots.map((slot) => (
          <View key={slot}>
            <Text style={{ paddingHorizontal: 16, paddingTop: 12, color: c.muted, fontSize: 13, fontWeight: '600' }}>
              {t(SLOT_LABEL[slot])}
            </Text>
            {d.today.filter((x) => x.slot === slot).map((dose) => (
              <View key={`${dose.med_id}-${slot}`} style={{ paddingHorizontal: 16, paddingVertical: 10, gap: 6 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: c.text, fontSize: 16, fontWeight: '600' }}>{dose.name}</Text>
                    <Body muted style={{ fontSize: 13 }}>
                      {[amount(dose.amount, t), dose.food ? t(dose.food) : null, dose.by ? t('marked by {who}', { who: dose.by === 'you' ? t('you') : dose.by }) : null].filter(Boolean).join(' · ')}
                    </Body>
                  </View>
                  <Badge label={t(STATUS_LABEL[dose.status])} fg={tone(dose.status).fg} bg={tone(dose.status).bg} />
                </View>
                <View style={{ flexDirection: 'row', gap: 16 }}>
                  {dose.status !== 'taken' && (
                    <Pressable accessibilityRole="button" accessibilityLabel={t('Mark {name} {slot} as taken', { name: dose.name, slot: t(slot) })}
                               onPress={() => run(() => api.careMarkDose(id, { med_id: dose.med_id, slot, status: 'taken' }))}>
                      <Text style={{ color: c.accent, fontSize: 15, fontWeight: '600' }}>{t('Taken')}</Text>
                    </Pressable>
                  )}
                  {dose.status !== 'skipped' && dose.status !== 'taken' && (
                    <Pressable accessibilityRole="button"
                               onPress={() => run(() => api.careMarkDose(id, { med_id: dose.med_id, slot, status: 'skipped' }))}>
                      <Text style={{ color: c.muted, fontSize: 15 }}>{t('Skipped')}</Text>
                    </Pressable>
                  )}
                  {(dose.status === 'taken' || dose.status === 'skipped') && (
                    <Pressable accessibilityRole="button"
                               onPress={() => run(() => api.careMarkDose(id, { med_id: dose.med_id, slot, status: null }))}>
                      <Text style={{ color: c.muted, fontSize: 15 }}>{t('Undo')}</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            ))}
          </View>
        ))}
      </Section>

      {d.week.some((w) => w.scheduled > 0) && (
        <Section title={t('Last 7 days')}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: 16 }}>
            {d.week.map((w) => (
              <View key={w.day} style={{ alignItems: 'center', gap: 4 }}>
                <Text style={{ color: c.muted, fontSize: 12 }}>{new Date(w.day).toLocaleDateString(lang === 'hi' ? 'hi-IN' : 'en-IN', { weekday: 'narrow' })}</Text>
                <Text style={{ color: w.scheduled && w.taken === w.scheduled ? c.accent : c.text, fontSize: 13, fontWeight: '600' }}>
                  {w.scheduled ? `${w.taken}/${w.scheduled}` : '–'}
                </Text>
              </View>
            ))}
          </View>
        </Section>
      )}

      {refills.length > 0 && (
        <Section title={t('Reorder soon')}>
          {refills.map((m, i) => (
            <Row key={m.id} title={m.name}
                 detail={m.refill!.days_left === 0 ? t('Runs out today') : t('{n} days left · runs out {date}', { n: m.refill!.days_left, date: formatDay(m.refill!.runs_out_on) })}
                 last={i === refills.length - 1} />
          ))}
        </Section>
      )}

      <Section title={t('Medicines')}>
        {d.medications.map((m) => (
          <View key={m.id} style={{ paddingHorizontal: 16, paddingVertical: 12, gap: 6, opacity: m.status === 'active' ? 1 : 0.5 }}>
            <Text style={{ color: c.text, fontSize: 16, fontWeight: '600' }}>{m.name}</Text>
            <Body muted style={{ fontSize: 13 }}>
              {[m.generic, m.dosage, !m.understood && !m.as_needed ? t("couldn't read the schedule; set it below") : null,
                m.refill ? t('{n} days left', { n: m.refill.days_left }) : null].filter(Boolean).join(' · ')}
            </Body>
            {m.status === 'active' && m.reminders && (
              <View style={{ flexDirection: 'row', gap: 8 }} accessibilityLabel={t('Reminder times')}>
                {(['morning', 'afternoon', 'night'] as Slot[]).map((s) => {
                  const on = !!m.schedule[s];
                  return (
                    <Pressable key={s} accessibilityRole="checkbox" accessibilityState={{ checked: on }}
                               onPress={() => {
                                 const next = { ...m.schedule };
                                 if (on) delete next[s]; else next[s] = 1;
                                 run(() => api.careUpdateMedication(id, m.id, { schedule: next }));
                               }}
                               style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, borderWidth: 1,
                                        borderColor: on ? c.accent : c.border, backgroundColor: on ? c.accent : 'transparent' }}>
                      <Text style={{ color: on ? '#fff' : c.text, fontSize: 13 }}>
                        {t(s)}{on && m.schedule[s] !== 1 ? ` ×${m.schedule[s]}` : ''}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            )}
            <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
              {m.status === 'active' && (
                <Pressable accessibilityRole="button" onPress={() => run(() => api.careUpdateMedication(id, m.id, { reminders: !m.reminders }))}>
                  <Text style={{ color: c.accent, fontSize: 14 }}>{t(m.reminders ? 'Turn off reminders' : 'Turn on reminders')}</Text>
                </Pressable>
              )}
              {m.status === 'active' && (
                <Pressable accessibilityRole="button" onPress={() => setStockFor({ id: m.id, value: m.stock != null ? String(m.stock) : '' })}>
                  <Text style={{ color: c.accent, fontSize: 14 }}>{t('Tablets at home')}</Text>
                </Pressable>
              )}
              <Pressable accessibilityRole="button"
                         onPress={() => run(() => api.careUpdateMedication(id, m.id, { status: m.status === 'active' ? 'stopped' : 'active' }))}>
                <Text style={{ color: c.muted, fontSize: 14 }}>{t(m.status === 'active' ? 'Stopped taking it' : 'Taking it again')}</Text>
              </Pressable>
            </View>
            {stockFor?.id === m.id && (
              <View style={{ gap: 8 }}>
                <Field label={t('Tablets at home today')} keyboardType="numeric" value={stockFor.value}
                       onChangeText={(v) => setStockFor({ id: m.id, value: v })} />
                <Button title={t('Save')} variant="primary" onPress={() => {
                  const n = Number(stockFor.value);
                  setStockFor(null);
                  run(() => api.careUpdateMedication(id, m.id, { stock: Number.isFinite(n) && stockFor.value !== '' ? n : null }));
                }} />
              </View>
            )}
          </View>
        ))}
        {adding ? (
          <View style={{ padding: 16, gap: 10 }}>
            <Field label={t('Medicine (as on the strip or prescription)')} value={newMed.name} placeholder={t('Telma 40')}
                   onChangeText={(v) => setNewMed({ ...newMed, name: v })} />
            <Field label={t('How it\'s taken')} value={newMed.dosage} placeholder={t('1-0-1 after food')}
                   onChangeText={(v) => setNewMed({ ...newMed, dosage: v })} />
            <Field label={t('Tablets at home (optional)')} value={newMed.stock} keyboardType="numeric"
                   onChangeText={(v) => setNewMed({ ...newMed, stock: v })} />
            <Button title={t('Add medicine')} variant="primary" disabled={!newMed.name.trim()} onPress={() => {
              const body = { name: newMed.name.trim(), dosage: newMed.dosage.trim() || undefined,
                             stock: newMed.stock ? Number(newMed.stock) : undefined };
              setAdding(false); setNewMed({ name: '', dosage: '', stock: '' });
              run(() => api.careAddMedication(id, body));
            }} />
          </View>
        ) : (
          <Row title={t('Add a medicine')} onPress={() => setAdding(true)} last />
        )}
      </Section>

      <Section title={t('Emergency details')}>
        {editingInfo && info ? (
          <View style={{ padding: 16, gap: 10 }}>
            <Chips label={t('Blood group')} options={[...BLOOD_GROUPS]} value={(info.blood_group ?? undefined) as (typeof BLOOD_GROUPS)[number]}
                   onChange={(v) => setInfo({ ...info, blood_group: v })} />
            <Field label={t('Allergies (comma-separated)')} value={allergies} onChangeText={setAllergies} placeholder={t('Penicillin, sulfa')} />
            <Field label={t('Emergency contact')} value={info.emergency_contact_name ?? ''}
                   onChangeText={(v) => setInfo({ ...info, emergency_contact_name: v || null })} />
            <Field label={t('Their phone')} value={info.emergency_contact_phone ?? ''} keyboardType="phone-pad"
                   onChangeText={(v) => setInfo({ ...info, emergency_contact_phone: v || null })} />
            <Field label={t('Doctor')} value={info.doctor_name ?? ''} onChangeText={(v) => setInfo({ ...info, doctor_name: v || null })} />
            <Field label={t('Doctor\'s phone')} value={info.doctor_phone ?? ''} keyboardType="phone-pad"
                   onChangeText={(v) => setInfo({ ...info, doctor_phone: v || null })} />
            <Field label={t('Usual hospital')} value={info.hospital ?? ''} onChangeText={(v) => setInfo({ ...info, hospital: v || null })} />
            <Field label={t('Notes for a doctor')} value={info.notes ?? ''} multiline
                   onChangeText={(v) => setInfo({ ...info, notes: v || null })} />
            <Button title={t('Save')} variant="primary" onPress={() => {
              const body = { ...info, allergies: allergies.split(',').map((a) => a.trim()).filter(Boolean) };
              setEditingInfo(false);
              run(() => api.careSetInfo(id, body));
            }} />
          </View>
        ) : (
          <>
            <Row title={t('Blood group: {group}', { group: d.info.blood_group ?? t('not recorded') })}
                 detail={t('Allergies: {list}', { list: d.info.allergies.length ? d.info.allergies.join(', ') : t('none recorded') })} />
            <Row title={t('Edit emergency details')} onPress={() => {
              setInfo(d.info); setAllergies(d.info.allergies.join(', ')); setEditingInfo(true);
            }} />
            <Row title={t('Print or share the emergency summary')} detail={t('One page: allergies, conditions, medicines, who to call')}
                 onPress={() => run(async () => shareHtmlAsPdf(await api.careSummaryHtml(id), t('{name}’s emergency summary', { name: d.name })))} />
            <Row title={t('Send a 24-hour emergency link')} detail={t('Opens without signing in. You\'re told when it\'s opened.')}
                 onPress={() => run(async () => {
                   const link = await api.careEmergencyLink(id, 24);
                   await shareOrShow(t('{name}’s emergency medical summary (valid 24 hours): {url}', { name: d.name, url: link.url }));
                 })} last={d.emergency_links.length === 0} />
            {d.emergency_links.map((l, i) => (
              <Row key={l.id} title={t('Active link · until {when}', { when: new Date(l.expires_at).toLocaleString() })}
                   detail={t(l.views === 1 ? 'Opened 1 time · tap to turn off' : 'Opened {n} times · tap to turn off', { n: l.views })}
                   onPress={() => run(() => api.careRevokeLink(id, l.id))} last={i === d.emergency_links.length - 1} />
            ))}
          </>
        )}
      </Section>

      {d.role === 'owner' ? (
        <Section title={t('Care circle')}>
          {d.caregivers.map((g) => (
            <Row key={g.user_id} title={g.name ?? t('Family member')} detail={t('Joined {date} · tap to remove', { date: formatDay(g.joined_at) })}
                 onPress={() => run(() => api.careRemove(id, g.user_id))} />
          ))}
          <Row title={t('Invite a sibling to help')} detail={t('They see the medicines, mark doses and get reminders too')}
               onPress={() => run(async () => { const inv = await api.careInvite(id); await shareOrShow(t('Help me look after {name} in Family Health Graph: {url}', { name: d.name, url: inv.url })); })} last />
        </Section>
      ) : (
        <Card>
          <H2>{t('You’re helping care for {name}', { name: d.name })}</H2>
          <Body muted>{t('Their record belongs to the family member who added them.')}</Body>
          <View style={styles.row}>
            <Button title={t('Leave the care circle')} onPress={() => run(async () => { await api.careRemove(id, 'me'); router.back(); })} />
          </View>
        </Card>
      )}
    </Screen>
  );
}
