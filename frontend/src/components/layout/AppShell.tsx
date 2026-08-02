import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import {
  Boxes,
  LogIn,
  LogOut,
  MapPinned,
  Layers3,
  Radar,
  ScanLine,
  Server,
  Shield,
  User,
  History,
  Waypoints,
} from 'lucide-react';
import type { NetBoxInventory } from '../../api';
import { getUser, login, logout } from '../../auth';
import { TabButton } from '../common';
import { motionPreset, ui } from '../../lib/ui';
import type { MainTab } from '../../types';

type AppShellProps = {
  activeTab: MainTab;
  onTabChange: (tab: MainTab) => void;
  inventory: NetBoxInventory | undefined;
  authReady: boolean;
  loggedIn: boolean;
  children: ReactNode;
};

const TABS: { key: MainTab; label: string; icon: ReactNode }[] = [
  { key: 'inventory', label: 'İnventar', icon: <Boxes size={16} /> },
  { key: 'graph', label: 'Qraf', icon: <Waypoints size={16} /> },
  { key: 'mac', label: 'MAC/OUI', icon: <Radar size={16} /> },
  { key: 'scanner', label: 'Skan', icon: <ScanLine size={16} /> },
  { key: 'ip', label: 'IP analizi', icon: <Radar size={16} /> },
  { key: 'monitoring', label: 'Monitoring', icon: <Shield size={16} /> },
  { key: 'audit', label: 'FMC Audit', icon: <History size={16} /> },
];

export function AppShell({ activeTab, onTabChange, inventory, authReady, loggedIn, children }: AppShellProps) {
  const user = getUser();

  return (
    <main className={ui.appShell}>
      {/* Header */}
      <motion.header {...motionPreset.page}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="Logo" className="h-10 w-10 object-contain" />
            <div>
              <h1 className="text-xl font-bold text-gray-900">NetLens</h1>
              <p className="text-sm text-gray-500">Şəbəkə Auditi · NetBox · OpenSearch</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-4 text-xs text-gray-400">
              <span className="flex items-center gap-1"><MapPinned size={14} /> {inventory?.regions.length ?? 0} region</span>
              <span className="flex items-center gap-1"><Layers3 size={14} /> {inventory?.sites.length ?? 0} sahə</span>
              <span className="flex items-center gap-1" title="NetBox inventory"><Server size={14} /> NetBox: {inventory?.devices.length ?? 0} qurğu</span>
            </div>
            {authReady && (
              loggedIn ? (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1 text-sm text-gray-600">
                    <User size={14} />
                    {user?.preferred_username ?? user?.sub}
                  </span>
                  <button className={ui.ghostButton} onClick={logout}>
                    <LogOut size={14} /> Çıxış
                  </button>
                </div>
              ) : (
                <button className={ui.primaryButton} onClick={() => void login()}>
                  <LogIn size={14} /> Giriş
                </button>
              )
            )}
          </div>
        </div>
      </motion.header>

      {/* Tabs */}
      <nav className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
        {TABS.map((tab) => (
          <TabButton
            key={tab.key}
            active={activeTab === tab.key}
            icon={tab.icon}
            onClick={() => onTabChange(tab.key)}
          >
            {tab.label}
          </TabButton>
        ))}
      </nav>

      {children}
    </main>
  );
}
