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
