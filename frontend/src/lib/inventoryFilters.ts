import type { NetBoxDevice, NetBoxInterface, NetBoxRegion, NetBoxSite } from '../api';
import type { QuickFilter } from '../types';
import { containsValue } from './format';

export function interfaceHasProblem(item: NetBoxInterface): boolean {
  return item.enabled === false || (!!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown'));
}

export function devicePassesFilters(device: NetBoxDevice, interfaces: NetBoxInterface[], needle: string, filter: QuickFilter): boolean {
  const matchesSearch = [device.name, device.site, device.region, device.role, device.device_type, device.manufacturer, device.status, device.primary_ip]
    .some((value) => containsValue(value, needle))
    || interfaces.some((item) => interfaceMatchesSearch(item, needle));
  if (!matchesSearch) return false;
  if (filter === 'active') return (device.status ?? '').toLowerCase() === 'active';
  if (filter === 'offline') return (device.status ?? '').toLowerCase() === 'offline';
  if (filter === 'unknownVendor') return interfaces.some((item) => !!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown'));
  if (filter === 'interfaceProblems') return interfaces.some(interfaceHasProblem);
  if (filter === 'missingPrimaryIp') return !device.primary_ip;
  return true;
}

export function interfaceMatchesSearch(item: NetBoxInterface, needle: string): boolean {
  return [item.name, item.device, item.type, item.mac_address, item.mac_vendor, item.mac_oui, item.description, item.mode, item.untagged_vlan]
    .some((value) => containsValue(value, needle));
}

export function interfacePassesFilters(item: NetBoxInterface, devices: NetBoxDevice[], needle: string, filter: QuickFilter): boolean {
  const relatedDevice = devices.find((device) => device.id === item.device_id);
  const matchesSearch = interfaceMatchesSearch(item, needle) || (relatedDevice ? containsValue(relatedDevice.name, needle) : false);
  if (!matchesSearch) return false;
  if (filter === 'unknownVendor') return !!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown');
  if (filter === 'interfaceProblems') return interfaceHasProblem(item);
  if (filter === 'active') return item.enabled !== false;
  if (filter === 'offline') return item.enabled === false || (relatedDevice?.status ?? '').toLowerCase() === 'offline';
  if (filter === 'missingPrimaryIp') return relatedDevice ? !relatedDevice.primary_ip : false;
  return true;
}

export function sitePassesFilters(site: NetBoxSite, devices: NetBoxDevice[], interfaces: NetBoxInterface[], needle: string, filter: QuickFilter): boolean {
  const siteDevices = devices.filter((device) => device.site === site.name);
  const siteInterfaces = interfaces.filter((item) => item.device && siteDevices.some((device) => device.name === item.device));
  const matchesSearch = [site.name, site.region, site.status, site.facility, site.physical_address].some((value) => containsValue(value, needle))
    || siteDevices.length > 0
    || siteInterfaces.length > 0;
  if (!matchesSearch) return false;
  return filter === 'all' || siteDevices.length > 0 || siteInterfaces.length > 0;
}

export function regionPassesFilters(region: NetBoxRegion, sites: NetBoxSite[], devices: NetBoxDevice[], needle: string, filter: QuickFilter): boolean {
  const regionSites = sites.filter((site) => site.region === region.name);
  const regionDevices = devices.filter((device) => device.region === region.name);
  const matchesSearch = [region.name, region.slug, region.description].some((value) => containsValue(value, needle))
    || regionSites.length > 0
    || regionDevices.length > 0;
  if (!matchesSearch) return false;
  return filter === 'all' || regionSites.length > 0 || regionDevices.length > 0;
}

export function buildRiskSummary(devices: NetBoxDevice[], interfaces: NetBoxInterface[]) {
  return {
    unknownVendor: interfaces.filter((item) => !!item.mac_address && (!item.mac_vendor || item.mac_vendor_source === 'unknown')).length,
    interfaceProblems: interfaces.filter(interfaceHasProblem).length,
    missingPrimaryIp: devices.filter((device) => !device.primary_ip).length,
    offlineDevices: devices.filter((device) => (device.status ?? '').toLowerCase() === 'offline').length,
  };
}
