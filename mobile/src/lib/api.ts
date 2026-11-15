import type {
  AcceptResult,
  AppNotification,
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

/** API bound to the signed-in user's token. */
export function createApi(token: string | null) {
  const authed = <T,>(path: string, opts: Omit<Options, 'token'> = {}) => request<T>(path, { ...opts, token });
  return {
    profile: (includeLinked = true) =>
      authed<Profile>(`/v1/profile${includeLinked ? '?include_linked=true' : ''}`),
    setDemographics: (body: { sex?: Sex; birth_date?: string }) =>
      authed<Profile>('/v1/profile/demographics', { method: 'PUT', body }),
    insights: () => authed<InsightReport>('/v1/insights'),
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
    exportFhir: () => authed<Record<string, unknown>>('/v1/export/fhir'),
    deleteAccount: () => authed<void>('/v1/me', { method: 'DELETE' }),
  };
}

export type Api = ReturnType<typeof createApi>;

// Endpoints that work without an account.
export const publicApi = {
  createAccount: () => request<{ user_id: string; token: string }>('/v1/users', { method: 'POST' }),
  previewInvite: (inviteToken: string) => request<InvitePreview>(`/v1/invites/${encodeURIComponent(inviteToken)}`),
  declineInvite: (inviteToken: string) =>
    request<void>(`/v1/invites/${encodeURIComponent(inviteToken)}/decline`, { method: 'POST' }),
  sampleRecord: () => request<unknown>('/sample/fhir'),
};

/**
 * Pull the invite token out of anything a user might paste or open:
 * https://host/invite/TOKEN, familyhealth://invite/TOKEN, or the bare token.
 */
export function parseInviteToken(input: string): string | null {
  const text = input.trim();
  const match = text.match(/invite\/([A-Za-z0-9_-]{20,})/);
  if (match) return match[1];
  return /^[A-Za-z0-9_-]{20,}$/.test(text) ? text : null;
}
