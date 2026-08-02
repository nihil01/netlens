import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Eye, FileWarning, Info, Search, ShieldCheck } from 'lucide-react';
import { fetchPolicyAnalysis } from '../../api';
import type { PolicySummary } from '../../api';
import { cn, ui } from '../../lib/ui';

const metrics = [
  { key: 'total_policies', label: 'Access policies yoxlanılıb', icon: ShieldCheck, tone: 'text-blue-600 bg-blue-50' },
  { key: 'enabled_rules', label: 'Aktiv qaydalar', icon: CheckCircle2, tone: 'text-emerald-600 bg-emerald-50' },
  { key: 'rules_without_logging', label: 'Log olmayan aktiv qaydalar', icon: FileWarning, tone: 'text-amber-600 bg-amber-50' },
  { key: 'allow_rules_without_ips_policy', label: 'IPS olmayan aktiv ALLOW', icon: AlertTriangle, tone: 'text-red-600 bg-red-50' },
] as const;

function reviewPriority(policy: PolicySummary) {
  const broadBoth = policy.rules_with_any_source > 0 && policy.rules_with_any_destination > 0;
  if (policy.allow_rules_without_ips_policy > 0 || broadBoth) return { label: 'Yüksək', tone: 'bg-red-50 text-red-700 border-red-200', rank: 2 };
  const findings = policy.rules_without_logging
    + policy.rules_with_any_source
    + policy.rules_with_any_destination
    + policy.rules_with_any_destination_port;
  if (findings > 0) return { label: 'Orta', tone: 'bg-amber-50 text-amber-700 border-amber-200', rank: 1 };
  return { label: 'Aşağı', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200', rank: 0 };
}

export function PolicyAnalysisPanel() {
  const [search, setSearch] = useState('');
  const query = useQuery({
    queryKey: ['fmc-policy-analysis'],
    queryFn: fetchPolicyAnalysis,
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });
  const data = query.data;
  const policies = useMemo(() => {
    if (!data) return [];
    const needle = search.trim().toLocaleLowerCase();
    return [...data.policies]
      .filter((policy) => !needle || policy.name?.toLocaleLowerCase().includes(needle))
      .sort((a, b) => reviewPriority(b).rank - reviewPriority(a).rank || b.total_rules - a.total_rules);
  }, [data, search]);
  if (query.isLoading) return <div className={ui.panel}>Policy analysis yüklənir…</div>;
  if (query.isError) return <div className={cn(ui.panel, 'text-red-600')}>Policy analysis əlçatan deyil</div>;
  if (!data?.total_policies) return <div className={ui.panel}>Policy analysis hələ toplanmayıb.</div>;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        <div className="flex items-start gap-3">
          <Eye className="mt-0.5 shrink-0" size={18} />
          <div>
            <h2 className="font-bold">Policy Review nə üçündür?</h2>
            <p className="mt-1 text-xs leading-5 text-blue-800">
              Bu, FMC Access Control Policy qaydalarının yalnız oxuma rejimində ilkin risk yoxlamasıdır. Heç nə dəyişmir və “policy təhlükəsizdir” qərarı vermir — manual review tələb edən policy-ləri önə çıxarır.
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ key, label, icon: Icon, tone }) => (
          <div key={key} className={ui.panel}>
            <div className={cn('inline-flex rounded-lg p-2', tone)}><Icon size={16} /></div>
            <div className="mt-3 text-2xl font-bold">{data[key]}</div>
            <div className="text-xs text-gray-500">{label}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-4">
        {[
          { label: 'Any source', value: data.rules_with_any_source, description: 'Mənbə şəbəkəsi məhdudlaşdırılmayıb.' },
          { label: 'Any destination', value: data.rules_with_any_destination, description: 'Təyinat şəbəkəsi məhdudlaşdırılmayıb.' },
          { label: 'Any destination port', value: data.rules_with_any_destination_port, description: 'Təyinat portu/service məhdudlaşdırılmayıb.' },
          { label: 'Disabled rules', value: data.disabled_rules, description: 'Risk deyil; təmizləmə üçün köhnə qaydaları göstərə bilər.' },
        ].map((finding) => (
          <div key={finding.label} className={ui.panel}>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700"><Info size={12} />{finding.label}</div>
            <div className="mt-2 text-xl font-bold">{finding.value}</div>
            <p className="mt-1 text-[11px] leading-4 text-gray-500">{finding.description}</p>
          </div>
        ))}
      </div>

      <div className={cn(ui.panel, 'overflow-hidden p-0')}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
          <div>
            <h3 className="font-semibold">Policy üzrə review növbəsi</h3>
            <p className="text-[11px] text-gray-500">Yüksək prioritet əvvəl göstərilir. Saylar eyni qaydanı bir neçə kateqoriyada əhatə edə bilər.</p>
          </div>
          <label className="relative">
            <Search className="absolute left-2.5 top-2.5 text-gray-400" size={13} />
            <input className={cn(ui.input, 'w-64 py-2 pl-8 text-xs')} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Policy adı ilə axtar…" />
          </label>
        </div>
        <div className="max-h-[520px] overflow-auto">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="sticky top-0 bg-gray-50 text-[10px] uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2">Policy</th>
                <th className="px-3 py-2 text-right">Rules</th>
                <th className="px-3 py-2 text-right">No log</th>
                <th className="px-3 py-2 text-right">ALLOW no IPS</th>
                <th className="px-3 py-2 text-right">Any source</th>
                <th className="px-3 py-2 text-right">Any destination</th>
                <th className="px-3 py-2 text-right">Any port</th>
                <th className="px-4 py-2">Review priority</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {policies.map((policy) => {
                const priority = reviewPriority(policy);
                return (
                  <tr key={policy.policy_id || policy.name} className="hover:bg-gray-50/70">
                    <td className="max-w-72 px-4 py-2.5 font-semibold text-gray-900"><div className="truncate" title={policy.name || undefined}>{policy.name || policy.policy_id || 'Unnamed policy'}</div></td>
                    <td className="px-3 py-2.5 text-right">{policy.total_rules}</td>
                    <td className="px-3 py-2.5 text-right text-amber-700">{policy.rules_without_logging}</td>
                    <td className="px-3 py-2.5 text-right font-semibold text-red-700">{policy.allow_rules_without_ips_policy}</td>
                    <td className="px-3 py-2.5 text-right">{policy.rules_with_any_source}</td>
                    <td className="px-3 py-2.5 text-right">{policy.rules_with_any_destination}</td>
                    <td className="px-3 py-2.5 text-right">{policy.rules_with_any_destination_port}</td>
                    <td className="px-4 py-2.5"><span className={cn('rounded-full border px-2 py-1 text-[10px] font-bold', priority.tone)}>{priority.label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!policies.length && <div className="p-8 text-center text-sm text-gray-400">Uyğun policy tapılmadı.</div>}
        </div>
      </div>
    </div>
  );
}
