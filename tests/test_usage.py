from talaria.usage import UsageTracker


def test_starts_at_zero():
    u = UsageTracker()
    assert u.total_tokens == 0
    assert u.calls == 0
    assert u.over_limit() is False


def test_add_accumulates_across_calls():
    u = UsageTracker()
    u.add(input_tokens=100, output_tokens=20)
    u.add(input_tokens=50, output_tokens=10)
    assert u.input_tokens == 150
    assert u.output_tokens == 30
    assert u.total_tokens == 180
    assert u.calls == 2


def test_estimated_cost_is_none_when_prices_unset():
    u = UsageTracker()
    u.add(1_000_000, 1_000_000)
    assert u.estimated_cost is None


def test_estimated_cost_uses_configured_prices():
    u = UsageTracker(input_price_per_m=3.0, output_price_per_m=15.0)
    u.add(input_tokens=1_000_000, output_tokens=1_000_000)
    assert u.estimated_cost == 18.0


def test_estimated_cost_scales_with_partial_millions():
    u = UsageTracker(input_price_per_m=10.0, output_price_per_m=0.0)
    u.add(input_tokens=500_000, output_tokens=0)
    assert u.estimated_cost == 5.0


def test_over_limit_false_when_no_limit_set():
    u = UsageTracker(max_tokens=0)
    u.add(10_000_000, 10_000_000)
    assert u.over_limit() is False


def test_over_limit_true_once_total_reaches_max():
    u = UsageTracker(max_tokens=100)
    u.add(60, 30)
    assert u.over_limit() is False
    u.add(5, 5)
    assert u.total_tokens == 100
    assert u.over_limit() is True


def test_summary_includes_cost_and_limit_only_when_configured():
    plain = UsageTracker()
    plain.add(10, 5)
    text = plain.summary()
    assert "15 tokens" in text
    assert "$" not in text
    assert "limit" not in text

    full = UsageTracker(max_tokens=1000, input_price_per_m=1.0, output_price_per_m=2.0)
    full.add(10, 5)
    text_full = full.summary()
    assert "$" in text_full
    assert "limit 1,000" in text_full


def test_as_dict_shape():
    u = UsageTracker(max_tokens=100, input_price_per_m=1.0)
    u.add(10, 5)
    d = u.as_dict()
    assert d == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "calls": 1,
        "estimated_cost": 10 * 1.0 / 1_000_000,
        "max_tokens": 100,
        "over_limit": False,
    }
