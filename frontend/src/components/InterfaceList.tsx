import { motion } from 'framer-motion';
import type { NetBoxInterface } from '../api';
import { emptyLabel } from '../lib/format';
import { cn, ui } from '../lib/ui';

export function InterfaceList({ interfaces, showDevice = false, showVendor = false }: { interfaces: NetBoxInterface[]; showDevice?: boolean; showVendor?: boolean }) {
  if (!interfaces.length) return <p className={ui.muted}>İnterfeys yoxdur</p>;

  return (
    <div className="mt-4 space-y-3">
      <h3 className="text-sm font-black uppercase tracking-[0.18em] text-slate-500">İnterfeyslər</h3>
      <div className="space-y-2">
        {interfaces.map((item, index) => (
          <motion.div
            className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-3 text-sm text-slate-700 md:grid-cols-[1.1fr_1fr_1fr_0.8fr_1.2fr_0.9fr_1.3fr]"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18, delay: Math.min(index * 0.025, 0.18) }}
            key={item.id ?? item.name}
          >
            <b className="min-w-0 break-words text-slate-950">{item.name}</b>
            {showDevice && <span className="min-w-0 break-words">{emptyLabel(item.device)}</span>}
            <span className="min-w-0 break-words">{emptyLabel(item.type)}</span>
            <span className={cn('font-black uppercase', item.enabled ? 'text-emerald-700' : 'text-slate-400')}>{item.enabled ? 'aktiv' : 'deaktiv'}</span>
            <span className="min-w-0 break-all font-mono text-xs text-slate-900">{emptyLabel(item.mac_address)}</span>
            <span>{item.learned_mac_addresses?.length ?? 0} MAC <small className="text-slate-400">portda</small></span>
            {showVendor && <span className="min-w-0 break-words">{emptyLabel(item.mac_vendor)} <small className="text-slate-400">{emptyLabel(item.mac_oui)} · {emptyLabel(item.mac_vendor_source)}</small></span>}
            <small className="min-w-0 break-words text-slate-400 md:col-span-full">{emptyLabel(item.description)}</small>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
