#!/usr/bin/env bash
# Локальный запуск Flamenco Studio одной командой: Telegram-бот + backend API +
# сайт (Next.js). Для разработки, не для продакшена — там compose.yaml
# (см. docs/deployment.md).
#
#   ./run.sh          бот + API + сайт
#   ./run.sh site     только API + сайт
#   ./run.sh bot      только бот
#
# Логи всех процессов — в одном терминале с префиксами [bot] [api] [web].
# Ctrl+C останавливает всё; если один процесс завершился — останавливаются и
# остальные (чтобы падение не прошло незамеченным).
#
# Порты: API_PORT (по умолчанию 8000), WEB_PORT (по умолчанию 3000).
# Совместим с системным bash 3.2 на macOS.

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODE="${1:-all}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

case "$MODE" in
    all) RUN_BOT=1; RUN_SITE=1 ;;
    site) RUN_BOT=0; RUN_SITE=1 ;;
    bot) RUN_BOT=1; RUN_SITE=0 ;;
    -h | --help)
        sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
    *)
        echo "Неизвестный режим «$MODE». Используйте: ./run.sh [all|site|bot]" >&2
        exit 2
        ;;
esac

fail() {
    echo "[run] $*" >&2
    exit 1
}

# ---------- Проверки окружения ----------
[ -x .venv/bin/python ] || fail "Не найден .venv/bin/python. Создайте окружение: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
if [ "$RUN_SITE" = 1 ] && [ ! -d frontend/node_modules ]; then
    fail "Не найден frontend/node_modules. Установите зависимости: (cd frontend && npm install)"
fi
[ -f .env ] || echo "[run] Внимание: нет файла .env — переменные берутся только из окружения (см. env.example)." >&2

port_busy() {
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}
if [ "$RUN_SITE" = 1 ]; then
    for port in "$API_PORT" "$WEB_PORT"; do
        if port_busy "$port"; then
            echo "[run] Порт $port уже занят:" >&2
            lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2
            fail "Остановите процесс выше (например, прежний run-website.sh) или задайте другой порт: API_PORT=… WEB_PORT=… ./run.sh"
        fi
    done
fi

# Пакет берётся из src/ напрямую — не зависим от editable-install `.pth`
# (на macOS с iCloud он иногда скрывается, см. pyproject.toml).
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# ---------- Процессы ----------
# set -m: каждый фоновый процесс — в своей группе, чтобы при остановке
# погасить его целиком (npm → node, uvicorn → reload-воркер).
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

if [ "$RUN_SITE" = 1 ]; then
    start api 36 .venv/bin/python -m uvicorn flamenco_bot.api.app:app \
        --host 127.0.0.1 --port "$API_PORT" --reload --reload-dir src
    start web 35 bash -c "cd frontend && API_BASE_URL='http://127.0.0.1:$API_PORT' exec npm run dev -- --port '$WEB_PORT'"
fi
if [ "$RUN_BOT" = 1 ]; then
    start bot 33 .venv/bin/python -m flamenco_bot
fi

if [ "$RUN_SITE" = 1 ]; then
    echo "[run] сайт: http://localhost:$WEB_PORT   API: http://127.0.0.1:$API_PORT"
fi
echo "[run] Ctrl+C — остановить всё"

# Следим за процессами: если один завершился, останавливаем остальные.
while :; do
    for i in "${!PIDS[@]}"; do
        if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
            echo "[run] процесс ${NAMES[$i]} завершился — останавливаю остальные" >&2
            exit 1
        fi
    done
    sleep 1
done
