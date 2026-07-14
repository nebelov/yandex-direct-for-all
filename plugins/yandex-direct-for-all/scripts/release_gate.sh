#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PLUGIN_DIR/../.." && pwd)"
WORDSTAT_DIR="$PLUGIN_DIR/mcp/yandex-wordstat"
SEARCH_DIR="$PLUGIN_DIR/mcp/yandex-search"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

step() { printf '\n== %s ==\n' "$1"; }
require_command() { command -v "$1" >/dev/null 2>&1 || { echo "Не найдена обязательная команда: $1" >&2; exit 2; }; }

cd "$REPO_ROOT"
for command in git python3 node npm bun uv gitleaks; do require_command "$command"; done

step "Сборка Wordstat из зафиксированных исходников"
(
  cd "$WORDSTAT_DIR"
  npm ci --ignore-scripts
  npm audit --omit=dev
  bun test
)

step "Все испытания Python, Node.js и оболочек"
bash "$PLUGIN_DIR/scripts/validate_bundle.sh"
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/test_direct_write_gate.py"
python3 "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/test_mark_search_queue_by_known_minus_words.py"
python3 -m unittest discover -s "$PLUGIN_DIR/skills/roistat-reports-api/tests" -v
python3 -m unittest discover -s "$PLUGIN_DIR/skills/amocrm-api-control/tests" -v
bash "$PLUGIN_DIR/tests/test_install_bundle.sh"

