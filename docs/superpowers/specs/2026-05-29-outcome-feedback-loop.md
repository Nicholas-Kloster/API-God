# Outcome-Feedback Loop (the engine's learning layer)

**Date:** 2026-05-29
**Status:** building (P1)
**Applies to:** the memecoin signal engine (`engine/`), not the search tool.

## Why

The engine scores new coins but never learns whether its picks were right. It has no idea if a coin it
ranked high later died, rugged, or ran. Without that, the scoring is a static guess and an attacker can
repeat the same fake forever. This loop measures what actually happened to scored coins and feeds it back.

## Free data path (confirmed working, keyless)

Public Solana RPC (`https://api.mainnet-beta.solana.com`), no key:
- `getSignaturesForAddress(mint, limit=1)` -> last on-chain activity -> age = is the coin dead or alive.
- `getTokenSupply(mint)` + `getTokenLargestAccounts(mint)` -> holder concentration (caveat: a pre-migration
  pump.fun coin's bonding-curve account shows as the largest holder, so concentration is noisy until P2).
- (P2) PumpPortal `subscribeMigration` -> graduation to Raydium/PumpSwap = the "ran" signal.
- (P2) bonding-curve account read / pool price -> price trajectory for full RUG/MOON labels.

## Components

- **EventRecorder** - when the engine scores a coin, log `{mint, creator, score, features, scored_at}` to
  a SQLite ledger (`outcomes.db`, separate from everything else).
- **OutcomeCollector** - for each recorded coin past its check window, query the free RPC for last-activity
  age + holder concentration, write it back to the row.
- **OutcomeLabeler** - rules -> a label. P1: `DEAD` (no activity in 24h) / `ALIVE` / `ALIVE-CONCENTRATED`.
  P2 adds `RAN`/`RUG`/`FLAT` once migration + price are wired.
- **(P3) Calibrator** - interpretable multinomial logistic regression over `(features -> label)`, per-feature
  information-gain, +/-10% weight-change cap, hold-out test + drift/bias guards. Publishes which features
  actually predicted good outcomes; updates the engine's weights.

## Schema (`outcomes.db`)

```sql
CREATE TABLE scored (
  mint TEXT PRIMARY KEY, creator TEXT, score REAL, features TEXT, scored_at REAL,
  outcome TEXT, checked_at REAL, last_trade_age_h REAL, top1_pct REAL, top5_pct REAL, raw TEXT
);
```

## Timing

Check a scored coin at T+6h, T+24h, T+72h after `scored_at`. T+6h catches fast death/rug; T+24h separates
dead from alive; T+72h is the final label (migrations settle by then).

## Phases

- **P1 (now):** EventRecorder + OutcomeCollector + OutcomeLabeler on free RPC. Label DEAD/ALIVE +
  concentration. Backtest: do high-scored coins survive more than low-scored ones?
- **P2:** migration (RAN) + price-based RUG/MOON labels (bonding-curve / pool reads, PumpPortal migration).
- **P3:** the calibrator that tunes the engine's weights from the labeled history.

## Build order

`outcomes.py` (record + collect + label + CLI) -> wire `record()` into the engine's scoring step ->
backtest on the aged capture set -> then P2/P3.
