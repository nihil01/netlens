import { lazy, Suspense, useEffect, useState } from 'react';
import { Loader2, LogIn } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchInventoryStatus,
  fetchNetBoxDeviceDetail,
  fetchNetBoxInventory,
  resetNetBoxData,
  triggerInventoryRefresh,
} from './api';
import { initAuth, login } from './auth';
import { AppShell } from './components/layout/AppShell';
import { ErrorBoundary } from './components/ErrorBoundary';
import { GraphPage } from './pages/GraphPage';
import { InventoryPage } from './pages/InventoryPage';
import { IpAnalysisPage } from './pages/IpAnalysisPage';
import { MacOuiPage } from './pages/MacOuiPage';
import { ScannerPage } from './pages/ScannerPage';
import { ui } from './lib/ui';
import type { GraphLevels, MainTab } from './types';

const AUTH_ENABLED = import.meta.env.VITE_AUTH_ENABLED === 'true';
const MonitoringPage = lazy(() =>
  import('./pages/MonitoringPage').then((module) => ({ default: module.MonitoringPage })),
);
const AuditPage = lazy(() =>
  import('./pages/AuditPage').then((module) => ({ default: module.AuditPage })),
);

export function App() {
  const queryClient = useQueryClient();
  const [authReady, setAuthReady] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<MainTab>('inventory');
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
  const [selectedRegionName, setSelectedRegionName] = useState<string | null>(null);
  const [inventorySearch, setInventorySearch] = useState('');
  const [graphLevels, setGraphLevels] = useState<GraphLevels>({ region: true, site: true, device: true, interface: true });

  useEffect(() => {
    const handleExpired = () => setLoggedIn(false);
    window.addEventListener('netlens-auth-expired', handleExpired);
    void initAuth()
      .then(setLoggedIn)
      .catch((error) => {
        console.error('Authentication initialization failed:', error);
        setAuthError(
          error instanceof Error ? error.message : 'Keycloak girişini tamamlamaq mümkün olmadı.',
        );
      })
      .finally(() => setAuthReady(true));
    return () => window.removeEventListener('netlens-auth-expired', handleExpired);
  }, []);

  const apiEnabled = !AUTH_ENABLED || loggedIn;

  const inventory = useQuery({
    queryKey: ['netbox-inventory'],
    queryFn: fetchNetBoxInventory,
    enabled: apiEnabled,
  });

  const inventoryStatus = useQuery({
    queryKey: ['inventory-status'],
    queryFn: fetchInventoryStatus,
    refetchInterval: 60_000,
    enabled: apiEnabled,
  });

  async function handleRefreshInventory() {
    try {
      await triggerInventoryRefresh();
      inventory.refetch();
      inventoryStatus.refetch();
    } catch (err) {
      console.error('Inventory refresh failed:', err);
    }
  }

  const netboxReset = useMutation({
    mutationFn: resetNetBoxData,
    onSuccess: async () => {
      setSelectedDeviceId(null);
      await queryClient.invalidateQueries({
        predicate: (query) => {
          const source = query.queryKey[0];
          return typeof source === 'string' && (
            source.startsWith('netbox-') || source === 'inventory-status'
          );
        },
      });
    },
  });

  function handleResetInventory() {
    const confirmed = window.confirm(
      'Bütün lokal NetBox keş məlumatları silinəcək və NetBox-dan yenidən yüklənəcək. Davam edilsin?',
    );
    if (confirmed) netboxReset.mutate();
  }

  const selectedDeviceDetail = useQuery({
    queryKey: ['netbox-device-detail', selectedDeviceId],
    queryFn: () => fetchNetBoxDeviceDetail(selectedDeviceId as number),
    enabled: apiEnabled && selectedDeviceId !== null,
  });

  function selectDevice(deviceId: number) {
    setSelectedDeviceId(deviceId);
    setActiveTab('inventory');
  }

  async function handleLogin() {
    setAuthError(null);
    try {
      await login();
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Keycloak girişini başlatmaq mümkün olmadı.');
    }
  }

  if (!authReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <Loader2 className="mx-auto animate-spin text-blue-600" size={40} />
          <p className="mt-4 text-sm text-gray-500">Yüklənir...</p>
        </div>
      </div>
    );
  }

  if (AUTH_ENABLED && !loggedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-lg">
          <img src="/logo.png" alt="Logo" className="mx-auto mb-4 h-16 w-16 object-contain" />
          <h1 className="text-xl font-bold text-gray-900">NetLens</h1>
          <p className="mt-2 text-sm text-gray-500">Şəbəkə Auditi · NetBox · OpenSearch</p>
          <p className="mt-4 text-sm text-gray-600">Daxil olmaq üçün Keycloak-a keçin</p>
          <button
            type="button"
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            onClick={() => void handleLogin()}
          >
            <LogIn size={16} />
            Daxil ol
          </button>
          {authError && (
            <p className="mt-4 max-w-sm rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {authError}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <AppShell
        activeTab={activeTab}
        onTabChange={setActiveTab}
        inventory={inventory.data}
        authReady={authReady}
        loggedIn={loggedIn}
      >
        {activeTab === 'inventory' && (
          <InventoryPage
            data={inventory.data}
            isLoading={inventory.isLoading}
            isError={inventory.isError}
            error={inventory.error as Error | null}
            selectedDeviceId={selectedDeviceId}
            onSelectDevice={selectDevice}
            onOpenGraph={() => setActiveTab('graph')}
            search={inventorySearch}
            onSearchChange={setInventorySearch}
            selectedRegionName={selectedRegionName}
            onRegionChange={setSelectedRegionName}
            selectedDeviceDetail={{
              data: selectedDeviceDetail.data,
              isLoading: selectedDeviceDetail.isLoading,
              isError: selectedDeviceDetail.isError,
              error: selectedDeviceDetail.error as Error | null,
            }}
            inventoryStatus={inventoryStatus.data}
            onRefreshInventory={handleRefreshInventory}
            onResetInventory={handleResetInventory}
            isResettingInventory={netboxReset.isPending}
            resetInventoryMessage={
              netboxReset.isError
                ? (netboxReset.error as Error).message
                : netboxReset.isSuccess
                  ? `NetBox yenidən yükləndi: ${netboxReset.data.devices_total ?? 0} qurğu`
                  : undefined
            }
            resetInventoryError={netboxReset.isError}
          />
        )}

        {activeTab === 'graph' && (
          <GraphPage
            data={inventory.data}
            selectedRegionName={selectedRegionName}
            onRegionChange={setSelectedRegionName}
            filteredRegions={inventory.data?.regions ?? []}
            graphLevels={graphLevels}
            onGraphLevelsChange={setGraphLevels}
            onSelectDevice={selectDevice}
          />
        )}

        {activeTab === 'scanner' && <ScannerPage />}

        {activeTab === 'mac' && (
          <MacOuiPage
            interfaces={inventory.data?.interfaces ?? []}
            ouiDataset={inventory.data?.oui_dataset}
          />
        )}

        {activeTab === 'ip' && <IpAnalysisPage />}

        {activeTab === 'monitoring' && (
          <Suspense fallback={<div className={ui.panel}>Monitoring modulu yüklənir…</div>}>
            <MonitoringPage />
          </Suspense>
        )}

        {activeTab === 'audit' && (
          <Suspense fallback={<div className={ui.panel}>Audit modulu yüklənir…</div>}>
            <AuditPage />
          </Suspense>
        )}
      </AppShell>
    </ErrorBoundary>
  );
}
