export function parseServerUrl(value: string | undefined): string | null {
  try {
    const url = new URL(value?.trim() ?? '');
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null;
    if (['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) return null;
    return url.toString().replace(/\/+$/, '');
  } catch { return null; }
}
export const serverUrl = parseServerUrl(process.env.EXPO_PUBLIC_SERVER_URL);
