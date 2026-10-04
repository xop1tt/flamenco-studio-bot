#!/usr/bin/env bash
# Локальный запуск backend Flamenco Studio одной командой: Telegram-бот +
# веб-API (FastAPI). Для разработки, не для продакшена — там compose.yaml
# (см. docs/deployment.md). Сайт — отдельный проект (FLAMENCO WEBSITE),
# запускается там через `npm run dev` и обращается к этому API по HTTP.
#
#   ./run.sh          бот + API
#   ./run.sh api      только API
#   ./run.sh bot      только бот
#
# Логи всех процессов — в одном терминале с префиксами [bot] [api].
# Процессы независимы: бот не обращается к API, поэтому падение API не
# останавливает бота, и наоборот — о завершении процесса пишется в лог,
# остальные продолжают работать. Ctrl+C останавливает всё.
#
# Порт API: API_PORT (по умолчанию 8000). Если порт занят, `./run.sh`
# запускает только бота, `./run.sh api` завершается с ошибкой.
# Совместим с системным bash 3.2 на macOS.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODE="${1:-all}"
API_PORT="${API_PORT:-8000}"

case "$MODE" in
    all) RUN_BOT=1; RUN_API=1 ;;
    api) RUN_BOT=0; RUN_API=1 ;;
    bot) RUN_BOT=1; RUN_API=0 ;;
    -h | --help)
        sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    *)
        echo "Неизвестный режим «$MODE». Используйте: ./run.sh [all|api|bot]" >&2
        exit 2
        ;;
esac

fail() {
    echo "[run] $*" >&2
    exit 1
}

# ---------- Проверки окружения ----------
[ -x .venv/bin/python ] || fail "Не найден .venv/bin/python. Создайте окружение: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
[ -f .env ] || echo "[run] Внимание: нет файла .env — переменные берутся только из окружения (см. env.example)." >&2

port_busy() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}
if [ "$RUN_API" = 1 ] && port_busy "$API_PORT"; then
    echo "[run] Порт $API_PORT уже занят:" >&2
    lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN >&2
    if [ "$RUN_BOT" = 0 ]; then
        fail "Остановите процесс выше или задайте другой порт: API_PORT=… ./run.sh api"
    fi
    # Бот от API не зависит — запускаем его в любом случае.
    echo "[run] API не запущен (порт занят), запускаю только бота." >&2
    RUN_API=0
fi

# Пакет берётся из src/ напрямую — не зависим от editable-install `.pth`
# (на macOS с iCloud он иногда скрывается, см. pyproject.toml).
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# ---------- Процессы ----------
# set -m: каждый фоновый процесс — в своей группе, чтобы при остановке
# погасить его целиком (uvicorn → reload-воркер).
set -m
PIDS=()
NAMES=()

start() {
    local name="$1" color="$2"
    shift 2
    (
        "$@" 2>&1 | while IFS= read -r line; do
            printf '\033[%sm[%s]\033[0m %s\n' "$color" "$name" "$line"
        done
    ) &
    local pid="$!"
    # За процессом следит цикл ниже (kill -0), а не таблица заданий bash —
    # disown убирает служебные сообщения «Terminated» при остановке.
    disown "$pid"
    PIDS+=("$pid")
    NAMES+=("$name")
    echo "[run] запущен $name (pid $pid)"
}

STOPPING=0
stop_all() {
    [ "$STOPPING" = 1 ] && return
    STOPPING=1
    echo "[run] останавливаю…"
    for pid in "${PIDS[@]:-}"; do
        [ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null
    done
    # Даём процессам до 10 секунд завершиться корректно, затем — принудительно.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        alive=0
        for pid in "${PIDS[@]:-}"; do
            [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && alive=1
        done
        [ "$alive" = 0 ] && break
        sleep 1
    done
    for pid in "${PIDS[@]:-}"; do
        [ -n "$pid" ] && kill -KILL -- "-$pid" 2>/dev/null
    done
    echo "[run] всё остановлено"
}
trap 'stop_all; exit 130' INT TERM
trap 'stop_all' EXIT

if [ "$RUN_API" = 1 ]; then
    start api 36 .venv/bin/python -m uvicorn flamenco_bot.api.app:app \
        --host 127.0.0.1 --port "$API_PORT" --reload --reload-dir src
fi
if [ "$RUN_BOT" = 1 ]; then
    start bot 33 .venv/bin/python -m flamenco_bot
fi

if [ "$RUN_API" = 1 ]; then
    echo "[run] API: http://127.0.0.1:$API_PORT (сайт: cd \"../FLAMENCO WEBSITE\" && npm run dev)"
fi
echo "[run] Ctrl+C — остановить всё"

# Следим за процессами: завершение одного не трогает остальные. Скрипт
# выходит, когда завершились все (или по Ctrl+C).
EXIT_CODE=0
while :; do
    alive=0
    for i in "${!PIDS[@]}"; do
        pid="${PIDS[$i]}"
        [ -n "$pid" ] || continue
        if kill -0 "$pid" 2>/dev/null; then
            alive=1
            continue
        fi
        echo "[run] процесс ${NAMES[$i]} завершился — остальные продолжают работать" >&2
        # Добиваем возможные дочерние процессы этой группы (воркер uvicorn).
        kill -TERM -- "-$pid" 2>/dev/null
        PIDS[$i]=""
        EXIT_CODE=1
    done
    if [ "$alive" = 0 ]; then
        echo "[run] все процессы завершены" >&2
        exit "$EXIT_CODE"
    fi
    sleep 1
done
