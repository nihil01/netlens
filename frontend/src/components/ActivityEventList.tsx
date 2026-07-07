import type { UnifiedActivityEvent } from '../api';
import { cn, ui } from '../lib/ui';

function EventField({ label, mono = false, value }: { label: string; mono?: boolean; value: string }) {
  return (
    <div className="min-w-0 rounded-md bg-gray-50 px-2 py-1.5">
      <dt className="text-[10px] font-medium uppercase text-gray-400">{label}</dt>
      <dd className={cn('min-w-0 break-words text-xs text-gray-700', mono && 'break-all font-mono')}>{value}</dd>
    </div>
  );
}

export function ActivityEventList({ events }: { events: UnifiedActivityEvent[] }) {
  if (!events.length) return null;
  return (
    <div className="mt-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">OpenSearch hadisələri</h3>
      <div className="mt-2 max-h-[400px] space-y-2 overflow-auto pr-1">
        {events.map((event, index) => (
          <article className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-sm" key={`${event.index}-${event.timestamp}-${event.source_ip}-${event.destination_ip}-${index}`}>
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px] font-medium text-gray-400">
              <span className="rounded bg-white px-1.5 py-0.5 ring-1 ring-gray-200">{event.source_name}</span>
              <span className="rounded bg-white px-1.5 py-0.5 ring-1 ring-gray-200">{event.index}</span>
              <span>{event.timestamp ?? '—'}</span>
            </div>
            <dl className="grid gap-1.5 sm:grid-cols-2">
              <EventField label="src" value={`${event.source_ip ?? '—'}:${event.source_port ?? '*'}`} mono />
              <EventField label="dst" value={`${event.destination_ip ?? '—'}:${event.destination_port ?? '*'}`} mono />
              <EventField label="action" value={event.action ?? '—'} />
              <EventField label="protocol" value={event.protocol ?? '—'} />
              <EventField label="app" value={event.application ?? '—'} />
              <EventField label="user" value={event.user ?? '—'} />
              <EventField label="rule" value={event.rule ?? '—'} />
              <EventField label="policy" value={event.policy ?? '—'} />
              <EventField label="domain" value={event.domain ?? '—'} />
              <EventField label="url" value={event.url ?? '—'} />
              <EventField label="bytes/pkts" value={`${event.bytes ?? '—'} / ${event.packets ?? '—'}`} />
              <EventField label="dir" value={event.direction ?? '—'} />
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
