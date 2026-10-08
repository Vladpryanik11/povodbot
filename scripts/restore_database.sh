#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 BACKUP_FILE DATABASE_URL" >&2
  exit 2
fi
backup_file="$1"
database_url="$2"
if [[ ! -f "$backup_file" || -z "$database_url" ]]; then
  echo "an existing backup file and an explicit target database are required" >&2
  exit 2
fi
read -r -p "Restore $backup_file into $database_url? Type RESTORE: " confirmation
if [[ "$confirmation" != "RESTORE" ]]; then
  echo "restore cancelled" >&2
  exit 1
fi
pg_restore --clean --if-exists --no-owner --dbname="$database_url" "$backup_file"
echo "restore completed"
