export function isLikelyIp(value: string): boolean {
  const trimmed = value.trim();
  const parts = trimmed.split('.');
  if (parts.length !== 4) return false;
  return parts.every((p) => /^\d{1,3}$/.test(p) && Number(p) <= 255);
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

/**
 * Format ISO timestamp to Baku time (GMT+4), 24h format.
 * Input: "2026-07-07T12:30:00Z" or "2026-07-07T12:30:00.000Z"
 * Output: "2026-07-07 16:30:00"
 */
export function toBakuTime(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString.slice(0, 19);
    // Baku is UTC+4
    const bakuTime = new Date(date.getTime() + (4 * 60 * 60 * 1000));
    const y = bakuTime.getUTCFullYear();
    const m = String(bakuTime.getUTCMonth() + 1).padStart(2, '0');
    const d = String(bakuTime.getUTCDate()).padStart(2, '0');
    const h = String(bakuTime.getUTCHours()).padStart(2, '0');
    const min = String(bakuTime.getUTCMinutes()).padStart(2, '0');
    const s = String(bakuTime.getUTCSeconds()).padStart(2, '0');
    return `${y}-${m}-${d} ${h}:${min}:${s}`;
  } catch {
    return isoString.slice(0, 19);
  }
}
