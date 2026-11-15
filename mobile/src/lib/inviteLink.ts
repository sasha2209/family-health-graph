// No React Native imports here, so this can be unit tested in plain Node.

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
