"""
auth_views.py — drop into your views.py or import from here.

Provides:
  POST  /auth/login/        — authenticates user, saves chat_id to profile, returns JWT
  POST  /create-user/       — creates user+profile with phone AND chat_id in one shot
  PATCH /auth/update-phone/ — lets an authenticated user save/update their phone number

The separate /save-telegram-chat-id/ and /auth/telegram/ endpoints are gone.
chat_id now flows in through the normal signup and login request bodies.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Profile


# ── helper ────────────────────────────────────────────────────────────────────

def _tokens_for_user(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access":  str(refresh.access_token),
    }


def _save_chat_id_if_missing(user: User, chat_id: str) -> None:
    """
    Write chat_id to the user's profile ONLY if it isn't already set.
    No-op if chat_id is empty, or if the profile already has a chat_id
    (so we never clobber it — e.g. a user logging in from a device/session
    where Telegram didn't hand us a chat_id shouldn't wipe the one we
    already have on file).
    """
    if not chat_id:
        return
    profile, _ = Profile.objects.get_or_create(user=user)
    if not profile.chat_id:
        profile.chat_id = chat_id
        profile.save(update_fields=["chat_id"])


# ── Login (replaces api/token/ so we can save chat_id in the same request) ───

class LoginView(APIView):
    """
    POST /auth/login/
    Body: { "username": "...", "password": "...", "chat_id": "123456789" }

    chat_id is optional — omitted when the app is opened outside Telegram.
    Returns the same { access, refresh } shape as SimpleJWT's TokenObtainPairView.
    """
    permission_classes     = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        chat_id  = str(request.data.get("chat_id",  "")).strip()

        if not username or not password:
            return Response(
                {"detail": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Incorrect username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Persist chat_id only if the profile doesn't already have one
        # (idempotent — safe on every login, never clobbers an existing value)
        _save_chat_id_if_missing(user, chat_id)

        return Response(_tokens_for_user(user), status=status.HTTP_200_OK)


# ── Sign-up ───────────────────────────────────────────────────────────────────

class CreateUserView(APIView):
    """
    POST /create-user/
    Body: {
        "username":    "alice",
        "password":    "secret",
        "phone":       "+251912345678",
        "chat_id":     "123456789",   ← optional, present when opened in Mini App
        "is_delivery": false
    }
    """
    permission_classes     = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username    = str(request.data.get("username",    "")).strip()
        password    = str(request.data.get("password",    ""))
        phone       = str(request.data.get("phone",       "")).strip()
        chat_id     = str(request.data.get("chat_id",     "")).strip()
        is_delivery = bool(request.data.get("is_delivery", False))

        # ── validation ────────────────────────────────────────────────────────
        if len(username) < 2:
            return Response(
                {"username": ["Username must be at least 2 characters."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(password) < 4:
            return Response(
                {"password": ["Password must be at least 4 characters."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(phone) < 9:
            return Response(
                {"phone": ["Enter a valid phone number."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username=username).exists():
            return Response(
                {"username": ["A user with that username already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── create user + profile in one go ───────────────────────────────────
        user = User.objects.create_user(username=username, password=password)

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.phone       = phone
        profile.is_delivery = is_delivery
        profile.save(update_fields=["phone", "is_delivery"])

        # Same if-missing logic as login — on a brand-new profile this always
        # writes, but sharing the helper keeps the rule in one place.
        _save_chat_id_if_missing(user, chat_id)

        return Response(
            {"ok": True, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


# ── Phone update ──────────────────────────────────────────────────────────────

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
