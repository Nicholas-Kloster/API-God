# API-God M1: Bulletproof + Tested Core

**Date:** 2026-05-30
**Status:** Approved (design)
**Scope:** Milestone 1 of making API-God fully functional. Harden and test the engine. No new features, no UI, no aesthetics. M2 (functional UI) and M3 (aesthetics) get their own spec cycles.

## Goal

Make the engine provably correct so a UI can be built on a known-good foundation. Every known bug fixed, each fix proven by a test that fails without it, and an automated suite that runs offline and deterministically so regressions cannot creep back.

## Non-goals

- No UI, no styling, no new product features.
- No new runtime dependencies. Dev-only test deps are allowed.
- No change to external behavior except the bug fixes listed here.

## The fixes

Each maps to a file and gets its own test.

### Regressions (from recent work)
1. `replay.py`: `has_ts` checks only the first event, so a mixed capture (some lines without `_ts`) raises KeyError mid-run. Fix: per-event `_ts` fallback.
2. `xsearch.py` session backend: drain budget is a fixed 2s; slow responses end pagination early and truncate results. Fix: tie the budget to the scroll delay / wait for the response.

### Crash or wrong label
3. `outcomes.py`: zero-supply guard `or 1.0` produces nonsense holder percentages and a false ALIVE-CONCENTRATED label. Fix: when supply <= 0, leave concentration null.
4. `discovery.py`: an xAI transport/HTTP error returns `[]` (reads as "searched, none found") instead of None ("not searched"), penalizing real coins. Fix: distinguish failure (None) from genuine empty.
5. `outcomes_calibrate.py`: the stratified split raises ValueError on extreme class imbalance near MIN_SAMPLES. Fix: require enough minority samples or fall back to a non-stratified split.

### Quietly skews results
6. `live.py` vs `replay.py`: cluster penalty yields the same score but different notes/counts, so a replay cannot match a live run. Fix: unify into one `engine_core` function with one canonical note.
7. `replay.py`: summary percentile lacks the empty-buffer guard `live.py` has; IndexError on an empty/all-green capture. Fix: add the guard.
8. `outcomes.py` run(): coins labeled UNKNOWN are never rechecked. Fix: include UNKNOWN in the recheck query.
9. `outcomes.py`: DexScreener migration detection uses a 2-string blocklist; fragile to provider naming. Fix: whitelist known graduated DEXes.
10. `outcomes.py`: a migrated coin with >90% single-holder concentration is labeled MOON/FLAT with no concentration flag and feeds the calibrator as "good." Fix: apply the concentration check on the migrated path too.
11. `discovery.py` / `solana_search.py` / `xsearch.py`: the syndication resolver is duplicated across files and has drifted. Fix: one resolver in `engine_core`, all callers use it.

### Minor
12. `outcomes.py`: `_db()` / `record()` can leak a connection on exception. Fix: context-managed connection.
13. `outcomes.py`: 429 retries ignore Retry-After. Fix: honor it.
14. `outcomes_calibrate.py`: `tempfile.mktemp` in selftest. Fix: NamedTemporaryFile.
15. `outcomes.py`: a legitimate `price_usd` of 0 is stored as None. Fix: preserve 0.
16. `outcomes_calibrate.py`: the `independent` count is marked discrete for mutual-info, biasing the estimate. Fix: bin it or mark continuous.

### The gap behind all of it
17. No automated tests exist. Build a pytest suite covering the pipeline so every fix above is proven and protected.

## Test architecture

- Dev deps only: `pytest`, `pytest-asyncio` (`engine/requirements-dev.txt`), `asyncio_mode = auto`. Runtime deps unchanged.
- `tests/` at repo root. `testdata/` holds committed fixtures: a PumpPortal `subscribeNewToken` frame, a pump.fun metadata JSON, syndication 200 / 404 / TweetTombstone responses, RPC + DexScreener payloads, and a small `_ts`-stamped `mints.jsonl`.
- No test touches the network. `monkeypatch` replaces `requests.get/post` with canned responses; a fake async `websockets.connect` context manager yields scripted frames and raises `asyncio.TimeoutError` to drive the stream loop. (Toolkit confirmed against Okken, Python Testing with pytest, 2nd ed, ch10: monkeypatch + unittest.mock, no requests-specific dependency.)

## Execution order (safety net first)

1. Characterization tests over current good behavior (engine_core pure functions, pipeline over a fixture). Suite green.
2. Fix each finding test-first: a test that fails without the fix, then the fix, then green.
3. Refactor under green: consolidate the resolver into `engine_core`; unify the cluster penalty into `engine_core`. Suite stays green throughout.
4. Run the code-reviewer agents on the M1 diff. Re-run `livetest.py`.

## Definition of done

- Every finding (1-16) fixed, each with a test that fails without the fix.
- Finding 17: pytest suite green, offline, deterministic.
- `engine_core` is the single home for the resolver and the cluster penalty.
- code-reviewer agents return clean on the M1 diff.
- No new runtime deps.
- **Verification gate (load-bearing):** individual fixes are proven by the suite as we go. A full end-to-end live run happens ONLY after checking in with Nick for his recommendations on how to run it. No full test fires without that check-in.

## After M1

Spec -> implementation plan (writing-plans) -> implement with review + test at each step -> M1 done -> then M2 (functional UI) gets its own spec cycle. Aesthetics (M3) come last.
