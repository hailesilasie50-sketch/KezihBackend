from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Order, Giveaway, Profile, GIVEAWAY_TARGET, SpinWheelResult
from .serializers import GiveawaySerializer
from .send_message import send_telegram_message, escape_markdown

from django.db.models import F


@receiver(post_save, sender=Order)
def grant_spin_chance_on_delivery(sender, instance, **kwargs):
    if instance.status != "delivered" or instance.spin_chance_granted:
        return
    Order.objects.filter(pk=instance.pk).update(spin_chance_granted=True)
    Profile.objects.filter(pk=instance.owner_id).update(
        available_spins=F("available_spins") + 1
    )

@receiver(post_save, sender=Order)
def order_giveaway_processor(sender, instance, created, **kwargs):
    """
    Every delivered order counts toward the *owning customer's own*
    progress bar, not a shared pool. The moment a single customer's
    delivered-order count (since their last win) reaches GIVEAWAY_TARGET,
    they win automatically — no pooling across customers, no randomness.
    """
    if instance.status != "delivered" or instance.counted_for_giveaway:
        return

    # Mark counted first so re-saves of this same order (e.g. attaching a
    # payment screenshot after delivery) never double-count it.
    Order.objects.filter(pk=instance.pk).update(counted_for_giveaway=True)

    profile = instance.owner
    Profile.objects.filter(pk=profile.pk).update(
        giveaway_progress=F("giveaway_progress") + 1
    )
    profile.refresh_from_db(fields=["giveaway_progress", "giveaway_wins_count"])

    winner_announced = None

    # 2. Check threshold — this customer alone, not a shared pool
    if profile.giveaway_progress >= GIVEAWAY_TARGET:
        recent_orders = Order.objects.filter(
            owner=profile, counted_for_giveaway=True
        ).order_by("-created_at")[:GIVEAWAY_TARGET]

        giveaway = Giveaway.objects.create(
            winner=profile,
            milestone=(profile.giveaway_wins_count + 1) * GIVEAWAY_TARGET,
        )
        giveaway.delivered_orders.set(list(recent_orders))

        Profile.objects.filter(pk=profile.pk).update(
            giveaway_progress=0,
            giveaway_wins_count=F("giveaway_wins_count") + 1,
        )
        profile.refresh_from_db(fields=["giveaway_progress", "giveaway_wins_count"])

        winner_announced = {
            "name": profile.name or profile.user.username,
            "phone": profile.phone or "",
            "price": giveaway.price,
            "milestone": giveaway.milestone,
        }

        # Personal Telegram DM to the winner, separate from the public
        # "giveaway_updates" broadcast below (which only drives the live
        # progress bar / winners feed UI, not a direct notification).
        if profile.chat_id:
            try:
                win_message = (
                    "🎉🎊 *Congratulations!*\n\n"
                    f"You've completed {giveaway.milestone} orders and won "
                    f"*{giveaway.price} Birr*!\n\n"
                    "Thank you for being a loyal Liyu Delivery customer."
                )
                send_telegram_message(win_message, profile.chat_id, use_portal_bot=False)
            except Exception as e:
                print(f"giveaway winner notification error (profile {profile.pk}): {e}")

    # 3. Gather payload for real-time push
    history = Giveaway.objects.order_by("-completed_at")[:5]
    history_data = GiveawaySerializer(history, many=True).data

    payload = {
        "winner_announced": winner_announced,
        "history": history_data,
    }

    # 4. Broadcast outside consumer using Channel Layer
    channel_layer = get_channel_layer()
    # Must match the group name your OrderConsumer joins for giveaway updates
    async_to_sync(channel_layer.group_send)(
        "giveaway_updates",
        {
            "type": "giveaway_update",
            "data": payload,
        },
    )


# ── Owner status notification ────────────────────────────────────────────
# Moved here from consumers.py: a post_save signal fires no matter where
# order.status was changed — the live WebSocket dashboard, Django admin,
# a management command, anything — so the owner is notified consistently
# either way, instead of only when the change happened to come through
# the WebSocket message handlers.

