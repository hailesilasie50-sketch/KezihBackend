"""
Spin wheel odds engine.

Two things live here:

1. Loyalty boost — customers with more *delivered* orders get better odds on
   "good" prizes (coins, free_delivery, extra_spin). This is the reward for
   ordering more.

2. EV cap enforcement — no matter how generous a loyalty tier gets, or how
   someone tunes SpinPrize.probability in admin later, the *expected* Birr
   payout of a single spin is capped. If a boosted distribution would pay out
   more than SPIN_EV_CAP_BIRR on average, the boost is automatically scaled
   back until it's within budget. This is what keeps the wheel profitable —
   the cap is enforced at spin time, not just assumed from how weights were
   set up once.

Tune the three constants below to your real numbers. Everything else is
mechanical.
"""

# Rough average delivery fee, used only to estimate the "cost" of a
# free_delivery win for EV purposes. Doesn't need to be exact — swap in
# whatever your CartFunc haversine calculation tends to land on.
AVG_DELIVERY_FEE_BIRR = 60

# Hard ceiling on the expected Birr payout of a single spin, after loyalty
# boosts and the amplification from "extra spin" prizes are both accounted
# for. This is the number that actually protects your margin — pick it based
# on what you can afford to give away per delivered order (e.g. a fraction of
# your average per-order profit).
SPIN_EV_CAP_BIRR = 15

# (min_delivered_orders, weight_multiplier_applied_to_good_prizes)
# Must be sorted ascending by threshold. The multiplier for the highest
# threshold the customer has reached is used.
LOYALTY_TIERS = [
    (0,   1.0),   # everyone starts here
    (5,   1.15),
    (15,  1.30),
    (30,  1.50),
    (60,  1.75),
]

# Prize kinds that loyalty boosts apply to. "thanks" is intentionally
# excluded — it's the counterweight, so boosting the others naturally shrinks
# its relative share without needing to touch it directly.
GOOD_KINDS = {"coins", "free_delivery", "extra_spin"}

# Safety clamp: if the probability of drawing another spin ever got close to
# 1.0, the EV amplification below would blow up toward infinity. This caps
# how much of that we trust.
MAX_EXTRA_SPIN_PROB = 0.90


def get_loyalty_multiplier(delivered_order_count: int) -> float:
    """Highest tier multiplier this customer has earned."""
    multiplier = LOYALTY_TIERS[0][1]
    for threshold, mult in LOYALTY_TIERS:
        if delivered_order_count >= threshold:
            multiplier = mult
        else:
            break
    return multiplier


def _boosted_weights(prizes, multiplier: float):
    weights = []
    for p in prizes:
        w = float(p.probability)
        if p.kind in GOOD_KINDS:
            w *= multiplier
        weights.append(w)
    return weights


def _estimate_ev(prizes, weights) -> float:
    """Expected Birr payout of one spin under the given weights, including
    the amplification from 'extra_spin' prizes granting more draws."""
    total = sum(weights)
    if total <= 0:
        return 0.0

    raw_ev = 0.0
    p_extra = 0.0
    for prize, w in zip(prizes, weights):
        prob = w / total
        if prize.kind == "coins":
            raw_ev += prob * prize.value
        elif prize.kind == "free_delivery":
            raw_ev += prob * AVG_DELIVERY_FEE_BIRR
        elif prize.kind == "extra_spin":
            p_extra += prob

    p_extra = min(p_extra, MAX_EXTRA_SPIN_PROB)
    return raw_ev / (1 - p_extra)


def get_capped_weights(prizes, delivered_order_count: int):
    """
    Returns (weights, multiplier_applied, estimated_ev) — the actual weights
    to hand to random.choices(), after applying this customer's loyalty
    boost and then scaling it back if needed to stay under SPIN_EV_CAP_BIRR.
    """
    target_multiplier = get_loyalty_multiplier(delivered_order_count)
    multiplier = target_multiplier

    weights = _boosted_weights(prizes, multiplier)
    ev = _estimate_ev(prizes, weights)

    # Back off the boost in small steps until we're under budget. If even the
    # *unboosted* (multiplier=1.0) distribution is over budget, that's a
    # pricing problem in the SpinPrize table itself, not something loyalty
    # tiers can fix — we stop at 1.0 and let it through as-is so the wheel
    # doesn't break, but this is a signal to lower probabilities in admin.
    while ev > SPIN_EV_CAP_BIRR and multiplier > 1.0:
        multiplier = max(1.0, multiplier - 0.05)
        weights = _boosted_weights(prizes, multiplier)
        ev = _estimate_ev(prizes, weights)

    return weights, multiplier, ev
