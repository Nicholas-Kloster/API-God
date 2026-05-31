#!/usr/bin/env python3
"""census - read X's per-endpoint rate-limit budget across the whole GraphQL surface, keyless.

X stamps x-rate-limit-limit/remaining/reset on every GraphQL response, including a 422 that fails
variable validation. So one throwaway request to any recognized queryId reveals that operation's
bucket: no browser, no features blob, no valid query. This pulls the live queryId map from X's JS
bundle, sweeps every read (Query) operation, and tabulates each bucket.

The read is cheap, not free: each probe spends one token of the bucket it measures (a rejected 422
still decrements). Every bucket is at least 50 deep, so one probe each is affordable, but it is a
budgeted sweep, not a free scan. Pace with --delay.

Mutations are skipped by default. A write op probed with empty variables 422s before it executes, so
it never writes, but we do not sweep the write surface unless asked (--include-mutations).

The counter sits at X's GraphQL routing layer: an op whose queryId does not route gets a 403 HTML
block from the edge WAF with no rate-limit headers; those are reported as no-headers, not buckets.

Rides the saved session (cookies + ct0 + the public web bearer). Reads only.

  python census.py                      # sweep all read ops, human table + histogram
  python census.py --json out.json      # also write the full per-op map
  python census.py --delay 0.4          # gentler pacing
  python census.py --limit-ops 5        # smoke test on the first few
  python census.py --include-mutations  # also probe write ops (still 422, never executes)
"""
import re, json, sys, time, argparse
from pathlib import Path
from collections import Counter
import requests

STATE = Path.home() / ".x-session" / "state.json"
# public X web-app bearer (a constant, not a secret); the real auth is the session cookies
BEARER = ("Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
          "=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
HOME = "https://x.com/"
GQL = "https://x.com/i/api/graphql/{qid}/{op}"
OP_RE = re.compile(r'queryId:"([^"]+)",operationName:"([^"]+)",operationType:"([^"]+)"')
BUNDLE_RE = re.compile(r'https://abs\.twimg\.com/responsive-web/client-web/[A-Za-z0-9._/-]+\.js')


def _load_cookies():
    d = json.loads(STATE.read_text())
    return {c["name"]: c["value"] for c in d.get("cookies", []) if c.get("name") and c.get("value")}


def _clean_session(cookies):
    """Plain session (cookies + UA only) for fetching the home HTML and the JS bundles. The GraphQL
    auth headers must NOT ride these: the abs.twimg.com CDN rejects an unexpected Authorization
    header, which empties the bundle so the extraction finds nothing."""
    g = requests.Session()
    g.trust_env = False
    g.headers.update({"user-agent": UA})
    g.cookies.update(cookies)
    return g


def _authed_session(cookies):
    """Session carrying the headers X's GraphQL layer checks, for the bucket probes. trust_env is
    off so an ambient proxy cannot intercept and mangle the requests."""
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "authorization": BEARER, "x-csrf-token": cookies.get("ct0", ""),
        "x-twitter-auth-type": "OAuth2Session", "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en", "user-agent": UA,
    })
    s.cookies.update(cookies)
    return s


def extract_ops(s):
    """Pull the live operationName -> {queryId, type} map from X's JS bundles. Reads the bundle URLs
    out of the home HTML, then regexes each. Lazy-loaded chunks are not referenced in the home HTML,
    so this is the core surface (the main bundle), not every op X ships."""
    html = s.get(HOME, timeout=20).text
    ops = {}
    for url in sorted(set(BUNDLE_RE.findall(html))):
        try:
            js = s.get(url, timeout=30).text
        except Exception:
            continue
        for qid, op, typ in OP_RE.findall(js):
            ops[op] = {"queryId": qid, "type": typ}
    return ops


def probe(s, qid, op):
    """One throwaway request; read the bucket off the response headers. Empty variables produce a 422
    that still carries x-rate-limit-*. A 403 (queryId did not route past the WAF) carries none."""
    try:
        r = s.get(GQL.format(qid=qid, op=op), params={"variables": "{}"}, timeout=20)
    except Exception as e:
        return {"status": None, "error": str(e)[:80]}
    out = {"status": r.status_code}
    for k in ("limit", "remaining", "reset"):
        v = r.headers.get("x-rate-limit-" + k)
        if v is not None:
            out[k] = int(v) if v.isdigit() else v
    if "limit" not in out:
        out["note"] = "no-headers (WAF/no-route)" if r.status_code == 403 else "no-headers"
    return out


def _lim(row):
    return row["limit"] if isinstance(row.get("limit"), int) else -1


def main():
    ap = argparse.ArgumentParser(description="census X's GraphQL rate-limit buckets, keyless")
    ap.add_argument("--delay", type=float, default=0.25, help="seconds between probes")
    ap.add_argument("--include-mutations", action="store_true",
                    help="also probe write ops (still 422, never executes)")
    ap.add_argument("--json", metavar="PATH", help="write the full per-op map as JSON")
    ap.add_argument("--limit-ops", type=int, default=0, help="probe only the first N ops (smoke test)")
    args = ap.parse_args()
    if not STATE.exists():
        sys.exit("[census] no saved session at ~/.x-session/state.json (run xsearch.py --login)")
    cookies = _load_cookies()
    ops = extract_ops(_clean_session(cookies))
    if not ops:
        sys.exit("[census] no ops extracted (bundle fetch failed?)")
    s = _authed_session(cookies)
    targets = [(op, m["queryId"], m["type"]) for op, m in sorted(ops.items())
               if args.include_mutations or m["type"] == "query"]
    skipped = len(ops) - len(targets)
    if args.limit_ops:
        targets = targets[:args.limit_ops]
    print(f"[census] {len(ops)} ops ({dict(Counter(m['type'] for m in ops.values()))}); "
          f"probing {len(targets)}, skipping {skipped} mutation(s)", file=sys.stderr)
    rows = {}
    for i, (op, qid, typ) in enumerate(targets):
        res = probe(s, qid, op)
        res["type"] = typ
        res["queryId"] = qid
        rows[op] = res
        if (i + 1) % 20 == 0:
            print(f"[census] {i + 1}/{len(targets)}", file=sys.stderr)
        time.sleep(args.delay)
    print(f"\n{'operation':42} {'type':9} {'status':>6} {'limit':>6} {'remaining':>9}")
    for op in sorted(rows, key=lambda o: (-_lim(rows[o]), o)):
        r = rows[op]
        shown = r["limit"] if isinstance(r.get("limit"), int) else r.get("note", "")
        print(f"{op:42} {r['type']:9} {str(r['status']):>6} {str(shown):>6} {str(r.get('remaining', '')):>9}")
    hist = Counter(r["limit"] for r in rows.values() if isinstance(r.get("limit"), int))
    print("\n[census] bucket sizes (limit -> #ops):",
          dict(sorted(hist.items(), reverse=True)), file=sys.stderr)
    no_hdr = [o for o, r in rows.items() if "limit" not in r]
    if no_hdr:
        print(f"[census] {len(no_hdr)} ops returned no headers (WAF/no-route): {no_hdr[:12]}", file=sys.stderr)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2))
        print(f"[census] wrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
