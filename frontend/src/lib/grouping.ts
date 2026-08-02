import type { NetBoxDevice, NetBoxInterface, NetBoxSite } from '../api';

export function groupInterfacesByDevice(interfaces: NetBoxInterface[]) {
  const grouped = new Map<number, NetBoxInterface[]>();
  for (const item of interfaces) {
    if (!item.device_id) continue;
    grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]);
  }
  return grouped;
}

export function groupSitesByRegion(sites: NetBoxSite[]) {
  const grouped = new Map<string, NetBoxSite[]>();
  for (const site of sites) {
    if (!site.region) continue;
    grouped.set(site.region, [...(grouped.get(site.region) ?? []), site]);
  }
  return grouped;
}

export function groupDevicesBySite(devices: NetBoxDevice[]) {
  const grouped = new Map<string, NetBoxDevice[]>();
  for (const device of devices) {
    if (!device.site) continue;
    grouped.set(device.site, [...(grouped.get(device.site) ?? []), device]);
  }
  return grouped;
}
