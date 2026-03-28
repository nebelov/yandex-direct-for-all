#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cat <<EOF
Yandex Direct For All: data collectors

Wordstat:
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/wordstat_preflight.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/wordstat_collect_wave.js
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/wordstat_tool.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/normalize_wordstat_regions.py

Direct:
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_all.py
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/collect_operational_precheck.py
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/fetch_sqr.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/audit_campaign_meta.py
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/audit_ad_delivery_failures.py

Metrika:
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/counters.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/counter_info.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/goals.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/conversions.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/traffic_summary.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/utm_report.sh
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika/search_engines.sh

Roistat:
  $PLUGIN_DIR/skills/yandex-performance-ops/scripts/roistat_query.sh
  $PLUGIN_DIR/skills/roistat-reports-api/scripts/build_roistat_report_pack.py
  $PLUGIN_DIR/skills/roistat-reports-api/scripts/sync_truth_layer_report.py

Research / SERP:
  $PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/yandex_search_batch.py
  $PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py
  $PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/firecrawl_scrape.py
  $PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/sitemap_probe_batch.py

See full inventory:
  $PLUGIN_DIR/docs/data-collection-scripts.md
EOF
