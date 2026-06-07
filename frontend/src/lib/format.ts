export function isLikelyIp(value: string): boolean {
  return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(value.trim());
}

export function emptyLabel(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

export function statusClass(status: string | null | undefined): string {
  const base = 'inline-flex rounded-full px-3 py-1 text-xs font-black uppercase';
  if (!status) return `${base} bg-slate-100 text-slate-500`;
  const normalized = status.toLowerCase();
  if (['active', 'online', 'ok'].includes(normalized)) return `${base} bg-emerald-50 text-emerald-700`;
  if (['planned', 'staged', 'offline'].includes(normalized)) return `${base} bg-amber-50 text-amber-700`;
  return `${base} bg-slate-100 text-slate-500`;
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
