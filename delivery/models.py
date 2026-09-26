from django.db import models
from django.utils.text import slugify
from django.conf import settings




class Profile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification_token = models.CharField(max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_delivery = models.BooleanField(default=False, blank=True)
    chat_id = models.CharField(max_length=500, null=True, blank=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    free_delivery_credits = models.PositiveIntegerField(default=0)

    # ── Saved delivery location ──────────────────────────────────────────
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address   = models.CharField(max_length=300, null=True, blank=True)

    # ── Giveaway milestone tracking ────────────────────────────────────
    giveaway_progress   = models.PositiveIntegerField(default=0)
    giveaway_wins_count = models.PositiveIntegerField(default=0)

    # ── Spin wheel chances ───────────────────────────────────────────────
    # +1 every time one of this user's orders is marked delivered.
    # Spent (decremented) every time they spin.
    available_spins = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name}'s Profile"


class CategoryModel(models.Model):
    name = models.CharField(max_length=50)
    deliveryTime = models.CharField(max_length=50, null=True, blank=True)
    image = models.ImageField(upload_to="category_image", null=True, blank=True)
    note = models.CharField(max_length=50, null=True, blank=True)
    is_sub_category = models.BooleanField(default=False, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    category = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_categories'
    )

    def save(self, *args, **kwargs):
        self.name = self.name.capitalize()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    image = models.ImageField(upload_to="category_images/")
    caption = models.CharField(max_length=100, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    alt = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.image}"


class ProductItem(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(max_length=500, null=True, blank=True, default="product description")
    images = models.ManyToManyField(ProductImage)
    location = models.CharField(max_length=200)
    price = models.IntegerField(default=0)
    rate = models.DecimalField(max_digits=2, decimal_places=1, default=0.0)
    date_time = models.DateTimeField(auto_now_add=True)
    is_sub_category = models.BooleanField(default=False, blank=True)
    category = models.ForeignKey(CategoryModel, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True, blank=True)
    delivery_fee = models.IntegerField(default=0)
    tags = models.JSONField(default=list, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.id:
            super().save(*args, **kwargs)
        if not self.slug:
            self.slug = slugify(f'{self.name}_{self.id}')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Order(models.Model):
    ORDER_STATUS = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE)
    special_instraction = models.TextField(max_length=1000, default="none", blank=True, null=True)
    items = models.JSONField(default=dict)
    order_number = models.CharField(max_length=20, unique=True, blank=True)
    total_price = models.IntegerField()
    shipping_address = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='pending')
    item_count = models.IntegerField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    delivery_person = models.CharField(max_length=100, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    payment_screenshot = models.ImageField(upload_to='payment_screenshots/', null=True, blank=True)

    # Guards against double-counting an order towards giveaway progress
    # (post_save fires again on every subsequent .save()).
    counted_for_giveaway = models.BooleanField(default=False)

    # Same idea, but for the spin wheel: guards against granting more than
    # one spin chance per delivered order, no matter how many times this
    # row gets re-saved after status is already 'delivered'.
    spin_chance_granted = models.BooleanField(default=False)

    PAYMENT_METHOD = [
        ('prepaid', 'Prepaid (Screenshot)'),
        ('cod', 'Pay on Delivery'),
    ]
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, default='prepaid')

    # Guards against re-sending the owner's Telegram status message every
    # time this row is re-saved while already in that status (e.g.
    # attaching a payment screenshot after delivery, or an unrelated admin
    # edit). Set only once a notification for that exact status has
    # actually been sent — see the post_save signal in signals.py.
    owner_notified_status = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"Order {self.order_number} - {self.owner.user.username}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        self.phone = self.owner.phone
        super().save(*args, **kwargs)

    def generate_order_number(self):
        import random
        import string
        return f"ORD{self.owner.id}{''.join(random.choices(string.digits, k=6))}"


class ContactUs(models.Model):
    name = models.CharField(max_length=50, null=True, blank=True)
    contact = models.CharField(max_length=100, null=True, blank=True)
    message = models.TextField(max_length=200, null=True, blank=True)
    reason = models.CharField(max_length=50, null=True, blank=True)


class WeeklySalaryRecord(models.Model):
    delivery_person = models.CharField(max_length=100, db_index=True)
    week_start      = models.DateField()
    week_end        = models.DateField()
    order_count     = models.IntegerField(default=0)
    fee_per_order   = models.IntegerField(default=0)
    total_earned    = models.IntegerField(default=0)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("delivery_person", "week_start")
        ordering        = ["-week_start"]

    def __str__(self):
        return f"{self.delivery_person} | {self.week_start} | {self.total_earned} ETB"


class ProductRating(models.Model):
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey(ProductItem, on_delete=models.CASCADE, related_name="ratings")
    score   = models.DecimalField(max_digits=2, decimal_places=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "product")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.db.models import Avg
        avg = ProductRating.objects.filter(product=self.product).aggregate(a=Avg("score"))["a"]
        ProductItem.objects.filter(pk=self.product_id).update(
            rate=round(avg, 1) if avg is not None else 0
        )

    def __str__(self):
        return f"{self.user.username} → {self.product.name}: {self.score}"


# ── Broadcasts (ads / discounts / recommendations) ──────────────────────
# An admin drafts one of these in Django admin, then runs the "Send to
# Telegram now" action to push it out. Saving a draft never sends
# anything by itself — only the action does, exactly once per broadcast.

class Broadcast(models.Model):
    TARGET_CHOICES = [
        ("all",       "Everyone"),
        ("customers", "Customers only"),
        ("delivery",  "Delivery staff only"),
    ]

    title   = models.CharField(max_length=100, help_text="Internal label only — not sent to users.")
    message = models.TextField(help_text="Telegram Markdown supported (*bold*, _italic_, etc.)")
    target  = models.CharField(max_length=20, choices=TARGET_CHOICES, default="all")

    created_at      = models.DateTimeField(auto_now_add=True)
    sent_at         = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({'sent' if self.sent_at else 'draft'})"


# ── Giveaway (milestone) ────────────────────────────────────────────────
GIVEAWAY_TARGET = 10


class Giveaway(models.Model):
    winner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="giveaway_wins", null=True)
    delivered_orders = models.ManyToManyField(Order, blank=True, related_name="giveaways")
    price = models.PositiveIntegerField(default=500)
    milestone = models.PositiveIntegerField(default=GIVEAWAY_TARGET)
    completed_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.winner} — {self.milestone} orders"


