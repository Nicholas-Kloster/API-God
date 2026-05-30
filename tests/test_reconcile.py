"""Replay guard regressions:
- finding #7: an empty / all-green capture must not crash on the percentile buffer.
- finding #1: a mixed capture (first line has _ts, a later line does not) must not KeyError."""
import replay


def test_replay_empty_capture_no_crash(tmp_path):
    f = tmp_path / "empty.jsonl"; f.write_text("")
    replay.run(str(f))          # must not raise IndexError on the empty percentile buffer


def test_replay_mixed_ts_no_crash(tmp_path):
    lines = [
        '{"mint":"a","name":"X","symbol":"X","solAmount":0.1,"_ts":1000.0}',  # has _ts -> time path
        '{"mint":"b","name":"X","symbol":"X","solAmount":0.1}',               # no _ts -> KeyError today
    ]
    f = tmp_path / "mixed.jsonl"; f.write_text("\n".join(lines))
    replay.run(str(f))          # must not raise KeyError on the second line
