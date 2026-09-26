import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.db.models import Q
from environ import Env

from .models import Order, Profile, WeeklySalaryRecord
from .serializers import OrderSerializer
from .send_message import send_telegram_message, escape_markdown

env = Env()


# ── Sync helpers (called via sync_to_async) ────────────────────────────────────

def get_delivery_profiles():
    return list(
        Profile.objects.filter(Q(is_delivery=True) | Q(user__is_superuser=True))
    )


def serialize_order(order):
    return OrderSerializer(order).data


def get_env_ids():
    return env("TELEGRAM_CHAT_ID", default=None), env("TELEGRAM_ADMIN_CHAT_ID", default=None)


def send_telegram(message, chat_id, use_portal_bot: bool = False):
    send_telegram_message(message, chat_id, use_portal_bot=use_portal_bot)


def get_username(profile):
    return profile.user.username


def get_phone(profile):
    return profile.phone


def upsert_weekly_salary(username: str, fee: int):
    """Create or update WeeklySalaryRecord for the current ISO week."""
    from django.utils import timezone
    import datetime

    now        = timezone.now()
    week_start = (now - datetime.timedelta(days=now.weekday())).date()
    week_end   = week_start + datetime.timedelta(days=6)

    count = Order.objects.filter(
        delivery_person=username,
        status="delivered",
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
    ).count()

    WeeklySalaryRecord.objects.update_or_create(
        delivery_person=username,
        week_start=week_start,
        defaults={
            "week_end":      week_end,
            "order_count":   count,
            "fee_per_order": fee,
            "total_earned":  count * fee,
        },
    )


def save_profile_chat_id(user, chat_id: str):
    """
    Save chat_id to the user's Profile if it is currently empty.
    Safe to call on every login — only writes when the field is blank.
    """
    try:
        profile = Profile.objects.get(user=user)
        if not profile.chat_id:
            profile.chat_id = chat_id
            profile.save(update_fields=["chat_id"])
    except Profile.DoesNotExist:
        pass  # profile not created yet — skip silently

# NOTE: owner status-change notifications (confirmed/delivered/cancelled)
# live in a post_save signal on Order in signals.py, not here — that
# fires no matter where status was changed (this consumer, Django admin,
# anywhere), and it reads order.owner.chat_id directly since order.owner
# IS the Profile already (the old get_owner_chat_id here incorrectly did
# Profile.objects.get(user=order.owner), comparing a Profile instance
# against the user FK — which can silently match the wrong profile).


# ── WebSocket Consumer ─────────────────────────────────────────────────────────

