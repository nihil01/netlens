import { useState } from 'react';
import { ChevronDown, ChevronUp, ArrowLeftRight, Shield, Lock, Unlock } from 'lucide-react';
import { cn } from '../../lib/ui';
import type { TunnelStatus, TunnelPeer } from '../../api';
import { TunnelAnalytics } from './TunnelAnalytics';

function stateColor(state: string) {
  if (state === 'TUNNEL_UP') return 'bg-emerald-50 text-emerald-700 ring-emerald-200';
  if (state === 'TUNNEL_DOWN') return 'bg-red-50 text-red-700 ring-red-200';
  return 'bg-gray-50 text-gray-500 ring-gray-200';
}
function stateDot(state: string) {
  if (state === 'TUNNEL_UP') return 'bg-emerald-500';
  if (state === 'TUNNEL_DOWN') return 'bg-red-500 animate-pulse';
  return 'bg-gray-400';
}
function stateLabel(state: string) {
  if (state === 'TUNNEL_UP') return 'UP';
  if (state === 'TUNNEL_DOWN') return 'DOWN';
  return 'UNKNOWN';
}

function PeerCard({ label, peer }: { label: string; peer: TunnelPeer | null }) {
  if (!peer) {
    return (
      <div className="rounded-lg bg-gray-50 p-3">
        <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</div>
        <p className="mt-1 text-xs text-gray-400">Məlumat yoxdur</p>
      </div>
    );
  }
  return (
    <div className="rounded-lg bg-gray-50 p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{label}</div>
      <div className="mt-2 space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-gray-900">{peer.device_name || '—'}</span>
          {peer.role && (
            <span className={cn(
              'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold',
              peer.role === 'HUB' ? 'bg-purple-100 text-purple-700' :
              peer.role === 'SPOKE' ? 'bg-orange-100 text-orange-700' :
              'bg-blue-100 text-blue-700',
            )}>{peer.role}</span>
          )}
        </div>
        {peer.vpn_interface && (
          <div className="space-y-1 text-xs">
            <div className="flex justify-between"><span className="text-gray-500">Interface</span><span className="font-mono font-medium text-gray-900">{peer.vpn_interface.name || '—'}</span></div>
            {peer.vpn_interface.ip_address && (
              <div className="flex justify-between"><span className="text-gray-500">Tunnel IP</span><span className="font-mono text-gray-900">{peer.vpn_interface.ip_address}</span></div>
            )}
            {peer.vpn_interface.public_ip && (
              <div className="flex justify-between"><span className="text-gray-500">Public IP</span><span className="font-mono text-gray-900">{peer.vpn_interface.public_ip}</span></div>
            )}
            <div className="flex justify-between"><span className="text-gray-500">Mode</span><span className="font-medium text-gray-900">{peer.vpn_interface.interface_type || '—'}</span></div>
          </div>
        )}
        {peer.ip_addresses.length > 0 && (
          <div className="text-xs"><span className="text-gray-500">IPs: </span><span className="font-mono text-gray-900">{peer.ip_addresses.join(', ')}</span></div>
        )}
      </div>
    </div>
  );
}

export function TunnelStatusCard({ tunnel }: { tunnel: TunnelStatus }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn(
      'rounded-xl border bg-white transition-all',
      tunnel.state === 'TUNNEL_DOWN' ? 'border-red-200 shadow-sm shadow-red-100' : 'border-gray-200 hover:border-gray-300',
    )}>
      <button
        className="flex w-full items-center gap-4 p-4 text-left"
        onClick={() => setExpanded(!expanded)}
        type="button"
      >
        <span className={cn('h-3 w-3 shrink-0 rounded-full', stateDot(tunnel.state))} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-bold text-gray-900">{tunnel.name}</span>
            {tunnel.topology_type && (
              <span className="hidden shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 sm:inline-block">
                {tunnel.topology_type.replace(/_/g, ' ')}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
            <span>{tunnel.active_tunnels}/{tunnel.total_tunnels} active</span>
            {tunnel.down_tunnels > 0 && <span className="font-semibold text-red-600">{tunnel.down_tunnels} down</span>}
            <span className="flex items-center gap-1">
              {tunnel.ike_v2_enabled && <span className="rounded bg-emerald-50 px-1 text-[10px] font-bold text-emerald-700">IKEv2</span>}
              {tunnel.ike_v1_enabled && <span className="rounded bg-amber-50 px-1 text-[10px] font-bold text-amber-700">IKEv1</span>}
            </span>
          </div>
        </div>
        <div className="hidden items-center gap-2 md:flex">
          <span className="max-w-[120px] truncate text-xs font-medium text-gray-600">{tunnel.peer_a?.device_name || '?'}</span>
          <ArrowLeftRight size={14} className="text-gray-300" />
          <span className="max-w-[120px] truncate text-xs font-medium text-gray-600">{tunnel.peer_b?.device_name || '?'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ring-1', stateColor(tunnel.state))}>
            {stateLabel(tunnel.state)}
          </span>
          {expanded ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-4 pb-4 pt-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <PeerCard label="Peer A" peer={tunnel.peer_a} />
            <PeerCard label="Peer B" peer={tunnel.peer_b} />
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-500">
            <span className="flex items-center gap-1"><Shield size={12} />{tunnel.ike_v2_enabled ? 'IKEv2' : tunnel.ike_v1_enabled ? 'IKEv1' : '—'}</span>
            <span className="flex items-center gap-1">{tunnel.route_based ? <><Lock size={12} />Route-based</> : <><Unlock size={12} />Policy-based</>}</span>
            {tunnel.message && <span className="rounded bg-gray-100 px-2 py-0.5 text-gray-600">{tunnel.message}</span>}
          </div>
          {tunnel.id && <TunnelAnalytics tunnelId={tunnel.id} />}
        </div>
      )}
    </div>
  );
}
