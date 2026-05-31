"""reactive: lock the velocity gate. evict_targets must drop the coldest tweets first, never drop the
protected stream id, and do nothing while there is room."""
import reactive


def test_evict_targets_drops_coldest_first():
    subscribed = {"a", "b", "c", "d"}
    activity = {"a": 100.0, "b": 50.0, "c": 200.0, "d": 10.0}
    # 4 subscribed + 2 new in a max of 4 -> overflow 2 -> evict the two coldest (d=10, b=50)
    evict = reactive.evict_targets(subscribed, activity, 2, 4)
    assert set(evict) == {"d", "b"}


def test_evict_targets_noop_when_room():
    assert reactive.evict_targets({"a", "b"}, {"a": 1.0, "b": 2.0}, 1, 5) == []


def test_evict_targets_protects_stream_id():
    # "a" is coldest but protected (the stream's own GET topic); evict the next coldest instead
    evict = reactive.evict_targets({"a", "b", "c"}, {"a": 1.0, "b": 2.0, "c": 3.0}, 1, 3, protect={"a"})
    assert "a" not in evict and evict == ["b"]


def test_evict_targets_missing_activity_is_coldest():
    # a tweet with no recorded activity sorts as coldest (default 0.0)
    evict = reactive.evict_targets({"a", "b"}, {"b": 5.0}, 1, 2)
    assert evict == ["a"]
