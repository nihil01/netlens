import { Fragment, useEffect, useRef, useState, type CSSProperties, type PointerEvent, type WheelEvent } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'framer-motion';
import { AlertTriangle, Building2, Cable, Eye, MapPinned, Router, Search, X } from 'lucide-react';
import type { NetBoxDevice, NetBoxInterface, NetBoxRegion, NetBoxSite } from '../api';
import { emptyLabel } from '../lib/format';
import { GRAPH_LEVEL_LABELS, iconColor, nodeColor } from '../lib/graphModel';
import { cn, motionPreset, ui } from '../lib/ui';
import type { GraphLevels, GraphNode, GraphNodeType, InventoryGraphModel } from '../types';

export function GraphLevelToggles({ levels, onChange }: { levels: GraphLevels; onChange: (levels: GraphLevels) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Eye className="text-blue-600" size={16} />
      {(Object.keys(levels) as GraphNodeType[]).map((level) => (
        <button
          className={cn(ui.pillButton, levels[level] && ui.selectedPill)}
          key={level}
          type="button"
          onClick={() => onChange({ ...levels, [level]: !levels[level] })}
        >
          {GRAPH_LEVEL_LABELS[level]}
        </button>
      ))}
    </div>
  );
}

type InventoryGraphProps = {
  graph: InventoryGraphModel;
  selectedNode: GraphNode | null;
  onSelect: (node: GraphNode | null) => void;
  expandedSiteId?: number | null;
  expandedDeviceId?: number | null;
  onToggleSite?: (siteId: number) => void;
  onToggleDevice?: (deviceId: number) => void;
  onReset?: () => void;
};

