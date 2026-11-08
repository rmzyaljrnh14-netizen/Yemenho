"""Unit tests for indicator computation and assessment (pure functions)."""
from __future__ import annotations

import pytest

from app.services.indicators import (
    CalculationError,
    assess,
    compute_value,
    trend,
    trend_is_improving,
)


# ---- compute_value ----
def test_percent_from_numerator_denominator():
    value, kind = compute_value(computation="percent", numerator=30, denominator=200, multiplier=100)
    assert value == 15.0
    assert kind == "computed"


def test_rate_uses_multiplier():
    value, _ = compute_value(computation="rate", numerator=4, denominator=1000, multiplier=1000)
    assert value == 4.0


def test_ratio_default_multiplier_is_one_when_missing():
    value, _ = compute_value(computation="ratio", numerator=12, denominator=3, multiplier=None)
    assert value == 4.0


def test_average_is_derived():
    value, kind = compute_value(computation="average", numerator=50, denominator=10, multiplier=1)
    assert value == 5.0
    assert kind == "computed"


def test_zero_denominator_yields_none_not_error():
    value, kind = compute_value(computation="percent", numerator=5, denominator=0, multiplier=100)
    assert value is None
    assert kind == "computed"


def test_missing_inputs_yield_none():
    value, _ = compute_value(computation="percent", numerator=None, denominator=10, multiplier=100)
    assert value is None
    value, _ = compute_value(computation="percent", numerator=10, denominator=None, multiplier=100)
    assert value is None


def test_count_is_entered_not_computed():
    value, kind = compute_value(computation="count", numerator=None, denominator=None, entered_value=7)
    assert value == 7.0
    assert kind == "entered"


def test_entered_without_value_is_none():
    value, kind = compute_value(computation="entered", numerator=None, denominator=None, entered_value=None)
    assert value is None
    assert kind == "entered"


def test_unsupported_computation_raises():
    with pytest.raises(CalculationError):
        compute_value(computation="nonsense", numerator=1, denominator=2)


def test_rounding_to_four_places():
    value, _ = compute_value(computation="percent", numerator=1, denominator=3, multiplier=100)
    assert value == 33.3333


# ---- assess ----
def test_lower_better_meets_target():
    a = assess(direction="lower_better", value=1.0, target_value=2.0, acceptable_min=None, acceptable_max=5.0)
    assert a.status == "good"


def test_lower_better_above_target_warns():
    a = assess(direction="lower_better", value=3.0, target_value=2.0, acceptable_min=None, acceptable_max=5.0)
    assert a.status == "warning"


def test_lower_better_above_acceptable_is_poor():
    a = assess(direction="lower_better", value=9.0, target_value=2.0, acceptable_min=None, acceptable_max=5.0)
    assert a.status == "poor"


def test_higher_better_meets_target():
    a = assess(direction="higher_better", value=92.0, target_value=90.0, acceptable_min=80.0, acceptable_max=None)
    assert a.status == "good"


def test_higher_better_below_acceptable_is_poor():
    a = assess(direction="higher_better", value=50.0, target_value=90.0, acceptable_min=80.0, acceptable_max=None)
    assert a.status == "poor"


def test_target_range_inside_is_warning_or_good():
    a = assess(direction="target_range", value=80.0, target_value=80.0, acceptable_min=60.0, acceptable_max=90.0)
    assert a.status == "good"
    b = assess(direction="target_range", value=62.0, target_value=80.0, acceptable_min=60.0, acceptable_max=90.0)
    assert b.status == "warning"
    c = assess(direction="target_range", value=95.0, target_value=80.0, acceptable_min=60.0, acceptable_max=90.0)
    assert c.status == "poor"


def test_assess_without_value_is_unknown():
    a = assess(direction="higher_better", value=None, target_value=90.0, acceptable_min=None, acceptable_max=None)
    assert a.status == "unknown"


def test_assess_without_target_is_warning_not_fabricated_good():
    a = assess(direction="higher_better", value=50.0, target_value=None, acceptable_min=None, acceptable_max=None)
    assert a.status == "warning"


# ---- trend ----
def test_trend_directions():
    assert trend(10, 5, "higher_better") == "up"
    assert trend(5, 10, "higher_better") == "down"
    assert trend(5, 5, "higher_better") == "flat"
    assert trend(None, 5, "higher_better") == "unknown"


def test_trend_improvement_depends_on_direction():
    assert trend_is_improving("up", "higher_better") is True
    assert trend_is_improving("down", "higher_better") is False
    assert trend_is_improving("down", "lower_better") is True
    assert trend_is_improving("up", "lower_better") is False
    assert trend_is_improving("flat", "lower_better") is None
    assert trend_is_improving("up", "target_range") is None
