# NetLens — FMC Integration Full Flow

## Архитектура (4 слоя)

```
API Route → Service → Collector → Client → FMC REST API
```

| Слой | Файл | Роль |
|------|------|------|
| **API Route** | `app/api/routes/monitoring.py` | HTTP endpoint для фронтенда |
| **Service** | `app/integrations/fmc/service.py` | Тонкая обёртка, делегирует коллектору |
| **Collector** | `app/integrations/fmc/collector.py` | Оркестрирует сбор: один токен → discovery → collect per device → normalize |
| **Client** | `app/integrations/fmc/client.py` | HTTP-клиент: auth, GET с retry/backoff, пагинация |

---

## 1. Конфигурация

Настройки в `app/core/config.py` (строки 103–108):

```python
fmc_url: str = "https://10.19.254.200/api"
fmc_username: str = "orxan.n"
fmc_password: str = ""  # required from the FMC_PASSWORD environment variable
fmc_verify_ssl: bool = False
fmc_monitoring_enabled: bool = True
```

Загружаются из `.env` файла через `pydantic-settings`. Singleton через `@lru_cache get_settings()`.

---

## 2. Аутентификация

**Метод:** `FmcClient.authenticate()` — `client.py:62-82`

```
POST /api/fmc_platform/v1/auth/generatetoken
Authorization: Basic base64(username:password)
```

**Ответ (Headers):**
- `X-auth-access-token` → сохраняется в `self._token`
- `X-auth-refresh-token` → сохраняется в `self._refresh_token`
- `DOMAIN_UUID` → сохраняется в `self._domain_uuid`

**Поведение:**
- Если токен уже есть — повторная авторизация НЕ делается (early return)
- Токен используется для всех последующих GET-запросов через заголовок `X-auth-access-token`

---

## 3. Построение URL

Все URL строятся через хелперы `client.py:188-195`:

```python
_cfg(ep)     → /api/fmc_config/v1/domain/{domain_uuid}{ep}
_health(ep)  → /api/fmc_config/v1/domain/{domain_uuid}/health{ep}
_platform(ep)→ /api/fmc_platform/v1/domain/{domain_uuid}{ep}
```

---

## 4. Discovery — Получение списков

**Метод:** `FmcCollector.collect()` — `collector.py:48-116`

После авторизации запрашиваются три вещи:

```python
devices_raw  = await client.get_devices()       # все FTD-устройства
ha_pairs_raw = await client.get_ha_pairs()       # HA-пары (FTD Device HA)
chassis_raw  = await client.get_chassis_list()   # управляемые шасси (Firepower 9000)
```

Каждый вызов — это `get_all()` (`client.py:158-175`) — paginated GET:

```
GET /api/fmc_config/v1/domain/{domain}/devices/devicerecords?offset=0&limit=1000&expanded=true
```

**Логика пагинации:**
1. Начинает с `offset=0`, `limit=1000`
2. Добавляет `expanded=true` для получения вложенных объектов
3. Цикл: берёт `items` из ответа, проверяет `paging.count`
4. Если `offset + len(items) >= total` — стоп
5. Если `len(items) < limit` — стоп (последняя страница)
6. Иначе `offset += len(items)` и следующая страница

**URL'ы для discovery:**
| Endpoint | URL |
|----------|-----|
| Устройства | `/api/fmc_config/v1/domain/{domain}/devices/devicerecords` |
| HA пары | `/api/fmc_config/v1/domain/{domain}/devicehapairs/ftddevicehapairs` |
| Шасси | `/api/fmc_config/v1/domain/{domain}/chassis/fmcmanagedchassis` |

---

## 5. Сбор данных по каждому устройству

**Метод:** `FmcCollector._collect_device()` — `collector.py:122-238`

Для каждого устройства из `devices_raw` вызывается эта функция. Внутри:

### 5.1 Device Detail (Tier 1)