OWNER_STATUS_MESSAGES = {
    "confirmed": (
        "✅ *Your order has been confirmed!*\n\n"
        "A delivery person has been assigned and is on the way.\n"
        "📦 Items: {item_count}\n"
        "💰 Total: {total_price} Birr\n"
        "📍 Address: {address}"
    ),
    "delivered": (
        "🎉 *Your order has been delivered!*\n\n"
        "Thank you for ordering with Liyu Delivery.\n"
        "📦 Items: {item_count}\n"
        "💰 Total: {total_price} Birr"
    ),
    # Order.ORDER_STATUS spells this "cancelled" (two Ls) — keep both
    # spellings mapped to the same message just in case anything (admin,
    # older client code) still sends the single-L version.
    "cancelled": (
        "❌ *Your order has been canceled.*\n\n"
        "📦 Items: {item_count}\n"
        "💰 Total: {total_price} Birr\n"
        "If you have questions, please contact us."
    ),
}
OWNER_STATUS_MESSAGES["canceled"] = OWNER_STATUS_MESSAGES["cancelled"]


def _build_owner_status_message(order, status):
    template = OWNER_STATUS_MESSAGES.get(status)
    if not template:
        return None
    return template.format(
        item_count=order.item_count,
        total_price=order.total_price,
        address=escape_markdown(getattr(order, "shipping_address", "—")),
    )


@receiver(post_save, sender=Order)
def notify_owner_on_status_change(sender, instance, created, **kwargs):
    """
    Send the order owner a Telegram message when status becomes
    confirmed / delivered / cancelled, exactly once per status.

    Guarded by owner_notified_status so re-saving an order that's already
    in that same status (e.g. attaching a payment screenshot after
    delivery, or an unrelated admin edit) never re-sends the message —
    only an actual status change triggers a new notification.
    """
    if created:
        return  # brand-new order — nothing to notify about yet

    if instance.status == instance.owner_notified_status:
        return  # already notified for this exact status

    message = _build_owner_status_message(instance, instance.status)
    if not message:
        return  # status not one we notify about (e.g. "pending")

    chat_id = instance.owner.chat_id
    if not chat_id:
        return  # owner hasn't linked Telegram yet — skip silently

    try:
        send_telegram_message(message, chat_id, use_portal_bot=False)
    except Exception as e:
        print(f"notify_owner_on_status_change error (order {instance.id}): {e}")
        return  # send failed — don't mark as notified, so it can retry on next save

    # .update() (not .save()) so this doesn't re-trigger post_save/recurse
    Order.objects.filter(pk=instance.pk).update(owner_notified_status=instance.status)


# ── Spin wheel win notification ──────────────────────────────────────────

def _build_spin_win_message(result):
    prize = result.prize
    if not prize or prize.kind == "thanks":
        return None  # no reward — nothing to notify about

    if prize.kind == "coins":
        detail = f"*{result.coins_awarded} Birr* in coins"
    elif prize.kind == "extra_spin":
        n = result.spins_awarded
        detail = f"*{n}* extra spin{'s' if n != 1 else ''}"
    elif prize.kind == "free_delivery":
        detail = "a *free delivery*"
    else:
        detail = f"*{escape_markdown(prize.label)}*"

    return (
        "🎡 *You won on the Spin Wheel!*\n\n"
        f"You just won {detail}. Keep placing orders to earn more spins!"
    )


@receiver(post_save, sender=SpinWheelResult)
def notify_spin_win(sender, instance, created, **kwargs):
    """
    Send a Telegram message when a spin actually wins something.
    Guarded by `created` rather than a separate flag — spin results are
    only ever created once (SpinWheelSpinView.post()); the only field
    that gets updated afterward is `status` (not_received → received),
    which must NOT re-trigger this notification.
    """
    if not created:
        return

    message = _build_spin_win_message(instance)
    if not message:
        return  # "thanks for playing" — no prize, no notification

    chat_id = instance.profile.chat_id
    if not chat_id:
        return  # user hasn't linked Telegram yet — skip silently

    try:
        send_telegram_message(message, chat_id, use_portal_bot=False)
    except Exception as e:
        print(f"notify_spin_win error (result {instance.id}): {e}")
