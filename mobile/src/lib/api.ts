import { Platform } from 'react-native';

import type {
  AcceptResult,
  AppNotification,
  AuthConfig,
  DeviceSession,
  Me,
  SignInResult,
  Consent,
  DocumentDetail,
  DocumentSaveBody,
  DocumentSummary,
  CreatedInvite,
  Activity,
  Booking,
  TestOffer,
  RiskReport,
  Nominee,
  PrivacyNotice,
  PrivacySummary,
  CareDetail,
  CareInfo,
  CareSummary,
  Slot,
  Connection,
  Grant,
  OAuthRequestInfo,
  FamilyLink,
  InboundInfo,
  TrendTest,
  FamilyMemberDetail,
  IngestResult,
  InsightReport,
  InvitePreview,
  Profile,
  ShareLevel,
  Sex,
} from './types';

/**
 * Where the backend runs. Set EXPO_PUBLIC_API_URL when starting Expo, e.g.
 *   EXPO_PUBLIC_API_URL=http://192.168.1.20:8000 npx expo start
 * On a physical phone "localhost" is the phone itself, so use your computer's
 * LAN address (and start the server with FHG_HOST=0.0.0.0).
 */
// An empty value means "same origin", used when the web build is served by the API itself.
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Options = { method?: string; body?: unknown; token?: string | null };

/** GET that returns text (e.g. the HTML clinician summary) instead of JSON. */
async function requestText(path: string, token: string | null): Promise<string> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(0, `Can't reach the server at ${API_URL}. Check your connection.`);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof data?.detail === 'string' ? data.detail : res.statusText || 'Request failed');
  }
  return res.text();
}