```
GET /api/fmc_config/v1/domain/{domain}/devices/devicerecords/{device_id}
```

**Что получаем:** модель, serial, версия ПО, role, health status, лицензии, snort engine, deployment status, health/access policies.

**Парсинг:** → `DeviceIdentity` (schemas.py:11-36)

### 5.2 Aggregate Metrics (Tier 1)

```
GET /api/fmc_config/v1/domain/{domain}/health/aggregatemetrics?filter=device_uuid:{device_id}&expanded=true
```

**Что получаем:**
- `cpuHealthMetrics` → linaUsageAvg, snortUsageAvg, systemUsageAvg
- `memoryHealthMetrics` → linaUsageAvg, snortUsageAvg, systemUsageAvg
- `diskHealthMetrics` → totalDiskUsageAvg
- `interfaceHealthMetricsList` → link status, oper status, bytes avg, errors avg, drops avg
- `chassisStatsHealthMetrics.fanRpmAvgList` → fan RPM

**Парсинг:** → dict `load` через `_parse_load()` (collector.py:396-443)

### 5.3 Operational CPU (Fallback)

Если CPU не пришёл из aggregate metrics:

```
GET /api/fmc_config/v1/domain/{domain}/devices/devicerecords/{device_id}/operational/metrics?filter=metric:cpu&expanded=true&limit=100
```

**Парсинг:** → `_parse_operational_cpu()` (collector.py:445-450)

### 5.4 Health Alerts (Tier 1)

```
GET /api/fmc_config/v1/domain/{domain}/health/alerts?filter=deviceUUIDs:{device_id};status:red,yellow&expanded=true&limit=1000
```

**Что получаем:** только красные и жёлтые алерты (status=RED или YELLOW).

**Парсинг:** → список `HealthAlert` (schemas.py:120-128)

### 5.5 All Interfaces (Tier 1)

```
GET /api/fmc_config/v1/domain/{domain}/devices/devicerecords/{device_id}/ftdallinterfaces?expanded=true&limit=1000
```

**Что получаем:** имя, ifname, IP (IPv4/IPv6), security zone, MTU, mode, enabled, managementOnly, MAC-адреса.

**Парсинг:** → список `NormalizedInterface` через `_parse_interface_config()` (collector.py:452-468)

## 6. Мерж данных интерфейсов

### 6.1 Runtime из Aggregate Metrics

**Метод:** `_merge_interface_runtime()` — `collector.py:470-494`

Мержит данные из `aggregateMetrics.interfaceHealthMetricsList` в конфигурацию интерфейсов из `ftdallinterfaces`.

**Матчинг по:** `physical_name`, `logical_name`, или `raw.name` (case-insensitive).

**Что мержится:**
- `linkStatus` → `runtime.link_status`
- `operationalStatus` → `runtime.operational_status`
- `duplexMode` → `runtime.duplex`
- `inputBytesAvg` → `runtime.input_bytes_average`
- `outputBytesAvg` → `runtime.output_bytes_average`
- `inputErrorsAvg` → `runtime.input_errors_average`
- `outputErrorsAvg` → `runtime.output_errors_average`
- `dropPacketsAvg` → `runtime.drops_average`
- `l2DecodeDropsAvg` → `runtime.l2_decode_drops_average`
- `bufferOverrunsAvg` → `runtime.buffer_overruns_average`
- `bufferUnderrunsAvg` → `runtime.buffer_underruns_average`
- `inputPacketSizeAvg` → `runtime.input_packet_size_average`
- `outputPacketSizeAvg` → `runtime.output_packet_size_average`

## 7. HA-пары

**Метод:** `FmcCollector._collect_ha_pairs()` — `collector.py:257-277`

Для каждой HA-пары:

