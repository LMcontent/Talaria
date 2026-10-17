from talaria.tools.meaning_cache import cache_clear, cache_get, cache_list, cache_put, make_meaning_cache_tools


def test_put_requires_query_and_value(tmp_path):
    assert "Error" in cache_put(str(tmp_path), query="", value="x")
    assert "Error" in cache_put(str(tmp_path), query="x", value="")


def test_put_rejects_bad_ttl(tmp_path):
    assert "Error" in cache_put(str(tmp_path), query="q", value="v", ttl_hours="0")
    assert "Error" in cache_put(str(tmp_path), query="q", value="v", ttl_hours="nope")


def test_put_then_get_roundtrip(tmp_path):
    cache_put(str(tmp_path), query="weather in Paris", value="sunny, 20C")
    result = cache_get(str(tmp_path), query="weather in Paris")
    assert "CACHE HIT" in result
    assert "sunny, 20C" in result


def test_get_miss_on_unrelated_query(tmp_path):
    cache_put(str(tmp_path), query="weather in Paris", value="sunny, 20C")
    assert "CACHE MISS" in cache_get(str(tmp_path), query="completely different topic")


def test_re_putting_same_query_overwrites(tmp_path):
    cache_put(str(tmp_path), query="weather in Paris", value="sunny, 20C")
    cache_put(str(tmp_path), query="weather in Paris", value="rainy, 15C")
    result = cache_get(str(tmp_path), query="weather in Paris")
    assert "rainy, 15C" in result
    assert cache_list(str(tmp_path)).count("weather in Paris") == 1


def test_list_empty_and_populated(tmp_path):
    assert cache_list(str(tmp_path)) == "(cache is empty)"
    cache_put(str(tmp_path), query="weather in Paris", value="sunny")
    assert "weather in Paris" in cache_list(str(tmp_path))


def test_clear_all(tmp_path):
    cache_put(str(tmp_path), query="q1", value="v1")
    cache_put(str(tmp_path), query="q2", value="v2")
    msg = cache_clear(str(tmp_path), mode="all")
    assert "Cleared all (2 entries)" in msg
    assert cache_list(str(tmp_path)) == "(cache is empty)"


def test_make_meaning_cache_tools_exposes_expected_names(tmp_path):
    names = {t.name for t in make_meaning_cache_tools(str(tmp_path))}
    assert names == {"cache_put", "cache_get", "cache_list", "cache_clear"}
