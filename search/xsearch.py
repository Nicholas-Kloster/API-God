#!/usr/bin/env python3
"""xsearch - find who's talking about a topic/coin on X. Two pluggable backends, switch or combine:

  session  FREE. Rides your saved X session, reads X's own search DOM. No cost; your account at risk
           if you hammer it. Setup once: python xsearch.py --login
  xai      CLEAN. xAI x_search finds posts, the free syndication CDN enriches them. ~$0.005/search,
           no account risk. Needs XAI_API_KEY (console.x.ai).
  both     Run both at once, merge, and tag each result by who found it. [SX] = found by BOTH
           backends independently = corroborated. Union = wider coverage.

  python xsearch.py "solana depin"                    # default backend (session)
  python xsearch.py '$GIGA' --backend xai
  python xsearch.py <contract_address> --backend both
  python xsearch.py "solana" --backend both --json --out who.jsonl
"""
import asyncio, json, sys, os, argparse, re
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

STATE = Path.home() / ".x-session" / "state.json"
XAI_KEY = os.environ.get("XAI_API_KEY")
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.3")

EXTRACT_JS = r"""
() => {
  const out = [];
  document.querySelectorAll('article').forEach(a => {
    const link = a.querySelector('a[href*="/status/"]')?.href; if (!link) return;
    const id = link.split('/status/')[1]?.split(/[/?]/)[0]; if (!id) return;
    const nb = (a.querySelector('[data-testid="User-Name"]')?.innerText || '').split('\n');
    const handle = (nb.find(s => s.startsWith('@')) || '').trim();
    const name = (nb[0] || '').trim();
    const text = (a.querySelector('[data-testid="tweetText"]')?.innerText || '').replace(/\n/g, ' ');
    const time = a.querySelector('time')?.getAttribute('datetime') || '';
    const m = sel => parseInt((a.querySelector(`[data-testid="${sel}"]`)?.getAttribute('aria-label') || '').replace(/[^0-9]/g, '')) || 0;
    out.push({ id, handle, name, text, time, url: link.split('?')[0],
               replies: m('reply'), reposts: m('retweet'), likes: m('like') });
  });
  return out;
}
"""

def _rec(id, handle, name, text, time, url, likes, replies, reposts, source):
    return {"id": id, "handle": handle, "name": name, "text": text, "time": time, "url": url,
            "likes": likes, "replies": replies, "reposts": reposts, "source": [source]}

# ---------- backend: session (free, rides your X login) ----------
async def find_session(query, tab, pages, delay, headed):
    if not STATE.exists():
        print("[session] no saved session (run: python xsearch.py --login) - skipping", file=sys.stderr)
        return []
    from playwright.async_api import async_playwright
    url = f"https://x.com/search?q={quote(query)}&src=typed_query&f={tab}"
    seen = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=not headed, args=["--disable-blink-features=AutomationControlled"])
        c = await b.new_context(storage_state=str(STATE))
        p = await c.new_page()
        await p.goto(url, wait_until="domcontentloaded", timeout=30000)
        for _ in range(pages):
            for r in await p.evaluate(EXTRACT_JS):
                if r["handle"] and r["id"] not in seen:
                    seen[r["id"]] = _rec(r["id"], r["handle"], r["name"], r["text"], r["time"],
                                         r["url"], r["likes"], r["replies"], r["reposts"], "session")
            await p.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await p.wait_for_timeout(delay)
        await b.close()
    return list(seen.values())

