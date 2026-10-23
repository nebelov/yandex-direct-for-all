#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=provider_select.sh
source "$SCRIPT_DIR/provider_select.sh"
CLOUD_READY=0
[[ " $* " == *" --credentials-file "* ]] && CLOUD_READY=1
select_provider "$@"
if [[ "$PROVIDER" == xmlriver ]]; then
  # Порядок XMLRiver: plan, затем collect по SHA плана, затем export (skills/xmlriver-serp-research/SKILL.md).
  exec python3 "$PLUGIN_DIR/skills/xmlriver-serp-research/scripts/xmlriver_collect.py" ${PASS_ARGS[@]+"${PASS_ARGS[@]}"} --kind serp --ads on
fi
exec python3 "$PLUGIN_DIR/skills/yandex-direct-client-lifecycle/scripts/yandex_search_ads_batch.py" ${PASS_ARGS[@]+"${PASS_ARGS[@]}"}
