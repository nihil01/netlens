import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, Database, Radar, Search, ShieldCheck } from 'lucide-react';
import { fetchIpSummary } from './api';

function isLikelyIp(value: string): boolean {
  return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(value.trim());
}

export function App() {
  const [input, setInput] = useState('10.255.127.60');
  const [ip, setIp] = useState('10.255.127.60');

  const summary = useQuery({
    queryKey: ['ip-summary', ip],
    queryFn: () => fetchIpSummary(ip),
    enabled: isLikelyIp(ip),
  });

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
            Быстрый контекст по IP: NetBox inventory, scan status и OpenSearch activity без ручного копания по логам.
          </p>
        </div>
        <div className="status-pill"><ShieldCheck size={18} /> SSO-ready MVP</div>
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