for file in "$PLUGIN_DIR/scripts"/*.sh "$PLUGIN_DIR/skills/yandex-performance-ops/scripts/metrika"/*.sh; do
  bash -n "$file"
done

step "Закреплённая сборка сервера поиска"
(
  cd "$SEARCH_DIR"
  UV_PROJECT_ENVIRONMENT="$TEMP_ROOT/search-venv" uv sync --frozen
  UV_PROJECT_ENVIRONMENT="$TEMP_ROOT/search-venv" uv run --frozen python -c 'import server; assert callable(server.main)'
)

python3 - <<'PY'
import hashlib
import importlib.util
import json
import os
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

path = Path("plugins/yandex-direct-for-all/mcp/yandex-search/detail.py").resolve()
spec = importlib.util.spec_from_file_location("release_search_detail", path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
body = {
    "query": "synthetic query",
    "search_region": "ru",
    "paid_search_approval": {"approved": True, "route": "web", "max_calls": 1, "approval_ref": "SYNTHETIC_APPROVAL"},
}
with mock.patch.dict(os.environ, {"YANDEX_SEARCH_ROUTE": "disabled"}, clear=True):
    try:
        module.authorize_paid_call("web", body)
    except module.SearchPolicyError:
        pass
    else:
        raise AssertionError("disabled paid search reached authorization")
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    manual_ledger = root / "manual" / "ledger.json"
    with mock.patch.dict(os.environ, {
        "YANDEX_SEARCH_ROUTE": "manual",
        "YANDEX_SEARCH_USAGE_LEDGER": str(manual_ledger),
    }, clear=True):
        assert module.authorize_paid_call("web", body) == "SYNTHETIC_APPROVAL"
        try:
            module.authorize_paid_call("web", body)
        except module.SearchPolicyError:
            pass
        else:
            raise AssertionError("manual approval was reusable")
        try:
            module.authorize_paid_call("generative", body)
        except module.SearchPolicyError:
            pass
        else:
            raise AssertionError("manual approval crossed routes")
    folder = "SYNTHETIC_FOLDER"
    approval = root / "approval.json"
    approval.write_text(json.dumps({
        "approved": True,
        "approval_ref": "SYNTHETIC_BATCH",
        "routes": ["web"],
        "max_calls": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "folder_sha256": hashlib.sha256(folder.encode()).hexdigest(),
    }), encoding="utf-8")
    os.chmod(approval, 0o600)
    ledger = root / "state" / "ledger.json"
    environment = {
        "YANDEX_SEARCH_ROUTE": "approved",
        "YANDEX_SEARCH_API_KEY": "SYNTHETIC_KEY",
        "YANDEX_SEARCH_FOLDER_ID": folder,
        "YANDEX_SEARCH_APPROVAL_FILE": str(approval),
        "YANDEX_SEARCH_USAGE_LEDGER": str(ledger),
    }
    with mock.patch.dict(os.environ, environment, clear=True):
        assert module.authorize_paid_call("web", {"query": "x", "search_region": "ru"}) == "SYNTHETIC_BATCH"
        try:
            module.authorize_paid_call("web", {"query": "x", "search_region": "ru"})
        except module.SearchPolicyError:
            pass
        else:
            raise AssertionError("approved call limit was not enforced")
    saved = ledger.read_text(encoding="utf-8")
    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600
    assert stat.S_IMODE(ledger.parent.stat().st_mode) == 0o700
    assert "query" not in saved and "SYNTHETIC_KEY" not in saved
PY

python3 - <<'PY'
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

root = Path("plugins/yandex-direct-for-all/skills/yandex-performance-ops/scripts").resolve()

def load(name):
    spec = importlib.util.spec_from_file_location(f"release_{name}", root / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

bootstrap = load("bootstrap_yougile_workspace")
push = load("push_yougile_file_bundle")
sync = load("sync_yougile")

workspace = {
    "project": {"title": "SYNTHETIC_PROJECT"},
    "boards": [{
        "alias": "main", "title": "SYNTHETIC_BOARD",
        "columns": [{"alias": "backlog", "title": "SYNTHETIC_BACKLOG"}],
        "tasks": [{"title": "SYNTHETIC_TASK", "column_alias": "backlog"}],
    }],
}
assert bootstrap.validate_spec(workspace)["tasks"] == 1

with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    workspace_path = temp / "workspace.json"
    workspace_path.write_text(json.dumps(workspace), encoding="utf-8")
    material = temp / "material.md"
    material.write_text("SYNTHETIC_MATERIAL\n", encoding="utf-8")
    bundle_path = temp / "bundle.json"
    bundle_path.write_text(json.dumps({
        "target_ref": "SYNTHETIC_CHAT",
        "chat_id": "SYNTHETIC_CHAT_ID",
        "files": [{"path": str(material), "sha256": push.sha256_file(material)}],
    }), encoding="utf-8")
    os.chmod(bundle_path, 0o600)
    target, chat_id, files = push.validate_bundle(bundle_path, push.load_json(bundle_path, private=True))
    assert target == "SYNTHETIC_CHAT" and chat_id == "SYNTHETIC_CHAT_ID" and len(files) == 1

    tasks = temp / "tasks.tsv"
    tasks.write_text("action\tpriority\tcategory\tdescription\nПроверить\tP2\treview\tSYNTHETIC_TASK\n", encoding="utf-8")
    columns = temp / "columns.json"
    columns.write_text(json.dumps({"default": {"backlog": "SYNTHETIC_COLUMN"}}), encoding="utf-8")
    os.chmod(columns, 0o600)
    package_path = temp / "package.json"
    package_path.write_text(json.dumps({
        "target_ref": "SYNTHETIC_BOARD",
        "tasks_file": str(tasks), "tasks_sha256": sync.sha256_file(tasks),
        "columns_file": str(columns), "columns_sha256": sync.sha256_file(columns),
        "board_preset": "default", "campaign_name": "SYNTHETIC_CAMPAIGN",
        "category": None, "priority": None,
    }), encoding="utf-8")
    os.chmod(package_path, 0o600)
    prepared = sync.prepare_package(package_path, sync.load_json(package_path, private=True))
    assert len(prepared["tasks"]) == 1

    for module, arguments in (
        (bootstrap, ["bootstrap", "--spec", str(workspace_path)]),
        (push, ["push", "--bundle", str(bundle_path)]),
        (sync, ["sync", "--package", str(package_path)]),
    ):
        with mock.patch.object(sys, "argv", arguments), mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used")):
            with contextlib.redirect_stdout(io.StringIO()):
                assert module.main() == 0

    with mock.patch.dict(os.environ, {}, clear=True):
        try:
            bootstrap.authorize(workspace_path, "SYNTHETIC_PROJECT", temp / "missing.json")
        except bootstrap.GateError:
            pass
        else:
            raise AssertionError("YouGile write was not fail-closed")
PY

LIFECYCLE="$PLUGIN_DIR/skills/yandex-direct-client-lifecycle"
python3 "$LIFECYCLE/scripts/scaffold_client_lifecycle.py" \
  --output-dir "$TEMP_ROOT/lifecycle" --client-key synthetic-client --client-name SYNTHETIC_CLIENT >/dev/null
python3 "$LIFECYCLE/scripts/verify_research_bundle.py" \
  --project-dir "$TEMP_ROOT/lifecycle" --output-json "$TEMP_ROOT/lifecycle-validation.json" >/dev/null

step "Относительные ссылки и состав навыков"
python3 - <<'PY'
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

root = Path.cwd()
files = subprocess.check_output(["git", "ls-files", "*.md"], text=True).splitlines()
errors = []
pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
for name in files:
    path = root / name
    text = path.read_text(encoding="utf-8")
    for raw in pattern.findall(text):
        target = raw.strip().strip("<>").split(" ", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:", "#", "app://", "vscode://")):
            continue
        target = unquote(target.split("#", 1)[0])
        if not target or "{" in target or "}" in target:
            continue
        if target.startswith("/"):
            errors.append(f"{name}: абсолютная ссылка {target}")
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"{name}: ссылка выходит из хранилища {target}")
            continue
        if not resolved.exists():
            errors.append(f"{name}: нет цели {target}")
if errors:
    raise SystemExit("\n".join(errors))

skills = root / "plugins/yandex-direct-for-all/skills"
for directory in sorted(path for path in skills.iterdir() if path.is_dir()):
    if not (directory / "SKILL.md").is_file():
        errors.append(f"Нет SKILL.md: {directory.relative_to(root)}")
    if not (directory / "agents/openai.yaml").is_file():
        errors.append(f"Нет agents/openai.yaml: {directory.relative_to(root)}")
installer = (root / "plugins/yandex-direct-for-all/scripts/install_bundle.sh").read_text(encoding="utf-8")
for directory in sorted(path.name for path in skills.iterdir() if path.is_dir()):
    if f'"skills/{directory}"' not in installer:
        errors.append(f"Установщик не включает навык: {directory}")
if errors:
    raise SystemExit("\n".join(errors))
PY

step "Маршрутизаторы инструментов"
routes="$TEMP_ROOT/tool-routes.txt"
bash "$PLUGIN_DIR/scripts/list_tool_routes.sh" > "$routes"
cmp "$routes" <(bash "$PLUGIN_DIR/scripts/list_data_collectors.sh")
while IFS= read -r route; do
  [[ -z "$route" || "$route" == "Yandex Direct For All:"* ]] && continue
  [[ "$route" != /* ]] || { echo "Абсолютный маршрут: $route" >&2; exit 3; }
  test -f "$PLUGIN_DIR/$route" || { echo "Несуществующий маршрут: $route" >&2; exit 3; }
done < "$routes"

step "Абсолютные домашние пути и частные привязки"
python3 - <<'PY'
import re
import subprocess
from pathlib import Path

tracked = subprocess.check_output(["git", "ls-files", "-z"])
errors = []
for raw in tracked.split(b"\0"):
    if not raw:
        continue
    name = raw.decode("utf-8")
    if "/tests/" in name or name.endswith((".png", ".jpg", ".jpeg", ".gif", ".lock")):
        continue
    path = Path(name)
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    if re.search(r"/(?:Users|home)/[^/\s`]+/", text):
        errors.append(f"{name}: абсолютный домашний путь")
if errors:
    raise SystemExit("\n".join(errors))
PY

forbidden='sync_truth_layer_report|wordstat_resilient_collect|filter_search_queue_by_known_minus_words|roistat-direct|roistat-mediaplan|media-plan|ppc-data-analysis|competitive-ads-extractor|agentic-direct-control-plane|yougile-tenevoy|yandex-kit|forecast_engine|mediaplan_template'
if git grep -I -n -i -E "$forbidden" -- . \
  ':(exclude)plugins/yandex-direct-for-all/scripts/release_gate.sh' \
  ':(exclude)docs/actualization-report.md'; then
  echo "Найден исключённый публичный контур" >&2
  exit 3
fi

if git ls-files | grep -E '(^|/)(\.env($|\.)|oauth[^/]*\.json$|[^/]*token[^/]*\.json$|credentials[^/]*\.json$|\.codex/|\.claude/|__pycache__/|\.DS_Store$)' | grep -vE '\.env\.example$|\.example$'; then
  echo "В индексе есть закрытый файл или файл среды" >&2
  exit 3
fi

step "Происхождение и лицензии"
test -s "$PLUGIN_DIR/mcp/yandex-wordstat/UPSTREAM.md"
test -s "$PLUGIN_DIR/mcp/yandex-wordstat/LICENSE"
test -s "$PLUGIN_DIR/mcp/yandex-search/LICENSE"
grep -q 'v-wordstat-2.0.1' "$PLUGIN_DIR/mcp/yandex-wordstat/UPSTREAM.md"
grep -q '4a3a55ecdc5a40b5c1a19fb32329df8065adbd14' "$PLUGIN_DIR/mcp/yandex-wordstat/UPSTREAM.md"

step "Секреты в дереве и всей истории"
cat > "$TEMP_ROOT/gitleaks.toml" <<'EOF'
[extend]
useDefault = true

[[allowlists]]
description = "Documented synthetic OAuth placeholder"
regexTarget = "match"
regexes = ['''YOUR_OAUTH_TOKEN''']
EOF
gitleaks dir "$REPO_ROOT" --no-banner --redact --config "$TEMP_ROOT/gitleaks.toml"
gitleaks git "$REPO_ROOT" --no-banner --redact --config "$TEMP_ROOT/gitleaks.toml"

step "Итог"
git diff --check
echo "release gate: PASS"
