#!/usr/bin/env bash
# Восстановление БД сервера из копии.
#   ./deploy/restore.sh backups/povod-XXXX.dump --rehearse   репетиция: во временную БД, боевая не тронута
#   ./deploy/restore.sh backups/povod-XXXX.dump              в боевую БД (нужно ввести RESTORE)
# Перед боевым восстановлением остановите приложение:
#   docker compose -f docker-compose.prod.yml --env-file .env stop api bot worker
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 BACKUP_FILE [--rehearse]" >&2
  exit 2
fi
backup_file="$1"
mode="${2:-}"
if [[ ! -f "$backup_file" ]]; then
  echo "backup file not found: $backup_file" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
compose=(docker compose -f docker-compose.prod.yml --env-file .env)
psql_admin=("${compose[@]}" exec -T postgres psql -U povod -d postgres -v ON_ERROR_STOP=1)

if [[ "$mode" == "--rehearse" ]]; then
  target="povod_rehearsal"
  "${psql_admin[@]}" -c "DROP DATABASE IF EXISTS $target" -c "CREATE DATABASE $target"
  "${compose[@]}" exec -T postgres pg_restore -U povod -d "$target" --no-owner --exit-on-error <"$backup_file"
  echo "tables restored:"
  "${compose[@]}" exec -T postgres psql -U povod -d "$target" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
  "${compose[@]}" exec -T postgres psql -U povod -d "$target" -tAc \
    "SELECT 'alembic version: ' || version_num FROM alembic_version"
  "${psql_admin[@]}" -c "DROP DATABASE $target"
  echo "rehearsal OK, the live database was not touched"
  exit 0
fi

if [[ -n "$mode" ]]; then
  echo "unknown option: $mode" >&2
  exit 2
fi
read -r -p "Replace the LIVE database with $backup_file? Type RESTORE: " confirmation
if [[ "$confirmation" != "RESTORE" ]]; then
  echo "restore cancelled" >&2
  exit 1
fi
"${compose[@]}" exec -T postgres pg_restore -U povod -d povod --clean --if-exists --no-owner --single-transaction <"$backup_file"
echo "restore completed; start the app again"
