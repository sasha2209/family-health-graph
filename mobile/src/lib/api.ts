import { Platform } from 'react-native';

import type {
  AcceptResult,
  AppNotification,
  AuthConfig,
  DeviceSession,
  Me,
  SignInResult,
  Consent,
  CreatedInvite,
  FamilyLink,
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
  if (!res.ok) throw new ApiError(res.status, res.statusText || 'Request failed');
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
    setDemographics: (body: { sex?: Sex; birth_date?: string }) =>
      authed<Profile>('/v1/profile/demographics', { method: 'PUT', body }),
    insights: () => authed<InsightReport>('/v1/insights'),
    clinicianReport: (includeShared = true) =>
      requestText(`/v1/report/clinician?include_shared=${includeShared}`, token),
    summary: () => authed<{ text: string; generated_by: string; disclaimer: string }>('/v1/insights/summary'),
    ingestText: (text: string, preview = false) =>
      authed<IngestResult>(`/v1/ingest/text${preview ? '?preview=true' : ''}`, { method: 'POST', body: { text } }),
    ingestFhir: (bundle: unknown) => authed<IngestResult>('/v1/ingest/fhir', { method: 'POST', body: bundle }),
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
    connectClinic: (code: string, displayName: string) =>
      authed<{ id: string; name: string }>('/v1/clinics', { method: 'POST', body: { code: code.trim(), display_name: displayName.trim() } }),
    referrals: () => authed<{ rule_id: string; status: 'referred' | 'scheduled' | 'completed' | 'declined';
      updated_at: string; org_name: string; org_id: string; program: string }[]>('/v1/referrals'),
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
  sampleRecord: () => request<unknown>('/sample/fhir'),
};

export { parseInviteToken } from './inviteLink';
