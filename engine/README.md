# engine

The Solana memecoin signal engine. It watches the pump.fun firehose, scores new launches in real time, and records what happened so the scoring can be calibrated against outcomes. It is a consumer of the keyless X access in `search/`: the social signal comes from there.

## The pipeline (`live.py`)

A new mint crosses the firehose and runs the gauntlet:

1. **Zone** the dev buy by size (`zone_of`). A small buy is green and suppressed; a large one earns attention.
2. **Enrich** from the token metadata (the IPFS `uri`) and resolve any linked tweet through the syndication CDN (`resolve_tweet`).
3. **Verify** the social claim against the data layer before trusting it.
4. **Discover** related accounts and posts.
5. **Cluster** and penalize coordinated launches (`cluster_penalty`). One wallet behind many names is a farm, and the score drops.
6. **Score** the survivor (`score_resolved`) and write it to the SQLite outcome ledger.

Every record is stamped with a timestamp, so `replay.py` can reconstruct the timing exactly.

## Modules

| File | Role |
|------|------|
| `live.py` | the firehose stream loop and the pipeline above |
| `engine_core.py` | the shared pure functions: zoning, scoring, name normalization, cluster penalty, the syndication resolver |
| `replay.py` | re-run the pipeline over a captured firehose log, deterministically |
| `outcomes.py` | revisit scored mints later and label the outcome (MOON, DEAD, migrated, concentrated) |
| `outcomes_calibrate.py` | fit the scoring weights against recorded outcomes |
| `discovery.py` | the social-discovery step (xAI x_search, syndication resolve, session pairs) |
| `solana_search.py` | Solana-side lookups |
| `stress.py` | load-test the stream loop |
| `livetest.py` | the full live run, kept as a committed regression guard |

## Running

```bash
pip install -r requirements.txt

python live.py                  # stream, score, write the ledger
python replay.py capture.jsonl  # re-run over a captured log
python outcomes.py              # label outcomes for scored mints
python outcomes_calibrate.py    # fit weights against the labels
```

`ENGINE_BUDGET` (seconds) bounds a `live.py` run. The raw capture goes to `/tmp/mints2.jsonl`.

## Tests

The offline suite lives in the repo root; run `pytest` from there. The engine logic is covered with the network and the websocket faked, so the pipeline, the guards, and the calibrator all run without touching the firehose or any RPC. `requirements-dev.txt` holds the test-only dependencies.

## Why verification is the load-bearing stage

A scanner produces candidates. Verification produces findings. The engine treats the social claim on a mint as a claim, not a fact, until the data layer backs it. Skipping that step does not fail randomly at scale; it fails confidently, with reproducible wrong numbers. The verify step is the difference between a score you can act on and a guess.
