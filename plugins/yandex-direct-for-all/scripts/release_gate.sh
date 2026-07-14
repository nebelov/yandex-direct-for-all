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
}
assert module.validate_input_data({
    **body,
    "paid_search_approval": {"approved": True},
}, {"query", "search_region"})
with mock.patch.dict(os.environ, {"YANDEX_SEARCH_ROUTE": "disabled"}, clear=True):
    try:
        module.authorize_paid_call("web", body)
    except module.SearchPolicyError:
        pass
    else:
        raise AssertionError("disabled paid search reached authorization")
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    folder = "SYNTHETIC_FOLDER"
    manual_approval = root / "manual-approval.json"
    manual_approval.write_text(json.dumps({
        "approved": True,
        "approval_ref": "SYNTHETIC_APPROVAL",
        "routes": ["web"],
        "max_calls": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "folder_sha256": hashlib.sha256(folder.encode()).hexdigest(),
        "request_sha256": module.request_sha256("web", body),
    }), encoding="utf-8")
    os.chmod(manual_approval, 0o600)
    manual_ledger = root / "manual" / "ledger.json"
    with mock.patch.dict(os.environ, {
        "YANDEX_SEARCH_ROUTE": "manual",
        "YANDEX_SEARCH_API_KEY": "SYNTHETIC_KEY",
        "YANDEX_SEARCH_FOLDER_ID": folder,
        "YANDEX_SEARCH_APPROVAL_FILE": str(manual_approval),
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
        try:
            module.authorize_paid_call("web", {
                **body,
                "paid_search_approval": {"approved": True, "approval_ref": "SELF_APPROVED"},
            })
        except module.SearchPolicyError:
            pass
        else:
            raise AssertionError("request body self-approved a paid call")
    wrong_manual_approval = json.loads(manual_approval.read_text(encoding="utf-8"))
    wrong_manual_approval["approval_ref"] = "SYNTHETIC_OTHER_QUERY"
    manual_approval.write_text(json.dumps(wrong_manual_approval), encoding="utf-8")
    os.chmod(manual_approval, 0o600)
    with mock.patch.dict(os.environ, {
        "YANDEX_SEARCH_ROUTE": "manual",
        "YANDEX_SEARCH_API_KEY": "SYNTHETIC_KEY",
        "YANDEX_SEARCH_FOLDER_ID": folder,
        "YANDEX_SEARCH_APPROVAL_FILE": str(manual_approval),
        "YANDEX_SEARCH_USAGE_LEDGER": str(root / "manual-other-ledger.json"),
    }, clear=True):
        try:
            module.authorize_paid_call("web", {"query": "other query", "search_region": "ru"})
        except module.SearchPolicyError:
            pass
        else:
            raise AssertionError("manual approval crossed exact query")
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
import sys
import hashlib
import json
import tempfile
from pathlib import Path
from unittest import mock

scripts = Path("plugins/yandex-direct-for-all/skills/yandex-performance-ops/scripts").resolve()
sys.path.insert(0, str(scripts))
import change_tracker as tracker

params = {"SelectionCriteria": {}, "FieldNames": ["Id"]}
with mock.patch.object(tracker, "api_call", side_effect=[
    {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 1}},
    {"result": {"Campaigns": [{"Id": 2}]}},
]):
    complete = tracker.fetch_paginated("campaigns", "get", params, "Campaigns", "TOKEN", "LOGIN")
assert complete.manifest.complete and complete.manifest.pages == 2 and complete.manifest.objects == 2
assert len(complete.manifest.checksum) == 64

with mock.patch.object(tracker, "api_call", return_value={"result": {"Campaigns": []}}):
    empty = tracker.fetch_paginated("campaigns", "get", params, "Campaigns", "TOKEN", "LOGIN")
assert empty.manifest.complete and empty.manifest.pages == 1 and empty.manifest.objects == 0

with mock.patch.object(tracker, "api_call", side_effect=[
    {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 1}},
    {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 2}},
]):
    repeated = tracker.fetch_paginated("campaigns", "get", params, "Campaigns", "TOKEN", "LOGIN")
