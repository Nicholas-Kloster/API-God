#!/usr/bin/env python3
"""reactive - discover a topic, react to it live.

Fuses the two halves built this session. ingest-style discovery (SearchTimeline for a topic, or a
List) finds tweets on a gentle poll; livepipe subscribes the new ones to X's push channel so their
engagement velocity streams in real time. One process: discover cheap and paced, react free and live.

Threading note: the live_pipeline session is owned by ONE thread (the reader). Discovery runs in the
asyncio main thread and hands new tweet ids over a queue; the reader drains the queue and subscribes
them itself, so the requests.Session is never used cross-thread (which stalls the SSE).

  python reactive.py --search "solana" --interval 30 --seconds 300 --out /tmp/solana.jsonl
  python reactive.py --list <id> --interval 30 --seconds 600
"""
import asyncio, json, sys, os, time, threading, queue, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsearch, livepipe


def _reader(session, first_id, subq, sink, stop):
    """Own the live_pipeline session: open the SSE, subscribe ids pulled off subq, emit velocity.
    All session use stays on this one thread."""
    try:
        r = session.get(livepipe.EVENTS, params={"topic": "/tweet_engagement/" + first_id},
                        stream=True, timeout=(10, 40))
    except Exception as e:
        print(f"[reactive] live connect failed: {e}", file=sys.stderr); return
    print(f"[reactive] live_pipeline connected {r.status_code}", file=sys.stderr)
    last, subscribed = {}, {first_id}

    def drain_and_subscribe():
        new = []
        try:
            while True:
                new.append(subq.get_nowait())
        except queue.Empty:
            pass
        todo = [i for i in new if i not in subscribed]
        if todo:
            subscribed.update(todo)
            window = list(subscribed)[-50:]              # keep a recent window inside the 120s TTL
            try: livepipe.subscribe(session, window)
            except Exception as e: print(f"[reactive] subscribe: {e}", file=sys.stderr)
            print(f"[reactive] subscribed +{len(todo)} (watching {len(window)})", file=sys.stderr)

    drain_and_subscribe()                                # subscribe the initial batch
    try:
        for line in r.iter_lines():
            if stop.is_set():
                break
            drain_and_subscribe()                        # pick up newly discovered ids (<=1 heartbeat late)
            if not line:
                continue
            try: ev = json.loads(line)
            except Exception: continue
            top = ev.get("topic", "")
            if not top.startswith("/tweet_engagement/"):
                continue
            tid = top.rsplit("/", 1)[-1]
            counts = livepipe.parse_engagement(ev.get("payload", {}))
            if not counts:
                continue
            now, vel = time.time(), 0.0
            if tid in last:
                pc, pt = last[tid]; dt = now - pt
                d = ((counts.get("favorite_count", 0) - pc.get("favorite_count", 0))
                     + (counts.get("retweet_count", 0) - pc.get("retweet_count", 0)))
                vel = d / dt * 60 if dt > 0 else 0.0
            last[tid] = (counts, now)
            rec = {"id": tid, "counts": counts, "velocity_per_min": round(vel, 1), "_t": now}
            sink.write(json.dumps(rec) + "\n"); sink.flush()
            if vel:
                print(f"  live {tid}  {counts}  {vel:.0f}/min", flush=True)
    except Exception as e:
        print(f"[reactive] reader stopped: {e}", file=sys.stderr)
    finally:
        r.close()


async def run(fetch, interval, seconds, out_path):
    session = livepipe._session()
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
    threading.Thread(target=_reader, args=(session, ids[0], subq, sink, stop), daemon=True).start()
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
    ap.add_argument("--out", default="/tmp/reactive.jsonl", help="velocity JSONL sink")
    args = ap.parse_args()
    if args.search:
        fetch = lambda: xsearch.find_session(args.search, "live", args.pages, 1000, False)
    else:
        fetch = lambda: xsearch.find_list(args.list, args.pages, 1000, False)
    asyncio.run(run(fetch, args.interval, args.seconds, args.out))


if __name__ == "__main__":
    main()
