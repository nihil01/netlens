import { FormEvent, ReactNode, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Database,
  Layers3,
  MapPinned,
  Network,
  Radar,
  Search,
  Server,
  ShieldCheck,
} from 'lucide-react';
import {
  fetchIpSummary,
  fetchNetBoxDeviceDetail,
  fetchNetBoxInventory,
  type NetBoxDevice,
  type NetBoxInterface,
} from './api';

function isLikelyIp(value: string): boolean {
  return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(value.trim());
}

function emptyLabel(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

function statusClass(status: string | null | undefined): string {
  if (!status) return 'muted';
  const normalized = status.toLowerCase();
  if (['active', 'online', 'ok'].includes(normalized)) return 'good';
  if (['planned', 'staged', 'offline'].includes(normalized)) return 'warn';
  return 'muted';
}

export function App() {
  const [input, setInput] = useState('10.255.127.60');
  const [ip, setIp] = useState('10.255.127.60');
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);

  const summary = useQuery({
    queryKey: ['ip-summary', ip],
    queryFn: () => fetchIpSummary(ip),
    enabled: isLikelyIp(ip),
  });

  const inventory = useQuery({
    queryKey: ['netbox-inventory'],
    queryFn: fetchNetBoxInventory,
  });

  const selectedDeviceDetail = useQuery({
    queryKey: ['netbox-device-detail', selectedDeviceId],
    queryFn: () => fetchNetBoxDeviceDetail(selectedDeviceId as number),
    enabled: selectedDeviceId !== null,
  });

  const selectedDevice = useMemo(() => {
    if (!selectedDeviceId) return null;
    return inventory.data?.devices.find((device) => device.id === selectedDeviceId) ?? null;
  }, [inventory.data?.devices, selectedDeviceId]);

  const interfacesByDevice = useMemo(() => {
    const grouped = new Map<number, NetBoxInterface[]>();
    for (const item of inventory.data?.interfaces ?? []) {
      if (!item.device_id) continue;
      grouped.set(item.device_id, [...(grouped.get(item.device_id) ?? []), item]);
    }
    return grouped;
  }, [inventory.data?.interfaces]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIp(input.trim());
  }

  return (
    <main className="shell">
      <section className="hero">
        <div>
          <p className="eyebrow">Network Intelligence Platform</p>
          <h1>NetLens</h1>
          <p className="subtitle">
            Один экран для NetBox inventory, IP context, scan status и OpenSearch activity. Списки NetBox тянем live, тяжелые детали девайса кешируем в Redis по ключу device id.
          </p>
        </div>
        <div className="status-pill"><ShieldCheck size={18} /> SSO-ready MVP</div>
      </section>

      <section className="overview-grid">
        <MetricCard icon={<MapPinned size={20} />} label="Regions" value={inventory.data?.regions.length ?? 0} />
        <MetricCard icon={<Layers3 size={20} />} label="Sites" value={inventory.data?.sites.length ?? 0} />
        <MetricCard icon={<Server size={20} />} label="Devices" value={inventory.data?.devices.length ?? 0} />
        <MetricCard icon={<Network size={20} />} label="Interfaces" value={inventory.data?.interfaces.length ?? 0} />
      </section>

      {inventory.isLoading && <div className="panel">Загружаю NetBox inventory...</div>}
      {inventory.isError && <div className="panel error">NetBox inventory error: {(inventory.error as Error).message}</div>}
      {inventory.data?.status.status !== 'ok' && (
        <div className="panel warning">NetBox status: {inventory.data?.status.message ?? inventory.data?.status.status}</div>
      )}

      <section className="inventory-layout">
        <article className="panel">
          <div className="panel-title"><MapPinned size={20} /> Regions / Sites</div>
          <div className="split-list">
            <div>
              <h3>Regions</h3>
              <ul className="compact-list">
                {(inventory.data?.regions ?? []).map((region) => (
                  <li key={region.id}><b>{region.name}</b><span>{region.slug ?? 'no-slug'}</span></li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Sites</h3>
              <ul className="compact-list">
                {(inventory.data?.sites ?? []).map((site) => (
                  <li key={site.id}>
                    <b>{site.name}</b>
                    <span>{emptyLabel(site.region)} · {emptyLabel(site.status)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </article>

        <article className="panel devices-panel">
          <div className="panel-title"><Server size={20} /> Devices</div>
          <div className="device-list">
            {(inventory.data?.devices ?? []).map((device) => (
              <DeviceRow
                key={device.id}
                device={device}
                interfaceCount={interfacesByDevice.get(device.id)?.length ?? 0}
                selected={device.id === selectedDeviceId}
                onSelect={() => setSelectedDeviceId(device.id)}
              />
            ))}
          </div>
        </article>

        <article className="panel detail-panel">
          <div className="panel-title"><Database size={20} /> Device details cache</div>
          {!selectedDevice && <p className="muted-text">Выбери девайс слева — подробные данные придут через cached endpoint.</p>}
          {selectedDeviceDetail.isLoading && <p>Загружаю detail...</p>}
          {selectedDeviceDetail.isError && <p className="error-text">{(selectedDeviceDetail.error as Error).message}</p>}
          {selectedDeviceDetail.data && (
            <>
              <div className="cache-line">
                <span className={selectedDeviceDetail.data.cache.hit ? 'badge good' : 'badge warn'}>
                  Redis cache: {selectedDeviceDetail.data.cache.hit ? 'hit' : 'miss'}
                </span>
                <code>{String(selectedDeviceDetail.data.cache.key ?? '')}</code>
              </div>
              <dl>
                <dt>Name</dt><dd>{selectedDeviceDetail.data.name}</dd>
                <dt>Site / Region</dt><dd>{emptyLabel(selectedDeviceDetail.data.site)} / {emptyLabel(selectedDeviceDetail.data.region)}</dd>
                <dt>Role</dt><dd>{emptyLabel(selectedDeviceDetail.data.role)}</dd>
                <dt>Type</dt><dd>{emptyLabel(selectedDeviceDetail.data.manufacturer)} {emptyLabel(selectedDeviceDetail.data.device_type)}</dd>
                <dt>Platform</dt><dd>{emptyLabel(selectedDeviceDetail.data.platform)}</dd>
                <dt>Serial</dt><dd>{emptyLabel(selectedDeviceDetail.data.serial)}</dd>
                <dt>Primary IP</dt><dd>{emptyLabel(selectedDeviceDetail.data.primary_ip)}</dd>
              </dl>
              <InterfaceList interfaces={selectedDeviceDetail.data.interfaces} />
            </>
          )}
        </article>
      </section>

      <form className="search-card" onSubmit={submit}>
        <Search size={22} />
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="10.255.127.60" />
        <button type="submit">Analyze IP</button>
      </form>

      {summary.isLoading && <div className="panel">Загружаю summary...</div>}
      {summary.isError && <div className="panel error">Ошибка: {(summary.error as Error).message}</div>}

      {summary.data && (
        <section className="grid">
          <article className="panel wide">
            <div className="panel-title"><Database size={20} /> NetBox Context</div>
            <dl>
              <dt>IP</dt><dd>{summary.data.ip}</dd>
              <dt>Known</dt><dd>{summary.data.netbox.known ? 'yes' : 'no'}</dd>
              <dt>Device</dt><dd>{summary.data.netbox.device ?? '—'}</dd>
              <dt>Site</dt><dd>{summary.data.netbox.site ?? '—'}</dd>
              <dt>Region / City</dt><dd>{summary.data.netbox.region ?? '—'} / {summary.data.netbox.city ?? '—'}</dd>
              <dt>Role</dt><dd>{summary.data.netbox.role ?? '—'}</dd>
            </dl>
            <InterfaceList interfaces={summary.data.netbox.interfaces as NetBoxInterface[]} />
          </article>

          <article className="panel">
            <div className="panel-title"><Radar size={20} /> Scan</div>
            <div className="metric">{summary.data.scan.status}</div>
            <p>Ports: {summary.data.scan.open_ports.length ? summary.data.scan.open_ports.join(', ') : 'not scanned yet'}</p>
            <p>OS: {summary.data.scan.os_guess ?? 'unknown'}</p>
          </article>

          <article className="panel">
            <div className="panel-title"><Activity size={20} /> Activity / {summary.data.activity.window}</div>
            <div className="cards">
              <span><b>{summary.data.activity.internal_connections}</b> internal</span>
              <span><b>{summary.data.activity.external_connections}</b> external</span>
              <span><b>{summary.data.activity.security_events}</b> security</span>
            </div>
            <h3>Top internal destinations</h3>
            <ul>
              {summary.data.activity.top_internal_destinations.map((item) => (
                <li key={`${item.ip}-${item.port}`}>{item.ip}:{item.port ?? '*'} — {item.count}</li>
              ))}
            </ul>
          </article>
        </section>
      )}
    </main>
  );
}

function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <article className="metric-card">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </article>
  );
}

function DeviceRow({
  device,
  interfaceCount,
  selected,
  onSelect,
}: {
  device: NetBoxDevice;
  interfaceCount: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button className={`device-row ${selected ? 'selected' : ''}`} type="button" onClick={onSelect}>
      <span>
        <b>{device.name}</b>
        <small>{emptyLabel(device.site)} · {emptyLabel(device.role)} · {interfaceCount} ifaces</small>
      </span>
      <em className={statusClass(device.status)}>{emptyLabel(device.status)}</em>
    </button>
  );
}

function InterfaceList({ interfaces }: { interfaces: NetBoxInterface[] }) {
  if (!interfaces.length) return <p className="muted-text">Interfaces: none</p>;

  return (
    <div className="interface-table">
      <h3>Interfaces</h3>
      {interfaces.map((item) => (
        <div className="interface-row" key={item.id ?? item.name}>
          <b>{item.name}</b>
          <span>{emptyLabel(item.type)}</span>
          <span>{item.enabled ? 'enabled' : 'disabled'}</span>
          <span>{emptyLabel(item.mac_address)}</span>
          <small>{emptyLabel(item.description)}</small>
        </div>
      ))}
    </div>
  );
}
