#!/usr/bin/env python3
"""livepipe - real-time X engagement, pushed not polled.

X runs a server-push channel at api.x.com/live_pipeline. You open one long-lived NDJSON stream and
subscribe to topics like /tweet_engagement/<tweet_id>; X then pushes a new payload every time that
tweet's like/repost/reply/quote counts change. No polling, so no rate-limit tax. This rides the saved
session (cookies + csrf, no API key), exactly like the rest of the toolkit, and turns the deltas into
a velocity signal, which is what a momentum engine wants.

Captured contract (our own session, 2026-05-31):
  GET  api.x.com/live_pipeline/events?topic=/tweet_engagement/<id>      -> 200, NDJSON
       first line: {"topic":"/system/config","payload":{"config":{"session_id","subscription_ttl_millis":120000,"heartbeat_millis":25000}}}
  POST api.x.com/1.1/live_pipeline/update_subscriptions  (x-www-form-urlencoded)
       body: sub_topics=/tweet_engagement/<id>,...  unsub_topics=...     (add/remove, many at once)

  python livepipe.py <tweet_id> [<tweet_id> ...] [--seconds=N]
"""
import json, sys, time, re, requests
from pathlib import Path

STATE = Path.home() / ".x-session" / "state.json"
# public X web-app bearer (a constant, not a secret); the real auth is the session cookies
BEARER = ("Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
          "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
EVENTS = "https://api.x.com/live_pipeline/events"
SUBS = "https://api.x.com/1.1/live_pipeline/update_subscriptions"


def _session():
    """A requests.Session carrying the saved X cookies + the headers live_pipeline checks."""
    d = json.loads(STATE.read_text())
    s = requests.Session()
    for c in d.get("cookies", []):
        if c.get("name") and c.get("value"):
            s.cookies.set(c["name"], c["value"], domain=(c.get("domain") or "x.com").lstrip("."))
    ct0 = next((c["value"] for c in d.get("cookies", []) if c["name"] == "ct0"), "")
    s.headers.update({
        "authorization": BEARER, "x-csrf-token": ct0, "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-active-user": "yes",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    })
    return s


def parse_engagement(payload):
    """Pull the counts out of a tweet_engagement payload. Defensive: the exact nesting is read off the
    live event, so we scan the payload JSON for the known count fields wherever they sit."""
    flat = json.dumps(payload)
    out = {}
    for k in ("favorite_count", "retweet_count", "reply_count", "quote_count", "view_count", "bookmark_count"):
        m = re.search(rf'"{k}":\s*"?(\d+)"?', flat)
        if m:
            out[k] = int(m.group(1))
    return out


def subscribe(s, ids):
    """Add /tweet_engagement topics to the open connection (many at once)."""
    subs = ",".join("/tweet_engagement/" + str(i) for i in ids)
    s.post(SUBS, data={"sub_topics": subs, "unsub_topics": ""}, timeout=10)


def stream(ids, seconds=0):
    s = _session()
    first, rest = str(ids[0]), [str(i) for i in ids[1:]]
    r = s.get(EVENTS, params={"topic": "/tweet_engagement/" + first}, stream=True, timeout=(10, 35))
    print(f"[livepipe] connected {r.status_code}; watching {len(ids)} tweet(s)", file=sys.stderr)
    if r.status_code != 200:
        sys.exit(f"[livepipe] connect failed: {r.status_code} {r.text[:120]}")
    if rest:
        try: subscribe(s, rest)
        except Exception as e: print(f"[livepipe] subscribe: {e}", file=sys.stderr)
    last = {}                                            # tweet_id -> (counts, t)
    start = time.time()
    try:
        for line in r.iter_lines():
            if seconds and time.time() - start > seconds:
                break
            if not line:
                continue
            try: ev = json.loads(line)
            except Exception: continue
            top = ev.get("topic", "")
            if not top.startswith("/tweet_engagement/"):
                continue                                 # /system/config, /system/subscriptions, heartbeats
            tid = top.rsplit("/", 1)[-1]
            counts = parse_engagement(ev.get("payload", {}))
            if not counts:
                continue
            now, vel = time.time(), ""
            if tid in last:
                pc, pt = last[tid]; dt = now - pt
                dlike = counts.get("favorite_count", 0) - pc.get("favorite_count", 0)
                drt = counts.get("retweet_count", 0) - pc.get("retweet_count", 0)
                if dt > 0:
                    vel = f"   velocity +{dlike}like +{drt}rt in {dt:.0f}s = {(dlike + drt) / dt * 60:.0f}/min"
            last[tid] = (counts, now)
            print(f"{tid}  {counts}{vel}", flush=True)
    except requests.exceptions.ReadTimeout:
        print("[livepipe] idle past the read window (no deltas); connection was healthy", file=sys.stderr)
    finally:
        r.close()


def main():
    ids = [a for a in sys.argv[1:] if a.isdigit()]
    secs = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--seconds=")), 0)
    if not ids:
        sys.exit("usage: livepipe.py <tweet_id> [<tweet_id> ...] [--seconds=N]")
    stream(ids, secs)


if __name__ == "__main__":
    main()
