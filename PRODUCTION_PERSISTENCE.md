# Production persistence architecture

VoiceLab now uses a versioned SQLite state store plus an append-only event stream.

## Guarantees

- SQLite WAL mode for concurrent readers/writers.
- 30-second busy timeout and serialized `BEGIN IMMEDIATE` mutations.
- Every successful state mutation increments a monotonic per-session version.
- Every mutation appends one row to `research_events`.
- Memory and verification history are merged append-only so concurrent FastAPI/LiveKit writes are not lost.
- Existing two-column `research_sessions` databases migrate in place.
- Replay reads the durable event stream, not only the in-memory process cache.
- FastAPI and LiveKit workers therefore share one durable source of truth.

## Concurrency model

Scalar state updates are serialized by SQLite. When two stale workers update different fields, their changes are merged against the latest committed snapshot. When they update the same scalar field concurrently, the later transaction wins deterministically. Scientific actions should therefore be modeled as immutable calculation events and should never depend on an uncommitted client-side snapshot.

For larger multi-node deployments, replace the local SQLite store with PostgreSQL while keeping the same event/snapshot contract.
