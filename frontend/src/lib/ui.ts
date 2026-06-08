// src/lib/ui.ts

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

export const motionPreset = {
  page: {
    initial: { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.28, ease: 'easeOut' },
  },
};

export const ui = {
  appShell:
    'min-h-screen space-y-6 bg-[#eef4ff] px-4 py-5 text-slate-900 sm:px-6 lg:px-8',

  panel:
    'rounded-[28px] border border-slate-200/80 bg-white/90 p-5 shadow-[0_18px_55px_rgba(15,23,42,0.08)] backdrop-blur',

  stickyPanel:
    'rounded-[28px] border border-slate-200/80 bg-white/90 p-5 shadow-[0_18px_55px_rgba(15,23,42,0.08)] backdrop-blur xl:sticky xl:top-5 xl:self-start',

  panelHeader:
    'flex flex-col justify-between gap-4 sm:flex-row sm:items-center',

  panelTitle:
    'flex items-center gap-2 text-base font-black text-slate-900',

  muted:
    'text-sm text-slate-500',

  errorText:
    'text-sm font-bold text-rose-600',

  eyebrow:
    'inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-black uppercase tracking-[0.18em] text-blue-700',

  inventoryLayout:
    'grid grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)_360px]',

  graphLayout:
    'grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]',

  twoColumnLayout:
    'grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]',

  siteCard:
    'rounded-3xl border border-slate-200 bg-slate-50/80 p-4 shadow-[0_12px_35px_rgba(15,23,42,0.04)]',

  cardButton:
    'flex w-full items-center justify-between gap-3 rounded-2xl border p-3 text-left transition focus:outline-none focus:ring-4 focus:ring-blue-100',

  cardButtonIdle:
    'border-slate-200 bg-white hover:border-blue-200 hover:bg-blue-50',

  cardButtonActive:
    'border-blue-500 bg-blue-50 text-blue-700 shadow-[0_12px_30px_rgba(37,99,235,0.12)]',

  primaryButton:
    'inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-black text-white shadow-[0_14px_35px_rgba(37,99,235,0.25)] transition hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-200',

  ghostButton:
    'inline-flex items-center justify-center gap-2 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-black text-blue-700 transition hover:border-blue-500 hover:bg-blue-100 focus:outline-none focus:ring-4 focus:ring-blue-100',

  pillButton:
    'inline-flex items-center justify-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-4 py-2 text-xs font-black uppercase text-blue-700 transition hover:border-blue-500 hover:bg-blue-100 focus:outline-none focus:ring-4 focus:ring-blue-100',

  selectedPill:
    'border-blue-600 bg-blue-600 text-white shadow-[0_14px_35px_rgba(37,99,235,0.25)] hover:bg-blue-700',

  input:
    'w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-100',

  select:
    'rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-800 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100',

  badgeGood:
    'inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-black uppercase text-emerald-700',

  badgeWarn:
    'inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-black uppercase text-amber-700',

  badgeError:
    'inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-black uppercase text-rose-700',

  dl:
    'grid grid-cols-[130px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm text-slate-700 [&_dt]:font-bold [&_dt]:text-slate-500 [&_dd]:min-w-0 [&_dd]:break-words [&_dd]:font-semibold [&_dd]:text-slate-900',

  emptyText:
  'rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-500',
};