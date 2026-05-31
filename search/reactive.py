#!/usr/bin/env python3
"""reactive - discover a topic, react to it live.

Fuses the two halves built this session. ingest-style discovery (SearchTimeline for a topic, or a
List) finds tweets on a gentle poll; livepipe subscribes the new ones to X's push channel so their
engagement velocity streams in real time. One process: discover cheap and paced, react free and live.

The reader thread owns the live_pipeline HTTP/2 client and the session_id, and does the subscribing
(fed new ids over a queue by the asyncio discovery loop). Multi-subscribe needs HTTP/2 + the
LivePipeline-Session header, both provided by livepipe.subscribe.

  python reactive.py --search "solana" --interval 30 --seconds 300 --out /tmp/solana.jsonl
  python reactive.py --list <id> --interval 30 --seconds 600
"""
import asyncio, json, sys, os, time, threading, queue, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsearch, livepipe


def _reader(first_id, subq, sink, stop):
    """Own the live_pipeline HTTP/2 stream: read the session_id, subscribe ids pulled off subq (with
    the session header), emit per-field velocity. All client use stays on this one thread."""
    last, sid, subscribed = {}, None, {first_id}
    with livepipe._client() as client:
        with client.stream("GET", livepipe.EVENTS, params={"topic": "/tweet_engagement/" + first_id}) as r:
            print(f"[reactive] live_pipeline connected {r.status_code} ({r.http_version})", file=sys.stderr)
            if r.status_code != 200:
                return

            def drain_subscribe():
                if sid is None:
                    return
                new = []
                try:
                    while True:
                        new.append(subq.get_nowait())
                except queue.Empty:
                    pass
                todo = [i for i in new if i not in subscribed]
                if todo:
                    subscribed.update(todo)
                    try: livepipe.subscribe(client, sid, todo)
                    except Exception as e: print(f"[reactive] subscribe: {e}", file=sys.stderr)
                    print(f"[reactive] subscribed +{len(todo)} (total {len(subscribed)})", file=sys.stderr)

            for line in r.iter_lines():
                if stop.is_set():
                    break
                if not line:
                    continue
                try: ev = json.loads(line)
                except Exception: continue
                top = ev.get("topic", "")
                if top == "/system/config" and sid is None:
                    sid = ev.get("payload", {}).get("config", {}).get("session_id")
                    drain_subscribe()                            # subscribe the initial batch + the queue
                    continue
                drain_subscribe()                                # pick up newly discovered ids
                if not top.startswith("/tweet_engagement/"):
                    continue
                tid = top.rsplit("/", 1)[-1]
                counts = livepipe.parse_engagement(ev.get("payload", {}))
                if not counts:
                    continue
                now, hist, parts = time.time(), last.setdefault(tid, {}), []
                for f, v in counts.items():
                    if f in hist:
                        pv, pt = hist[f]; dt = now - pt
                        if dt > 0 and v != pv:
                            parts.append(f"{f.split('_')[0]} +{v - pv} ({(v - pv) / dt * 60:.0f}/min)")
                    hist[f] = (v, now)
                sink.write(json.dumps({"id": tid, "counts": counts, "_t": now}) + "\n"); sink.flush()
                if parts:
                    print(f"  live {tid}  {'  '.join(parts)}", flush=True)


async def run(fetch, interval, seconds, out_path):
    seen, subq = set(), queue.Queue()
    posts = await fetch()
    ids = [p["id"] for p in posts]
    if not ids:
        sys.exit("[reactive] nothing discovered to subscribe to")
    seen.update(ids)
    for i in ids[1:]:
        subq.put(i)
    sink = open(out_path, "a")
    stop = threading.Event()
    threading.Thread(target=_reader, args=(ids[0], subq, sink, stop), daemon=True).start()
    print(f"[reactive] discovered {len(ids)}", file=sys.stderr)
    start = time.time()
    try:
        while time.time() - start < seconds:
            await asyncio.sleep(interval)
            posts = await fetch()
            new = [p["id"] for p in posts if p["id"] not in seen]
            seen.update(new)
            for i in new:
                subq.put(i)
            print(f"[reactive] +{len(new)} new discovered", file=sys.stderr)
    finally:
        stop.set(); await asyncio.sleep(0.3); sink.close()


def main():
    ap = argparse.ArgumentParser(description="discover a topic and stream its tweets' engagement velocity live")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--search", metavar="QUERY", help="topic via SearchTimeline (e.g. 'solana')")
    src.add_argument("--list", metavar="LISTID", help="a List")
    ap.add_argument("--interval", type=int, default=30, help="seconds between discovery polls")
    ap.add_argument("--seconds", type=int, default=180, help="total run time")
    ap.add_argument("--pages", type=int, default=2, help="discovery pages per poll")
    ap.add_argument("--tab", choices=["top", "live"], default="top", help="search discovery tab: top (movers) or live (newest)")
    ap.add_argument("--out", default="/tmp/reactive.jsonl", help="velocity JSONL sink")
    args = ap.parse_args()
    if args.search:
        fetch = lambda: xsearch.find_session(args.search, args.tab, args.pages, 1000, False)
    else:
        fetch = lambda: xsearch.find_list(args.list, args.pages, 1000, False)
    asyncio.run(run(fetch, args.interval, args.seconds, args.out))


if __name__ == "__main__":
    main()
