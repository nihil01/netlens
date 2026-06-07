export function isLikelyIp(value: string): boolean {
  return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(value.trim());
}

export function emptyLabel(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function statusClass(status: string | null | undefined): string {
  if (!status) return 'muted';
  const normalized = status.toLowerCase();
  if (['active', 'online', 'ok'].includes(normalized)) return 'good';
  if (['planned', 'staged', 'offline'].includes(normalized)) return 'warn';
  return 'muted';
}

export function containsValue(value: string | number | boolean | null | undefined, needle: string): boolean {
  return needle.length === 0 || emptyLabel(value).toLowerCase().includes(needle);
}

export function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
