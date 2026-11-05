#!/bin/sh
# Har kuni 03:00 (Toshkent) da pg_dump, KEEP_DAYS kundan eskilarini o'chiradi.
set -eu
while true; do
  now=$(TZ=Asia/Tashkent date +%H%M)
  if [ "$now" = "0300" ]; then
    f="/backups/bot_$(date +%Y%m%d_%H%M).sql.gz"
    pg_dump --no-owner | gzip > "$f" && echo "backup ok: $f"
    find /backups -name 'bot_*.sql.gz' -mtime +"${KEEP_DAYS:-14}" -delete
    sleep 61
  fi
  sleep 30
done
