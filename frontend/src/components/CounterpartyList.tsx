import type { ActivityCounterparty } from '../api';
import { cn, ui } from '../lib/ui';

export function CounterpartyList({ items, title }: { items: ActivityCounterparty[]; title: string }) {
  if (!items.length) return null;
  return (
    <div className="mt-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{title}</h3>
      <ul className="mt-2 space-y-1">
        {items.map((item) => (
          <li className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm" key={`${item.ip}-${item.port}-${item.count}`}>
            <code className="min-w-0 truncate font-mono text-xs text-gray-900">{item.ip || '—'}</code>
            <span className="ml-2 shrink-0 text-xs text-gray-500">:{item.port ?? '*'}</span>
            <span className="ml-2 shrink-0 font-semibold text-gray-900">{item.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
