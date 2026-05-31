#!/usr/bin/env python3
"""fielddiff - which X operation exposes the most of an object, introspection-free.

X serves the same tweet through several resolvers, and they do not return the same fields. The keyless
syndication CDN is silent on some (it drops retweet_count); the authed GraphQL path carries more. This
fetches one tweet id through each path, collects the field-name vocabulary of each response, and diffs
them: how many distinct fields each path exposes and which are unique to one.

The schema is hidden (persisted queries, introspection off), so diffing real responses is the only way
to learn which op to call for which data. The authed path needs the live features blob, captured once
via xsearch.capture_features (one headless browser launch); the CDN path is keyless.

  python fielddiff.py <tweet_id>
"""
import sys, os, json, asyncio
from pathlib import Path
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xsearch

STATE = Path.home() / ".x-session" / "state.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
QID_BATCH = "ZrFhyt8DYdkK3IY6_Le22g"   # TweetResultsByRestIds


def field_names(obj):
    """The set of every dict key anywhere in a nested response: the vocabulary of fields that response
    exposes, regardless of nesting depth or list length. Lets two differently-shaped responses (the
    flat CDN object vs the deeply-wrapped GraphQL one) be compared by what data they carry."""
    names = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            names.add(k)
            names |= field_names(v)
    elif isinstance(obj, list):
        for v in obj:
            names |= field_names(v)
    return names


def cdn_raw(tid):
    """Raw tweet object from the keyless syndication CDN."""
    r = requests.get(f"https://cdn.syndication.twimg.com/tweet-result?id={tid}&token=x&lang=en", timeout=10)
    return r.json() if r.status_code == 200 else None


def graphql_raw(tid, cap, cookies):
    """Raw TweetResultsByRestIds response (authed), using the captured features/bearer."""
    hdr = {"authorization": cap["bearer"], "x-csrf-token": cookies.get("ct0", ""),
           "x-twitter-active-user": "yes", "x-twitter-auth-type": "OAuth2Session",
           "x-twitter-client-language": "en", "user-agent": UA}
    variables = json.dumps({"tweetIds": [str(tid)], "includePromotedContent": False,
                            "withBirdwatchNotes": False, "withVoice": True, "withCommunity": True})
    s = requests.Session()
    s.trust_env = False
    r = s.get(f"https://x.com/i/api/graphql/{QID_BATCH}/TweetResultsByRestIds",
              params={"variables": variables, "features": cap["features"], "fieldToggles": cap["fieldToggles"]},
              headers=hdr, cookies=cookies, timeout=20)
    return r.json() if r.status_code == 200 else {"_status": r.status_code, "_body": r.text[:200]}


def main():
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        sys.exit("usage: fielddiff.py <tweet_id>")
    tid = sys.argv[1]
    if not STATE.exists():
        sys.exit("[fielddiff] no saved session (run xsearch.py --login)")
    cookies = {c["name"]: c["value"] for c in json.loads(STATE.read_text()).get("cookies", [])
               if c.get("name") and c.get("value")}
    print(f"[fielddiff] tweet {tid}: resolving via CDN and authed GraphQL", file=sys.stderr)
    cdn = cdn_raw(tid)
    cap = asyncio.run(xsearch.capture_features())
    if not cap:
        sys.exit("[fielddiff] could not capture client features")
    gql = graphql_raw(tid, cap, cookies)
    cdn_f = field_names(cdn) if cdn else set()
    gql_f = field_names(gql) if gql else set()
    only_cdn = sorted(cdn_f - gql_f)
    only_gql = sorted(gql_f - cdn_f)
    common = cdn_f & gql_f
    print(f"\nCDN (syndication, keyless):              {len(cdn_f):3} field names")
    print(f"GraphQL TweetResultsByRestIds (authed):  {len(gql_f):3} field names")
    print(f"shared:                                  {len(common):3}")
    print(f"\nonly via authed GraphQL ({len(only_gql)}):")
    print("  " + ", ".join(only_gql) if only_gql else "  (none)")
    print(f"\nonly via keyless CDN ({len(only_cdn)}):")
    print("  " + ", ".join(only_cdn) if only_cdn else "  (none)")


if __name__ == "__main__":
    main()
