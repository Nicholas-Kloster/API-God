"""xsearch: lock the SearchTimeline parser so the drain-budget change cannot silently break it,
and verify the non-first drain budget tracks the scroll delay so slow responses are not truncated (#2)."""
import pytest
import xsearch


def test_extract_session_parses_rich_fields():
    body = {"data": {"search_by_raw_query": {"search_timeline": {"timeline": {"instructions": [
        {"type": "TimelineAddEntries", "entries": [{"content": {"itemContent": {"itemType": "TimelineTweet",
            "tweet_results": {"result": {
                "legacy": {"id_str": "1", "full_text": "hi $TST", "favorite_count": 3, "retweet_count": 1},
                "core": {"user_results": {"result": {
                    "legacy": {"screen_name": "a", "followers_count": 9},
                    "core": {"name": "A"}, "is_blue_verified": True}}}}}}}}]}]}}}}}
    recs = xsearch.extract_session(body)
    assert len(recs) == 1
    r = recs[0]
    assert r["handle"] == "@a" and r["followers"] == 9 and r["blue"] is True and r["likes"] == 3


def test_drain_budget_tracks_delay():
    assert xsearch._drain_budget(first=True, delay=1300) == 6.0
    assert xsearch._drain_budget(first=False, delay=1300) == pytest.approx(2.8)   # 1.3s + 1.5s
    assert xsearch._drain_budget(first=False, delay=300) == 2.0                    # floored at 2.0


def test_logged_in_rejects_guest_session():
    # the exact guest-only cookie set the broken --login saved on 2026-05-30: no auth_token => logged out
    guest = [{"name": n} for n in ("guest_id", "gt", "personalization_id", "__cf_bm", "g_state")]
    assert xsearch._logged_in(guest) is False


def test_logged_in_accepts_real_session():
    real = [{"name": "guest_id"}, {"name": "auth_token"}, {"name": "ct0"}, {"name": "twid"}]
    assert xsearch._logged_in(real) is True


def test_probe_report_finds_cutoff():
    # 30 good SearchTimeline responses, then X returns 429 at 24.6s -> that is the cutoff
    log = [(200, i * 0.8) for i in range(30)] + [(429, 24.6)]
    rep = xsearch._probe_report(log)
    assert rep["requests"] == 31
    assert rep["ok_before_limit"] == 30
    assert rep["limit_status"] == 429
    assert rep["limit_at_s"] == 24.6


def test_probe_report_no_limit_hit():
    # never cut off within budget -> limit_status None, all counted as ok
    log = [(200, i * 0.8) for i in range(20)]
    rep = xsearch._probe_report(log)
    assert rep["limit_status"] is None
    assert rep["ok_before_limit"] == 20


def test_extract_user_timeline_parses():
    # UserTweets body: same tweet shape as search, different timeline path (user.result.timeline_v2)
    tweet = {"result": {
        "legacy": {"id_str": "9", "full_text": "gm", "favorite_count": 5, "retweet_count": 0},
        "core": {"user_results": {"result": {
            "legacy": {"screen_name": "elonmusk", "followers_count": 100},
            "core": {"name": "Elon"}, "is_blue_verified": True}}}}}
    entry = {"content": {"itemContent": {"itemType": "TimelineTweet", "tweet_results": tweet}}}
    instructions = [{"type": "TimelineAddEntries", "entries": [entry]}]
    body = {"data": {"user": {"result": {"timeline_v2": {"timeline": {"instructions": instructions}}}}}}
    recs = xsearch.extract_user_timeline(body)
    assert len(recs) == 1
    assert recs[0]["handle"] == "@elonmusk" and recs[0]["id"] == "9" and recs[0]["likes"] == 5


def test_tweet_ts_orders_chronologically():
    older = xsearch._tweet_ts("Wed May 27 10:00:00 +0000 2026")
    newer = xsearch._tweet_ts("Sat May 30 10:00:00 +0000 2026")
    assert newer > older > 0
