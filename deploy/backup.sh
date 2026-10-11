#!/usr/bin/env bash
# Резервная копия БД сервера. Запуск из каталога с docker-compose.prod.yml:
#   ./deploy/backup.sh            -> backups/povod-ГГГГММДД-ЧЧММСС.dump
# Хранит последние 14 копий. Для расписания: crontab -e
#   15 3 * * * cd /opt/povod && ./deploy/backup.sh >> backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
compose=(docker compose -f docker-compose.prod.yml --env-file .env)
mkdir -p backups
umask 077
file="backups/povod-$(date +%Y%m%d-%H%M%S).dump"

"${compose[@]}" exec -T postgres pg_dump -U povod -d povod --format=custom >"$file"
# Пустая или обрезанная копия хуже, чем её отсутствие: проверяем, что архив читается.
"${compose[@]}" exec -T postgres pg_restore --list >/dev/null <"$file"

ls -1t backups/povod-*.dump | tail -n +15 | xargs -r rm --
echo "backup written to $file ($(du -h "$file" | cut -f1))"
