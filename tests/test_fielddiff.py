"""fielddiff: lock the field-name collector, the core of the cross-operation diff. It must gather
dict keys at every depth and ignore list length and scalars, so two differently-shaped responses
compare by the data they carry."""
import fielddiff


def test_field_names_collects_keys_at_all_depths():
    obj = {"a": 1, "b": {"c": 2, "d": [{"e": 3}, {"f": 4}]}}
    assert fielddiff.field_names(obj) == {"a", "b", "c", "d", "e", "f"}


def test_field_names_ignores_scalars_and_list_length():
    assert fielddiff.field_names(5) == set()
    assert fielddiff.field_names([]) == set()
    assert fielddiff.field_names({"x": [1, 2, 3]}) == {"x"}


def test_field_names_diff_surfaces_the_extra_field():
    cdn = {"favorite_count": 1, "user": {"screen_name": "a"}}
    gql = {"legacy": {"favorite_count": 1, "retweet_count": 0}, "core": {"screen_name": "a"}}
    extra = fielddiff.field_names(gql) - fielddiff.field_names(cdn)
    assert "retweet_count" in extra
    assert "favorite_count" not in extra        # shared field is not reported as unique