assert not repeated.manifest.complete and repeated.manifest.pages == 1 and repeated.manifest.objects == 1

with mock.patch.object(tracker, "api_call", side_effect=[
    {"result": {"Campaigns": [{"Id": 1}], "LimitedBy": 1}},
    None,
]):
    partial = tracker.fetch_paginated("campaigns", "get", params, "Campaigns", "TOKEN", "LOGIN")
assert not partial.manifest.complete and partial.manifest.pages == 1 and partial.manifest.objects == 1

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    responses = iter([
        (201, b"", {"RequestId": "report-1", "retryIn": "0", "reportsInQueue": "2"}),
        (202, b"", {"RequestId": "report-1", "retryIn": "0", "reportsInQueue": "1"}),
        (200, b"CampaignId\tClicks\n1\t2\n", {"RequestId": "report-1"}),
    ])
    states = []
    def requester(url, headers, body):
        assert url.endswith("/json/v5/reports")
        assert headers.get("Client-Login") == "client"
        return next(responses)
    def sleeper(_seconds):
        state_path = next(output.glob("_api_reports_*.state.json"))
        states.append(json.loads(state_path.read_text(encoding="utf-8")))
    ready = tracker.fetch_direct_report(
        tracker.DirectAccess("TOKEN", "client", "production"),
        {"ReportName": "contract", "ReportType": "CAMPAIGN_PERFORMANCE_REPORT"},
        output,
        requester=requester,
        sleeper=sleeper,
    )
    assert [item["status"] for item in states] == ["queued", "pending"]
    assert all(item["request_id"] == "report-1" for item in states)
    request_path = output / ready["request_artifact"]
    artifact_path = output / ready["artifact"]
    assert hashlib.sha256(request_path.read_bytes()).hexdigest() == ready["request_sha256"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == ready["artifact_sha256"]
    assert ready["status"] == "ready" and ready["request_id"] == "report-1"
PY

python3 - <<'PY'
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

scripts = Path("plugins/yandex-direct-for-all/skills/yandex-performance-ops/scripts").resolve()
sys.path.insert(0, str(scripts))
from check_access_paths import DirectAccess, PageManifest, PageResult

def load(name):
    spec = importlib.util.spec_from_file_location(f"release_pages_{name}", scripts / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def page(service, key, rows, *, pages=1, complete=True, error=""):
    return PageResult(rows, PageManifest(service, key, pages, len(rows), complete, "a" * 64, error))

access = DirectAccess("TOKEN", "client", "production")
campaign_autotest = load("campaign_autotest")
audit_delivery = load("audit_ad_delivery_failures")
audit_copy = load("audit_group_ad_copy")
readiness = load("verify_live_readiness")
fetch_sqr = load("fetch_sqr_parallel")

with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    manifest_path = temp / "autotest-manifest.json"
    tester = campaign_autotest.CampaignAutotest(access, [1], collection_manifest=manifest_path)
    with mock.patch.object(campaign_autotest, "fetch_direct_pages", side_effect=[
        page("campaigns", "Campaigns", [{"Id": 1}, {"Id": 2}], pages=2),
        page("ads", "Ads", [{"Id": 3}], pages=1, complete=False, error="partial"),
    ]):
        assert len(tester.call("campaigns", "get", {}, version="v501")["result"]["Campaigns"]) == 2
        assert tester.call("ads", "get", {}) == {"error": "partial"}
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not saved["complete"] and saved["source_count"] == 2
    assert saved["sources"]["001-campaigns"]["pages"] == 2
    assert saved["sources"]["001-campaigns"]["objects"] == 2
    assert saved["sources"]["002-ads"]["complete"] is False

    delivery_dir = temp / "delivery"
    with mock.patch.object(sys, "argv", ["audit", "--output-dir", str(delivery_dir)]), \
         mock.patch.object(audit_delivery, "load_direct_access", return_value=access), \
         mock.patch.object(audit_delivery, "fetch_direct_pages", return_value=page("campaigns", "Campaigns", [{"Id": 1}], complete=False, error="partial")):
        try:
            audit_delivery.main()
        except RuntimeError as exc:
            assert str(exc) == "partial"
        else:
            raise AssertionError("delivery audit accepted a partial page result")
    delivery_manifest = json.loads((delivery_dir / "collection-manifest.json").read_text(encoding="utf-8"))
    assert not delivery_manifest["complete"] and delivery_manifest["sources"]["campaigns"]["objects"] == 1

    cluster = temp / "cluster.tsv"
    cluster.write_text("campaign_name\tadgroup_name\tphrase\nC\tG\tphrase\n", encoding="utf-8")
    copy_json = temp / "copy" / "result.json"
    with mock.patch.object(sys, "argv", [
        "audit", "--campaign-ids", "1", "--cluster-map", str(cluster),
        "--output-tsv", str(temp / "copy" / "result.tsv"), "--output-json", str(copy_json),
    ]), mock.patch.object(audit_copy, "load_direct_access", return_value=access), \
         mock.patch.object(audit_copy, "fetch_direct_pages", return_value=page("adgroups", "AdGroups", [], complete=False, error="partial")):
        try:
            audit_copy.main()
        except RuntimeError as exc:
            assert str(exc) == "partial"
        else:
            raise AssertionError("copy audit accepted a partial page result")
    copy_manifest = json.loads((copy_json.parent / "result.collection-manifest.json").read_text(encoding="utf-8"))
    assert not copy_manifest["complete"] and copy_manifest["sources"]["adgroups"]["pages"] == 1

    minus = temp / "minus.tsv"
    minus.write_text("word\nminus\n", encoding="utf-8")
    readiness_json = temp / "readiness" / "result.json"
    with mock.patch.object(sys, "argv", [
        "verify", "--campaign-ids", "1", "--cluster-map", str(cluster),
        "--minus-words", str(minus), "--output", str(readiness_json),
    ]), mock.patch.object(readiness, "load_direct_access", return_value=access), \
         mock.patch.object(readiness, "fetch_direct_pages", return_value=page("campaigns", "Campaigns", [], complete=False, error="partial")):
        try:
            readiness.main()
        except RuntimeError as exc:
            assert str(exc) == "partial"
        else:
            raise AssertionError("readiness check accepted a partial page result")
    readiness_manifest = json.loads((readiness_json.parent / "result.collection-manifest.json").read_text(encoding="utf-8"))
    assert not readiness_manifest["complete"] and readiness_manifest["sources"]["campaigns"]["checksum"] == "a" * 64

    sqr_dir = temp / "sqr"
    sqr_dir.mkdir()
    (sqr_dir / "one.tsv").write_text("CampaignId\tClicks\n1\t2\n", encoding="utf-8")
    def report(_access, definition, _output):
        if definition["ReportName"].startswith("public-sqr-1-"):
            return {"status": "ready", "artifact": "one.tsv", "artifact_sha256": "b" * 64}
        raise RuntimeError("synthetic report failure")
    with mock.patch.object(fetch_sqr, "load_direct_access", return_value=access), \
         mock.patch.object(fetch_sqr, "fetch_direct_report", side_effect=report):
        sqr_manifest = fetch_sqr.collect(None, [1, 2], "2026-01-01", "2026-01-02", sqr_dir, 1)
    assert not sqr_manifest["complete"] and sqr_manifest["ready"] == 1 and sqr_manifest["failed"] == 1
    assert sqr_manifest["merged"]["parts"] == 1
    assert json.loads((sqr_dir / "manifest.json").read_text(encoding="utf-8"))["parts"][1]["status"] == "error"
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
