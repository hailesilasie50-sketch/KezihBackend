from .models import Profile
from rest_framework.views import APIView
from django.http import Http404
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import ListAPIView, CreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .serializers import ProductItemSerializer, CategorySerializer, OrderSerializer, UserSerializer, ProfileSerializer, ContactUsSerializer, GiveawaySerializer
from .models import ProductItem, CategoryModel, Order, ContactUs, WeeklySalaryRecord, ProductRating, Giveaway
from .send_message import send_telegram_message
from environ import Env
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
import datetime
from django.utils import timezone
from .spin_wheel_engine import get_capped_weights

from rest_framework.decorators import api_view, permission_classes

from .models import SpinPrize, SpinWheelResult
from .serializers import SpinPrizeSerializer, SpinWheelResultSerializer

env = Env()


class SpinWheelStatusView(APIView):
    """
    GET → { available_spins, prizes[], history[] (mine), public_wins[] (everyone's) }

    `prizes` doubles as the wheel's segment list for the frontend — order
    matches SpinPrize.order, so segment index i on the wheel === prizes[i].
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = Profile.objects.get(user=request.user)
        prizes = SpinPrize.objects.filter(is_active=True).order_by("order")
        my_history = SpinWheelResult.objects.filter(profile=profile)[:20]
        public_wins = SpinWheelResult.objects.exclude(prize__kind="lose_all")[:10]

        return Response({
            "available_spins": profile.available_spins,
            "prizes": SpinPrizeSerializer(prizes, many=True).data,
            "history": SpinWheelResultSerializer(my_history, many=True).data,
            "public_wins": SpinWheelResultSerializer(public_wins, many=True).data,
        }, status=status.HTTP_200_OK)


class SpinWheelSpinView(APIView):
    """
    POST → spend one available spin, pick a prize server-side using each
    active SpinPrize's `probability` as a weight, log a SpinWheelResult,
    and return the winner + its wheel index so the frontend animation
    knows exactly where to land the pointer.

    The client's wheel animation is cosmetic only — this endpoint is the
    single source of truth for what was actually won.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import random

        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"error": "Profile not found"}, status=status.HTTP_404_NOT_FOUND)

        if profile.available_spins <= 0:
            return Response(
                {"error": "No spins available. Place an order to earn another chance."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prizes = list(SpinPrize.objects.filter(is_active=True).order_by("order"))
        if not prizes:
            return Response({"error": "Spin wheel is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        delivered_count = Order.objects.filter(owner=profile, status="delivered").count()
        weights, multiplier_applied, estimated_ev = get_capped_weights(prizes, delivered_count)

        if sum(weights) <= 0:
            weights = [1] * len(prizes)  # fallback: equal odds if nobody set probabilities yet

        winner = random.choices(prizes, weights=weights, k=1)[0]
        winner_index = prizes.index(winner)

        profile.available_spins -= 1

        coins_awarded = 0
        spins_awarded = 0
        free_delivery_awarded = False

        if winner.kind == "coins":
            coins_awarded = winner.value
        elif winner.kind == "extra_spin":
            spins_awarded = winner.spin_count
            profile.available_spins += winner.spin_count
        elif winner.kind == "free_delivery":
            free_delivery_awarded = True
            profile.free_delivery_credits += 1
            # kind == "thanks" → nothing awarded

        profile.save(update_fields=["available_spins", "free_delivery_credits"])

        result = SpinWheelResult.objects.create(
            profile=profile,
            prize=winner,
            coins_awarded=coins_awarded,
            spins_awarded=spins_awarded,
            free_delivery_awarded=free_delivery_awarded,
         )

        return Response({
            "prize": SpinPrizeSerializer(winner).data,
            "winning_index": winner_index,
            "available_spins": profile.available_spins,
            "result_id": result.id,
        }, status=status.HTTP_200_OK)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_telegram_chat_id(request):
    """
    POST { "chat_id": "123456789" }
    Saves the Telegram chat_id to the user's Profile if it is currently empty.
    Always returns 200 — errors are caught and logged server-side.
    """
    chat_id = str(request.data.get("chat_id", "")).strip()
    if chat_id:
        try:
            # Safer execution: get_or_create guarantees it won't crash if signals are slow
            profile, created = Profile.objects.get_or_create(user=request.user)
            if not profile.chat_id:
                profile.chat_id = chat_id
                profile.save(update_fields=["chat_id"])
        except Exception as e:
            print(f"save_telegram_chat_id error: {e}")
    return Response({"ok": True})


def _current_week_bounds():
    now        = timezone.now()
    week_start = (now - datetime.timedelta(days=now.weekday())).date()
    week_end   = week_start + datetime.timedelta(days=6)
    return week_start, week_end


class WeeklySalaryView(APIView):
    """Current ISO-week earnings for the authenticated delivery person."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        username   = request.user.username
        fee        = int(env("DELIVERY_FEE_PER_ORDER", default=100))
        week_start, week_end = _current_week_bounds()

        # Always return fresh count from Order table for current week
        count = Order.objects.filter(
            delivery_person=username,
            status="delivered",
            created_at__date__gte=week_start,
            created_at__date__lte=week_end,
        ).count()

        # Upsert so history stays in sync even on page load
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

        return Response({
            "count":      count,
            "fee":        fee,
            "total":      count * fee,
            "week_start": week_start.isoformat(),
            "week_end":   week_end.isoformat(),
        })


class SalaryHistoryView(APIView):
    """All saved weekly salary records for the authenticated delivery person."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        username = request.user.username
        records  = WeeklySalaryRecord.objects.filter(
            delivery_person=username
        ).order_by("-week_start")

        data = [
            {
                "week_start":   r.week_start.isoformat(),
                "week_end":     r.week_end.isoformat(),
                "order_count":  r.order_count,
                "fee_per_order": r.fee_per_order,
                "total_earned": r.total_earned,
            }
            for r in records
        ]
        return Response(data)


class UploadPaymentScreenshot(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request, pk):
        order = get_object_or_404(Order, pk=pk, owner__user=request.user)
        screenshot = request.FILES.get('payment_screenshot')

        if not screenshot:
            return Response(
                {'error': 'No screenshot file provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.payment_screenshot = screenshot
        order.save()
        return Response({'status': 'ok', 'order_id': order.id}, status=status.HTTP_200_OK)


class CreateUserView(CreateAPIView):
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    queryset  = User.objects.all()


class ListProduct(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ProductItemSerializer

    def get_queryset(self):
        qs = ProductItem.objects.all()
        if self.request.query_params.get('shuffle') == 'true':
            return qs.order_by('?')   # DB-level random sort
        return qs.order_by('-id')


class ListCategory(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    """
    Without params  → all categories
    ?is_sub=false   → top-level tabs (is_sub_category=False)
    ?is_sub=true&parent_id=X → restaurants under tab X (is_sub_category=True, category_id=X)
    """
    serializer_class = CategorySerializer

    def get_queryset(self):
        qs = CategoryModel.objects.all()
        is_sub = self.request.query_params.get('is_sub')
        parent_id = self.request.query_params.get('parent_id')
        if is_sub == 'false':
            qs = qs.filter(is_sub_category=False)
        elif is_sub == 'true':
            qs = qs.filter(is_sub_category=True)
            if parent_id:
                qs = qs.filter(category_id=parent_id)
        return qs.order_by('id')


class ListFilterProduct(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    """
    ?category_id=X → all ProductItems whose category FK = X (foods in a restaurant)
    """
    serializer_class = ProductItemSerializer
    def get_queryset(self):
        category_id = self.request.query_params.get('category_id')
        if not category_id:
            return ProductItem.objects.none()
        return ProductItem.objects.filter(category_id=category_id).order_by('id')


class ListFilterCategory(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    """
    ?category_id=X → sub-categories (restaurants) whose parent = X
    """
    serializer_class = CategorySerializer
    def get_queryset(self):
        category_id = self.request.query_params.get('category_id')
        if not category_id:
            return CategoryModel.objects.none()
        return CategoryModel.objects.filter(
            is_sub_category=True, category_id=category_id
        ).order_by('id')


class GetProduct(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def get(self, request, **kwargs):
        product_slug = kwargs.get("slug")
        print(product_slug)
        product = ProductItem.objects.get(slug=product_slug)
        product_serializers = ProductItemSerializer(product)
        return Response(product_serializers.data, status=status.HTTP_200_OK)


class GetOrders(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, **kwargs):
        owner = Profile.objects.get(user=request.user)
        my_orders = Order.objects.filter(owner=owner)
        order_serializer = OrderSerializer(my_orders, many=True)
        return Response(order_serializer.data, status=status.HTTP_200_OK)


class GetOrdersForMonitor(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, **kwargs):
        person = Profile.objects.get(user=request.user)
        if person.user.is_superuser:
            my_orders = Order.objects.all()
        elif person.is_delivery:
            my_orders = Order.objects.filter(status="pending")
            my_orders = my_orders.union(Order.objects.filter(status="confirmed", delivery_person=person.user.username))
            my_orders = my_orders.union(Order.objects.filter(status="delivered", delivery_person=person.user.username))
        else:
            return Response(status=status.HTTP_403_FORBIDDEN)
        orders = my_orders.order_by("-created_at")[:100]
        order_serializer = OrderSerializer(orders, many=True)
        return Response(order_serializer.data, status=status.HTTP_200_OK)


class GetDeliveryInfo(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        profile = Profile.objects.get(user=request.user)
        data = {"is_delivery": profile.is_delivery, "person": f"{profile.user.username}", "is_admin": profile.user.is_superuser}
        return Response(data=data)


class GetProfile(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer
    def get_object(self):
        try:
            return Profile.objects.get(user=self.request.user)
        except Profile.DoesNotExist:
            raise Http404("Profile does not exist")
            
    def get(self, request):
        try:
            profile = Profile.objects.get(user=request.user)
            serializer = ProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Profile.DoesNotExist:
            return Response({"error": "Profile not found"}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request):
        """Allows updating the profile location, coordinates, and phone dynamically."""
        try:
            profile = Profile.objects.get(user=request.user)
        except Profile.DoesNotExist:
            return Response({"error": "Profile not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = ProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        

class SaveToken(APIView):
    def post(self, *args, **kwargs):
        token = self.request.data.get("token")
        print("token", token)
        if self.request.user.is_authenticated:
            profile = Profile.objects.get(user=self.request.user)
            print(token)
            profile.notification_token = token
            profile.save()
            return Response(status=status.HTTP_202_ACCEPTED)
        return Response(status=status.HTTP_403_FORBIDDEN)


class GetAdminToken(APIView):
    def get(self, *args, **kwargs):
        admin = User.objects.get(username="root")
        profile = Profile.objects.get(user=admin)
        print(profile.notification_token)
        if profile:
            send_to_token(
                token=profile.notification_token,
                title="Hello from Python",
                body="This is a test notification",
                data={"key1": "value1", "key2": "value2"}
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CreateContactUsView(CreateAPIView):
    serializer_class = ContactUsSerializer
    queryset  = ContactUs.objects.all()


class CheckAuth(APIView):
    """Always 200. Manually validates JWT so a missing/expired token
    never causes a hard 401 — the frontend reads the 'authenticated' flag."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from rest_framework_simplejwt.authentication import JWTAuthentication
        try:
            result = JWTAuthentication().authenticate(request)
            if result is not None:
                user, _ = result
                return Response({"authenticated": True, "username": user.username}, status=status.HTTP_200_OK)
        except Exception:
            pass
        return Response({"authenticated": False}, status=status.HTTP_200_OK)


class RateProductView(APIView):
    """
    GET  /rate-product/<slug>/  → returns the authenticated user's existing rating (or null)
    POST /rate-product/<slug>/  → creates or updates the user's rating, returns new avg
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, slug):
        product = get_object_or_404(ProductItem, slug=slug)
    
        if not request.user.is_authenticated:
            return Response({"score": None, "product_rate": float(product.rate)})
    
        try:
            rating = ProductRating.objects.get(user=request.user, product=product)
            return Response({"score": float(rating.score), "product_rate": float(product.rate)})
        except ProductRating.DoesNotExist:
            return Response({"score": None, "product_rate": float(product.rate)})

    def post(self, request, slug):
        product = get_object_or_404(ProductItem, slug=slug)
        score = request.data.get("score")

        if score is None:
            return Response({"error": "score is required"}, status=status.HTTP_400_BAD_REQUEST)

        score = float(score)
        if not (0.5 <= score <= 5.0):
            return Response({"error": "score must be between 0.5 and 5"}, status=status.HTTP_400_BAD_REQUEST)

        rating, created = ProductRating.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={"score": score},
        )
        product.refresh_from_db()
        return Response({
            "score":        float(rating.score),
            "product_rate": float(product.rate),
            "created":      created,
        }, status=status.HTTP_200_OK)


# views.py - Append to your views

class GiveawayDashboardView(APIView):
    """
    Public + personalized giveaway dashboard.

    - Always returns the 5 most recent winners (public feed — anyone can see
      who's been winning).
    - If the request carries a valid JWT, also returns *that* customer's own
      progress toward their next free item (out of GIVEAWAY_TARGET orders).
      Anonymous visitors get `progress: null` and the frontend shows a
      "sign in to track your progress" prompt instead.

    Manually authenticates (like CheckAuth) instead of using
    permission_classes=[IsAuthenticated] so this endpoint never 401s — it
    just degrades to the public-only view.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from rest_framework_simplejwt.authentication import JWTAuthentication

        profile = None
        try:
            result = JWTAuthentication().authenticate(request)
            if result is not None:
                user, _ = result
                profile = Profile.objects.filter(user=user).first()
        except Exception:
            pass

        progress_data = None
        if profile:
            progress_data = {
                "progress": profile.giveaway_progress,
                "target": 10,
                "total_wins": profile.giveaway_wins_count,
            }

        history = Giveaway.objects.order_by("-completed_at")[:5]
        history_data = GiveawaySerializer(history, many=True).data

        return Response({
            "progress": progress_data,
            "history": history_data,
            "rule_text": (
                "Every 10 orders you complete earns you a free item! "
                "Pick anything under 500 Birr for free, or add your own "
                "money towards something pricier."
            ),
        }, status=status.HTTP_200_OK)