export function InventoryGraph({
  graph,
  selectedNode,
  onSelect,
  expandedSiteId = null,
  expandedDeviceId = null,
  onToggleSite,
  onToggleDevice,
  onReset,
}: InventoryGraphProps) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const graphContainerRef = useRef<HTMLDivElement | null>(null);
  const [graphMode, setGraphMode] = useState<'inline' | 'expanded'>('inline');
  const [viewport, setViewport] = useState({ x: 0, y: 0, scale: 1 });
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);

  function resetGraph() {
    setViewport({ x: 0, y: 0, scale: 1 });
    onReset?.();
  }

  function moveViewport(deltaX: number, deltaY: number) {
    setViewport((current) => ({ ...current, x: current.x + deltaX, y: current.y + deltaY }));
  }

  function zoom(delta: number) {
    setViewport((current) => ({ ...current, scale: Math.min(5, Math.max(0.18, current.scale + delta)) }));
  }

  function getSiteId(node: GraphNode): number | null {
    if (node.type !== 'site') return null;
    const meta = node.meta as NetBoxSite | undefined;
    if (meta?.id !== undefined) return Number(meta.id);
    const parsed = Number(node.id.replace('site:', ''));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function getDeviceId(node: GraphNode): number | null {
    if (node.type !== 'device') return null;
    const meta = node.meta as NetBoxDevice | undefined;
    if (meta?.id !== undefined) return Number(meta.id);
    const parsed = Number(node.id.replace('device:', ''));
    return Number.isFinite(parsed) ? parsed : null;
  }

  useEffect(() => {
    function syncFullscreenMode() {
      if (!document.fullscreenElement && graphMode === 'expanded') {
        setGraphMode('inline');
      }
    }

    document.addEventListener('fullscreenchange', syncFullscreenMode);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenMode);
  }, [graphMode]);

  async function toggleFullscreen() {
    if (graphMode === 'expanded') {
      if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined);
      setGraphMode('inline');
      return;
    }

    setGraphMode('expanded');
    window.requestAnimationFrame(() => {
      graphContainerRef.current?.requestFullscreen?.().catch(() => undefined);
    });
  }

  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
    const target = event.target as Element | null;
    if (target?.closest('[data-graph-node="true"]')) return;

    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({ x: event.clientX, y: event.clientY });
  }

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    if (!dragStart) return;
    moveViewport(event.clientX - dragStart.x, event.clientY - dragStart.y);
    setDragStart({ x: event.clientX, y: event.clientY });
  }

  function onWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    zoom(event.deltaY > 0 ? -0.14 : 0.14);
  }

  const selectedId = selectedNode?.id;
  const popoverLeft = selectedNode ? Math.min(Math.max((selectedNode.x / graph.width) * 100, 16), 84) : 50;
  const popoverTop = selectedNode ? Math.min(Math.max((selectedNode.y / graph.height) * 100, 14), 76) : 20;

  const canvas = (
    <div
      className={cn(ui.graphCanvasBase, graphMode === 'expanded' ? ui.graphCanvasExpanded : ui.graphCanvasInline)}
      ref={graphContainerRef}
    >
      <div className={ui.graphToolbar}>
        <button className={ui.pillButton} type="button" onClick={() => zoom(0.24)}>+</button>
        <button className={ui.pillButton} type="button" onClick={() => zoom(-0.24)}>−</button>
        <button className={ui.pillButton} type="button" onClick={resetGraph}>sıfırla</button>
        <button className={ui.pillButton} type="button" onClick={toggleFullscreen}>{graphMode === 'expanded' ? 'div-ə qayıt' : 'tam pəncərə'}</button>
      </div>
      <svg
        className={cn(ui.graphSvg, graphMode === 'expanded' ? 'h-[100vh]' : 'h-[min(72vh,760px)]')}
        onPointerDown={onPointerDown}
        onPointerLeave={() => setDragStart(null)}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragStart(null)}
        onWheel={onWheel}
        role="img"
        aria-label="NetBox region qrafı"
        viewBox={`0 0 ${graph.width} ${graph.height}`}
      >
        <defs>
          <filter id="glow"><feGaussianBlur stdDeviation="4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <motion.g animate={{ x: viewport.x, y: viewport.y, scale: viewport.scale }} transition={{ type: 'spring', stiffness: 260, damping: 30 }}>
          {graph.links.map((link) => {
            const from = nodeById.get(link.from);
            const to = nodeById.get(link.to);
            if (!from || !to) return null;
            const isCollapsing = link.lifecycle === 'collapsing';
            return (
              <motion.line
                className="stroke-slate-400"
                key={`${link.from}-${link.to}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                strokeWidth={1.25}
                strokeDasharray="9 10"
                initial={{ opacity: 0, pathLength: 0 }}
                animate={{ opacity: isCollapsing ? 0 : 1, pathLength: isCollapsing ? 0 : 1 }}
                transition={{ duration: isCollapsing ? 0.22 : 0.28 }}
              />
            );
          })}
          {graph.nodes.map((node) => {
            const siteId = getSiteId(node);
            const deviceId = getDeviceId(node);
            const isExpandedSite = siteId !== null && expandedSiteId === siteId;
            const isExpandedDevice = deviceId !== null && expandedDeviceId === deviceId;
            const isCollapsing = node.lifecycle === 'collapsing';
            const isSelected = selectedId === node.id;

            return (
              <motion.g
                className={cn('outline-none', (node.type === 'site' || node.type === 'device') && 'cursor-pointer')}
                data-graph-node="true"
                key={node.id}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(node);

                  if (node.type === 'site' && siteId !== null) onToggleSite?.(siteId);
                  if (node.type === 'device' && deviceId !== null) onToggleDevice?.(deviceId);
                }}
                tabIndex={0}
                transform={`translate(${node.x} ${node.y})`}
                initial={{ opacity: 0, y: -18, scale: 0.82 }}
                animate={{ opacity: isCollapsing ? 0 : 1, y: isCollapsing ? -18 : 0, scale: isCollapsing ? 0.82 : 1 }}
                transition={{ duration: isCollapsing ? 0.22 : 0.24, ease: 'easeOut' }}
                whileHover={{ scale: 1.04 }}
              >
                <circle
                  fill={nodeColor(node.type)}
                  filter="url(#glow)"
                  r={node.type === 'region' ? 34 : node.type === 'interface' ? 19 : 27}
                  stroke={nodeStroke(node.type, isSelected, isExpandedSite || isExpandedDevice)}
                  strokeWidth={isSelected ? 5 : isExpandedSite || isExpandedDevice ? 3 : 1.6}
                />

                <g className="pointer-events-none" style={{ color: iconColor(node.type) }} transform="translate(-12 -12)">
                  <GraphNodeIcon type={node.type} />
                </g>

                <text className="pointer-events-none select-none fill-slate-950 text-[13px] font-black [paint-order:stroke] [stroke-width:5px] [stroke:rgba(255,255,255,.96)]" textAnchor="middle" y={node.type === 'interface' ? 45 : 52}>{node.label}</text>

                {node.type === 'site' && (
                  <text className="pointer-events-none select-none fill-slate-500 text-[10px] font-bold" textAnchor="middle" y="72">
                    {isExpandedSite ? 'qurğuları gizlət' : 'qurğuları göstər'}
                  </text>
                )}

                {node.type === 'device' && (
                  <text className="pointer-events-none select-none fill-slate-500 text-[10px] font-bold" textAnchor="middle" y="72">
                    {isExpandedDevice ? 'interfeysləri gizlət' : 'interfeysləri göstər'}
                  </text>
                )}
              </motion.g>
            );
          })}
        </motion.g>
      </svg>
      {selectedNode && (
        <GraphPopover
          node={selectedNode}
          style={{ left: `${popoverLeft}%`, top: `${popoverTop}%` }}
          onClose={() => onSelect(null)}
        />
      )}
      {!graph.nodes.length && <p className={cn(ui.muted, 'p-5')}>Qraf üçün məlumat yoxdur.</p>}
    </div>
  );

  return graphMode === 'expanded' ? createPortal(canvas, document.body) : canvas;
}

function GraphPopover({ node, onClose, style }: { node: GraphNode; onClose: () => void; style: CSSProperties }) {
  return (
    <motion.aside
      className={ui.graphPopover}
      style={{ ...style, transform: 'translate(-50%, 10px)' }}
      initial={{ opacity: 0, y: 8, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.18 }}
    >
      <button aria-label="Bağla" className={cn(ui.iconButton, 'absolute right-3 top-3 h-7 w-7')} onClick={onClose} type="button"><X size={14} /></button>
      <strong className="mb-3 block pr-8 text-sm font-black">{nodeTypeLabel(node.type)}: {node.label}</strong>
      <dl className={ui.dl}>
        {inspectorFields(node).slice(0, 7).map(([key, value]) => (
          <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
        ))}
      </dl>
      {node.type === 'interface' && <LearnedMacList item={node.meta as NetBoxInterface} />}
    </motion.aside>
  );
}

function LearnedMacList({ item }: { item?: NetBoxInterface }) {
  const learned = item?.learned_mac_addresses ?? [];
  if (!learned.length) return <p className={cn(ui.muted, 'mt-3 text-xs')}>Bu interfeysdə əlavə MAC yoxdur.</p>;
  return (
    <div className="mt-4 max-h-64 space-y-2 overflow-auto text-xs">
      <b className="block text-slate-900">Bu interfeysdə olan MAC-lar</b>
      {learned.slice(0, 12).map((mac) => (
        <span className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-2" key={`${item?.id}-${mac.mac_address}`}>
          <code className="break-all font-mono text-slate-900">{mac.mac_address}</code>
          <small className="text-slate-500">{emptyLabel(mac.mac_vendor)} {mac.vlan ? `· VLAN ${mac.vlan}` : ''}</small>
        </span>
      ))}
      {learned.length > 12 && <small className="text-slate-500">+{learned.length - 12} MAC daha</small>}
    </div>
  );
}

function GraphNodeIcon({ type }: { type: GraphNodeType }) {
  const props = { size: 24, strokeWidth: 2.7 };
  if (type === 'region') return <MapPinned {...props} />;
  if (type === 'site') return <Building2 {...props} />;
  if (type === 'device') return <Router {...props} />;
  return <Cable {...props} />;
}

function nodeStroke(type: GraphNodeType, selected: boolean, expanded: boolean) {
  if (selected) return 'rgba(37, 99, 235, 0.95)';
  if (expanded && type === 'site') return 'rgba(109, 40, 217, 0.95)';
  if (expanded && type === 'device') return 'rgba(21, 128, 61, 0.95)';
  if (type === 'site') return 'rgba(109, 40, 217, 0.3)';
  if (type === 'device') return 'rgba(22, 163, 74, 0.28)';
  return 'rgba(15, 23, 42, 0.22)';
}

export function GraphInspector({ node, onSelectDevice }: { node: GraphNode | null; onSelectDevice: (deviceId: number) => void }) {
  if (!node) {
    return <motion.aside className={ui.stickyPanel} {...motionPreset.side}><div className={ui.panelTitle}><Search size={20} /> Obyekt məlumatı</div><p className={cn(ui.emptyText, 'mt-4')}>Qrafdan obyekt seçin.</p></motion.aside>;
  }
  const meta = node.meta as Record<string, unknown> | undefined;
  const risks = nodeRisks(node);
  return (
    <motion.aside className={ui.stickyPanel} {...motionPreset.side}>
      <div className={ui.panelTitle}><Search size={20} /> {nodeTypeLabel(node.type)}: {node.label}</div>
      {!!risks.length && <div className="my-3 flex flex-wrap gap-2">{risks.map((risk) => <span key={risk} className={ui.badgeWarn}><AlertTriangle size={14} /> {risk}</span>)}</div>}
      <dl className={cn(ui.dl, 'mt-4')}>
        {inspectorFields(node).map(([key, value]) => (
          <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
        ))}
      </dl>
      {node.type === 'device' && meta?.id !== undefined && <button className={cn(ui.primaryButton, 'mt-4 w-full')} onClick={() => onSelectDevice(Number(meta.id))} type="button">Detalları aç</button>}
    </motion.aside>
  );
}

function nodeTypeLabel(type: GraphNodeType): string {
  return GRAPH_LEVEL_LABELS[type];
}

function inspectorFields(node: GraphNode): Array<[string, string]> {
  const meta = node.meta as NetBoxRegion | NetBoxSite | NetBoxDevice | NetBoxInterface | undefined;
  if (!meta) return [['Ad', node.label]];
  if (node.type === 'region') {
    const item = meta as NetBoxRegion;
    return [['Ad', item.name], ['Slug', emptyLabel(item.slug)], ['Təsvir', emptyLabel(item.description)]];
  }
  if (node.type === 'site') {
    const item = meta as NetBoxSite;
    return [['Ad', item.name], ['Region', emptyLabel(item.region)], ['Status', emptyLabel(item.status)], ['Ünvan', emptyLabel(item.physical_address ?? item.facility)]];
  }
  if (node.type === 'device') {
    const item = meta as NetBoxDevice;
    return [['Ad', item.name], ['Sahə / Region', `${emptyLabel(item.site)} / ${emptyLabel(item.region)}`], ['Rol', emptyLabel(item.role)], ['Tip', `${emptyLabel(item.manufacturer)} ${emptyLabel(item.device_type)}`], ['Status', emptyLabel(item.status)], ['Əsas IP', emptyLabel(item.primary_ip)]];
  }
  const item = meta as NetBoxInterface;
  return [['Ad', item.name], ['Qurğu', emptyLabel(item.device)], ['Tip', emptyLabel(item.type)], ['Status', item.enabled ? 'aktiv' : 'deaktiv'], ['İnterfeys MAC', emptyLabel(item.mac_address)], ['Oturmuş MAC sayı', String(item.learned_mac_addresses?.length ?? 0)], ['Vendor', `${emptyLabel(item.mac_vendor)} / ${emptyLabel(item.mac_oui)}`]];
}

function nodeRisks(node: GraphNode): string[] {
  const meta = node.meta as NetBoxDevice | NetBoxInterface | undefined;
  if (node.type === 'device') {
    const item = meta as NetBoxDevice | undefined;
    return [!item?.site ? 'Sahə yoxdur' : null, !item?.primary_ip ? 'Primary IP yoxdur' : null, (item?.status ?? '').toLowerCase() === 'offline' ? 'Offline' : null].filter(Boolean) as string[];
  }
  if (node.type === 'interface') {
    const item = meta as NetBoxInterface | undefined;
    return [item?.enabled === false ? 'Deaktiv' : null, item?.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown') ? 'Vendor tapılmadı' : null].filter(Boolean) as string[];
  }
  return [];
}
