import type {
  NetBoxDevice,
  NetBoxInterface,
  NetBoxRegion,
  NetBoxSite,
} from './api';

export type MainTab = 'inventory' | 'graph' | 'ip' | 'mac';
export type GraphNodeType = 'region' | 'site' | 'device' | 'interface';
export type GraphLifecycle = 'stable' | 'expanding' | 'collapsing';
export type QuickFilter = 'all' | 'active' | 'offline' | 'unknownVendor' | 'interfaceProblems' | 'missingPrimaryIp';
export type GraphLevels = Record<GraphNodeType, boolean>;

export type GraphNode = {
  id: string;
  label: string;
  type: GraphNodeType;
  x: number;
  y: number;
  siteId?: number;
  lifecycle?: GraphLifecycle;
  meta?: NetBoxRegion | NetBoxSite | NetBoxDevice | NetBoxInterface;
};

export type GraphLink = {
  from: string;
  to: string;
  siteId?: number;
  lifecycle?: GraphLifecycle;
};

export type InventoryGraphModel = { nodes: GraphNode[]; links: GraphLink[]; width: number; height: number };

export type RiskSummary = {
  unknownVendor: number;
  interfaceProblems: number;
  missingPrimaryIp: number;
  offlineDevices: number;
};