async function request<T>(path: string, { method = 'GET', body, token }: Options = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Can't reach the server at ${API_URL}. Check your connection.`);
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : res.statusText || 'Request failed';
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

/** Shown in the "signed-in devices" list so people can recognise a lost phone. */
export const DEVICE_NAME =
  Platform.OS === 'ios' ? 'iPhone' : Platform.OS === 'android' ? 'Android phone' : 'Web browser';

/** API bound to the signed-in user's token. */
export function createApi(token: string | null) {
  const authed = <T,>(path: string, opts: Omit<Options, 'token'> = {}) => request<T>(path, { ...opts, token });
  return {
    profile: (includeLinked = true) =>
      authed<Profile>(`/v1/profile${includeLinked ? '?include_linked=true' : ''}`),
    setLifestyle: (body: { activity?: Activity; waist_cm?: number }) =>
      authed<Profile>('/v1/profile/lifestyle', { method: 'PUT', body }),
    setDemographics: (body: { sex?: Sex; birth_date?: string }) =>
      authed<Profile>('/v1/profile/demographics', { method: 'PUT', body }),
    insights: (lang?: string) => authed<InsightReport>(`/v1/insights${lang ? `?lang=${encodeURIComponent(lang)}` : ''}`),
    clinicianReport: (includeShared = true) =>
      requestText(`/v1/report/clinician?include_shared=${includeShared}`, token),
    summary: () => authed<{ text: string; generated_by: string; disclaimer: string }>('/v1/insights/summary'),
    ingestText: (text: string, preview = false) =>
      authed<IngestResult>(`/v1/ingest/text${preview ? '?preview=true' : ''}`, { method: 'POST', body: { text } }),
    uploadDocument: (dataBase64: string, filename?: string) =>
      authed<DocumentDetail>('/v1/documents', { method: 'POST', body: { data_base64: dataBase64, filename } }),
    documents: () => authed<DocumentSummary[]>('/v1/documents'),
    document: (id: string) => authed<DocumentDetail>(`/v1/documents/${encodeURIComponent(id)}`),
    saveDocument: (id: string, body: DocumentSaveBody) =>
      authed<IngestResult & { document: DocumentDetail }>(`/v1/documents/${encodeURIComponent(id)}/save`,
        { method: 'POST', body }),
    deleteDocument: (id: string) => authed<void>(`/v1/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    ingestFhir: (bundle: unknown) => authed<IngestResult>('/v1/ingest/fhir', { method: 'POST', body: bundle }),
    connections: () => authed<{ connections: Connection[]; available: { id: string; name: string; kind: string }[] }>(
      '/v1/connections'),
    connectSmart: (provider: string, returnTo?: string) =>
      authed<{ authorize_url: string }>('/v1/connect/smart', { method: 'POST', body: { provider, return_to: returnTo } }),
    syncConnection: (id: string) =>
      authed<{ status?: string; message?: string; merged: Record<string, number> | null }>(
        `/v1/connections/${encodeURIComponent(id)}/sync`, { method: 'POST' }),
    connectAbha: (abhaAddress: string) =>
      authed<{ id: string; status: string; message: string }>('/v1/connect/abha', { method: 'POST', body: { abha_address: abhaAddress } }),
    privacy: () => authed<PrivacySummary>('/v1/privacy'),
    privacyNotice: (lang: string) => authed<PrivacyNotice>(`/v1/privacy/notice?lang=${encodeURIComponent(lang)}`),
    privacyExport: () => requestText('/v1/privacy/export', token),
    setNominee: (body: Nominee) => authed<Nominee>('/v1/privacy/nominee', { method: 'PUT', body }),
    removeNominee: () => authed<void>('/v1/privacy/nominee', { method: 'DELETE' }),
    raiseGrievance: (category: string, message: string) =>
      authed<{ id: string; message: string }>('/v1/privacy/grievances', { method: 'POST', body: { category, message } }),
    deleteConnection: (id: string) => authed<void>(`/v1/connections/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    oauthRequest: (q: { client_id: string; redirect_uri: string; scope: string }) =>
      authed<OAuthRequestInfo>(`/v1/oauth/request?${new URLSearchParams(q).toString()}`),
    oauthApprove: (body: { client_id: string; redirect_uri: string; scopes: string[]; state?: string;
                           code_challenge: string; code_challenge_method: string }) =>
      authed<{ redirect_to: string }>('/v1/oauth/approve', { method: 'POST', body }),
    oauthDeny: (body: { client_id: string; redirect_uri: string; state?: string }) =>
      authed<{ redirect_to: string }>('/v1/oauth/deny', { method: 'POST', body }),
    grants: () => authed<Grant[]>('/v1/grants'),
    revokeGrant: (id: string) => authed<void>(`/v1/grants/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    risk: (lang?: string) => authed<RiskReport>(`/v1/risk${lang ? `?lang=${encodeURIComponent(lang)}` : ''}`),
    setLanguage: (lang: string) => authed<{ lang: string }>('/v1/profile/language', { method: 'PUT', body: { lang } }),
    care: () => authed<CareSummary[]>('/v1/care'),
    surveys: () => authed<{ id: string; text: string; options: string[] }[]>('/v1/surveys'),
    answerSurvey: (id: string, answer: string) =>
      authed<void>(`/v1/surveys/${encodeURIComponent(id)}`, { method: 'POST', body: { answer } }),
    careDetail: (id: string) => authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}`),
    careSetInfo: (id: string, body: CareInfo) =>
      authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}/info`, { method: 'PUT', body }),
    careAddMedication: (id: string, body: { name: string; dosage?: string; stock?: number }) =>
      authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}/medications`, { method: 'POST', body }),
    careUpdateMedication: (id: string, medId: string, body: { reminders?: boolean; stock?: number | null;
                                                              schedule?: Partial<Record<Slot, number>>; status?: 'active' | 'stopped' }) =>
      authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}/medications/${encodeURIComponent(medId)}`,
        { method: 'PATCH', body }),
    careMarkDose: (id: string, body: { med_id: string; slot: Slot; status: 'taken' | 'skipped' | null }) =>
      authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}/doses`, { method: 'POST', body }),
    careInvite: (id: string) =>
      authed<{ url: string; message: string; expires_at: string }>(`/v1/care/${encodeURIComponent(id)}/invite`, { method: 'POST' }),
    careJoin: (inviteToken: string, name?: string) =>
      authed<CareDetail>(`/v1/care/join/${encodeURIComponent(inviteToken)}`, { method: 'POST', body: { name } }),
    careRemove: (id: string, caregiverId: string) =>
      authed<void>(`/v1/care/${encodeURIComponent(id)}/caregivers/${encodeURIComponent(caregiverId)}`, { method: 'DELETE' }),
    careSummaryHtml: (id: string) => requestText(`/v1/care/${encodeURIComponent(id)}/summary`, token),
    careEmergencyLink: (id: string, hours: number) =>
      authed<{ id: string; url: string; expires_at: string }>(`/v1/care/${encodeURIComponent(id)}/emergency-links`,
        { method: 'POST', body: { hours } }),
    careWhatsAppOn: (id: string, body: { phone: string; lang: 'en' | 'hi'; agreed: boolean }) =>
      authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}/whatsapp`, { method: 'PUT', body }),
    careWhatsAppOff: (id: string) => authed<CareDetail>(`/v1/care/${encodeURIComponent(id)}/whatsapp`, { method: 'DELETE' }),
    careRevokeLink: (id: string, linkId: string) =>
      authed<void>(`/v1/care/${encodeURIComponent(id)}/emergency-links/${encodeURIComponent(linkId)}`, { method: 'DELETE' }),
    canriskFile: () => requestText('/v1/risk/canrisk', token),
    insightTests: (ruleId: string) =>
      authed<{ tests: TestOffer[]; bookings: Booking[] }>(`/v1/insights/${encodeURIComponent(ruleId)}/tests`),
    book: (body: { partner_id: string; tests: string[]; rule_id?: string; preferred_date?: string; slot?: string;
                   contact: { name: string; phone: string; address?: string; pincode?: string } }) =>
      authed<Booking>('/v1/bookings', { method: 'POST', body }),
    bookings: () => authed<Booking[]>('/v1/bookings'),
    cancelBooking: (id: string) => authed<Booking>(`/v1/bookings/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
    bookingDoneElsewhere: (id: string) =>
      authed<Booking>(`/v1/bookings/${encodeURIComponent(id)}/done-elsewhere`, { method: 'POST' }),
    inbound: () => authed<InboundInfo>('/v1/inbound'),
    rotateInboundEmail: () => authed<InboundInfo>('/v1/inbound/email/rotate', { method: 'POST' }),
    whatsappCode: () => authed<{ code: string; message: string; number: string; expires_in_minutes: number }>(
      '/v1/inbound/whatsapp/code', { method: 'POST' }),
    unlinkWhatsapp: () => authed<void>('/v1/inbound/whatsapp', { method: 'DELETE' }),
    trends: (memberId?: string) =>
      authed<{ tests: TrendTest[] }>(`/v1/trends${memberId ? `?member_id=${encodeURIComponent(memberId)}` : ''}`),
    familyMember: (id: string) => authed<FamilyMemberDetail>(`/v1/family/${encodeURIComponent(id)}`),
    updateFamilyMember: (id: string, body: { name?: string | null; age?: number | null; deceased?: boolean | null }) =>
      authed<FamilyMemberDetail>(`/v1/family/${encodeURIComponent(id)}`, { method: 'PATCH', body }),
    deleteFamilyItem: (id: string, itemId: string) =>
      authed<void>(`/v1/family/${encodeURIComponent(id)}/items/${encodeURIComponent(itemId)}`, { method: 'DELETE' }),
    deleteRelative: (id: string) => authed<void>(`/v1/family/${encodeURIComponent(id)}`, { method: 'DELETE' }),

    createInvite: (body: { relationship: string; inviter_name?: string; message?: string; share_level: ShareLevel }) =>
      authed<CreatedInvite>('/v1/invitations', { method: 'POST', body }),
    acceptInvite: (inviteToken: string, body: { share_level: ShareLevel; relationship?: string }) =>
      authed<AcceptResult>(`/v1/invites/${encodeURIComponent(inviteToken)}/accept`, { method: 'POST', body }),
    links: () => authed<FamilyLink[]>('/v1/links'),
    setSharing: (linkId: string, share_level: ShareLevel) =>
      authed<unknown>(`/v1/links/${encodeURIComponent(linkId)}`, { method: 'PUT', body: { share_level } }),
    unlink: (linkId: string) => authed<void>(`/v1/links/${encodeURIComponent(linkId)}`, { method: 'DELETE' }),

    notifications: () => authed<AppNotification[]>('/v1/notifications'),
    markNotificationsRead: () => authed<void>('/v1/notifications/read', { method: 'POST' }),

    consents: () => authed<{ consents: Consent[] }>('/v1/consents'),
    setConsent: (scope: string, granted: boolean) =>
      authed<unknown>('/v1/consents', { method: 'POST', body: { scope, granted } }),
    // Sign-in. With a token these attach the sign-in method to the current account.
    emailVerify: (email: string, code: string) =>
      authed<SignInResult>('/v1/auth/email/verify', { method: 'POST', body: { email, code, device: DEVICE_NAME } }),
    appleSignIn: (idToken: string, nonce: string) =>
      authed<SignInResult>('/v1/auth/oidc/apple', {
        method: 'POST', body: { id_token: idToken, nonce, device: DEVICE_NAME },
      }),
    me: () => authed<Me>('/v1/auth/me'),
    lookupClinic: (code: string) => authed<{ id: string; name: string }>(`/v1/clinics/lookup/${encodeURIComponent(code.trim())}`),
    connectClinic: (code: string, displayName: string, source: 'code' | 'link' = 'code') =>
      authed<{ id: string; name: string }>('/v1/clinics', {
        method: 'POST', body: { code: code.trim(), display_name: displayName.trim(), source },
      }),
    referrals: () => authed<{ rule_id: string; status: 'referred' | 'scheduled' | 'completed' | 'declined';
      updated_at: string; org_name: string; org_id: string; program: string; partner_name: string | null }[]>('/v1/referrals'),
    clinics: () => authed<{ id: string; name: string; connected_at: string }[]>('/v1/clinics'),
    disconnectClinic: (orgId: string) => authed<void>(`/v1/clinics/${encodeURIComponent(orgId)}`, { method: 'DELETE' }),
    registerPush: (token: string, platform: 'ios' | 'android') =>
      authed<{ registered: boolean }>('/v1/devices/push', { method: 'PUT', body: { token, platform } }),
    pushStatus: () => authed<{ registered: boolean }>('/v1/devices/push'),
    unregisterPush: () => authed<void>('/v1/devices/push', { method: 'DELETE' }),
    sessions: () => authed<DeviceSession[]>('/v1/auth/sessions'),
    revokeSession: (id: string) => authed<void>(`/v1/auth/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    logout: () => authed<void>('/v1/auth/logout', { method: 'POST' }),

    exportFhir: () => authed<Record<string, unknown>>('/v1/export/fhir'),
    deleteAccount: () => authed<void>('/v1/me', { method: 'DELETE' }),
  };
}

export type Api = ReturnType<typeof createApi>;

// Endpoints that work without an account.
export const publicApi = {
  createAccount: () =>
    request<{ user_id: string; token: string }>('/v1/users', { method: 'POST', body: { device: DEVICE_NAME } }),
  authConfig: () => request<AuthConfig>('/v1/auth/config'),
  emailStart: (email: string) =>
    request<{ sent: boolean; expires_in_minutes: number }>('/v1/auth/email/start', { method: 'POST', body: { email } }),
  previewInvite: (inviteToken: string) => request<InvitePreview>(`/v1/invites/${encodeURIComponent(inviteToken)}`),
  declineInvite: (inviteToken: string) =>
    request<void>(`/v1/invites/${encodeURIComponent(inviteToken)}/decline`, { method: 'POST' }),
  clinicByCode: (code: string) => request<{ name: string; code: string }>(`/v1/public/clinics/${encodeURIComponent(code)}`),
  sampleRecord: () => request<unknown>('/sample/fhir'),
};

export { parseInviteToken } from './inviteLink';
