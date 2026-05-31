#!/usr/bin/env python3
"""livepipe - real-time X engagement, pushed not polled.

X runs a server-push channel at api.x.com/live_pipeline. You open one long-lived NDJSON stream and
subscribe to topics like /tweet_engagement/<tweet_id>; X then pushes a new payload every time that
tweet's like/repost/reply counts change. No polling, so no rate-limit tax. Rides the saved session
(cookies + csrf, no API key), and turns the deltas into a velocity signal.

Contract (captured + verified, our own session, 2026-05-31):
  GET  api.x.com/live_pipeline/events?topic=/tweet_engagement/<id>   -> 200 NDJSON over HTTP/2.
       first line: {"topic":"/system/config","payload":{"config":{"session_id",...,"subscription_ttl_millis":120000,"heartbeat_millis":25000}}}
  POST api.x.com/1.1/live_pipeline/update_subscriptions
       header  LivePipeline-Session: <session_id>     (REQUIRED; missing -> 400 code 38)
       body    sub_topics=/tweet_engagement/<id>,...  unsub_topics=...
  Multi-subscribe only works when the POST shares the stream's connection (HTTP/2) AND carries the
  session header. Both matter: plain requests on HTTP/1.1 without the header is a silent no-op.

  python livepipe.py <tweet_id> [<tweet_id> ...] [--seconds=N]
"""
import json, sys, time, re
from pathlib import Path
import httpx

STATE = Path.home() / ".x-session" / "state.json"
# public X web-app bearer (a constant, not a secret); the real auth is the session cookies
BEARER = ("Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
          "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
EVENTS = "https://api.x.com/live_pipeline/events"
SUBS = "https://api.x.com/1.1/live_pipeline/update_subscriptions"


def _client():
    """An HTTP/2 httpx.Client carrying the saved X cookies + the headers live_pipeline checks.
    HTTP/2 is required so the subscribe POST multiplexes onto the stream's connection."""
    d = json.loads(STATE.read_text())
    cookies = {c["name"]: c["value"] for c in d.get("cookies", []) if c.get("name") and c.get("value")}
    headers = {
        "authorization": BEARER, "x-csrf-token": cookies.get("ct0", ""),
        "x-twitter-auth-type": "OAuth2Session", "x-twitter-active-user": "yes",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    return httpx.Client(http2=True, cookies=cookies, headers=headers, timeout=httpx.Timeout(40.0, connect=10.0))


def subscribe(client, session_id, ids, unsub=()):
    """Add/remove /tweet_engagement topics on the open connection. The LivePipeline-Session header
    (the session_id from /system/config) is required, or X returns 400 code 38."""
    data = {"sub_topics": ",".join("/tweet_engagement/" + str(i) for i in ids),
            "unsub_topics": ",".join("/tweet_engagement/" + str(i) for i in unsub)}
    return client.post(SUBS, headers={"LivePipeline-Session": session_id}, data=data)


def parse_engagement(payload):
    """Pull the counts out of a tweet_engagement payload. Events push the count that changed, so we
    scan for whatever count fields are present."""
    flat = json.dumps(payload)
    out = {}
    for k in ("favorite_count", "retweet_count", "reply_count", "quote_count", "view_count", "bookmark_count"):
        m = re.search(rf'"{k}":\s*"?(\d+)"?', flat)
        if m:
            out[k] = int(m.group(1))
    return out


def stream(ids, seconds=0):
    last, start = {}, time.time()
    with _client() as client:
        with client.stream("GET", EVENTS, params={"topic": "/tweet_engagement/" + str(ids[0])}) as r:
            print(f"[livepipe] connected {r.status_code} ({r.http_version}); watching {len(ids)} tweet(s)", file=sys.stderr)
            if r.status_code != 200:
                sys.exit(f"[livepipe] connect failed: {r.status_code}")
            sid = None
            for line in r.iter_lines():
                if seconds and time.time() - start > seconds:
                    break
                if not line:
                    continue
                try: ev = json.loads(line)
                except Exception: continue
                top = ev.get("topic", "")
                if top == "/system/config" and sid is None:        # grab the session id, then subscribe the rest
                    sid = ev.get("payload", {}).get("config", {}).get("session_id")
                    if sid and ids[1:]:
                        try: subscribe(client, sid, ids[1:])
                        except Exception as e: print(f"[livepipe] subscribe: {e}", file=sys.stderr)
                    continue
                if not top.startswith("/tweet_engagement/"):
                    continue
                tid = top.rsplit("/", 1)[-1]
                counts = parse_engagement(ev.get("payload", {}))
                if not counts:
                    continue
                now = time.time()
                hist = last.setdefault(tid, {})                   # field -> (value, t); events carry one field at a time
                parts = []
                for f, v in counts.items():
                    if f in hist:                                 # only after a baseline for that field
                        pv, pt = hist[f]; dt = now - pt
                        if dt > 0 and v != pv:
                            parts.append(f"{f.split('_')[0]} +{v - pv} ({(v - pv) / dt * 60:.0f}/min)")
                    hist[f] = (v, now)
                print(f"{tid}  {counts}" + (("   " + "  ".join(parts)) if parts else ""), flush=True)


def main():
    ids = [a for a in sys.argv[1:] if a.isdigit()]
    secs = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--seconds=")), 0)
    if not ids:
        sys.exit("usage: livepipe.py <tweet_id> [<tweet_id> ...] [--seconds=N]")
    stream(ids, secs)


if __name__ == "__main__":
    main()
