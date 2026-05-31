"""Characterization net for engine_core pure functions. Locks current good behavior before
any fix or refactor. Ports the stress.py adversarial cases; the two known-open BUILD gaps
are documented xfail so they are tracked, not silently failing."""
from engine_core import (norm_name, cashtag_hit, classify, zone_of,
                         score_resolved, independent_bonus, dedup_name, cluster_penalty,
                         velocity_bonus, engagement_velocity)
import pytest


def test_cashtag_common_word_needs_dollar():
    assert cashtag_hit("MOON", "we are going to the moon") is False
    assert cashtag_hit("TRUMP", "Trump announced tariffs") is False
    assert cashtag_hit("MOON", "buy $MOON now") is True
    assert cashtag_hit("WIFHAT", "gm $WIFHAT holders") is True


def test_norm_name_collapses_compat_not_homoglyph():
    assert norm_name("Token") == norm_name("Ｔｏｋｅｎ")
    assert norm_name("Token") == norm_name("Token!")
    assert norm_name("Token") == norm_name("Token ")
    assert norm_name("Token") != norm_name("Тoken")   # cyrillic, accepted residual
    assert norm_name("Token") != norm_name("T0ken")    # leet, accepted residual


def test_classify_link_kinds():
    assert classify("https://x.com/h/status/123") == ("status", "h", "123")
    assert classify("https://x.com/i/status/456")[0] == "status"
    assert classify("https://x.com/handle")[:2] == ("profile", "handle")
    assert classify("https://x.com/search?q=a")[0] == "search"
    assert classify("https://x.com/i/communities/9")[0] == "community"
    assert classify("")[0] == "none"


def test_zone_warmup_is_green():
    assert zone_of(5.0, [0.1, 0.1, 0.1]) == "green"      # < 5 samples -> suppress
    assert zone_of(0.0, [0.1] * 50) == "green"            # non-positive buy


def test_zone_percentiles():
    buf = [0.2] * 80 + [0.5] * 15 + [2, 3, 4, 5, 8]
    assert zone_of(8, buf) == "red"
    assert zone_of(0.2, buf) == "green"


def test_handle_mismatch_voids_verification():
    s_spoof, _ = score_resolved("amber", refs=True, blue=True, mism=True)
    assert s_spoof <= 0
    s_clean, _ = score_resolved("amber", refs=True, blue=True, mism=False)
    assert s_clean >= 4


def test_independent_bonus_weights():
    assert independent_bonus(0, 0)[0] == 0                # lonely shill
    assert independent_bonus(4, 0)[0] == 3                # 4+ CA posters
    assert independent_bonus(1, 0)[0] == 1


def test_dedup_name_time_window():
    seen = {}
    assert dedup_name("a", 1000.0, seen) is False         # first sight
    assert dedup_name("a", 1100.0, seen) is True           # within 300s
    assert dedup_name("a", 1500.0, seen) is False          # outside 300s of last
    assert dedup_name("", 1.0, seen) is False              # empty never dedups


def test_cluster_penalty_canonical():
    s, note, serial = cluster_penalty(3, 3, 1)
    assert s == 1 and serial == 3 and "w3" in note          # repeated wallet -> -2
    s2, note2, ser2 = cluster_penalty(3, 2, 2)
    assert s2 == 0 and ser2 == 2 and "BOTH" in note2        # both repeat -> -3
    s3, note3, ser3 = cluster_penalty(3, 1, 1)
    assert s3 == 3 and ser3 == 1 and note3 == ""            # no cluster -> unchanged


@pytest.mark.xfail(reason="known-open BUILD gap: self-attested perfect fake scores high", strict=True)
def test_perfect_fake_neutralized():
    s, _ = score_resolved("red", refs=True, blue=True, mism=False)
    assert s < 4


def test_velocity_bonus_tiers():
    assert velocity_bonus(0) == (0, "")
    assert velocity_bonus(5) == (0, "")                    # below the warm threshold
    assert velocity_bonus(20)[0] == 1                      # warm
    hot_pts, hot_note = velocity_bonus(80)
    assert hot_pts == 2 and "hot" in hot_note              # viral


def test_velocity_bonus_absence_is_neutral():
    assert velocity_bonus(None) == (0, "")                 # no live reading -> no bonus, no penalty


def test_engagement_velocity_sums_and_excludes_views():
    rates = {"favorite_count": 30.0, "retweet_count": 12.0, "reply_count": 3.0, "view_count": 9000.0}
    assert engagement_velocity(rates) == 45.0              # commitment signals summed, views excluded
    assert engagement_velocity({}) == 0.0
    assert velocity_bonus(engagement_velocity(rates))[0] == 1   # the live_pipeline -> engine bridge: 45/min -> warm
