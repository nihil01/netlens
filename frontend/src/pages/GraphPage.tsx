import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { GraphInspector, GraphLevelToggles, InventoryGraph } from '../components/InventoryGraph';
import type { NetBoxDevice, NetBoxInterface, NetBoxRegion, NetBoxSite } from '../api';
import { groupDevicesBySite, groupInterfacesByDevice, groupSitesByRegion } from '../lib/grouping';
import { buildGraph } from '../lib/graphModel';
import { cn, ui } from '../lib/ui';
import type { GraphLevels, GraphNode } from '../types';

type GraphPageProps = {
  data: {
    regions: NetBoxRegion[];
    sites: NetBoxSite[];
    devices: NetBoxDevice[];
    interfaces: NetBoxInterface[];
  } | undefined;
  selectedRegionName: string | null;
  onRegionChange: (name: string) => void;
  filteredRegions: NetBoxRegion[];
  graphLevels: GraphLevels;
  onGraphLevelsChange: (levels: GraphLevels) => void;
  onSelectDevice: (id: number) => void;
};

export function GraphPage({
  data, selectedRegionName, onRegionChange, filteredRegions,
  graphLevels, onGraphLevelsChange, onSelectDevice,
}: GraphPageProps) {
  const [selectedGraphNode, setSelectedGraphNode] = React.useState<GraphNode | null>(null);
  const [expandedSiteId, setExpandedSiteId] = React.useState<number | null>(null);
  const [collapsingSiteId, setCollapsingSiteId] = React.useState<number | null>(null);
  const [expandedGraphDeviceId, setExpandedGraphDeviceId] = React.useState<number | null>(null);
  const [collapsingGraphDeviceId, setCollapsingGraphDeviceId] = React.useState<number | null>(null);
  const siteCollapseTimerRef = React.useRef<number | null>(null);
  const deviceCollapseTimerRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (siteCollapseTimerRef.current !== null) window.clearTimeout(siteCollapseTimerRef.current);
      if (deviceCollapseTimerRef.current !== null) window.clearTimeout(deviceCollapseTimerRef.current);
    };
  }, []);

  function clearSiteCollapseTimer() {
    if (siteCollapseTimerRef.current !== null) { window.clearTimeout(siteCollapseTimerRef.current); siteCollapseTimerRef.current = null; }
  }
  function clearDeviceCollapseTimer() {
    if (deviceCollapseTimerRef.current !== null) { window.clearTimeout(deviceCollapseTimerRef.current); deviceCollapseTimerRef.current = null; }
  }
  function animateSiteCollapse(siteId: number | null) {
    clearSiteCollapseTimer();
    if (siteId === null) { setCollapsingSiteId(null); return; }
    setCollapsingSiteId(siteId);
    siteCollapseTimerRef.current = window.setTimeout(() => { setCollapsingSiteId(null); siteCollapseTimerRef.current = null; }, 200);
  }
  function animateDeviceCollapse(deviceId: number | null) {
    clearDeviceCollapseTimer();
    if (deviceId === null) { setCollapsingGraphDeviceId(null); return; }
    setCollapsingGraphDeviceId(deviceId);
    deviceCollapseTimerRef.current = window.setTimeout(() => { setCollapsingGraphDeviceId(null); deviceCollapseTimerRef.current = null; }, 200);
  }
  function toggleSiteDevices(siteId: number) {
    if (expandedSiteId === siteId) {
      animateDeviceCollapse(expandedGraphDeviceId); animateSiteCollapse(expandedSiteId);
      setExpandedGraphDeviceId(null); setExpandedSiteId(null); return;
    }
    animateDeviceCollapse(expandedGraphDeviceId); animateSiteCollapse(expandedSiteId);
    setExpandedGraphDeviceId(null); setExpandedSiteId(siteId);
  }
  function toggleDeviceInterfaces(deviceId: number) {
    if (expandedGraphDeviceId === deviceId) { animateDeviceCollapse(expandedGraphDeviceId); setExpandedGraphDeviceId(null); return; }
    animateDeviceCollapse(expandedGraphDeviceId); setExpandedGraphDeviceId(deviceId);
  }
  function resetGraphView() {
    clearSiteCollapseTimer(); clearDeviceCollapseTimer();
    setExpandedSiteId(null); setCollapsingSiteId(null);
    setExpandedGraphDeviceId(null); setCollapsingGraphDeviceId(null); setSelectedGraphNode(null);
  }

  const selectedRegion = selectedRegionName && filteredRegions.some((r) => r.name === selectedRegionName)
    ? selectedRegionName
    : filteredRegions[0]?.name ?? data?.regions[0]?.name ?? null;

  const sitesByRegion = useMemo(() => groupSitesByRegion(data?.sites ?? []), [data?.sites]);
  const devicesBySite = useMemo(() => groupDevicesBySite(data?.devices ?? []), [data?.devices]);
  const interfacesByDevice = useMemo(() => groupInterfacesByDevice(data?.interfaces ?? []), [data?.interfaces]);

  const selectedRegionSites = useMemo(
    () => (selectedRegion ? sitesByRegion.get(selectedRegion) ?? [] : []),
    [selectedRegion, sitesByRegion],
  );
  const selectedRegionDevices = useMemo(
    () => selectedRegionSites.flatMap((s) => devicesBySite.get(s.name) ?? []),
    [devicesBySite, selectedRegionSites],
  );

  const graph = useMemo(
    () => buildGraph(selectedRegion, selectedRegionSites, selectedRegionDevices, interfacesByDevice, graphLevels, expandedSiteId, collapsingSiteId, expandedGraphDeviceId, collapsingGraphDeviceId),
    [selectedRegion, selectedRegionSites, selectedRegionDevices, interfacesByDevice, graphLevels, expandedSiteId, collapsingSiteId, expandedGraphDeviceId, collapsingGraphDeviceId],
  );

  function handleRegionChange(value: string) {
    onRegionChange(value);
    animateDeviceCollapse(expandedGraphDeviceId);
    animateSiteCollapse(expandedSiteId);
    setExpandedGraphDeviceId(null);
    setExpandedSiteId(null);
    setSelectedGraphNode(null);
  }

  return (
    <motion.section className={ui.graphLayout} {...{ initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: 'easeOut' } }}>
      <article className={cn(ui.panel, 'space-y-4')}>
        <div className={ui.panelHeader}>
          <div className={ui.panelTitle}>Region qrafı</div>
          <select className={ui.select} value={selectedRegion ?? ''} onChange={(e) => handleRegionChange(e.target.value)}>
            {(filteredRegions ?? []).map((r) => <option key={r.id} value={r.name}>{r.name}</option>)}
          </select>
        </div>
        <GraphLevelToggles levels={graphLevels} onChange={onGraphLevelsChange} />
        <InventoryGraph graph={graph} selectedNode={selectedGraphNode} onSelect={setSelectedGraphNode} expandedSiteId={expandedSiteId} expandedDeviceId={expandedGraphDeviceId} onToggleDevice={toggleDeviceInterfaces} onReset={resetGraphView} onToggleSite={toggleSiteDevices} />
      </article>
      <GraphInspector node={selectedGraphNode} onSelectDevice={onSelectDevice} />
    </motion.section>
  );
}

import React from 'react';
