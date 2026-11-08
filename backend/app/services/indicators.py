"""Indicator computation and assessment.

Pure functions with no database access, so they are easy to test and reuse.

Design:
  * ``computation`` decides whether a value is computed from a numerator and a
    denominator (ratio/rate/percent/average) or entered directly (count/sum/
    entered).
  * ``direction`` decides whether a higher or a lower value is better, and for
    ``target_range`` whether the value sits inside an acceptable band.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Computations that are derived from numerator / denominator.
DERIVED = {"ratio", "rate", "percent", "average"}
# Computations entered as a single number.
DIRECT = {"count", "sum", "entered"}

DIRECTIONS = {"higher_better", "lower_better", "target_range"}


class CalculationError(ValueError):
    """Raised when a value cannot be computed from the supplied inputs."""


def _dec(x: object) -> Decimal | None:
    if x is None:
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def compute_value(
    *,
    computation: str,
    numerator: object | None,
    denominator: object | None,
    multiplier: object | None = 100,
    entered_value: object | None = None,
) -> tuple[float | None, str]:
    """Return (value, value_type).

    ``value_type`` is 'computed' when derived from numerator/denominator and
    'entered' when taken directly. A denominator of zero yields (None, ...) and
    never raises or divides by zero.
    """
    if computation in DIRECT:
        return (float(entered_value) if entered_value is not None else None, "entered")

    if computation not in DERIVED:
        raise CalculationError(f"unsupported computation: {computation}")

    num = _dec(numerator)
    den = _dec(denominator)
    if num is None or den is None:
        return (None, "computed")
    if den == 0:
        return (None, "computed")

    mult = _dec(multiplier)
    if mult is None or mult == 0:
        mult = Decimal(1)

    result = (num / den) * mult
    return (float(result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)), "computed")


@dataclass(frozen=True)
class Assessment:
    status: str          # 'good' | 'warning' | 'poor' | 'unknown'
    label_ar: str
    message_ar: str


def assess(
    *,
    direction: str,
    value: float | None,
    target_value: float | None,
    acceptable_min: float | None,
    acceptable_max: float | None,
) -> Assessment:
    """Judge a single value against its target and acceptable limits.

    Never invents a judgement when there is not enough information: it returns
    'unknown' instead.
    """
    if value is None:
        return Assessment("unknown", "غير محسوب", "لا توجد قيمة لحساب التقييم.")

    if direction not in DIRECTIONS:
        return Assessment("unknown", "غير معروف", "اتجاه التحسن غير معرّف.")

    if direction == "higher_better":
        if acceptable_min is not None and value < acceptable_min:
            return Assessment("poor", "أقل من الحد المقبول", "القيمة أقل من الحد الأدنى المقبول.")
        if target_value is not None and value >= target_value:
            return Assessment("good", "محقق للهدف", "القيمة بلغت القيمة المستهدفة أو تجاوزتها.")
        return Assessment("warning", "دون الهدف", "القيمة دون القيمة المستهدفة.")

    if direction == "lower_better":
        if acceptable_max is not None and value > acceptable_max:
            return Assessment("poor", "أعلى من الحد المقبول", "القيمة أعلى من الحد الأقصى المقبول.")
        if target_value is not None and value <= target_value:
            return Assessment("good", "محقق للهدف", "القيمة بلغت القيمة المستهدفة أو أقل.")
        return Assessment("warning", "أعلى من الهدف", "القيمة أعلى من القيمة المستهدفة.")

    # target_range
    in_range = True
    if acceptable_min is not None and value < acceptable_min:
        in_range = False
    if acceptable_max is not None and value > acceptable_max:
        in_range = False
    if not in_range:
        return Assessment("poor", "خارج النطاق المقبول", "القيمة خارج النطاق المقبول.")
    if target_value is not None:
        # Within range and close to target (within 10% of the band width) counts
        # as meeting the target.
        lo = acceptable_min if acceptable_min is not None else target_value
        hi = acceptable_max if acceptable_max is not None else target_value
        span = abs(hi - lo) or abs(target_value) or 1.0
        if abs(value - target_value) <= 0.1 * span:
            return Assessment("good", "قريب من الهدف", "القيمة قريبة من القيمة المستهدفة.")
    return Assessment("warning", "داخل النطاق", "القيمة داخل النطاق المقبول لكنها ليست عند الهدف.")


def trend(current: float | None, previous: float | None, direction: str) -> str:
    """Return 'up' | 'down' | 'flat' | 'unknown' for a value versus the previous."""
    if current is None or previous is None:
        return "unknown"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "flat"


def trend_is_improving(movement: str, direction: str) -> bool | None:
    """Whether a movement is an improvement, given the indicator's direction."""
    if movement == "unknown" or movement == "flat":
        return None
    if direction == "higher_better":
        return movement == "up"
    if direction == "lower_better":
        return movement == "down"
    # target_range: cannot judge direction alone
    return None
