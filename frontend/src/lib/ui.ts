export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

export const motionPreset = {
  page: {
    initial: { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.22 },
  },
  panel: {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.22 },
  },
  side: {
    initial: { opacity: 0, x: 14 },
    animate: { opacity: 1, x: 0 },
    transition: { duration: 0.22 },
  },
};

export const ui = {
  appShell: 'relative mx-auto flex w-full max-w-[1580px] flex-col gap-6 px-4 py-5 text-slate-950 sm:px-6 lg:px-8',
  pageSection: 'grid gap-5',
  inventoryLayout: 'grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)_440px]',
  graphLayout: 'grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]',
  twoColumnLayout: 'grid gap-5 lg:grid-cols-[1.2fr_.8fr]',

  panel: 'rounded-3xl border border-slate-200/80 bg-white p-5 shadow-[0_18px_60px_rgba(15,23,42,0.08)] ring-1 ring-white/70',
  panelSoft: 'rounded-3xl border border-slate-200 bg-slate-50/80 p-4',
  stickyPanel: 'sticky top-6 h-fit rounded-3xl border border-slate-200/80 bg-white p-5 shadow-[0_18px_60px_rgba(15,23,42,0.08)] ring-1 ring-white/70',
  panelHeader: 'flex flex-col gap-3 md:flex-row md:items-start md:justify-between',
  panelTitle: 'flex min-w-0 items-center gap-2 text-base font-black tracking-tight text-slate-950',
  eyebrow: 'inline-flex w-fit items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-4 py-2 text-xs font-black uppercase tracking-[0.18em] text-blue-700',
  muted: 'text-sm leading-6 text-slate-500',
  emptyText: 'rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm font-semibold text-slate-500',
  errorText: 'text-sm font-bold text-rose-600',

  primaryButton: 'inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-black text-white shadow-[0_16px_35px_rgba(37,99,235,0.22)] transition hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-100 active:scale-[0.99]',
  ghostButton: 'inline-flex items-center justify-center gap-2 rounded-2xl border border-blue-200 bg-white px-4 py-3 text-sm font-black text-blue-700 transition hover:border-blue-400 hover:bg-blue-50 focus:outline-none focus:ring-4 focus:ring-blue-100 active:scale-[0.99]',
  subtleButton: 'inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-black text-slate-700 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-100 active:scale-[0.99]',
  pillButton: 'inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-black uppercase tracking-wide text-slate-600 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-100 active:scale-[0.99]',
  selectedPill: 'border-blue-600 bg-blue-600 text-white shadow-[0_14px_30px_rgba(37,99,235,0.22)] hover:bg-blue-700 hover:text-white',
  iconButton: 'grid h-8 w-8 place-items-center rounded-full border border-blue-100 bg-blue-50 text-blue-700 transition hover:border-blue-300 hover:bg-blue-100 focus:outline-none focus:ring-4 focus:ring-blue-100',

  input: 'w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-4 focus:ring-blue-100',
  searchBox: 'grid gap-3 rounded-3xl border border-slate-200 bg-slate-50 p-3 md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-center',
  select: 'min-w-[220px] rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100',

  badgeGood: 'inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-black uppercase text-emerald-700',
  badgeWarn: 'inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-black uppercase text-amber-700',
  badgeError: 'inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-black uppercase text-rose-700',
  countBadge: 'rounded-full bg-slate-100 px-4 py-2 text-xs font-black uppercase text-slate-600',

  dl: 'grid grid-cols-[120px_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm text-slate-700 sm:grid-cols-[140px_minmax(0,1fr)] [&_dt]:font-bold [&_dt]:text-slate-500 [&_dd]:min-w-0 [&_dd]:break-words [&_dd]:font-semibold [&_dd]:text-slate-900',
  mono: 'min-w-0 break-all rounded-xl bg-slate-100 px-3 py-2 font-mono text-xs font-bold text-slate-700',

  cardButton: 'grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-2xl border p-4 text-left transition focus:outline-none focus:ring-4 focus:ring-blue-100',
  cardButtonIdle: 'border-slate-200 bg-white hover:border-blue-200 hover:bg-blue-50',
  cardButtonActive: 'border-blue-500 bg-blue-50 shadow-[0_12px_32px_rgba(37,99,235,0.14)]',
  siteCard: 'rounded-3xl border border-slate-200 bg-slate-50/80 p-4 shadow-sm',

  graphCanvasBase: 'relative overflow-hidden bg-gradient-to-b from-white to-slate-50',
  graphCanvasInline: 'min-h-[560px] rounded-[28px] border border-blue-100 shadow-inner',
  graphCanvasExpanded: '!fixed !inset-0 !z-[1000] !m-0 !h-screen !w-screen min-h-0 rounded-none border-0 bg-white shadow-2xl',
  graphToolbar: 'absolute right-4 top-4 z-10 flex max-w-[calc(100%-2rem)] flex-wrap gap-2 rounded-2xl border border-white/80 bg-white/90 p-2 shadow-[0_14px_40px_rgba(15,23,42,0.12)] backdrop-blur',
  graphSvg: 'w-full cursor-grab touch-none select-none active:cursor-grabbing',
  graphPopover: 'absolute z-20 w-[min(360px,calc(100%-32px))] rounded-3xl border border-blue-200 bg-white/95 p-4 text-slate-900 shadow-2xl ring-1 ring-white/80 backdrop-blur',
};
