export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

export const ui = {
  panel: 'rounded-[28px] border border-slate-200/80 bg-white/90 p-5 shadow-panel backdrop-blur',
  panelTitle: 'flex items-center gap-2 text-base font-black text-slate-900',
  muted: 'text-sm text-slate-500',
  errorText: 'text-sm font-bold text-rose-600',
  primaryButton: 'inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-black text-white shadow-glow transition hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-200',
  ghostButton: 'inline-flex items-center justify-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-black text-blue-700 transition hover:border-blue-500 hover:bg-blue-100 focus:outline-none focus:ring-4 focus:ring-blue-100',
  pillButton: 'inline-flex items-center justify-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-4 py-2 text-xs font-black uppercase text-blue-700 transition hover:border-blue-500 hover:bg-blue-100 focus:outline-none focus:ring-4 focus:ring-blue-100',
  selectedPill: 'border-blue-600 bg-blue-600 text-white shadow-glow hover:bg-blue-700',
  input: 'w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-100',
  badgeGood: 'inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-black uppercase text-emerald-700',
  badgeWarn: 'inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-black uppercase text-amber-700',
  badgeError: 'inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-black uppercase text-rose-700',
  dl: 'grid grid-cols-[130px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm text-slate-700 [&_dt]:font-bold [&_dt]:text-slate-500 [&_dd]:min-w-0 [&_dd]:break-words [&_dd]:font-semibold [&_dd]:text-slate-900',
};
