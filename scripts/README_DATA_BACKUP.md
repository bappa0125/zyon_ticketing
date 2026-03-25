# Data backup (MongoDB, Redis, Qdrant)

Backs up all data stores into the project `data_backup/` directory so you can copy to Google Drive or elsewhere.

## What is backed up

| Store    | Contents                    | Backup path                    |
|----------|-----------------------------|---------------------------------|
| MongoDB  | `chat` database             | `data_backup/<timestamp>/mongodb/chat.archive` |
| Redis    | Cache/session data          | `data_backup/<timestamp>/redis/dump.rdb`       |
| Qdrant   | Vector DB (embeddings)      | `data_backup/<timestamp>/qdrant/full.snapshot` |

## Run once

From the project root (where `docker-compose.yml` is):

```bash
./scripts/run_data_backup.sh
```

Output goes to `data_backup/YYYYMMDD_HHMMSS/`. Upload that folder to Google Drive.

## Run every hour

**Option A – cron (recommended)**

```bash
crontab -e
# Add (replace path with your project root):
0 * * * * /path/to/zyon_ai_ticketing/scripts/run_data_backup.sh
```

**Option B – long-running loop**

```bash
./scripts/run_data_backup_hourly.sh
```

Runs a backup every 3600 seconds. Override with `BACKUP_INTERVAL_SECONDS=1800` if you want every 30 minutes.

## Requirements

- `docker compose` (or `docker-compose`) and stack running
- `curl` (for Qdrant snapshot)
- Optional: `jq` (for Qdrant snapshot name parsing; script has a fallback without it)

## Restore (reference)

## Restore (script)

From the project root:

```bash
./scripts/restore_data_backup.sh data_backup/<timestamp>
```

This restores:

- **MongoDB**: `chat` database (uses `--drop`)
- **Redis**: replaces `/data/dump.rdb` and restarts the `redis` container
- **Qdrant**: best-effort (snapshot restore is version/collection dependent; may require manual restore)

## Restore (manual reference)

- **MongoDB:** `docker compose exec -T mongodb mongorestore --drop --db=chat --archive < data_backup/<ts>/mongodb/chat.archive`
- **Redis:** copy `data_backup/<ts>/redis/dump.rdb` to `redis:/data/dump.rdb` then `docker compose restart redis`
- **Qdrant:** use Qdrant’s snapshot restore (see [Qdrant docs](https://qdrant.tech/documentation/tutorials-operations/create-snapshot/))
