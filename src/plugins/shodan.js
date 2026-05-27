// Shodan plugin — rides the authenticated browser session to pull structured JSON results.
// No API key file needed. Key is extracted from the logged-in page context and cached.
// onPageLoad fires on every shodan.io navigation; for search pages it fetches JSON results.

let cachedKey = null;

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return 'unknown'; }
}

// Extract the API key Shodan embeds in the authenticated page JS context.
async function extractKey(page) {
  if (cachedKey) return cachedKey;
  try {
    const result = await page.evaluate(async () => {
      // Method 1: try the account profile endpoint (session-authenticated)
      try {
        const r = await fetch('/account/info', { credentials: 'include' });
        if (r.ok) {
          const j = await r.json();
          if (j.api_key || j.apiKey) return j.api_key ?? j.apiKey;
        }
      } catch {}

      // Method 2: check common window globals Shodan injects
      if (window.SHODAN_API_KEY) return window.SHODAN_API_KEY;
      if (window.apiKey)         return window.apiKey;

      // Method 3: scan meta tags
      const meta = document.querySelector('meta[name="api-key"], meta[name="shodan-key"]');
      if (meta) return meta.getAttribute('content');

      return null;
    });
    if (result) {
      cachedKey = result;
      console.log(`[shodan] key extracted (${result.slice(0,8)}…)`);
    }
  } catch {}
  return cachedKey;
}

function parseQuery(url) {
  try {
    const u = new URL(url);
    return u.searchParams.get('query') ?? u.searchParams.get('q');
  } catch { return null; }
}

function mapHost(host, query) {
  return {
    domain:      'shodan.io',
    type:        'shodan-host',
    url:         `https://www.shodan.io/host/${host.ip_str}`,
    query,
    ip:          host.ip_str,
    org:         host.org          ?? null,
    isp:         host.isp          ?? null,
    asn:         host.asn          ?? null,
    country:     host.location?.country_name ?? null,
    city:        host.location?.city         ?? null,
    hostnames:   host.hostnames?.join(',')   ?? null,
    ports:       host.ports?.join(',')       ?? null,
    vulns:       host.vulns ? Object.keys(host.vulns).join(',') : null,
    tags:        host.tags?.join(',')        ?? null,
    last_update: host.last_update            ?? null,
    data:        JSON.stringify(host),
  };
}

export default {
  name: 'shodan',

  match: (url) => /shodan\.io/i.test(url),

  // Passive: capture any JSON Shodan API responses that flow through naturally
  async onResponse(url, body) {
    if (!url.includes('api.shodan.io') && !url.includes('/shodan/')) return null;
    let parsed;
    try { parsed = JSON.parse(body); } catch { return null; }

    const hosts = Array.isArray(parsed?.matches) ? parsed.matches : null;
    if (!hosts) return null;

    const query = parseQuery(url) ?? 'unknown';
    return hosts.map(h => mapHost(h, query));
  },

  // Active: when a search page loads, fetch JSON results via the authenticated session
  async onPageLoad(url, page) {
    if (!/shodan\.io\/(search|host\/search)/i.test(url)) return null;

    const query = parseQuery(url);
    if (!query) return null;

    const key = await extractKey(page);
    if (!key) {
      console.log('[shodan] no key available — passive capture only');
      return null;
    }

    const page_num = (() => {
      try { return parseInt(new URL(url).searchParams.get('page') ?? '1', 10); } catch { return 1; }
    })();

    const apiUrl = `https://api.shodan.io/shodan/host/search?key=${key}&query=${encodeURIComponent(query)}&page=${page_num}`;

    let result;
    try {
      result = await page.evaluate(async (fetchUrl) => {
        const r = await fetch(fetchUrl, { credentials: 'omit' });
        if (!r.ok) return null;
        return r.json();
      }, apiUrl);
    } catch { return null; }

    if (!result?.matches?.length) return null;

    console.log(`[shodan] query="${query}" page=${page_num} → ${result.matches.length} hosts (total: ${result.total})`);
    return result.matches.map(h => mapHost(h, query));
  },
};
