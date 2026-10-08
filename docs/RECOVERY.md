# Backup и recovery

Backup выполняется PostgreSQL custom format с ограниченными правами файла:

```bash
./scripts/backup_database.sh "$DATABASE_URL" ./backups/povod-$(date +%Y%m%d-%H%M).dump
```

Restore никогда не направляется в production без явной проверки target:

```bash
./scripts/restore_database.sh ./backups/povod-YYYYMMDD-HHMM.dump "$RECOVERY_DATABASE_URL"
```

Скрипт restore требует интерактивное слово `RESTORE`, использует `--clean
--if-exists --no-owner` и должен запускаться только в изолированном окружении.
После восстановления выполнить `alembic current`, acceptance tests и проверить
последний payment event/заказ. Политика retention, шифрование backup и RPO/RTO
утверждаются владельцем инфраструктуры до коммерческого запуска.
