// src/lib/ui.ts — Clean minimal design system

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

export const motionPreset = {
  page: {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.2, ease: 'easeOut' },
  },
} as const;

export const ui = {
  appShell: 'min-h-screen space-y-5 bg-gray-50 px-4 py-6 text-gray-900 sm:px-6 lg:px-8',

  panel: 'rounded-xl border border-gray-200 bg-white p-5',

  stickyPanel:
    'rounded-xl border border-gray-200 bg-white p-5 xl:sticky xl:top-5 xl:self-start',

  panelHeader: 'flex flex-col justify-between gap-3 sm:flex-row sm:items-center',

  panelTitle: 'flex items-center gap-2 text-sm font-semibold text-gray-900',

  muted: 'text-xs text-gray-500',

  errorText: 'text-sm font-medium text-red-600',

  eyebrow:
    'inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-blue-700',

  inventoryLayout: 'grid grid-cols-1 gap-5 xl:grid-cols-[260px_minmax(0,1fr)_340px]',

  graphLayout: 'grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_340px]',

  twoColumnLayout: 'grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)]',

  siteCard: 'rounded-lg border border-gray-200 bg-gray-50 p-4',

  cardButton:
    'flex w-full items-center justify-between gap-3 rounded-lg border p-3 text-left transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1',

  cardButtonIdle: 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50',

  cardButtonActive: 'border-blue-500 bg-blue-50 text-blue-700',

  primaryButton:
    'inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50',

  ghostButton:
    'inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50',

  pillButton:
    'inline-flex items-center justify-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:border-gray-300 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500',

  selectedPill: 'border-blue-600 bg-blue-600 text-white hover:bg-blue-700',

  input:
    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-offset-1',

  select:
    'rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm font-medium text-gray-700 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-offset-1',

  badgeGood:
    'inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200',

  badgeWarn:
    'inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200',

  badgeError:
    'inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700 ring-1 ring-red-200',

  dl: 'grid grid-cols-[120px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm text-gray-700 [&_dt]:font-medium [&_dt]:text-gray-500 [&_dd]:min-w-0 [&_dd]:break-words [&_dd]:text-gray-900',

  emptyText: 'rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500',
};
