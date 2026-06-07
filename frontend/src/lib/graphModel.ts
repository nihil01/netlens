import type { NetBoxDevice, NetBoxInterface, NetBoxSite } from '../api';
import type { GraphLevels, GraphLifecycle, GraphNodeType, InventoryGraphModel } from '../types';

export const GRAPH_LEVEL_LABELS: Record<GraphNodeType, string> = {
  region: 'Region',
  site: 'Sahə',
  device: 'Qurğu',
  interface: 'İnterfeys',
};

export function nodeColor(type: GraphNodeType): string {
  return {
    region: '#e0f2fe',
    site: '#ede9fe',
    device: '#dcfce7',
    interface: '#fef3c7',
  }[type];
}

export function iconColor(type: GraphNodeType): string {
  return {
    region: '#0369a1',
    site: '#6d28d9',
    device: '#15803d',
    interface: '#b45309',
  }[type];
}

function clamp(min: number, value: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function getInterfaceGrid(count: number): { columns: number; rows: number } {
  if (count <= 0) return { columns: 0, rows: 0 };
  const columns = clamp(2, Math.ceil(Math.sqrt(count * 1.35)), 7);
  return { columns, rows: Math.ceil(count / columns) };
}

function getExpandedLifecycle(
  siteId: number,
  expandedSiteId: number | null,
  collapsingSiteId: number | null,
): GraphLifecycle | null {
  if (siteId === collapsingSiteId) return 'collapsing';
  if (siteId === expandedSiteId) return 'expanding';
  return null;
}

export function buildGraph(
  region: string | null,
  sites: NetBoxSite[],
  devices: NetBoxDevice[],
  interfacesByDevice: Map<number, NetBoxInterface[]>,
  levels: GraphLevels,
  expandedSiteId: number | null = null,
  collapsingSiteId: number | null = null,
): InventoryGraphModel {
  if (!region || !levels.region) {
    return { nodes: [], links: [], width: 1440, height: 760 };
  }

  const regionY = 92;
  const siteY = 285;
  const deviceY = 505;
  const interfaceY = 700;
  const siteGap = 128;
  const sitePaddingX = 112;
  const deviceGap = 96;
  const interfaceGapX = 132;
  const interfaceGapY = 84;

  const devicesBySite = new Map<string, NetBoxDevice[]>();
  for (const site of sites) {
    devicesBySite.set(site.name, devices.filter((device) => device.site === site.name));
  }

  let cursorX = 120;
  let maxInterfaceRows = 0;

  const siteLayouts = sites.map((site) => {
    const siteDevices = devicesBySite.get(site.name) ?? [];
    const lifecycle = getExpandedLifecycle(site.id, expandedSiteId, collapsingSiteId);
    const showChildren = lifecycle !== null && levels.device;

    const deviceLayouts = showChildren
      ? siteDevices.map((device) => {
          const interfaces = levels.interface ? interfacesByDevice.get(device.id) ?? [] : [];
          const { columns, rows } = getInterfaceGrid(interfaces.length);
          maxInterfaceRows = Math.max(maxInterfaceRows, rows);
          const interfaceBlockWidth = columns > 0 ? (columns - 1) * interfaceGapX + 180 : 0;
          return {
            device,
            interfaces,
            columns,
            rows,
            blockWidth: Math.max(190, interfaceBlockWidth),
          };
        })
      : [];

    const devicesWidth =
      deviceLayouts.reduce((sum, item) => sum + item.blockWidth, 0) +
      Math.max(0, deviceLayouts.length - 1) * deviceGap;
    const laneWidth = Math.max(250, devicesWidth + sitePaddingX * 2);
    const startX = cursorX;
    const centerX = startX + laneWidth / 2;
    cursorX += laneWidth + siteGap;

    return { site, lifecycle, deviceLayouts, startX, laneWidth, centerX };
  });

  const width = Math.max(1440, cursorX + 120);
  const height = Math.max(700, interfaceY + Math.max(0, maxInterfaceRows - 1) * interfaceGapY + 150);
  const centerX = width / 2;
  const nodes: InventoryGraphModel['nodes'] = [
    { id: `region:${region}`, label: region, type: 'region', x: centerX, y: regionY },
  ];
  const links: InventoryGraphModel['links'] = [];

  for (const siteLayout of siteLayouts) {
    const { site, lifecycle, deviceLayouts, startX, centerX: siteX } = siteLayout;
    const siteNode = {
      id: `site:${site.id}`,
      label: site.name,
      type: 'site' as const,
      x: siteX,
      y: siteY,
      siteId: site.id,
      lifecycle: lifecycle ?? ('stable' as const),
      meta: site,
    };

    if (levels.site) {
      nodes.push(siteNode);
      links.push({ from: `region:${region}`, to: siteNode.id, siteId: site.id });
    }

    if (!lifecycle || !levels.device) continue;

    let deviceCursorX = startX + sitePaddingX;
    for (const deviceLayout of deviceLayouts) {
      const { device, interfaces, columns, blockWidth } = deviceLayout;
      const deviceX = deviceCursorX + blockWidth / 2;
      const deviceNode = {
        id: `device:${device.id}`,
        label: device.name,
        type: 'device' as const,
        x: deviceX,
        y: deviceY,
        siteId: site.id,
        lifecycle,
        meta: device,
      };

      nodes.push(deviceNode);
      links.push({ from: levels.site ? siteNode.id : `region:${region}`, to: deviceNode.id, siteId: site.id, lifecycle });

      if (levels.interface) {
        const gridWidth = columns > 0 ? (columns - 1) * interfaceGapX : 0;
        const interfaceStartX = deviceX - gridWidth / 2;

        interfaces.forEach((iface, ifaceIndex) => {
          const column = columns > 0 ? ifaceIndex % columns : 0;
          const row = columns > 0 ? Math.floor(ifaceIndex / columns) : 0;
          const ifaceNode = {
            id: `interface:${iface.id}`,
            label: iface.name,
            type: 'interface' as const,
            x: interfaceStartX + column * interfaceGapX,
            y: interfaceY + row * interfaceGapY,
            siteId: site.id,
            lifecycle,
            meta: iface,
          };
          nodes.push(ifaceNode);
          links.push({ from: deviceNode.id, to: ifaceNode.id, siteId: site.id, lifecycle });
        });
      }

      deviceCursorX += blockWidth + deviceGap;
    }
  }

  return { nodes, links, width, height };
}
