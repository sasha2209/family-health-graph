// Shapes returned by the Family Health Graph API (see fhg/api.py).

export type Level = 'high' | 'moderate' | 'info';
export type ShareLevel = 'none' | 'conditions' | 'conditions_and_tree';
export type Sex = 'female' | 'male' | 'other' | 'unknown';

export interface Reference {
  title: string;
  url: string;
}

export interface Insight {
  rule_id: string;
  category: string;
  level: Level;
  title: string;
  summary: string;
  evidence: string[];
  recommendation: string;
  references: Reference[];
}

export interface InsightReport {
  generated_at: string;
  insights: Insight[];
  pedigree: Record<string, unknown>;
  disclaimer: string;
}

export interface Condition {
  id: string;
  name: string;
  category: string | null;
  onset_age: number | null;
  age_estimated: boolean;
}

export interface FamilyMember {
  id: string;
  relationship: string;
  name: string | null;
  sex: Sex | null;
  deceased: boolean | null;
  age: number | null;
  conditions: Condition[];
  linked: boolean;
}

export interface Profile {
  user_id: string;
  sex: Sex | null;
  birth_date: string | null;
  conditions: Condition[];
  family: FamilyMember[];
}

export interface FamilyLink {
  link_id: string;
  relationship: string;
  member_id: string | null;
  you_share: ShareLevel;
  they_share: ShareLevel;
  since: string;
}

export interface AppNotification {
  id: number;
  kind: string;
  message: string;
  created_at: string;
  read: boolean;
}

export interface InvitePreview {
  inviter_name: string | null;
  message: string | null;
  you_are_their: string;
  they_are_your: string;
  they_will_share: ShareLevel;
  expires_at: string;
}

export interface CreatedInvite {
  invite_url: string;
  token: string;
  invitation: { id: string; relationship: string; expires_at: string };
}

export interface AcceptResult {
  link_id: string;
  they_are_your: string;
  you_share: ShareLevel;
  token?: string;
}

export interface IngestResult {
  preview: boolean;
  parsed?: Profile;
  merged?: { relatives_added: number; relative_conditions: number; conditions: number };
  warnings: string[];
}

export interface Consent {
  scope: string;
  active: boolean;
}

export interface AuthConfig {
  email: boolean;
  apple: boolean;
  google: boolean;
}

export interface SignInResult {
  user_id: string;
  new_account: boolean;
  token?: string; // present when signing in; absent when linking to the current account
  linked?: boolean;
  email?: string;
}

export interface Identity {
  provider: 'email' | 'apple' | 'google';
  email: string | null;
  created_at: string;
}

export interface Me {
  user_id: string;
  session_id: string;
  secured: boolean;
  identities: Identity[];
}

export interface DeviceSession {
  id: string;
  device: string | null;
  created_at: string;
  last_used_at: string;
  current: boolean;
}

// --- uploaded documents ---------------------------------------------------------------
export type DocType = 'prescription' | 'lab_report' | 'discharge_summary' | 'other';

export interface DocCondition { name: string; category: string | null; onset_age?: number | null; evidence?: string }
export interface DocMedication { name: string; dosage: string | null; evidence?: string }
export interface DocObservation {
  code: string; display?: string; value: number; unit: string; flag?: string | null; evidence?: string;
}
export interface DocRelative { relationship: string; conditions: DocCondition[] }

export interface DocExtraction {
  doc_type: DocType;
  doc_date: string | null;
  facility: string | null;
  doctor: string | null;
  patient: { name: string | null; age: number | null; sex: string | null };
  conditions: DocCondition[];
  medications: DocMedication[];
  observations: DocObservation[];
  family: DocRelative[];
  read_by: 'rules' | 'rules+ai';
}

export interface DocumentSummary {
  id: string;
  status: 'review' | 'saved';
  doc_type: DocType;
  doc_date: string | null;
  subject: string;
  filename: string | null;
  media_type: string;
  method: 'pdf_text' | 'ocr' | 'none';
  ai_model: string | null;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  has_file: boolean;
}

export interface DocumentDetail extends DocumentSummary {
  extraction: DocExtraction;
  text_preview: string;
  ai_used: boolean;
  warnings?: string[];
}

export interface DocumentSaveBody {
  subject: string;
  doc_type: DocType;
  doc_date: string | null;
  relative_age?: number | null;
  conditions: DocCondition[];
  medications: DocMedication[];
  observations: DocObservation[];
  family: DocRelative[];
}
