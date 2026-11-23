import type { ShareLevel } from './types';

export const label = (relationship: string): string => relationship.replace(/_/g, ' ');
export const capitalize = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

export const SHARE_OPTIONS: { value: ShareLevel; label: string; description: string }[] = [
  { value: 'conditions', label: 'My conditions', description: 'Your own diagnoses and ages at diagnosis' },
  { value: 'conditions_and_tree', label: 'Conditions + family tree', description: 'Also the family history you record' },
  { value: 'none', label: 'Nothing for now', description: 'Stay linked without sharing' },
];

export const SHARE_SHORT: Record<ShareLevel, string> = {
  none: 'Nothing',
  conditions: 'Conditions',
  conditions_and_tree: 'Conditions + family tree',
};

export const INVITE_RELATIONSHIPS = [
  'mother', 'father', 'sister', 'brother', 'daughter', 'son',
  'maternal_grandmother', 'maternal_grandfather', 'paternal_grandmother', 'paternal_grandfather',
  'maternal_aunt', 'maternal_uncle', 'paternal_aunt', 'paternal_uncle', 'cousin',
];

export const ALL_RELATIONSHIPS = [
  'mother', 'father', 'parent', 'sister', 'brother', 'sibling', 'daughter', 'son', 'child',
  'maternal_grandmother', 'maternal_grandfather', 'paternal_grandmother', 'paternal_grandfather',
  'grandmother', 'grandfather', 'granddaughter', 'grandson', 'grandchild',
  'maternal_aunt', 'maternal_uncle', 'paternal_aunt', 'paternal_uncle', 'aunt', 'uncle',
  'niece', 'nephew', 'half_sister', 'half_brother', 'cousin', 'other',
];

export function sideOf(relationship: string): string {
  if (relationship.startsWith('maternal')) return 'Maternal';
  if (relationship.startsWith('paternal')) return 'Paternal';
  if (['mother', 'father', 'parent', 'sister', 'brother', 'sibling', 'son', 'daughter', 'child'].includes(relationship)) {
    return 'Immediate';
  }
  return 'Extended';
}

export const REFERRAL_LABEL: Record<string, string> = {
  referred: 'Referred',
  scheduled: 'Appointment scheduled',
  completed: 'Completed',
  declined: 'Not pursuing',
};

export const DOC_TYPE_LABEL: Record<string, string> = {
  prescription: 'Prescription',
  lab_report: 'Lab report',
  discharge_summary: 'Discharge summary',
  other: 'Medical document',
};

/** "2026-03-14" -> "14 Mar 2026" without timezone surprises. */
export function formatDay(iso: string | null): string {
  if (!iso) return 'Date not found';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${d} ${months[m - 1]} ${y}`;
}

/** Where a fact in the record came from, in words people recognise. */
export function sourceLabel(source: string | undefined | null): string | null {
  if (!source) return null;
  if (source.startsWith('document:')) return 'From a document';
  if (source.startsWith('linked:')) return 'Shared by them';
  if (source.startsWith('fhir') || source === 'csv') return 'Imported record';
  return 'Added by you';
}

export const VIA_LABEL: Record<string, string> = { email: 'via email', whatsapp: 'via WhatsApp', upload: '' };

/** "2026-01-15" -> "Jan 2026" */
export function monthYear(iso: string | null): string {
  if (!iso) return 'undated';
  const [y, m] = iso.split('-').map(Number);
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} ${y}`;
}

export const BOOKING_LABEL: Record<string, string> = {
  requested: 'Requested, waiting for the lab to confirm',
  scheduled: 'Confirmed',
  sample_collected: 'Sample collected, results pending',
  completed: 'Done, results in your record',
  cancelled: 'Cancelled',
  completed_elsewhere: 'Done elsewhere',
};

export const rupees = (n: number | null | undefined) => (n == null ? '' : `₹${Math.round(n).toLocaleString('en-IN')}`);
