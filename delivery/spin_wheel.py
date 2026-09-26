"""
Odds logic for the bonus spin wheel. Kept separate from views.py so the
math is easy to test and tune on its own.
"""
import random

from .models import SPIN_WHEEL_PRIZES, Order, SpinWheelResult

# How much total win-weight (1000 + 700 + 500 combined) is allowed to
# climb to. Without a ceiling, a customer who goes a long stretch between
# spins would eventually make "thanks" mathematically impossible. Capping
# it here guarantees "thanks" never drops below (100 - MAX_WIN_WEIGHT)%.
MAX_WIN_WEIGHT = 90  # -> "thanks" floor is always >= 10%


def get_orders_since_last_spin(profile) -> int:
    """Delivered orders the user has racked up since their last spin (or
    all-time, if they've never spun)."""
    last_spin = SpinWheelResult.objects.filter(profile=profile).order_by("-spun_at").first()
    total_delivered = Order.objects.filter(owner=profile, status="delivered").count()
    if not last_spin:
        return total_delivered
    return max(total_delivered - last_spin.order_count_at_spin, 0)


def get_spin_weights(orders_since_last_spin: int) -> dict:
    """
    Returns {prize_key: weight}, weights summing to 100.

    At n=0 (no orders since last spin): 1000 Birr sits at exactly 1/100.
    Each qualifying order adds:
      +3   raw points to "1000"
      +2   raw points to "700"
      +1.5 raw points to "500"
    "thanks" absorbs whatever's left, floored at (100 - MAX_WIN_WEIGHT)%.
    """
    n = max(orders_since_last_spin, 0)
    raw = {
        "1000": 1 + 3 * n,
        "700":  3 + 2 * n,
        "500":  8 + 1.5 * n,
    }

    non_thanks_total = sum(raw.values())
    if non_thanks_total > MAX_WIN_WEIGHT:
        scale = MAX_WIN_WEIGHT / non_thanks_total
        raw = {k: v * scale for k, v in raw.items()}
        non_thanks_total = MAX_WIN_WEIGHT

    raw["thanks"] = 100 - non_thanks_total
    return raw


def pick_prize(orders_since_last_spin: int):
    weights = get_spin_weights(orders_since_last_spin)
    keys, values = list(weights.keys()), list(weights.values())
    chosen_key = random.choices(keys, weights=values, k=1)[0]
    prize = next(p for p in SPIN_WHEEL_PRIZES if p["key"] == chosen_key)
    return prize, weights
