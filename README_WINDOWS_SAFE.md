# Windows-safe legacy conversion

This converter is designed for the 48-session legacy VoiceLab SQLite database.

Safety:
- Source database is opened read-only (`mode=ro` + `query_only`).
- Original and backup are never modified.
- A separate output database is created directly; no temp-to-final rename is used.
- Existing output is refused unless `--force` is explicit.
- Writer connection is closed before validation.
- Validation connection is closed before cleanup.
- Exactly 48 sessions are required by default.
- One `legacy_import` event is created per session.
- Stale `.tmp-*.db` files are removed only after successful validation.
- Source size and mtime are checked after conversion.

Run from the VoiceLab project root:

```powershell
python .\scripts\convert_legacy_sqlite.py --source "D:\my server\pawan11\voicelab\voicelab_state.db" --output "D:\my server\pawan11\voicelab\voicelab_state.current.db" --owner-id admin --stale-temp-glob "voicelab_state.current.db.tmp-*.db"
```

Do not delete the original or backup. The stale temp files from earlier failed attempts
will only be removed after this new conversion has passed validation.