class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'status_{self.room_name}'
        self.giveaway_group_name = "giveaway_updates"

        # Join dynamic tracking status group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Join global giveaway live updates channel group
        await self.channel_layer.group_add(
            self.giveaway_group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WebSocket connected for room: {self.room_name}")

    async def disconnect(self, close_code):
        # Leave status tracker group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

        # Leave global giveaway channel group
        await self.channel_layer.group_discard(
            self.giveaway_group_name,
            self.channel_name
        )
        print(f"WebSocket disconnected for room: {self.room_name}")

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
            message_type = payload.get("type")
            data = payload.get("data", {})
            owner_profile = self.scope["user"]

            if message_type == "status_update":
                await self.handle_status_update(data)

            elif message_type == "add_order":
                await self.handle_add_order(data, owner_profile)

            elif message_type == "cancel_order":
                await self.handle_cancel_order(data)

            # save Telegram chat_id sent from the Mini App on login
            elif message_type == "save_chat_id":
                await self.handle_save_chat_id(data, owner_profile)

            elif "text-message" in payload:
                await self.send(text_data=json.dumps({
                    "type": "connection_ack",
                    "message": "WebSocket connection established successfully"
                }))

            else:
                print("Unknown message:", payload)

        except Exception as e:
            print("WebSocket receive error:", e)

    # ── Handlers ───────────────────────────────────────────────────────────────

    async def handle_status_update(self, data):
        if "order_id" not in data or "status" not in data:
            return

        try:
            order = await sync_to_async(Order.objects.get)(id=data["order_id"])
            order.status = data["status"]

            if data["status"] == "confirmed":
                order.delivery_person = data.get("person", order.delivery_person)

            await sync_to_async(order.save)()

            # Keep weekly salary record in sync whenever an order is delivered
            if data["status"] == "delivered" and order.delivery_person:
                fee = int(env("DELIVERY_FEE_PER_ORDER", default=50))
                await sync_to_async(upsert_weekly_salary)(order.delivery_person, fee)

            serialized = await sync_to_async(serialize_order)(order)

            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "status_update", "data": serialized}
            )

            # Owner Telegram notification handled by the post_save signal
            # on Order in signals.py — fires from order.save() above.

        except Order.DoesNotExist:
            print("Order not found")

    async def handle_add_order(self, data, owner_profile):
        items = data.get("items", [])
        order = await sync_to_async(Order.objects.create)(
            item_count=data.get("item_count", len(items)),
            owner=owner_profile,
            items=items,
            total_price=data.get("total_price", 0),
            shipping_address=data.get("address", ""),
            special_instraction=data.get("special_instraction", "none"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
        )

        serialized = await sync_to_async(serialize_order)(order)

        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "add_order", "data": serialized}
        )

        # Build Telegram message for delivery team. Wrapped so a
        # malformed/missing field in one cart item (e.g. no "category")
        # can never silently prevent notify_delivery from being called —
        # previously a bare KeyError/TypeError here aborted the whole
        # handler before the rider/admin notification was ever sent.
        try:
            username = await sync_to_async(get_username)(owner_profile)
            phone    = await sync_to_async(get_phone)(owner_profile)

            items_details = ""
            for item in items:
                category = item.get("category") or {}
                category_name = category.get("name", "—") if isinstance(category, dict) else "—"
                items_details += (
                    f"• {escape_markdown(item.get('name', 'Item'))} - "
                    f"Qty: {item.get('quantity', 1)} - "
                    f"Price: {item.get('price', 0)} Birr - Location: {escape_markdown(category_name)}\n"
                )

            lat = data.get("latitude")
            lng = data.get("longitude")
            maps_line = (
                f"\n🗺️ *Live Location:* https://maps.google.com/?q={lat},{lng}"
                if lat and lng else ""
            )

            message = f"""
🛒 *NEW ORDER RECEIVED*

👤 *Customer:* {escape_markdown(username)}
📞 *Phone:* {escape_markdown(phone)}
📍 *Delivery Address:* {escape_markdown(data.get('address', '—'))}{maps_line}

📋 *ORDER ITEMS:*
{items_details}

📊 *Item Count:* {data.get('item_count', len(items))}
💰 *Total Amount:* {data.get('total_price', 0)} Birr
📝 *Special Instructions:* {escape_markdown(data.get('special_instraction', 'none'))}

   *Packaging:* {escape_markdown(data.get('packaging', '—'))}
"""
            await self.notify_delivery(message)
        except Exception as e:
            print(f"handle_add_order notification build error (order {order.id}): {e}")

    async def handle_cancel_order(self, data):
        try:
            order = await sync_to_async(Order.objects.get)(id=data["order_id"])
            order.status = data["status"]
            await sync_to_async(order.save)()

            serialized = await sync_to_async(serialize_order)(order)

            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "status_update", "data": serialized}
            )

            username = await sync_to_async(get_username)(order.owner)
            phone    = await sync_to_async(get_phone)(order.owner)

            message = f"""
🛒 *ORDER CANCELED*

👤 *Customer:* {escape_markdown(username)}
📦 *Items:* {order.item_count}
💰 *Total:* {order.total_price} Birr
📍 *Address:* {escape_markdown(order.shipping_address)}
📞 *Phone:* {escape_markdown(phone)}
"""
            await self.notify_delivery(message)

            # Owner Telegram notification (cancelled) handled by the
            # post_save signal on Order in signals.py.

        except Order.DoesNotExist:
            print("Cancel failed: order not found")

    async def handle_save_chat_id(self, data, user):
        """
        Silently save the Telegram chat_id for the authenticated user.
        Called from the Mini App frontend after login/on mount.
        Only writes if the profile chat_id is currently empty.
        """
        chat_id = str(data.get("chat_id", "")).strip()
        if not chat_id:
            return
        try:
            await sync_to_async(save_profile_chat_id)(user, chat_id)
            print(f"chat_id saved for user {getattr(user, 'username', user)}: {chat_id}")
        except Exception as e:
            print(f"Failed to save chat_id: {e}")

    # ── Channel layer event handlers ───────────────────────────────────────────

    async def status_update(self, event):
        try:
            await self.send(text_data=json.dumps({
                "type": "status_update",
                "data": event["data"],
            }))
        except Exception as e:
            print(f"Error sending status update: {e}")

    async def add_order(self, event):
        try:
            await self.send(text_data=json.dumps({
                "type": "add_order",
                "data": event["data"],
            }))
        except Exception as e:
            print(f"Error sending add_order: {e}")

    async def giveaway_update(self, event):
        """
        Catches the event broadcast from the Django Post-Save signal layer
        and directly streams the real-time payload downstream to the front-end.
        """
        try:
            await self.send(text_data=json.dumps({
                "type": "giveaway_update",
                "data": event["data"],
            }))
        except Exception as e:
            print(f"Error sending giveaway update: {e}")

    # ── Notification helpers ───────────────────────────────────────────────────

    async def notify_delivery(self, message):
        """Send a message to all delivery staff + admin channels (portal bot)."""
        profiles = await sync_to_async(get_delivery_profiles)()
        CHAT_ID, ADMIN_CHAT_ID = await sync_to_async(get_env_ids)()

        ids = {CHAT_ID, ADMIN_CHAT_ID}
        ids.update(p.chat_id for p in profiles if p.chat_id)
        ids.discard(None)  # env() defaults or a blank chat_id shouldn't count as a recipient

        for chat_id in ids:
            try:
                await sync_to_async(send_telegram)(message, chat_id, use_portal_bot=True)
            except Exception as e:
                print(f"notify_delivery send error (chat_id {chat_id}): {e}")
