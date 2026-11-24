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
  source?: string;
}

export interface FamilyMember {
  id: string;
  relationship: string;
  name: string | null;
  sex: Sex | null;
  deceased: boolean | null;
  age: number | null;
  conditions: Condition[];
  medications?: Medication[];
  observations?: Observation[];
  linked: boolean;
}

export interface Medication {
  id: string; name: string; dosage: string | null; prescribed_on: string | null; source?: string;
  generic?: string | null; drug_class?: string | null;
}
export interface Observation { id: string; code: string; value: number; unit: string; effective_date: string | null }

export interface FamilyMemberDetail extends FamilyMember {
  degree: number | null;
  side: string | null;
  documents: DocumentSummary[];
}

export interface Profile {
  user_id: string;
  sex: Sex | null;
  birth_date: string | null;
  conditions: Condition[];
  observations?: Observation[];
  family: FamilyMember[];
  activity?: Activity | null;
}

export type Activity = 'exercise_and_active_work' | 'exercise_or_active_work' | 'sedentary';

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
export interface DocMedication {
  name: string; dosage: string | null; evidence?: string; generic?: string | null; drug_class?: string | null;
}
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
  source?: 'upload' | 'email' | 'whatsapp';
  doc_type: DocType;
  doc_date: string | null;
  subject: string;
  subject_member_id: string | null;
  filename: string | null;
  media_type: string;
  method: 'pdf_text' | 'ocr' | 'fhir' | 'none';
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
  member_id?: string | null;
  conditions: DocCondition[];
  medications: DocMedication[];
  observations: DocObservation[];
  family: DocRelative[];
}

// --- forwarding & trends ----------------------------------------------------------------
export interface InboundInfo {
  email: { available: boolean; address: string | null };
  whatsapp: { available: boolean; number: string | null; linked: boolean };
}

export type Tone = 'good' | 'watch' | 'high';
export interface TrendPoint {
  date: string | null; value: number; unit: string; source: 'document' | 'record' | 'typed'; document_id: string | null;
}
export interface TrendTest {
  code: string;
  display: string;
  unit: string;
  points: TrendPoint[];
  latest: TrendPoint;
  change: number | null;
  latest_band: { label: string; tone: Tone } | null;
  bands: { from: number | null; to: number | null; label: string; tone: Tone }[];
  bands_source: string | null;
}

// --- connected record sources ------------------------------------------------------------
export interface Connection {
  id: string;
  kind: 'smart' | 'abdm';
  provider: string;
  display_name: string;
  status: 'active' | 'pending' | 'error' | 'denied' | 'revoked' | 'expired';
  last_sync_at: string | null;
  last_sync_summary: { read?: Record<string, number>; merged?: Record<string, number>; waiting?: string } | null;
}

// --- apps with access (Connect with Family Health Graph) ---------------------------------
export interface ScopeInfo { scope: string; description: string }
export interface OAuthRequestInfo {
  partner: { id: string; name: string; kind: string };
  scopes: ScopeInfo[];
  already_granted: string[];
  expires_in_days: number;
}
export interface Grant {
  id: string;
  partner: { id: string; name: string; kind: string };
  scopes: ScopeInfo[];
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
}

// --- test booking ---------------------------------------------------------------------------
export interface TestOffer {
  test: string; name: string; prep: string; service: boolean;
  offers: { partner_id: string; partner_name: string; price_inr: number | null; home_collection: boolean;
            turnaround_days: number | null }[];
}
export type BookingStatus = 'requested' | 'scheduled' | 'sample_collected' | 'completed' | 'cancelled' | 'completed_elsewhere';
export interface Booking {
  id: string; partner_id: string; partner_name: string; rule_id: string | null; tests: string[]; test_names: string[];
  status: BookingStatus; preferred_date: string | null; slot: string | null; scheduled_for: string | null;
  price_inr: number | null; created_at: string; note: string | null;
}

// --- hereditary-risk models (/v1/risk) ---------------------------------------------------------
export interface CriteriaResult {
  model: string;
  met: boolean;
  criteria: string[];
  evidence: string[];
  not_assessable: string[];
}

export interface RiskAssessment {
  id: string;
  partner_name: string;
  created_at: string;
  model: string;
  predictions: { outcome: string; probability_percent: number; horizon: string; population_percent: number | null }[];
  note: string | null;
}

export interface RiskReport {
  needs?: string;
  pedigree?: { people: number; placeholders: number; not_placed: string[] };
  lynch?: { amsterdam_ii: CriteriaResult; revised_bethesda: CriteriaResult[]; suggests_evaluation: boolean };
  calculators?: { model: string; for: string; how: string; download: string }[];
  assessments: RiskAssessment[];
}

// --- caregiver mode (/v1/care) ----------------------------------------------------------------
export type Slot = 'morning' | 'afternoon' | 'night';
export interface Dose {
  med_id: string; name: string; generic: string | null; slot: Slot; amount: number; food: string | null;
  at: string; status: 'taken' | 'skipped' | 'missed' | 'due' | 'upcoming'; by: string | null;
}
export interface CareMedication {
  id: string; name: string; generic: string | null; drug_class: string | null; dosage: string | null;
  status: 'active' | 'stopped'; reminders: boolean; schedule: Partial<Record<Slot, number>>; as_needed: boolean;
  food: string | null; understood: boolean; course_days: number | null; prescribed_on: string | null;
  stock: number | null; stock_on: string | null;
  refill: { days_left: number; runs_out_on: string; basis: 'stock' | 'course'; due: boolean } | null;
}
export interface CareInfo {
  blood_group: string | null; allergies: string[]; emergency_contact_name: string | null;
  emergency_contact_phone: string | null; doctor_name: string | null; doctor_phone: string | null;
  hospital: string | null; notes: string | null;
}
export interface CareSummary {
  care_id: string; role: 'owner' | 'caregiver'; name: string; relationship: string; relationship_code: string;
  has_name: boolean; today: Dose[]; refills_due: number;
}
export interface CareDetail extends Omit<CareSummary, 'refills_due'> {
  member_id: string;
  week: { day: string; taken: number; scheduled: number }[];
  medications: CareMedication[];
  info: CareInfo;
  caregivers: { user_id: string; name: string | null; joined_at: string }[];
  emergency_links: { id: string; expires_at: string; views: number; created_at: string }[];
}

// --- privacy rights (/v1/privacy) -----------------------------------------------------------------
export interface PrivacyNotice {
  lang: string; available_languages: string[]; title: string; controller: string; summary: string;
  sections: { heading: string; items: { title: string; detail?: string }[] }[];
  contact: { heading: string; name: string | null; email: string | null; response_days: number };
}
export interface Grievance {
  id: string; category: string; message: string; status: 'open' | 'resolved'; response: string | null;
  created_at: string; due_at: string;
}
export interface Nominee { name: string; relationship: string; phone: string | null; email: string | null }
export interface PrivacySummary {
  held: { category: string; count: number; detail: string }[];
  connections: { name: string; status: string }[];
  shared_with: { with: string; what: string; since: string; until?: string }[];
  processors: { name: string; active: boolean }[];
  nominee: Nominee | null;
  grievances: Grievance[];
  minor: boolean;
  contact: { name: string | null; email: string | null; response_days: number };
}
