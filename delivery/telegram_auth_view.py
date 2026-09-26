"""
telegram_auth_view.py  —  add to your views.py (or import from here)

Provides two endpoints:
  POST  /save-telegram-chat-id/   — stores the Telegram chat_id on the
                                    authenticated user's Profile (called
                                    automatically when the Mini App opens).
  PATCH /auth/update-phone/       — lets users add/update their phone number.

No Telegram login / Widget / initData verification is needed here.
The Mini App simply uses the normal username+password auth flow and then
POSTs the chat_id separately so the backend can reach the user via the bot.

Django settings required
────────────────────────
  (none for these two views — TELEGRAM_BOT_TOKEN is no longer needed here)
"""

from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from .models import Profile


# ── Save Telegram chat_id ─────────────────────────────────────────────────────

class SaveTelegramChatIdView(APIView):
    """
    POST /save-telegram-chat-id/
    Body: { "chat_id": "123456789" }

    Called by the frontend immediately after the user logs in or signs up
    while inside the Telegram Mini App. Reads window.Telegram.WebApp
    .initDataUnsafe.user.id on the client side and sends it here.

    Requires a valid JWT (IsAuthenticated) so we know which user to update.
    Safe to call on every login — it's idempotent.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        chat_id = str(request.data.get("chat_id", "")).strip()
        if not chat_id:
            return Response(
                {"error": "chat_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.chat_id = chat_id
        profile.save(update_fields=["chat_id"])

        return Response({"ok": True, "chat_id": chat_id})


# ── Phone-update endpoint ─────────────────────────────────────────────────────

class UpdatePhoneView(APIView):
    """
    PATCH /auth/update-phone/
    Body: { "phone": "+251912345678" }
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        phone = str(request.data.get("phone", "")).strip()
        if not phone:
            return Response(
                {"error": "phone is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.phone = phone
        profile.save(update_fields=["phone"])
        return Response({"ok": True, "phone": phone})
