#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=provider_select.sh
source "$SCRIPT_DIR/provider_select.sh"
CLOUD_READY=0
[[ " $* " == *" --config "* ]] && CLOUD_READY=1
select_provider "$@"
if [[ "$PROVIDER" == xmlriver ]]; then
  # Порядок XMLRiver: plan, затем collect по SHA плана, затем export (skills/xmlriver-serp-research/SKILL.md).
  exec python3 "$PLUGIN_DIR/skills/xmlriver-serp-research/scripts/xmlriver_collect.py" ${PASS_ARGS[@]+"${PASS_ARGS[@]}"} --kind wordstat
fi
exec python3 "$PLUGIN_DIR/mcp/yandex-wordstat/scripts/wordstat_cloud_gateway_collect.py" ${PASS_ARGS[@]+"${PASS_ARGS[@]}"}
