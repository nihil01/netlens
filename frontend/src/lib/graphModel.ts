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

export function buildGraph(
  region: string | null,
  sites: NetBoxSite[],
  devices: NetBoxDevice[],
  interfacesByDevice: Map<number, NetBoxInterface[]>,
  levels: GraphLevels,
): InventoryGraphModel {
  if (!region || !levels.region) return { nodes: [], links: [], width: 1440, height: 760 };

  const maxSiteDevices = Math.max(1, ...sites.map((site) => devices.filter((device) => device.site === site.name).length));
  const maxDeviceInterfaces = Math.max(1, ...devices.map((device) => (interfacesByDevice.get(device.id) ?? []).length));
  const siteGap = Math.max(280, Math.min(420, 260 + maxSiteDevices * 12));
  const deviceGap = 128;
  const siteLaneWidth = Math.max(siteGap, maxSiteDevices * deviceGap + 160);
  const width = Math.max(1440, sites.length * siteLaneWidth + 220);
  const height = Math.max(820, 720 + maxDeviceInterfaces * 74);
  const centerX = width / 2;

  const nodes: InventoryGraphModel['nodes'] = [{ id: `region:${region}`, label: region, type: 'region', x: centerX, y: 92 }];
  const links: InventoryGraphModel['links'] = [];

  sites.forEach((site, siteIndex) => {
    const siteX = 110 + siteLaneWidth * siteIndex + siteLaneWidth / 2;
    const siteNode = { id: `site:${site.id}`, label: site.name, type: 'site' as const, x: siteX, y: 270, meta: site };
    if (levels.site) {
      nodes.push(siteNode);
      links.push({ from: `region:${region}`, to: siteNode.id });
    }

    if (!levels.device) return;
    const siteDevices = devices.filter((device) => device.site === site.name);
    const startX = siteX - ((siteDevices.length - 1) * deviceGap) / 2;

    siteDevices.forEach((device, deviceIndex) => {
      const deviceX = Math.max(70, startX + deviceIndex * deviceGap);
      const deviceNode = {
        id: `device:${device.id}`,
        label: device.name,
        type: 'device' as const,
        x: deviceX,
        y: 490,
        meta: device,
      };
      nodes.push(deviceNode);
      links.push({ from: levels.site ? siteNode.id : `region:${region}`, to: deviceNode.id });

      if (!levels.interface) return;
      const ifaces = interfacesByDevice.get(device.id) ?? [];
      ifaces.forEach((iface, ifaceIndex) => {
        const sideOffset = ifaceIndex % 2 === 0 ? -34 : 34;
        const ifaceNode = {
          id: `interface:${iface.id}`,
          label: iface.name,
          type: 'interface' as const,
          x: deviceX + sideOffset,
          y: 680 + ifaceIndex * 74,
          meta: iface,
        };
        nodes.push(ifaceNode);
        links.push({ from: deviceNode.id, to: ifaceNode.id });
      });
    });
  });

  return { nodes, links, width, height };
}
