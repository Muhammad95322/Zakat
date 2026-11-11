#!/usr/bin/env sh
# Backup/restore PostgreSQL + unggahan pada stack docker compose.
#   sh scripts/backup_postgres_compose.sh backup            -> backups/pg-<waktu>.dump + uploads-<waktu>.tar.gz
#   sh scripts/backup_postgres_compose.sh restore <dump> <uploads.tar.gz>
set -eu
DB_USER="${POSTGRES_USER:-zakat}"; DB_NAME="${POSTGRES_DB:-zakat_insight}"
mkdir -p backups && umask 077
case "${1:-}" in
  backup)
    t=$(date +%Y%m%d-%H%M%S)
    docker compose exec -T db pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "backups/pg-$t.dump"
    tar czf "backups/uploads-$t.tar.gz" uploads 2>/dev/null || true
    echo "Backup: backups/pg-$t.dump backups/uploads-$t.tar.gz" ;;
  restore)
    [ -n "${2:-}" ] || { echo "Pakai: restore <dump> [uploads.tar.gz]"; exit 2; }
    docker compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner < "$2"
    [ -n "${3:-}" ] && tar xzf "$3"
    echo "Restore selesai." ;;
  *) echo "Pakai: $0 backup|restore"; exit 2 ;;
esac
