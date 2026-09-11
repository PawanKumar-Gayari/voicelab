# PostgreSQL Production Event Store

VoiceLab supports PostgreSQL as the production source of truth while retaining SQLite as a local/development backend.

## Guarantees

- Durable session snapshot in `research_sessions.state_json` (`JSONB`).
- Monotonically increasing per-session `version`.
- Immutable `research_events` rows with `UNIQUE(session_id, version)`.
- `SELECT ... FOR UPDATE` serializes concurrent mutations for the same session.
- Append-only `memory` and `verification_history` are merged against the latest state so concurrent workers do not silently lose entries.
- Snapshot update and event append commit in the same PostgreSQL transaction.
- Rollback leaves both snapshot and event stream unchanged.
- Replay reads the immutable event stream in event order.
- Session deletion cascades to events.

Scalar fields retain the same optimistic last-writer-wins semantics as the SQLite implementation; append-only collections use merge semantics.

## Deployment

Set:

```env
POSTGRES_PASSWORD=<long-random-secret>
VOICELAB_DATABASE_URL=postgresql://voicelab:<password>@postgres:5432/voicelab
```

Then:

```bash
docker compose up -d --build
```

Schema creation is idempotent and runs automatically. For a pre-existing deployment, take a database backup before switching the backend.

## Migration strategy

The application does not automatically copy an existing SQLite database into PostgreSQL. This is intentional: production data migration should be explicit and audited. Export/import tooling should be run once against a maintenance copy, verify row counts and event versions, then switch `VOICELAB_DATABASE_URL`.

## Verification

Static contract:

```bash
python scripts/verify_postgres_store.py
```

Live database connectivity:

```bash
VOICELAB_DATABASE_URL='postgresql://...' python scripts/verify_postgres_store.py --live
```

## SQLite → PostgreSQL migration

VoiceLab now includes an explicit migration command at `scripts/migrate_sqlite_to_postgres.py`.
It is intentionally separate from application startup so a production cutover cannot silently
copy or mutate data.

### 1. Prepare a consistent SQLite source

For production, stop SQLite writers before the final migration, or make a maintenance copy of
the database and migrate from that copy. Keep the original SQLite file untouched as the rollback
source until PostgreSQL has been accepted in production.

### 2. Dry run first

```bash
VOICELAB_DATABASE_URL='postgresql://...' \
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/voicelab_state.db \
  --dry-run
```

The dry run reports row counts and SHA-256 checksums for `research_sessions` and
`research_events`. It writes no migration rows. A new migration also requires an empty
PostgreSQL research database; this prevents accidental mixing of two histories.

### 3. Start the migration

```bash
VOICELAB_DATABASE_URL='postgresql://...' \
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/voicelab_state.db \
  --job-id 2026-09-09-voicelab-01
```

Each batch is committed independently. The PostgreSQL migration table records the source
fingerprint and progress, so an interrupted process can resume safely:

```bash
VOICELAB_DATABASE_URL='postgresql://...' \
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/voicelab_state.db \
  --job-id 2026-09-09-voicelab-01
```

The command refuses to resume if the SQLite source fingerprint has changed. Existing rows are
never overwritten silently: an identical row is accepted, while a conflicting row aborts the
job.

### 4. Validation and cutover

A migration is marked `completed` only after both tables have identical row counts and identical
canonical SHA-256 checksums. The event sequence is also advanced so future PostgreSQL-generated
event IDs continue after the imported IDs.

Only after validation should the application be switched to PostgreSQL. Stop SQLite writers before
cutover so the validated source cannot diverge.

### 5. Rollback guidance

If the cutover must be reversed **before PostgreSQL receives any new writes**, first stop all
application workers and then run:

```bash
VOICELAB_DATABASE_URL='postgresql://...' \
python scripts/migrate_sqlite_to_postgres.py \
  --job-id 2026-09-09-voicelab-01 \
  --rollback
```

Rollback is deliberately refused if PostgreSQL has changed since the completed migration. If the
checksum no longer matches, do **not** delete rows: restore PostgreSQL from a database backup or
use the application-level recovery procedure, because deleting the migrated rows could destroy
new production writes.

Keep the original SQLite database read-only until the PostgreSQL cutover has been validated and
backed up. The migration command does not delete or modify the SQLite source.
