#!/usr/bin/env bash
# Выбор пути сбора: yandex-cloud или xmlriver. Подключается через source из collect_*.sh.
# Выход: PROVIDER и массив PASS_ARGS без --provider.
# auto решает только по переменным окружения: ровно один настроенный путь — он; оба или ни одного — ошибка.
# Файл доступа (--credentials-file, --config) по имени не говорит, чей он, поэтому с ним провайдер
# указывается явно. Молча переключаться между платными путями нельзя.

select_provider() {
  PROVIDER="auto"
  PASS_ARGS=()
  local xml_ready=0 cloud_ready=0 file_arg=0
  while (($#)); do
    case "$1" in
      --provider) PROVIDER="${2:-}"; shift 2 ;;
      --provider=*) PROVIDER="${1#--provider=}"; shift ;;
      --use-demo-key) xml_ready=1; PASS_ARGS+=("$1"); shift ;;
      --credentials-file|--config|--credentials-file=*|--config=*) file_arg=1; PASS_ARGS+=("$1"); shift ;;
      *) PASS_ARGS+=("$1"); shift ;;
    esac
  done
  if [[ -n "${XMLRIVER_CREDENTIALS_FILE:-}" ]] || { [[ -n "${XMLRIVER_USER:-${XMLRIVER_USER_ID:-}}" ]] && [[ -n "${XMLRIVER_KEY:-}" ]]; }; then
    xml_ready=1
  fi
  [[ -n "${YANDEX_SEARCH_API_KEY:-}${YANDEX_SEARCH_IAM_TOKEN:-}${YANDEX_WORDSTAT_API_KEY:-}" ]] && cloud_ready=1
  case "$PROVIDER" in
    yandex-cloud|xmlriver) ;;
    auto)
      if [[ "$file_arg" == 1 ]]; then
        echo "Передан файл доступа: укажите --provider yandex-cloud или --provider xmlriver." >&2
        exit 2
      elif [[ "$cloud_ready" == 1 && "$xml_ready" == 1 ]]; then
        echo "Заданы доступы и Yandex Cloud, и XMLRiver. Укажите --provider yandex-cloud или --provider xmlriver." >&2
        exit 2
      elif [[ "$xml_ready" == 1 ]]; then
        PROVIDER="xmlriver"
      elif [[ "$cloud_ready" == 1 ]]; then
        PROVIDER="yandex-cloud"
      else
        echo "Не задан доступ ни к Yandex Cloud (YANDEX_SEARCH_API_KEY или YANDEX_WORDSTAT_API_KEY), ни к XMLRiver (XMLRIVER_USER и XMLRIVER_KEY). Укажите --provider." >&2
        exit 2
      fi
      ;;
    *) echo "Неизвестный --provider: $PROVIDER (yandex-cloud, xmlriver или auto)" >&2; exit 2 ;;
  esac
}
