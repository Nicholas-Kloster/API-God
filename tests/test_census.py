"""census: lock the queryId extraction regex, the bundle-walk, and the header parsing so the
browserless bucket sweep cannot silently break. The functions take the session as a parameter, so
a tiny fake session drives them offline (no monkeypatch, no network)."""
import census


class FakeResp:
    def __init__(self, status=200, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


class FakeSession:
    """Routes .get(url) to a FakeResp by URL substring, in order."""
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, *a, **k):
        for sub, resp in self.routes:
            if sub in url:
                return resp
        raise AssertionError(f"unmocked URL: {url}")


def test_op_regex_extracts_query_and_mutation():
    js = ('x queryId:"ABC",operationName:"UserTweets",operationType:"query" y '
          'queryId:"DEF",operationName:"CreateTweet",operationType:"mutation"')
    found = {op: (qid, typ) for qid, op, typ in census.OP_RE.findall(js)}
    assert found["UserTweets"] == ("ABC", "query")
    assert found["CreateTweet"] == ("DEF", "mutation")


def test_extract_ops_walks_bundles_from_html():
    html = '<link href="https://abs.twimg.com/responsive-web/client-web/main.deadbeef.js" as="script">'
    js = 'q queryId:"Q1",operationName:"SearchTimeline",operationType:"query"'
    s = FakeSession([("https://x.com/", FakeResp(text=html)),
                     ("main.deadbeef.js", FakeResp(text=js))])
    ops = census.extract_ops(s)
    assert ops["SearchTimeline"] == {"queryId": "Q1", "type": "query"}


def test_probe_parses_422_headers():
    s = FakeSession([("graphql", FakeResp(422, headers={
        "x-rate-limit-limit": "500", "x-rate-limit-remaining": "499", "x-rate-limit-reset": "1780197412"}))])
    r = census.probe(s, "Q1", "TweetResultsByRestIds")
    assert r["status"] == 422 and r["limit"] == 500 and r["remaining"] == 499 and r["reset"] == 1780197412


def test_probe_403_no_headers_flagged():
    s = FakeSession([("graphql", FakeResp(403, headers={}))])
    r = census.probe(s, "Q1", "UsersByRestIds")
    assert r["status"] == 403 and "limit" not in r and "WAF" in r["note"]


def test_chunk_urls_parses_webpack_u_builder():
    html = ('x _.u=e=>""+(({10:"bundle.Bookmarks",20:"i18n/th"}[e]||e)+"."+'
            '{10:"abc123",20:"def456",30:"99hash"}[e]+"a.js"),y')
    urls = census._chunk_urls(html)
    assert "https://abs.twimg.com/responsive-web/client-web/bundle.Bookmarks.abc123a.js" in urls
    assert any("30.99hasha.js" in u for u in urls)      # a chunk with no name uses its id
    assert not any("i18n/th" in u for u in urls)        # i18n chunk skipped
