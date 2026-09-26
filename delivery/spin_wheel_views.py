"""
Spin wheel API views. Kept in their own module so they can be dropped into
your project and wired up in urls.py without touching your existing
views.py.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, Profile, SpinWheelResult, SPIN_WHEEL_PRIZES, SPIN_COOLDOWN_HOURS
from .serializers import SpinWheelResultSerializer
from .spin_wheel import get_orders_since_last_spin, get_spin_weights, pick_prize


def get_profile(request):
    """
    Profile.user has no related_name, so request.user.profile isn't a
    valid accessor (Django defaults to profile_set for a plain FK). Look
    it up directly instead — matches however your other views already do
    it, just made explicit here so this module doesn't assume a shortcut
    that isn't wired up.
    """
    return Profile.objects.get(user=request.user)


class SpinWheelStatusView(APIView):
    """GET current odds, orders since last spin, and whether the user can
    spin right now (cooldown check)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_profile(request)
        orders_since_last_spin = get_orders_since_last_spin(profile)
        weights = get_spin_weights(orders_since_last_spin)

        last_spin = SpinWheelResult.objects.filter(profile=profile).order_by("-spun_at").first()
        can_spin, next_spin_at = True, None
        if last_spin:
            unlock_at = last_spin.spun_at + timedelta(hours=SPIN_COOLDOWN_HOURS)
            if timezone.now() < unlock_at:
                can_spin, next_spin_at = False, unlock_at

        return Response({
            "orders_since_last_spin": orders_since_last_spin,
            "prizes": SPIN_WHEEL_PRIZES,
            "weights": weights,
            "can_spin": can_spin,
            "next_spin_at": next_spin_at,
        })


class SpinWheelSpinView(APIView):
    """POST to spin. The server picks the winner server-side — the
    frontend only animates to whatever result it's given."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = get_profile(request)

        last_spin = SpinWheelResult.objects.filter(profile=profile).order_by("-spun_at").first()
        if last_spin:
            unlock_at = last_spin.spun_at + timedelta(hours=SPIN_COOLDOWN_HOURS)
            if timezone.now() < unlock_at:
                return Response(
                    {"detail": "You've already spun today. Come back later!", "next_spin_at": unlock_at},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        orders_since_last_spin = get_orders_since_last_spin(profile)
        total_delivered = Order.objects.filter(owner=profile, status="delivered").count()

        prize, weights = pick_prize(orders_since_last_spin)
        result = SpinWheelResult.objects.create(
            profile=profile,
            prize_key=prize["key"],
            prize_label=prize["label"],
            prize_value=prize["value"],
            # Baseline for the *next* spin's "orders since last spin" count.
            order_count_at_spin=total_delivered,
        )
        return Response({
            "result": SpinWheelResultSerializer(result).data,
            "weights_used": weights,
        })


class SpinWheelHistoryView(APIView):
    """Public-ish list of recent wins (excludes 'thanks' results)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SpinWheelResult.objects.exclude(prize_key="thanks").select_related("profile", "profile__user")[:20]
        return Response(SpinWheelResultSerializer(qs, many=True).data)
