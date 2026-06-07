import type { NetBoxDevice, NetBoxInterface, NetBoxSite } from '../api';
import type { GraphLevels, GraphNodeType, InventoryGraphModel } from '../types';

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
  if (count <= 0) {
    return { columns: 0, rows: 0 };
  }

  const columns = clamp(2, Math.ceil(Math.sqrt(count * 1.6)), 8);
  const rows = Math.ceil(count / columns);

  return { columns, rows };
}

export function buildGraph(
  region: string | null,
  sites: NetBoxSite[],
  devices: NetBoxDevice[],
  interfacesByDevice: Map<number, NetBoxInterface[]>,
  levels: GraphLevels,
  expandedDeviceIds: ReadonlySet<number> = new Set(),
): InventoryGraphModel {
  if (!region || !levels.region) {
    return {
      nodes: [],
      links: [],
      width: 1440,
      height: 760,
    };
  }

  const regionY = 92;
  const siteY = 270;
  const deviceY = 500;
  const interfaceY = 705;

  const sitePaddingX = 120;
  const siteGap = 130;
  const deviceGap = 80;
  const interfaceGapX = 150;
  const interfaceGapY = 92;

  const devicesBySite = new Map<string, NetBoxDevice[]>();

  for (const site of sites) {
    devicesBySite.set(
      site.name,
      devices.filter((device) => device.site === site.name),
    );
  }

  let maxInterfaceRows = 0;
  let cursorX = 120;

  const siteLayouts = sites.map((site) => {
    const siteDevices = devicesBySite.get(site.name) ?? [];

    const deviceLayouts = siteDevices.map((device) => {
      const allInterfaces = interfacesByDevice.get(device.id) ?? [];
      const isExpanded = levels.interface && expandedDeviceIds.has(device.id);
      const visibleInterfaces = isExpanded ? allInterfaces : [];

      const { columns, rows } = getInterfaceGrid(visibleInterfaces.length);

      maxInterfaceRows = Math.max(maxInterfaceRows, rows);

      const interfaceBlockWidth =
        columns > 0 ? (columns - 1) * interfaceGapX + 260 : 0;

      const blockWidth = Math.max(220, interfaceBlockWidth);

      return {
        device,
        interfaces: visibleInterfaces,
        columns,
        rows,
        blockWidth,
      };
    });

    const devicesWidth =
      deviceLayouts.reduce((sum, item) => sum + item.blockWidth, 0) +
      Math.max(0, deviceLayouts.length - 1) * deviceGap;

    const laneWidth = Math.max(420, devicesWidth + sitePaddingX * 2);
    const startX = cursorX;
    const centerX = startX + laneWidth / 2;

    cursorX += laneWidth + siteGap;

    return {
      site,
      siteDevices,
      deviceLayouts,
      laneWidth,
      startX,
      centerX,
    };
  });

  const width = Math.max(1440, cursorX + 120);
  const height = Math.max(820, interfaceY + Math.max(1, maxInterfaceRows) * interfaceGapY + 150);
  const centerX = width / 2;

  const nodes: InventoryGraphModel['nodes'] = [
    {
      id: `region:${region}`,
      label: region,
      type: 'region',
      x: centerX,
      y: regionY,
    },
  ];

  const links: InventoryGraphModel['links'] = [];

  for (const siteLayout of siteLayouts) {
    const { site, deviceLayouts, startX, laneWidth, centerX: siteX } = siteLayout;

    const siteNode = {
      id: `site:${site.id}`,
      label: site.name,
      type: 'site' as const,
      x: siteX,
      y: siteY,
      meta: site,
    };

    if (levels.site) {
      nodes.push(siteNode);
      links.push({
        from: `region:${region}`,
        to: siteNode.id,
      });
    }

    if (!levels.device) {
      continue;
    }

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
        meta: device,
      };

      nodes.push(deviceNode);

      links.push({
        from: levels.site ? siteNode.id : `region:${region}`,
        to: deviceNode.id,
      });

      if (levels.interface && expandedDeviceIds.has(device.id)) {
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
            meta: iface,
          };

          nodes.push(ifaceNode);

          links.push({
            from: deviceNode.id,
            to: ifaceNode.id,
          });
        });
      }

      deviceCursorX += blockWidth + deviceGap;
    }
  }

  return {
    nodes,
    links,
    width,
    height,
  };
}