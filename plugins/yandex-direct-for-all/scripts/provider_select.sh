#!/usr/bin/env bash
# Выбор пути сбора: yandex-cloud или xmlriver. Подключается через source из collect_*.sh.
# Вход: CLOUD_READY=1, если для облака задан доступ; аргументы сборщика.
# Выход: PROVIDER и массив PASS_ARGS без --provider.
# В режиме auto берётся единственный настроенный путь; если настроены оба — ошибка, молча
# переключаться между платными путями нельзя.

select_provider() {
  PROVIDER="auto"
  PASS_ARGS=()
  local xml_ready=0 arg
  while (($#)); do
    case "$1" in
      --provider) PROVIDER="${2:-}"; shift 2 ;;
      --provider=*) PROVIDER="${1#--provider=}"; shift ;;
      --use-demo-key) xml_ready=1; PASS_ARGS+=("$1"); shift ;;
      *) PASS_ARGS+=("$1"); shift ;;
    esac
  done
  if [[ -n "${XMLRIVER_CREDENTIALS_FILE:-}" ]] || { [[ -n "${XMLRIVER_USER:-${XMLRIVER_USER_ID:-}}" ]] && [[ -n "${XMLRIVER_KEY:-}" ]]; }; then
    xml_ready=1
  fi
  case "$PROVIDER" in
    yandex-cloud|xmlriver) ;;
    auto)
      if [[ "${CLOUD_READY:-0}" == 1 && "$xml_ready" == 1 ]]; then
        echo "Заданы доступы и Yandex Cloud, и XMLRiver. Укажите --provider yandex-cloud или --provider xmlriver." >&2
        exit 2
      elif [[ "$xml_ready" == 1 ]]; then
        PROVIDER="xmlriver"
      else
        PROVIDER="yandex-cloud"
      fi
      ;;
    *) echo "Неизвестный --provider: $PROVIDER (yandex-cloud, xmlriver или auto)" >&2; exit 2 ;;
  esac
}
