# Yandex Cloud Search Handoffs

## Localized canonical bundle

- local mirror: `/Users/vitalijtravin/.codex/credentials/yandex-cloud-search-tenevoy.json`
- source host: `macbook-air-remote`
- source file: `/Users/remote-mac/ads/tenevoy/.yandex_cloud_search_api.json`
- source handoff: `/Users/remote-mac/ads/tenevoy/YANDEX_TRANSFER_BUNDLE_20260312.md`
- official ad-SERP proof:
  - `/Users/remote-mac/ads/tenevoy/claude/docs/WORDSTAT_AND_COMPETITORS_OFFICIAL_PATH_20260308.md`
  - `/Users/remote-mac/ads/tenevoy/claude/docs/COMPETITOR_LAYER_LIVE_PROOF_20260308.md`
  - `/Users/remote-mac/ads/tenevoy/direct-orchestrator/scripts/collector_competitor_scan.py`
  - `/Users/remote-mac/ads/tenevoy/direct-orchestrator/scripts/local_competitor_scan_matrix.py`

## Rule

Если в локальном клиентском проекте еще нет собственных `YANDEX_SEARCH_FOLDER_ID` и `YANDEX_SEARCH_API_KEY`, но нужен срочный live `Yandex Cloud Search API` collector, сначала проверить этот localized bundle.

Использовать как временный operational bridge, а не как замену клиентскому собственному cloud-search path навсегда.
