import { Fragment, useState, type CSSProperties, type PointerEvent, type WheelEvent } from 'react';
import { AlertTriangle, Building2, Cable, Eye, MapPinned, Router, Search, X } from 'lucide-react';
import type { NetBoxDevice, NetBoxInterface, NetBoxRegion, NetBoxSite } from '../api';
import { emptyLabel } from '../lib/format';
import { GRAPH_LEVEL_LABELS, iconColor, nodeColor } from '../lib/graphModel';
import type { GraphLevels, GraphNode, GraphNodeType, InventoryGraphModel } from '../types';

export function GraphLevelToggles({ levels, onChange }: { levels: GraphLevels; onChange: (levels: GraphLevels) => void }) {
  return (
    <div className="level-toggles">
      <Eye size={16} />
      {(Object.keys(levels) as GraphNodeType[]).map((level) => (
        <button
          className={levels[level] ? 'selected' : ''}
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
  expandedDeviceIds?: ReadonlySet<number>;
  onToggleDevice?: (deviceId: number) => void;
};

export function InventoryGraph({
  graph,
  selectedNode,
  onSelect,
  expandedDeviceIds = new Set<number>(),
  onToggleDevice,
}: InventoryGraphProps) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const [graphMode, setGraphMode] = useState<'inline' | 'expanded'>('inline');
  const [viewport, setViewport] = useState({ x: 0, y: 0, scale: 1 });
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);

  function resetViewport() {
    setViewport({ x: 0, y: 0, scale: 1 });
  }

  function moveViewport(deltaX: number, deltaY: number) {
    setViewport((current) => ({ ...current, x: current.x + deltaX, y: current.y + deltaY }));
  }

  function zoom(delta: number) {
    setViewport((current) => ({ ...current, scale: Math.min(2.6, Math.max(0.28, current.scale + delta)) }));
  }

  function getDeviceId(node: GraphNode): number | null {
  if (node.type !== 'device') {
    return null;
  }

  const meta = node.meta as NetBoxDevice | undefined;

  if (meta?.id !== undefined) {
    return Number(meta.id);
  }

  const rawId = node.id.replace('device:', '');
  const parsed = Number(rawId);

  return Number.isFinite(parsed) ? parsed : null;
}

  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
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
    zoom(event.deltaY > 0 ? -0.08 : 0.08);
  }

  const selectedId = selectedNode?.id;
  const popoverLeft = selectedNode ? Math.min(Math.max((selectedNode.x / graph.width) * 100, 16), 84) : 50;
  const popoverTop = selectedNode ? Math.min(Math.max((selectedNode.y / graph.height) * 100, 14), 76) : 20;

  return (
    <div className={`graph-canvas ${graphMode}`}>
      <div className="graph-toolbar">
        <button type="button" onClick={() => zoom(0.12)}>+</button>
        <button type="button" onClick={() => zoom(-0.12)}>−</button>
        <button type="button" onClick={resetViewport}>sıfırla</button>
        <button type="button" onClick={() => setGraphMode((current) => (current === 'expanded' ? 'inline' : 'expanded'))}>{graphMode === 'expanded' ? 'div-ə qayıt' : 'tam pəncərə'}</button>
      </div>
      <svg
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
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
          {graph.links.map((link) => {
            const from = nodeById.get(link.from);
            const to = nodeById.get(link.to);
            if (!from || !to) return null;
            return <line className="graph-link" key={`${link.from}-${link.to}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} />;
          })}
          {graph.nodes.map((node) => {
              const deviceId = getDeviceId(node);
              const isExpandedDevice = deviceId !== null && expandedDeviceIds.has(deviceId);

              return (
                <g
                  className={[
                    'graph-node',
                    selectedId === node.id ? 'selected' : '',
                    node.type === 'device' ? 'clickable-device' : '',
                    isExpandedDevice ? 'expanded' : '',
                  ].filter(Boolean).join(' ')}
                  key={node.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(node);

                    if (node.type === 'device' && deviceId !== null) {
                      onToggleDevice?.(deviceId);
                    }
                  }}
                  tabIndex={0}
                  transform={`translate(${node.x} ${node.y})`}
                >
                  <g className="graph-node-inner">
                    <circle
                      fill={nodeColor(node.type)}
                      filter="url(#glow)"
                      r={node.type === 'region' ? 34 : node.type === 'interface' ? 19 : 27}
                    />

                    <foreignObject x="-16" y="-16" width="32" height="32">
                      <div className="graph-node-icon" style={{ color: iconColor(node.type) }}>
                        <GraphNodeIcon type={node.type} />
                      </div>
                    </foreignObject>

                    <text y={node.type === 'interface' ? 45 : 52}>
                      {node.label}
                    </text>

                    {node.type === 'device' && (
                      <text className="graph-node-hint" y="72">
                        {isExpandedDevice ? 'interfeysləri gizlət' : 'interfeysləri göstər'}
                      </text>
                    )}
                  </g>
                </g>
              );
            })}
        </g>
      </svg>
      {selectedNode && (
        <GraphPopover
          node={selectedNode}
          style={{ left: `${popoverLeft}%`, top: `${popoverTop}%` }}
          onClose={() => onSelect(null)}
        />
      )}
      {!graph.nodes.length && <p className="muted-text">Qraf üçün məlumat yoxdur.</p>}
    </div>
  );
}

function GraphPopover({ node, onClose, style }: { node: GraphNode; onClose: () => void; style: CSSProperties }) {
  return (
    <aside className="graph-popover" style={style}>
      <button aria-label="Bağla" className="popover-close" onClick={onClose} type="button"><X size={14} /></button>
      <strong>{nodeTypeLabel(node.type)}: {node.label}</strong>
      <dl>
        {inspectorFields(node).slice(0, 7).map(([key, value]) => (
          <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
        ))}
      </dl>
      {node.type === 'interface' && <LearnedMacList item={node.meta as NetBoxInterface} />}
    </aside>
  );
}

function LearnedMacList({ item }: { item?: NetBoxInterface }) {
  const learned = item?.learned_mac_addresses ?? [];
  if (!learned.length) return <p className="muted-text compact-text">Bu interfeysdə əlavə MAC yoxdur.</p>;
  return (
    <div className="learned-macs">
      <b>Bu interfeysdə olan MAC-lar</b>
      {learned.slice(0, 12).map((mac) => (
        <span key={`${item?.id}-${mac.mac_address}`}>
          <code>{mac.mac_address}</code>
          <small>{emptyLabel(mac.mac_vendor)} {mac.vlan ? `· VLAN ${mac.vlan}` : ''}</small>
        </span>
      ))}
      {learned.length > 12 && <small>+{learned.length - 12} MAC daha</small>}
    </div>
  );
}

function GraphNodeIcon({ type }: { type: GraphNodeType }) {
  const size = 22;
  if (type === 'region') return <MapPinned size={size} />;
  if (type === 'site') return <Building2 size={size} />;
  if (type === 'device') return <Router size={size} />;
  return <Cable size={size} />;
}

export function GraphInspector({ node, onSelectDevice }: { node: GraphNode | null; onSelectDevice: (deviceId: number) => void }) {
  if (!node) {
    return <aside className="panel inspector"><div className="panel-title"><Search size={20} /> Obyekt məlumatı</div><p className="muted-text">Qrafdan obyekt seçin.</p></aside>;
  }
  const meta = node.meta as Record<string, unknown> | undefined;
  const risks = nodeRisks(node);
  return (
    <aside className="panel inspector">
      <div className="panel-title"><Search size={20} /> {nodeTypeLabel(node.type)}: {node.label}</div>
      {!!risks.length && <div className="risk-list">{risks.map((risk) => <span key={risk} className="risk-pill warn"><AlertTriangle size={14} /> {risk}</span>)}</div>}
      <dl>
        {inspectorFields(node).map(([key, value]) => (
          <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
        ))}
      </dl>
      {node.type === 'device' && meta?.id !== undefined && <button className="primary-button" onClick={() => onSelectDevice(Number(meta.id))} type="button">Detalları aç</button>}
    </aside>
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
