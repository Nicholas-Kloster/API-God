# API-God — Design Spec
**Date:** 2026-05-27  
**Status:** Approved

## What It Is

A Playwright-powered research browser that intercepts all network traffic passing through an authenticated session — WebSocket frames, XHR, fetch — and routes it through a per-site plugin system. Plugins are both passive (capture + store) and active (inject, modify, act on the page). You log in once through a real visible Chromium window; the capture and action layer runs underneath transparently.

---

## Architecture

Three components, clean boundaries:

```
┌─────────────────────────────────────────┐
│           Browser Core                  │
│  Playwright + CDP network interception  │
│  Persistent session (cookies survive)   │
│  addInitScript for WS hook injection    │
└────────────────┬────────────────────────┘
                 │ events: request / response / ws-frame / navigate
                 ▼
┌─────────────────────────────────────────┐
│           Plugin Registry               │
│  Loads plugins/   on startup            │
│  Routes events by domain match          │
│  Exposes page handle to each plugin     │
│  Exposes action runner for CLI          │
└────────────────┬────────────────────────┘
                 │ normalized captures + writes
                 ▼
┌─────────────────────────────────────────┐
│         Storage + Query Layer           │
│  SQLite via better-sqlite3              │
│  captures table (domain/type/url/data)  │
│  CLI: query, export, run actions        │
└─────────────────────────────────────────┘
```

---

## Browser Core

- Playwright launches **visible Chromium** (headless: false)
- **Persistent browser context** at `data/session/` — cookies and local storage survive restarts, login once
- **CDP route interception** on `**` — sees every request and response before the page does
- **WebSocket interception** via `page.addInitScript()` — patches `window.WebSocket` at page load, proxies all frames through a `window.__apigod__` channel that CDP reads
- Core emits normalized events: `request`, `response`, `ws-frame`, `navigate`
- Never modifies traffic unless a plugin explicitly returns a modification

---

## Plugin System

### File layout
```
src/plugins/
  axiom.js
  oreilly.js
  x.js
  _template.js
```

### Plugin interface
```js
export default {
  name: 'axiom',
  match: ['axiom.trade'],          // domain(s) to activate on

  // Passive hooks — return nothing to pass through unchanged
  async onRequest(req, ctx)  {},   // outgoing request
  async onResponse(req, res, ctx) {},  // incoming response; return {body} to modify
  async onWebSocket(frame, ctx) {},    // WS frame (send or receive)
  async onNavigate(url, ctx)  {},  // page navigated

  // Active actions — callable from CLI or other plugins
  actions: {
    async injectData(ctx, payload) {},
    async scrape(ctx) {},
  }
}
```

### Context object (`ctx`)
Every hook receives a `ctx` with:
- `ctx.page` — live Playwright Page handle (full DOM + JS access)
- `ctx.db` — storage handle (write a capture)
- `ctx.log(msg)` — structured logger
- `ctx.plugin` — plugin metadata

### Plugin capabilities
- **Capture**: `ctx.db.save({ type, url, data })`
- **Modify response**: return `{ body: newBody }` from `onResponse`
- **Inject JS**: `ctx.page.evaluate(fn, args)`
- **Click / fill / navigate**: via `ctx.page` directly
- **WebSocket injection**: `ctx.page.evaluate(() => window.__apigod__.inject(frame))`
- **Abort request**: return `{ abort: true }` from `onRequest`
- **Replay / fork request**: return `{ override: { url, headers, body } }`

---

## Storage Layer

**Schema** (single `captures` table):
```sql
CREATE TABLE captures (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT DEFAULT (datetime('now')),
  domain      TEXT,
  plugin      TEXT,
  type        TEXT,   -- 'request' | 'response' | 'ws' | 'navigate'
  url         TEXT,
  status      INTEGER,
  data        TEXT    -- JSON blob
);
CREATE INDEX idx_domain_ts ON captures(domain, ts);
```

**Library:** `better-sqlite3` — synchronous, no async ceremony, fast.

---

## CLI

```
api-god start                          # launch browser, load all plugins
api-god start --plugin axiom           # load single plugin only
api-god query <domain>                 # dump captures for domain (NDJSON to stdout)
api-god query <domain> --type ws       # filter by capture type
api-god query <domain> --since 1h      # time filter
api-god run <plugin> <action> [args]   # trigger an active action
api-god plugins                        # list loaded plugins + match domains
```

---

## File Structure

```
API-God/
├── src/
│   ├── index.js          # CLI entry point
│   ├── browser.js        # Playwright launch + persistent context
│   ├── interceptor.js    # CDP route + WS interception, event emitter
│   ├── registry.js       # plugin loader + event router
│   ├── storage.js        # better-sqlite3 wrapper
│   ├── cli.js            # command parser
│   └── plugins/
│       ├── _template.js
│       ├── axiom.js
│       ├── oreilly.js
│       └── x.js
├── data/
│   ├── session/          # persistent browser profile
│   └── captures.db       # SQLite
├── docs/
│   └── superpowers/specs/
├── package.json
└── .gitignore
```

---

## Build Order

1. `storage.js` — DB schema + save/query methods
2. `browser.js` — Playwright launch, persistent context
3. `interceptor.js` — CDP routes + WS proxy script
4. `registry.js` — plugin loader, event routing, ctx builder
5. `cli.js` + `index.js` — entry point + commands
6. `plugins/_template.js` — documented starter
7. `plugins/axiom.js` — first real plugin (Wallet Hunter use case)
8. `plugins/oreilly.js` — second plugin (content API capture)
9. `plugins/x.js` — third plugin (GraphQL timeline capture)

---

## Dependencies

```json
{
  "playwright": "latest",
  "better-sqlite3": "latest",
  "commander": "latest"
}
```

No framework. No transpilation. Node ESM throughout.

---

## Non-Goals (v0.1)

- No GUI dashboard (CLI only)
- No headless mode (visible browser, login manually)
- No plugin hot-reload (restart to pick up changes)
- No multi-browser-window support
