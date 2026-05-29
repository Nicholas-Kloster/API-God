"""Outcome-feedback loop (P1): the engine's learning layer.

The engine scores coins but never learns if its picks were right. This logs every scored coin, then
later checks on-chain what actually happened to it (free public Solana RPC, no key), and labels it.
Later (P3) those labels tune the engine's weights.

Usage:
    python outcomes.py collect <mint>     # one-shot: check + label a single mint (the test surface)
    python outcomes.py run                 # check every recorded coin that's past its window
    python outcomes.py stats               # label distribution + win-rate by score band
record(coin) is called by the engine at scoring time.
"""
import sqlite3, json, time, sys, os
import requests

RPC = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
DB  = os.environ.get("OUTCOMES_DB", os.path.join(os.path.dirname(__file__), "outcomes.db"))
CHECK_AFTER_H = 6           # first outcome check at T+6h
DEAD_SILENCE_H = 6          # no on-chain activity in this many hours = abandoned (live memecoins trade constantly)

def _db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS scored (
        mint TEXT PRIMARY KEY, creator TEXT, score REAL, features TEXT, scored_at REAL,
        outcome TEXT, checked_at REAL, last_trade_age_h REAL, top1_pct REAL, top5_pct REAL, raw TEXT)""")
    return c

def record(coin):
    """Called by the engine when it scores a coin. coin = {mint, creator, score, features dict}."""
    c = _db()
    c.execute("INSERT OR IGNORE INTO scored(mint,creator,score,features,scored_at) VALUES(?,?,?,?,?)",
              (coin.get("mint"), coin.get("creator"), coin.get("score"),
               json.dumps(coin.get("features", {})), time.time()))
    c.commit(); c.close()

def _rpc(method, params, retries=4):
    """Public RPC throttles hard; retry with backoff. For volume, point SOLANA_RPC at Helius (free key)."""
    for i in range(retries):
        try:
            r = requests.post(RPC, timeout=15,
                              json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            if r.status_code == 429:
                time.sleep(1.5 * (i + 1)); continue
            res = r.json()
            if "result" in res:
                return res["result"]
            time.sleep(1.0 * (i + 1))          # error / rate note -> back off and retry
        except Exception:
            time.sleep(1.0 * (i + 1))
    return None

def collect_outcome(mint):
    """Read free on-chain signals for a mint: last-activity age + holder concentration."""
    out = {"last_trade_age_h": None, "top1_pct": None, "top5_pct": None}
    sigs = _rpc("getSignaturesForAddress", [mint, {"limit": 1}])
    if sigs and sigs[0].get("blockTime"):
        out["last_trade_age_h"] = round((time.time() - sigs[0]["blockTime"]) / 3600, 2)
    sup = _rpc("getTokenSupply", [mint])
    largest = _rpc("getTokenLargestAccounts", [mint])
    if sup and largest and largest.get("value"):
        total = float(sup["value"]["amount"]) or 1.0
        amts = sorted((float(a["amount"]) for a in largest["value"]), reverse=True)
        out["top1_pct"] = round(100 * amts[0] / total, 1) if amts else None
        out["top5_pct"] = round(100 * sum(amts[:5]) / total, 1) if amts else None
    return out

def label(o):
    """P1 labels (note: concentration includes the bonding-curve account pre-migration, so it's noisy;
    activity age is the reliable signal). RUG/MOON come in P2 with price + migration."""
    age = o.get("last_trade_age_h")
    if age is None:
        return "UNKNOWN"
    if age > DEAD_SILENCE_H:
        return "DEAD"                       # no recent on-chain activity = abandoned
    if (o.get("top1_pct") or 0) > 90 or (o.get("top5_pct") or 0) > 98:
        return "ALIVE-CONCENTRATED"         # still traded but whale/curve-dominated
    return "ALIVE"

def _apply(mint, c):
    o = collect_outcome(mint); lab = label(o)
    c.execute("""UPDATE scored SET outcome=?, checked_at=?, last_trade_age_h=?, top1_pct=?, top5_pct=?, raw=?
                 WHERE mint=?""",
              (lab, time.time(), o["last_trade_age_h"], o["top1_pct"], o["top5_pct"], json.dumps(o), mint))
    c.commit()
    return lab, o

def run():
    c = _db(); now = time.time()
    due = c.execute("SELECT mint FROM scored WHERE outcome IS NULL AND scored_at <= ?",
                    (now - CHECK_AFTER_H * 3600,)).fetchall()
    print(f"{len(due)} coins due for outcome check")
    for (mint,) in due:
        lab, o = _apply(mint, c)
        print(f"  {mint[:14]}.. -> {lab}  (age {o['last_trade_age_h']}h, top1 {o['top1_pct']}%)")
    c.close()

def stats():
    c = _db()
    rows = c.execute("SELECT outcome, COUNT(*) FROM scored WHERE outcome IS NOT NULL GROUP BY outcome").fetchall()
    print("label distribution:", dict(rows))
    # survival (not DEAD) by score band -> does a higher engine score predict survival?
    bands = c.execute("""SELECT CASE WHEN score>=4 THEN 'high(>=4)' WHEN score>=1 THEN 'mid(1-3)' ELSE 'low(<1)' END band,
                                COUNT(*) n, SUM(outcome!='DEAD' AND outcome!='UNKNOWN') survived
                         FROM scored WHERE outcome IS NOT NULL GROUP BY band""").fetchall()
    print("survival by score band (the backtest):")
    for band, n, surv in bands:
        print(f"  {band:10} {surv or 0}/{n} survived ({100*(surv or 0)//max(n,1)}%)")
    c.close()

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "collect" and len(sys.argv) > 2:
        o = collect_outcome(sys.argv[2]); print(json.dumps({**o, "label": label(o)}, indent=1))
    elif cmd == "run": run()
    elif cmd == "stats": stats()
    else: print(__doc__)
