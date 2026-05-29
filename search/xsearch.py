#!/usr/bin/env python3
"""xsearch - find who's talking about a topic/coin on X. FREE: rides your own saved X session and
reads X's own search results. No API key, no $30k firehose, no xAI.

One-time setup (opens a browser, you log in once, it saves the session):
    python xsearch.py --login

Then search anything - a topic, a $ticker, or a contract address:
    python xsearch.py "solana depin"
    python xsearch.py '$GIGA' --pages 6
    python xsearch.py 6y3mVtvrUpiTdfmazndxvtj1WsGWqpX1MKy8XW76pump      # a CA = sharpest
    python xsearch.py "solana" --json --out who.jsonl                  # structured out

Note: this rides your logged-in account. Fine for your own searches; don't hammer it on a tight loop
(X bans automation). One run = one browser session, scrolls a few times, done.
"""
import asyncio, json, sys, argparse
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("pip install playwright && playwright install chromium")

STATE = Path.home() / ".x-session" / "state.json"

# Proven DOM extractor (validated live: one pass -> 60 distinct accounts for "solana").
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

async def login():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://x.com/login")
        print("Log in to X in the window. When you see your home feed, press Enter here to save...")
        input()
        await ctx.storage_state(path=str(STATE))
        await browser.close()
    print(f"session saved -> {STATE}")

async def search(args):
    if not STATE.exists():
        sys.exit("no saved session. run once:  python xsearch.py --login")
    url = f"https://x.com/search?q={quote(args.query)}&src=typed_query&f={args.tab}"
    seen = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headed,
                                           args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(storage_state=str(STATE))
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        for _ in range(args.pages):
            for r in await page.evaluate(EXTRACT_JS):
                if r["handle"] and r["id"] not in seen:
                    seen[r["id"]] = r
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(args.delay)
        await browser.close()

    posts = list(seen.values())
    key = (lambda r: r["likes"] + r["reposts"]) if args.sort == "engagement" else (lambda r: r["time"])
    posts.sort(key=key, reverse=True)

    if args.json or args.out:
        out = open(args.out, "w") if args.out else sys.stdout
        for r in posts:
            print(json.dumps(r), file=out)
        if args.out:
            out.close(); print(f"{len(posts)} posts -> {args.out}", file=sys.stderr)
        return

    # readable: collapse to distinct ACCOUNTS (the people), each shown by their top post
    by_acct = {}
    for r in posts:
        cur = by_acct.get(r["handle"])
        if not cur or (r["likes"] + r["reposts"]) > (cur["likes"] + cur["reposts"]):
            by_acct[r["handle"]] = r
    accts = sorted(by_acct.values(), key=key, reverse=True)
    print(f"{len(accts)} accounts talking about {args.query!r}  ({len(posts)} posts, {args.tab})\n")
    for r in accts[:args.limit]:
        print(f"{r['handle'][:18]:18} ♥{r['likes']:>5} ↻{r['reposts']:>4}  {r['text'][:96]}")

def main():
    ap = argparse.ArgumentParser(description="find who's talking about a topic/coin on X (free, rides your session)")
    ap.add_argument("query", nargs="?", help="topic, $ticker, or contract address")
    ap.add_argument("--login", action="store_true", help="one-time: open a browser and save your X session")
    ap.add_argument("--tab", choices=["live", "top"], default="live", help="live=newest, top=most engaged")
    ap.add_argument("--pages", type=int, default=5, help="scroll passes (more = deeper, default 5)")
    ap.add_argument("--delay", type=int, default=1300, help="ms between scrolls")
    ap.add_argument("--sort", choices=["recent", "engagement"], default="engagement")
    ap.add_argument("--limit", type=int, default=30, help="accounts to show (readable mode)")
    ap.add_argument("--out", help="write JSONL of every post to a file")
    ap.add_argument("--json", action="store_true", help="JSONL of every post to stdout")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    args = ap.parse_args()
    if args.login:
        asyncio.run(login()); return
    if not args.query:
        ap.error("give a query (topic / $ticker / contract address), or run --login first")
    asyncio.run(search(args))

if __name__ == "__main__":
    main()
