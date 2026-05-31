"""livepipe parser: the live_pipeline event pushes whatever count changed, sometimes one field,
sometimes several. parse_engagement must pull the counts out wherever they sit and ignore the rest."""
import livepipe


def test_parse_engagement_full():
    p = {"tweet_engagement": {"favorite_count": 100, "retweet_count": 5, "quote_count": 2, "reply_count": 9}}
    out = livepipe.parse_engagement(p)
    assert out == {"favorite_count": 100, "retweet_count": 5, "quote_count": 2, "reply_count": 9}


def test_parse_engagement_single_field():
    # the shape we actually saw live: a lone retweet_count delta
    assert livepipe.parse_engagement({"retweet_count": 63568}) == {"retweet_count": 63568}


def test_parse_engagement_quoted_numbers():
    assert livepipe.parse_engagement({"favorite_count": "42"}) == {"favorite_count": 42}


def test_parse_engagement_none():
    assert livepipe.parse_engagement({"topic": "/system/config", "config": {"x": 1}}) == {}
