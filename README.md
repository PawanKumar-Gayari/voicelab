# VoiceLab PubChem Integration — Phase 5

Phase 5 hardens the external-geometry path.

## Added

1. Principal-axis based candidate generation.
   - Centers geometry first.
   - Uses the covariance/inertia-style eigensystem.
   - Adds atom-direction and pairwise-cross-product axes for degenerate frames.
   - Generates rotations, reflections, improper rotations and inversion.
   - Does not assign a point group by itself.

2. SQLite cache.
   - Stores only successful external records.
   - Keeps PubChem retrieval separate from scientific verification.

3. Registry-first fallback boundary.
   - BF3/H2O/NH3 remain on the existing registry path.
   - External lookup is attempted only after a registry miss.
   - External data cannot be returned as scientific output without final PASS/VERIFIED status.

## Deliberate production boundary

This package does NOT automatically patch production `full_analysis.py`, because
the current public `full_analysis()` contract resolves its molecule ID through
the persistent registry. Changing that contract blindly would risk the existing
BF3/H2O/NH3 regression path.

The next wiring step should inject these components into the existing
`full_analysis()` orchestration behind a registry-miss-only branch, then run the
full regression suite before restarting services.
