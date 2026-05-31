# API-God

Read X (Twitter) without the X API. No developer account, no $50,000/year tier, no key.

API-God rides a browser session you are already logged into. X's own JavaScript calls X's internal GraphQL endpoints; API-God captures those responses off the wire. The auth is your session cookie, not an API key. That is the whole point of the project: search and track X at all, keyless, on your own login.

A Solana memecoin signal engine sits downstream of that capability. The engine is a consumer. The keyless X access is the headline.

## What it is doing

X is a single-page app. Open a search or a profile and the page does not ship you HTML with the tweets in it. It runs a GraphQL query (`SearchTimeline`, `UserTweets`, `ListLatestTweetsTimeline`) and renders the JSON. API-God drives a real logged-in browser with Playwright, lets X make its own authenticated request, and reads the JSON response as it lands:

```
page.on("response")  ->  filter for the GraphQL op  ->  parse the tweet records
```

X made the request, so every signed header and token is already correct. API-God never forges a request. It reads the answer to a request the browser was going to make anyway. The session lives in `~/.x-session/state.json`, captured once, and carries the login cookies (`auth_token`, `ct0`, `twid`).

A second path needs no login at all. The syndication CDN (`cdn.syndication.twimg.com/tweet-result?id=`) returns a full tweet by id, keyless and uncapped. API-God uses it to hydrate tweet ids in bulk without spending any account budget.

## Layout

| Path | What |
|------|------|
| `search/` | `xsearch.py` (the X tool) and `ingest.py` (the continuous ingestion engine) |
| `engine/` | the Solana memecoin signal engine that consumes the X stream |
| `legacy/` | the retired Node interceptor, kept for reference |
| `tests/` | offline pytest suite (no network, no browser) |
| `testdata/` | fixtures for the suite |

## Quick start

```bash
cd search
pip install -r requirements.txt
python -m playwright install chromium

python xsearch.py --login              # opens a browser, log in once
python xsearch.py "solana depin"       # search, keyless
python xsearch.py elonmusk --track     # one account's timeline
python xsearch.py --list <listId>      # a whole List in one call
```

Every mode is in `search/README.md`.

## The rate-limit map

X rate-limits each GraphQL endpoint separately, per login, over a rolling 15-minute window. API-God measured the walls so you can stay under them:

| Door | Limit |
|------|-------|
| `SearchTimeline` (search) | ~45 requests / 15 min, then HTTP 429 |
| `UserTweets` (a profile) | separate bucket; serves 200 while search is 429'd |
| `ListLatestTweetsTimeline` (a List) | separate bucket; one call returns every member |
| syndication CDN (by id) | no per-IP limit observed (250 requests, all 200) |

The strategy falls out of the map. Spend one search or List call to harvest tweet ids, then hydrate them through the keyless CDN. Search is the only real wall, so do not waste it on data the CDN hands out free.

## Tests

```bash
pip install -r engine/requirements-dev.txt
pytest
```

The suite is offline and deterministic. The network and the browser are faked, so it runs in seconds and never touches X.

## A note on use

API-God reads public posts through your own logged-in session, the same data the browser in front of you already shows. Keep request rates under the measured walls. It is built for research and for feeding the signal engine, not for mass scraping.
