#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 DATABASE_URL OUTPUT_FILE" >&2
  exit 2
fi
database_url="$1"
output_file="$2"
if [[ -z "$database_url" || -z "$output_file" || "$output_file" == "/" ]]; then
  echo "database URL and an explicit output file are required" >&2
  exit 2
fi
umask 077
pg_dump --format=custom --file="$output_file" "$database_url"
echo "backup written to $output_file"
