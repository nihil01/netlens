import { cn, ui } from '../lib/ui';

export function StatMap({ stats, title }: { stats: Record<string, number>; title: string }) {
  const entries = Object.entries(stats ?? {}).sort(([, a], [, b]) => b - a);
  if (!entries.length) return null;
  return (
    <div className="mt-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{title}</h3>
      <ul className="mt-2 space-y-1">
        {entries.map(([name, count]) => (
          <li className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm" key={name}>
            <code className="min-w-0 truncate font-mono text-xs text-gray-900">{name}</code>
            <span className="ml-2 shrink-0 font-semibold text-gray-900">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