# ---------- backend: xai (clean, ~$0.005/search, no account risk) ----------
def find_xai(query):
    if not XAI_KEY:
        print("[xai] XAI_API_KEY not set - skipping", file=sys.stderr)
        return []
    try:
        r = requests.post("https://api.x.ai/v1/responses", timeout=60,
                          headers={"Authorization": f"Bearer {XAI_KEY}", "Content-Type": "application/json"},
                          json={"model": XAI_MODEL, "tools": [{"type": "x_search"}],
                                "input": f"Find recent posts mentioning {query}. List the accounts and what they said."})
        r.raise_for_status(); d = r.json()
    except Exception as e:
        print(f"[xai] search failed: {e}", file=sys.stderr); return []
    urls = []
    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "url_citation" and o.get("url"): urls.append(o["url"])
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, str) and o.startswith("http"): urls.append(o)
    walk(d)
    out = {}
    for u in dict.fromkeys(urls):
        m = re.search(r'/status/(\d+)', u)
        if not m: continue
        tid = m.group(1)
        if tid in out: continue
        try:
            tr = requests.get(f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&token=x&lang=en", timeout=10)
            if tr.status_code != 200: continue
            t = tr.json()
            if not t or t.get("__typename") != "Tweet": continue
        except Exception:
            continue
        usr = t.get("user", {})
        out[tid] = _rec(tid, "@" + (usr.get("screen_name") or ""), usr.get("name") or "",
                        (t.get("text") or "").replace("\n", " "), t.get("created_at") or "",
                        f"https://x.com/{usr.get('screen_name')}/status/{tid}",
                        t.get("favorite_count") or 0, t.get("conversation_count") or 0, 0, "xai")
    return list(out.values())

def merge(*lists):
    by_id = {}
    for lst in lists:
        for r in lst:
            cur = by_id.get(r["id"])
            if cur:
                cur["source"] = sorted(set(cur["source"]) | set(r["source"]))
                # prefer the record that has engagement metrics
                if r["likes"] + r["reposts"] > cur["likes"] + cur["reposts"]:
                    src = cur["source"]; by_id[r["id"]] = {**r, "source": src}
            else:
                by_id[r["id"]] = dict(r)
    return list(by_id.values())

async def run(args):
    backends = {"session": ["session"], "xai": ["xai"], "both": ["session", "xai"]}[args.backend]
    tasks = []
    if "session" in backends:
        tasks.append(find_session(args.query, args.tab, args.pages, args.delay, args.headed))
    if "xai" in backends:
        tasks.append(asyncio.to_thread(find_xai, args.query))
    results = await asyncio.gather(*tasks)
    posts = merge(*results)
    if not posts:
        sys.exit("no results (check --login for session, or XAI_API_KEY for xai)")
    key = (lambda r: r["likes"] + r["reposts"]) if args.sort == "engagement" else (lambda r: r["time"])
    posts.sort(key=key, reverse=True)

    if args.json or args.out:
        out = open(args.out, "w") if args.out else sys.stdout
        for r in posts: print(json.dumps(r), file=out)
        if args.out: out.close(); print(f"{len(posts)} posts -> {args.out}", file=sys.stderr)
        return

    # readable: distinct accounts, each shown by their top post, tagged by which backend(s) found them
    by_acct = {}
    for r in posts:
        cur = by_acct.get(r["handle"])
        if not cur:
            by_acct[r["handle"]] = dict(r)
        else:
            cur["source"] = sorted(set(cur["source"]) | set(r["source"]))
            if r["likes"] + r["reposts"] > cur["likes"] + cur["reposts"]:
                src = cur["source"]; by_acct[r["handle"]] = {**r, "source": src}
    accts = sorted(by_acct.values(), key=key, reverse=True)
    tag = lambda s: f"[{'S' if 'session' in s else ' '}{'X' if 'xai' in s else ' '}]"
    nS = sum('session' in a['source'] for a in accts); nX = sum('xai' in a['source'] for a in accts)
    nB = sum(len(a['source']) > 1 for a in accts)
    print(f"{len(accts)} accounts for {args.query!r}  (backend={args.backend}: {nS} session, {nX} xai, {nB} in both)\n")
    for r in accts[:args.limit]:
        print(f"{tag(r['source'])} {r['handle'][:18]:18} ♥{r['likes']:>5} ↻{r['reposts']:>4}  {r['text'][:88]}")

async def login():
    from playwright.async_api import async_playwright
    STATE.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=False); c = await b.new_context(); p = await c.new_page()
        await p.goto("https://x.com/login")
        print("Log in to X, then press Enter here to save the session...")
        input()
        await c.storage_state(path=str(STATE)); await b.close()
    print(f"session saved -> {STATE}")

def main():
    ap = argparse.ArgumentParser(description="find who's talking about a topic/coin on X")
    ap.add_argument("query", nargs="?", help="topic, $ticker, or contract address")
    ap.add_argument("--backend", choices=["session", "xai", "both"], default="session")
    ap.add_argument("--login", action="store_true", help="one-time: save your X session (for the session backend)")
    ap.add_argument("--tab", choices=["live", "top"], default="live")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--delay", type=int, default=1300)
    ap.add_argument("--sort", choices=["recent", "engagement"], default="engagement")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--out", help="write JSONL of every post")
    ap.add_argument("--json", action="store_true", help="JSONL to stdout")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    if args.login: asyncio.run(login()); return
    if not args.query: ap.error("give a query, or --login first")
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