# NOTE: the post_save signal that drives Giveaway (Profile.giveaway_progress
# + auto-creating a win) lives in signals.py.


# ── Spin wheel ───────────────────────────────────────────────────────────
# Chances are earned 1:1 with delivered orders (Profile.available_spins,
# incremented by a signal in signals.py). Every prize on the wheel is a
# real DB row here — the price list — with a server-side probability so
# the wheel's odds are never something the client can see or influence.

class SpinPrize(models.Model):
    KIND_CHOICES = [
        ("coins", "Coins"),
        ("extra_spin", "Extra Spin Chance"),   # grants `spin_count` spins
        ("free_delivery", "Free Delivery"),
        ("thanks", "Thanks for Playing"),      # no reward
    ]

    key = models.SlugField(max_length=30, unique=True)
    label = models.CharField(max_length=50)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="coins")
    value = models.PositiveIntegerField(default=0)  # Birr amount — only used for kind="coins"
    spin_count = models.PositiveIntegerField(
        default=1,
        help_text="Only used for kind='extra_spin' — how many spins this prize grants."
    )
    color = models.CharField(max_length=20, default="#FF5722")
    probability = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.label} — {self.probability}%"

class SpinWheelResult(models.Model):
    """One row per spin — this is the win history."""
    STATUS_CHOICES = [
        ("not_received", "Not Received"),
        ("received", "Received"),
    ]

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="spin_results")
    prize = models.ForeignKey(
    SpinPrize, on_delete=models.SET_NULL, null=True, blank=True, related_name="results"
)
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="spin_result",
        help_text="The delivered order whose chance was spent on this spin, if any."
    )
    coins_awarded = models.IntegerField(default=0)  # snapshot of prize.value at spin time
    spins_awarded = models.PositiveIntegerField(default=0)          # NEW
    free_delivery_awarded = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_received")
    spun_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-spun_at"]

    def __str__(self):
        prize_label = self.prize.label if self.prize else "Deleted prize"
        return f"{self.profile} — {prize_label} ({self.spun_at:%Y-%m-%d})"
