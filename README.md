# API-God

Universal browser interception layer. Log in once through a real Chromium
window, then everything that session touches is captured to SQLite.

Most recon tooling fights the auth wall: it scrapes from outside, juggles API
keys, or replays cookies that go stale. API-God sidesteps the problem. It drives
a visible, persistent browser. You authenticate by hand the way a human would,
the cookies live on disk, and a transparent capture layer underneath records
every request, response, and WebSocket frame the page makes. Per-site plugins
turn the raw stream into structured records when a site is worth normalizing.
Operate it only against your own accounts and authorized targets.

## Install

```
git clone https://github.com/nuclide-research/API-God
cd API-God
npm install
npx playwright install chromium
```

Node 18+ (uses ESM and `node --watch`). Two dependencies: `playwright` (drives
Chromium) and `better-sqlite3` (the capture store). `npx playwright install`
downloads the Chromium build Playwright needs the first time.

## Usage

```
npm start                                   # launch the browser, begin capturing
node src/index.js                           # same as npm start
node src/index.js query                     # dump the last 200 captures as NDJSON
node src/index.js query x.com               # only captures for one domain
node src/index.js query x.com --type x-tweet  # filter by capture type
node src/index.js query x.com --limit 50    # cap the row count
node src/index.js query x.com --pretty      # pretty-print parsed data (-p)
node src/index.js stats                     # per-domain / per-type counts table
```

Run with no subcommand to start a session. A visible Chromium window opens on a
persistent profile at `data/session/`. Browse and log in normally. Every HTTP
request and response (minus static assets and analytics beacons) and every
WebSocket frame lands in `data/captures.db`. Cookies survive restarts, so you
authenticate once. Stop with Ctrl+C.

`query` prints one JSON object per line (NDJSON) to stdout, newest first, so it
pipes cleanly into `jq` or another file. `--pretty` parses each row's `data`
blob and prints it indented with `_id`, `_ts`, `_type`, and `_url` attached.

### Subcommands

| Command | Arguments | What it does |
|---------|-----------|--------------|
| (default) | none | Launch the browser and capture everything until Ctrl+C |
| `query` | `[domain] [--type T] [--limit N] [--pretty\|-p]` | Read captures back as NDJSON |
| `stats` | none | Print a table of capture counts grouped by domain and type |

`--limit` defaults to 200 on the CLI. `domain` is optional; omit it to query
across all domains.

### Capture types

The interceptor writes these `type` values:

| Type | Source |
|------|--------|
| `request` | Every non-skipped outgoing HTTP request (headers + body) |
| `response` | JSON and text responses (headers + body, status) |
| `ws-send` / `ws-recv` | WebSocket frames, by direction |

Static assets (fonts, images, CSS, source maps, media) and common analytics
hosts are skipped to keep the noise down.

## Plugins

Plugins live in `src/plugins/` and load automatically at startup. A plugin
matches a URL and transforms the raw response or WebSocket frame into structured
records. When a plugin matches, its records are saved instead of the raw
capture. Three ship in this repo:

| Plugin | Matches | Emits |
|--------|---------|-------|
| `axiom` | `axiom.trade` REST and socket.io feeds | `axiom-token`, `axiom-alert` records normalized from the trending feed |
| `shodan` | `shodan.io` search result pages and `api.shodan.io` | `shodan-host` records parsed from the authenticated session, no API key |
| `x` | `x.com` `SearchTimeline` GraphQL responses | `x-tweet` records with author, text, and metrics |

A plugin is a default-exported object with a `name`, a `match(url)` predicate,
and one or more of `onResponse(url, body)`, `onWebSocket(frame)`, and
`onPageLoad(url, page)`. Files prefixed with `_` are skipped by the loader. Each
hook returns an array of records to save, or null to fall through to the raw
capture. Restart to pick up plugin changes.

## Scripts

Helper scripts under `scripts/` reuse the same browser and storage modules:

```
node scripts/nav.js https://www.shodan.io --wait 3000   # navigate once, report what got captured
node scripts/shodan-search.js "<query>" --pages 5       # paginate Shodan results via the session DOM
```

`scripts/shodan-search.js` drives the persistent session to page through Shodan
search results and extract host records straight from the DOM, no API key. It
takes `--pages N`, `--start-page N`, `--delay N`, and `--headless`. If it hits a
login wall it pauses for you to log in, then continues.

## Status

v0.1.0. The capture layer, the SQLite store, the `query` and `stats`
subcommands, and the three plugins above are working. The plugin selection
flags, active-action runner, and time filters sketched in the design spec
(`docs/`) are not implemented yet. Visible browser only, no headless start, no
hot reload: restart to pick up changes.

This is operator tooling. It rides your own authenticated sessions. Point it
only at accounts and targets you are authorized to access.

## License

MIT. Part of the NuClide toolchain.
