import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { NetBoxInterface } from '../api';
import { emptyLabel } from '../lib/format';
import { cn, ui } from '../lib/ui';

type LearnedMac = NonNullable<NetBoxInterface['learned_mac_addresses']>[number];

export function InterfaceList({
  interfaces,
  showDevice = false,
  showVendor = false,
}: {
  interfaces: NetBoxInterface[];
  showDevice?: boolean;
  showVendor?: boolean;
}) {
  const [openPorts, setOpenPorts] = useState<Record<string, boolean>>({});

  const groupedByDevice = useMemo(() => {
    const map = new Map<string, NetBoxInterface[]>();

    for (const item of interfaces) {
      const deviceName = item.device || 'Unknown device';
      map.set(deviceName, [...(map.get(deviceName) ?? []), item]);
    }

    return Array.from(map.entries()).map(([device, items]) => ({
      device,
      interfaces: items,
      learnedCount: items.reduce((sum, item) => sum + (item.learned_mac_addresses?.length ?? 0), 0),
      activeCount: items.filter((item) => item.enabled).length,
    }));
  }, [interfaces]);

  if (!interfaces.length) return <p className={ui.emptyText}>İnterfeys yoxdur</p>;

  function togglePort(key: string) {
    setOpenPorts((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }

  return (
    <div className="mt-4 space-y-4">
      <h3 className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">
        İnterfeyslər
      </h3>

      {groupedByDevice.map((group) => (
        <section
          key={group.device}
          className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          {showDevice && (
            <div className="mb-4 flex flex-col gap-2 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <b className="block text-base text-slate-950">{group.device}</b>
                <span className="text-sm font-semibold text-slate-500">
                  {group.interfaces.length} port · {group.activeCount} aktiv · {group.learnedCount} learned MAC
                </span>
              </div>
            </div>
          )}

          <div className="space-y-2">
            {group.interfaces.map((item, index) => {
              const learned = item.learned_mac_addresses ?? [];
              const portKey = `${item.device_id}-${item.id ?? item.name}`;
              const isOpen = openPorts[portKey];

              return (
                <motion.div
                  className={cn(
                    'rounded-2xl border p-3 text-sm shadow-sm transition',
                    learned.length
                      ? 'border-blue-200 bg-blue-50/60'
                      : 'border-slate-200 bg-slate-50/80',
                  )}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18, delay: Math.min(index * 0.025, 0.18) }}
                  key={portKey}
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <b className="block break-words text-slate-950">{item.name}</b>
                      <small className="block break-words font-semibold text-slate-500">
                        {emptyLabel(item.type)} · {item.enabled ? 'aktiv' : 'deaktiv'}
                        {item.description ? ` · ${item.description}` : ''}
                      </small>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <span
                        className={cn(
                          'w-fit rounded-full px-3 py-1 text-xs font-black uppercase',
                          item.enabled
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-slate-100 text-slate-400',
                        )}
                      >
                        {item.enabled ? 'aktiv' : 'deaktiv'}
                      </span>

                      <button
                        type="button"
                        onClick={() => togglePort(portKey)}
                        className={cn(
                          'rounded-full px-3 py-1 text-xs font-black uppercase transition',
                          learned.length
                            ? 'bg-blue-600 text-white hover:bg-blue-700'
                            : 'bg-slate-200 text-slate-500',
                        )}
                      >
                        {learned.length} MAC
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    {showDevice && <Info label="Qurğu" value={emptyLabel(item.device)} />}
                    <Info label="Port MAC" value={emptyLabel(item.mac_address)} mono />
                    <Info label="Speed" value={item.speed ? `${item.speed}` : '—'} />
                    <Info label="Duplex" value={emptyLabel(item.duplex)} />
                    <Info label="VLAN" value={emptyLabel(item.untagged_vlan)} />
                    {showVendor && (
                      <Info
                        label="Vendor"
                        value={`${emptyLabel(item.mac_vendor)} · ${emptyLabel(item.mac_oui)}`}
                        wide
                      />
                    )}
                  </div>

                  <AnimatePresence>
                    {isOpen && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                      >
                        <LearnedMacList macs={learned} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function LearnedMacList({ macs }: { macs: LearnedMac[] }) {
  if (!macs.length) {
    return (
      <div className="mt-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-500">
        Bu portda learned MAC yoxdur.
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-2xl border border-blue-100 bg-white p-3">
      <div className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-slate-400">
        Portda görünən MAC addresslər
      </div>

      <div className="max-h-80 space-y-2 overflow-auto pr-1">
        {macs.map((mac) => (
          <div
            key={`${mac.mac_address}-${mac.vlan ?? 'none'}`}
            className="grid gap-2 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-sm sm:grid-cols-[190px_minmax(0,1fr)_90px]"
          >
            <span className="font-mono text-xs font-black text-slate-900">
              {emptyLabel(mac.mac_address)}
            </span>

            <span className="min-w-0 break-words font-semibold text-slate-600">
              {emptyLabel(mac.mac_vendor)}
              {mac.mac_oui ? ` · ${mac.mac_oui}` : ''}
            </span>

            <span className="text-xs font-black uppercase text-blue-700">
              {emptyLabel(mac.type)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Info({
  label,
  mono = false,
  value,
  wide = false,
}: {
  label: string;
  mono?: boolean;
  value: string;
  wide?: boolean;
}) {
  return (
    <span className={cn('min-w-0 rounded-xl bg-white px-3 py-2 ring-1 ring-slate-200', wide && 'sm:col-span-2 xl:col-span-4')}>
      <small className="block text-[10px] font-black uppercase tracking-wide text-slate-400">
        {label}
      </small>
      <span className={cn('block min-w-0 break-words font-semibold text-slate-800', mono && 'break-all font-mono text-xs')}>
        {value}
      </span>
    </span>
  );
}