```
GET /api/fmc_config/v1/domain/{domain}/devicehapairs/ftddevicehapairs/{pair_id}
GET /api/fmc_config/v1/domain/{domain}/devicehapairs/ftddevicehapairs/{pair_id}/monitoredinterfaces
GET /api/fmc_config/v1/domain/{domain}/devicehapairs/ftddevicehapairs/{pair_id}/monitoredinterfaces/{object_id}
```

Список monitored interfaces используется для обнаружения object ID, после чего detail endpoint
загружает IPv4/IPv6 active/standby адреса и флаг `monitorForFailures`.

**Дополнительно:** строится `ha_map` — dict `device_id → HaPair` для быстрого поиска. Если устройство является primary или secondary в какой-то HA-паре, в `CollectedDevice.ha` прикрепляется эта пара.

---

## 8. Chassis (Firepower 9000)

**Метод:** `FmcCollector._collect_chassis()` — `collector.py:304-364`

Для каждого шасси собираются:

| Endpoint | URL суффикс |
|----------|-------------|
| Детали | `/chassis/fmcmanagedchassis/{id}` |
| Инвентарь | `/chassis/fmcmanagedchassis/{id}/inventorysummary` |
| Faults | `/chassis/fmcmanagedchassis/{id}/faultsummary` |
| Interface summary | `/chassis/fmcmanagedchassis/{id}/interfacesummary` |
| Instances | `/chassis/fmcmanagedchassis/{id}/instancesummary` |
| Logical devices | `/chassis/fmcmanagedchassis/{id}/logicaldevices` |

**Парсинг:** → `ChassisData` со списком `ChassisFault` — `schemas.py:150-171`

---

## 9. VPN (optional)

```
GET /api/fmc_config/v1/domain/{domain}/health/tunnelstatuses?expanded=true&limit=1000
GET /api/fmc_config/v1/domain/{domain}/health/tunnelsummaries?expanded=true&limit=1000
```

Оборачивается в try/except — если VPN нет, данные остаются пустыми.

---

## 10. Retry / Backoff

**Метод:** `FmcClient.get()` — `client.py:95-152`

Каждый GET-запрос проходит через retry-логику:

| HTTP Status | Поведение |
|-------------|-----------|
| **200** | OK, возвращает JSON |
| **401** | Реавторизация + повтор запроса (1 раз) |
| **429** | Exponential backoff: 2с → 4с → 8с → 16с → 30с (макс), до 5 попыток, jitter ±50% |
| **400** | Endpoint не поддерживается — возврат `{"items": [], "_status": "UNSUPPORTED"}` |
| **500/502/503/504** | Exponential backoff, до 2 retry, потом `{"items": [], "_status": "TEMPORARY_ERROR"}` |
| **ConnectError/ReadTimeout** | Exponential backoff, до 5 попыток |

**Throttle:** между любыми запросами `asyncio.sleep(1.0)` — защита от rate limiting.

---

## 11. Capability Detection

Каждый endpoint помечается в `capabilities: dict[str, str]` на уровне устройства:

| Статус | Значение |
|--------|----------|
| `SUPPORTED` | Данные успешно получены |
| `AVAILABLE_NO_DATA` | Endpoint работает, но вернул пустой список |
| `UNSUPPORTED` | Устройство не поддерживает этот endpoint |
| `TEMPORARY_ERROR` | Ошибка 429/5xx |
| `PERMISSION_ERROR` | 401/403 |

---

## 12. Raw Responses

Все ответы FMC сохраняются в `self._raw_responses` (client.py:136):

```python
self._raw_responses.append({"path": path, "status": r.status_code, "data": data})
```

Плюс в `CollectedDevice.raw_references` хранятся:
- `raw_summary` — данные из list devices (базовый набор)
- `raw_detail` — данные из detail endpoint (полный набор)

---

## 13. Итоговый ответ

**Модель:** `MonitoringDashboard` — `schemas.py:189-204`

