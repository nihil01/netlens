# Community FMC integrations

NetLens reviewed the following community projects and reimplemented the compatible
read-only monitoring ideas against `backend/app/oas/fmc_oas3.json`:

- `gve-sw/gve_devnet_fmc_snort_utilization_network_performance_dashboard` — historical
  `health/metrics` polling with `cpu` / `snort_avg`, safe Prometheus-matrix parsing,
  average/max/latest calculations, and fallback into the normalized Snort CPU metric.
- `veeratcisco/fmc-health-stats` — its device-record, health-alert, authentication, and
  pagination use cases are covered by the existing asynchronous FMC client and collectors.
- `GetCon-Hungary/fmc-analyser` — read-only access-policy and expanded access-rule
  collection, with NetLens-native review counters for broad rules, disabled logging, and
  ALLOW rules without an IPS policy. The analysis is scheduled every 24 hours by default.

No third-party UI, credential handling, file-writing behavior, or configuration-changing
operation was imported. The implementation is original NetLens code so the Cisco Sample
Code and GPL projects are not copied into the application. All FMC operations remain GET-only.

Source projects:

- https://github.com/gve-sw/gve_devnet_fmc_snort_utilization_network_performance_dashboard
- https://github.com/veeratcisco/fmc-health-stats
- https://github.com/GetCon-Hungary/fmc-analyser
