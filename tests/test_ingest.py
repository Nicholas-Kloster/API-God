"""ingest pipeline: the dedup core. A List re-returns the same tweets every poll, so _new must pass
a tweet downstream exactly once across cycles."""
import ingest


def test_new_passes_each_tweet_once():
    seen = set()
    first = ingest._new([{"id": "1"}, {"id": "2"}], seen)
    assert [p["id"] for p in first] == ["1", "2"]
    assert seen == {"1", "2"}


def test_new_dedups_across_polls():
    seen = set()
    ingest._new([{"id": "1"}, {"id": "2"}], seen)
    # next poll re-returns 1 and 2 (unchanged) plus a new 3 -> only 3 is new
    second = ingest._new([{"id": "2"}, {"id": "1"}, {"id": "3"}], seen)
    assert [p["id"] for p in second] == ["3"]
    assert seen == {"1", "2", "3"}