```python
MonitoringDashboard(
    collected_at="2026-07-30T12:00:00+00:00",
    domain_id="a]1b2c3d4-...",
    devices=[CollectedDevice(...)],       # все устройства с load, interfaces, alerts, ha, capabilities
    ha_pairs=[HaPair(...)],               # HA-пары с monitored interfaces
    chassis=[ChassisData(...)],           # шасси с inventory, faults, instances
    tunnel_statuses=[...],                # VPN туннели
    tunnel_summaries=[...],               # Сводки по туннелям
    total_devices=12,
    devices_connected=10,
    tunnel_up=5,
    tunnel_down=1,
    alerts_total=3,
    alerts_red=1,
    alerts_yellow=2,
)
```

**API endpoint:** `GET /api/monitoring/dashboard` → `monitoring.py:18-30`

Сериализуется через `model_dump()` → JSON фронтенду.

---

## Визуальная схема одного цикла сбора

```
authenticate()
    │
    ├── get_devices()          ──► paginated GET
    ├── get_ha_pairs()         ──► paginated GET
    └── get_chassis_list()     ──► paginated GET
         │
         ▼ для каждого устройства:
         │
         ├── get_device(id)              ──► DeviceIdentity
         │
         ├── get_aggregate_metrics(id)   ──► CPU/mem/disk/interface metrics
         │     │
         │     └── fallback: get_operational_metrics(id, "cpu")
         │
         ├── get_alerts(id)              ──► HealthAlert[] (RED/YELLOW)
         │
         ├── get_all_interfaces(id)      ──► NormalizedInterface[]
         │     │
         │     └── merge runtime/performance averages from aggregate metrics
         │
         └── return CollectedDevice
         │
         ▼ для каждой HA-пары:
         │
         ├── get_ha_pair(id)                    ──► HaPair detail
         ├── get_ha_monitored_interfaces(id)    ──► monitored interface list
         └── get_ha_monitored_interface(id, object_id) ──► interface detail
         │
         ▼ для каждого chassis:
         │
         ├── get_chassis(id)                    ──► ChassisData detail
         ├── get_chassis_inventory(id)          ──► inventory summary
         ├── get_chassis_faults(id)             ──► fault list
         ├── get_chassis_interface_summary(id)  ──► interface list
         ├── get_chassis_instances(id)          ──► instance list
         └── get_chassis_logical_devices(id)    ──► logical devices
         │
         ▼ VPN (optional):
         │
         ├── get_tunnel_statuses()              ──► tunnel list
         └── get_tunnel_summaries()             ──► tunnel summaries
         │
         ▼ MonitoringDashboard (JSON) → фронтенд
```

---

## Типы устройств и tiers

| Tier | Что собирается | Endpoint'ы |
|------|----------------|------------|
| **Tier 1** | Device detail, Aggregate metrics, Alerts, Interfaces | `devicerecords`, `aggregatemetrics`, `alerts`, `ftdallinterfaces` |
| **Tier 2** | Health metrics (historical), Operational metrics | `health/metrics`, `operational/metrics` |
| **Tier 4** | HA Pairs, HA Monitored Interfaces | `devicehapairs`, `monitoredinterfaces` |
| **Tier 5** | Chassis (9000 series) | `fmcmanagedchassis` + sub-endpoints |
| **VPN** | Tunnel statuses, summaries, S2S policies | `tunnelstatuses`, `tunnelsummaries` |

---

## Ключевые особенности

1. **Read-only** — нигде нет POST/PUT/PATCH/DELETE
2. **Одна авторизация** на весь цикл сбора
3. **Capability detection** — каждый endpoint помечается как SUPPORTED/UNSUPPORTED/ERROR
4. **Unsupported cache** — если устройство не поддерживает endpoint, это кэшируется и не запрашивается повторно
5. **Graceful degradation** — ошибки на одном endpoint не ломают сбор данных с других
6. **Raw storage** — оригинальные ответы FMC сохраняются для отладки
7. **Pagination** — автоматическая обход всех страниц
