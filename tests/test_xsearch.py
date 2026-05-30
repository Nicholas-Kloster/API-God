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
