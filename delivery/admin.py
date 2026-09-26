from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import AdminSite
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count, Sum, Q
from django.utils import timezone
from .models import (Profile, CategoryModel, ProductItem, ProductImage,
                     Order, ContactUs, WeeklySalaryRecord, ProductRating,
                     SpinPrize, SpinWheelResult, Broadcast)
from .send_message import send_telegram_message

@admin.register(WeeklySalaryRecord)
class WeeklySalaryRecordAdmin(admin.ModelAdmin):
    list_display = ["delivery_person", "week_start", "week_end",
                    "order_count", "fee_per_order", "total_earned"]
    list_filter  = ["delivery_person"]
    ordering     = ["-week_start"]

@admin.register(ProductRating)
class ProductRatingAdmin(admin.ModelAdmin):
    list_display  = ["user", "product", "score", "created_at"]
    search_fields = ["user__username", "product__name"]
    list_filter   = ["score"]


# ──────────────────────────────────────────────────────────────────────────────
#  Custom Admin Site
# ──────────────────────────────────────────────────────────────────────────────

class LiyuDeliveryAdminSite(AdminSite):
    site_header  = mark_safe(
        '<span style="font-family:\'Playfair Display\',serif;letter-spacing:1px;">'
        '🚀 Kezih Delivery</span>'
    )
    site_title   = "Kezih Delivery Admin"
    index_title  = mark_safe(
        '<span style="font-family:\'Playfair Display\',serif;">'
        'Welcome to Kezih Delivery Dashboard</span>'
    )

    def each_context(self, request):
        ctx = super().each_context(request)
        ctx["custom_css"] = GLOBAL_CSS          # injected via base_site.html override or inline
        return ctx


# Use the default admin site but brand it
admin.site.site_header  = mark_safe(
    '<span style="font-family:\'Playfair Display\',Georgia,serif;'
    'font-size:22px;font-weight:700;letter-spacing:1.5px;color:#fff;">'
    '🚀 Kezih Delivery</span>'
)
admin.site.site_title   = "Kezih Delivery"
admin.site.index_title  = "Operations Dashboard"


# ──────────────────────────────────────────────────────────────────────────────
#  Shared style helpers
# ──────────────────────────────────────────────────────────────────────────────

PALETTE = {
    "primary":   "#1a1a2e",
    "accent":    "#e94560",
    "success":   "#00b894",
    "warning":   "#fdcb6e",
    "info":      "#0984e3",
    "muted":     "#636e72",
    "surface":   "#f8f9ff",
    "card":      "#ffffff",
}

STATUS_COLORS = {
    "pending":   ("#fdcb6e", "#2d3436"),
    "confirmed": ("#0984e3", "#ffffff"),
    "delivered": ("#00b894", "#ffffff"),
    "cancelled": ("#e94560", "#ffffff"),
}


def _badge(text, bg, fg="#fff", radius="20px"):
    return format_html(
        '<span style="background:{};color:{};padding:3px 12px;border-radius:{};'
        'font-size:11px;font-weight:700;letter-spacing:.5px;display:inline-block;">'
        '{}</span>',
        bg, fg, radius, text
    )


def _card(inner_html, border_color=PALETTE["accent"]):
    return format_html(
        '<div style="background:#fff;border-radius:12px;padding:20px 24px;'
        'border-left:4px solid {};box-shadow:0 2px 12px rgba(0,0,0,.08);">'
        '{}</div>',
        border_color, mark_safe(inner_html)
    )


def _stat_row(*stats):
    """Render a row of stat boxes. Each stat is (value, label, color)."""
    boxes = "".join(
        f'<div style="text-align:center;padding:12px 20px;background:#f8f9ff;'
        f'border-radius:10px;min-width:110px;">'
        f'<div style="font-size:28px;font-weight:800;color:{c};">{v}</div>'
        f'<div style="font-size:12px;color:#636e72;margin-top:2px;">{l}</div>'
        f'</div>'
        for v, l, c in stats
    )
    return format_html(
        '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:4px;">{}</div>',
        mark_safe(boxes)
    )


def _thumb(url, size=64):
    if url:
        return format_html(
            '<img src="{}" style="width:{}px;height:{}px;object-fit:cover;'
            'border-radius:8px;border:2px solid #eee;" />',
            url, size, size
        )
    return format_html(
        '<div style="width:{0}px;height:{0}px;background:#f0f0f0;border-radius:8px;'
        'display:flex;align-items:center;justify-content:center;'
        'color:#bbb;font-size:10px;border:1px dashed #ddd;">No img</div>',
        size
    )


# ──────────────────────────────────────────────────────────────────────────────
#  Profile Admin
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display  = ["name_display", "username_display", "phone", "role_badge", "chat_id_short"]
    search_fields = ["name", "user__username", "user__email", "phone", "chat_id","latitude","longitude","address"]
    list_filter   = ["is_delivery"]
    ordering      = ["name"]

    fieldsets = [
        ("👤 Identity", {
            "fields": ["user", "name", "phone"]
        }),
        ("📦 Delivery & Notifications", {
            "fields": ["is_delivery", "notification_token", "chat_id","latitude","longitude","address"]
        }),
    ]

    def name_display(self, obj):
        return format_html(
            '<strong style="color:#1a1a2e;">{}</strong>',
            obj.name or "—"
        )
    name_display.short_description = "Name"

    def username_display(self, obj):
        return format_html(
            '<span style="color:#0984e3;">@{}</span>',
            obj.user.username
        )
    username_display.short_description = "Username"

    def role_badge(self, obj):
        if obj.is_delivery:
            return _badge("🛵 Rider", PALETTE["success"])
        return _badge("🛒 Customer", PALETTE["info"])
    role_badge.short_description = "Role"

    def chat_id_short(self, obj):
        if obj.chat_id:
            return format_html(
                '<code style="background:#f0f0f0;padding:2px 6px;border-radius:4px;font-size:11px;">{}</code>',
                obj.chat_id[:20] + ("…" if len(obj.chat_id) > 20 else "")
            )
        return "—"
    chat_id_short.short_description = "Chat ID"


# ──────────────────────────────────────────────────────────────────────────────
#  Category Admin
# ──────────────────────────────────────────────────────────────────────────────

class SubCategoryInline(admin.TabularInline):
    model  = CategoryModel
    fk_name = "category"
    extra  = 0
    fields = ["name", "deliveryTime", "is_sub_category", "note", "image", "location", "phone"]
    verbose_name        = "Sub-category"
    verbose_name_plural = "Sub-categories"
    show_change_link    = True


@admin.register(CategoryModel)
class CategoryModelAdmin(admin.ModelAdmin):
    list_display  = ["name_display", "deliveryTime", "parent_display", "subcategory_count", "note", "image_thumb"]
    search_fields = ["name", "deliveryTime", "note"]
    list_filter   = ["is_sub_category", "deliveryTime"]
    inlines       = [SubCategoryInline]
    ordering      = ["name"]

    fieldsets = [
        ("🗂️ Category Details", {
            "fields": ["name", "deliveryTime", "note", "image"]
        }),
        ("🔗 Hierarchy", {
            "fields": ["is_sub_category", "category"]
        }),
        ("📍 Location & Contact", {                          # ← add this section
            "fields": ["latitude", "longitude", "location", "phone"]
        }),
    ]

    def name_display(self, obj):
        indent = "↳ " if obj.is_sub_category else ""
        return format_html(
            '<span style="font-weight:600;color:#1a1a2e;">{}{}</span>',
            indent, obj.name
        )
    name_display.short_description = "Category Name"

    def parent_display(self, obj):
        if obj.category:
            return format_html(
                '<span style="color:#0984e3;">{}</span>', obj.category.name
            )
        return format_html('<span style="color:#b2bec3;">Root</span>')
    parent_display.short_description = "Parent"

    def subcategory_count(self, obj):
        count = obj.sub_categories.count()
        if count:
            return _badge(f"{count} subs", PALETTE["info"])
        return "—"
    subcategory_count.short_description = "Sub-categories"

    def image_thumb(self, obj):
        return _thumb(obj.image.url if obj.image else None, 44)
    image_thumb.short_description = "Image"


# ──────────────────────────────────────────────────────────────────────────────
#  ProductImage Admin
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display  = ["preview", "caption", "alt", "order", "created_at"]
    search_fields = ["caption", "alt"]
    ordering      = ["order", "created_at"]
    list_editable = ["order"]

    fieldsets = [
        ("🖼️ Image", {
            "fields": ["image", "caption", "alt", "order"]
        }),
    ]

    def preview(self, obj):
        return _thumb(obj.image.url if obj.image else None, 56)
    preview.short_description = "Preview"


# ──────────────────────────────────────────────────────────────────────────────
#  ProductItem Admin
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(ProductItem)
class ProductItemAdmin(admin.ModelAdmin):
    list_display   = ["name_display", "category", "price_display", "rate_stars",
                      "delivery_fee_display", "location", "date_time"]
    search_fields  = ["name", "category__name", "location", "slug", "tags"]
    list_filter    = ["category", "is_sub_category", "date_time"]
    autocomplete_fields = ["category"]
    filter_horizontal   = ["images"]
    readonly_fields = ["slug", "date_time", "images_gallery"]

    fieldsets = [
        ("📦 Product Info", {
            "fields": ["name", "description", "category", "is_sub_category", "tags"]
        }),
        ("💰 Pricing", {
            "fields": ["price", "delivery_fee"]
        }),
        ("📍 Location & Rating", {
            "fields": ["location", "rate"]
        }),
        ("🖼️ Images", {
            "fields": ["images", "images_gallery"]
        }),
        ("🔗 Meta", {
            "fields": ["slug", "date_time"],
            "classes": ["collapse"]
        }),
    ]

    def name_display(self, obj):
        return format_html('<strong style="color:#1a1a2e;">{}</strong>', obj.name)
    name_display.short_description = "Product"

    def price_display(self, obj):
        return format_html(
            '<span style="font-weight:700;color:#00b894;">{} ETB</span>',
            f"{obj.price:,}"
        )
    price_display.short_description = "Price"

    def delivery_fee_display(self, obj):
        if obj.delivery_fee:
            return format_html(
                '<span style="color:#e17055;">+{} ETB</span>', f"{obj.delivery_fee:,}"
            )
        return _badge("Free", PALETTE["success"])
    delivery_fee_display.short_description = "Delivery Fee"

    def rate_stars(self, obj):
        filled = int(obj.rate)
        half   = (float(obj.rate) - filled) >= 0.5
        stars  = "★" * filled + ("½" if half else "") + "☆" * (5 - filled - (1 if half else 0))
        return format_html(
            '<span style="color:#fdcb6e;letter-spacing:2px;" title="{}/5">{}</span>',
            obj.rate, stars
        )
    rate_stars.short_description = "Rating"

    def images_gallery(self, obj):
        imgs = obj.images.all()
        if not imgs:
            return "No images attached."
        thumbs = "".join(
            f'<img src="{i.image.url}" style="width:70px;height:70px;object-fit:cover;'
            f'border-radius:8px;border:2px solid #eee;margin:4px;" title="{i.caption or i.alt or ""}" />'
            for i in imgs if i.image
        )
        return format_html('<div style="display:flex;flex-wrap:wrap;gap:4px;">{}</div>', mark_safe(thumbs))
    images_gallery.short_description = "Image Gallery"


# ──────────────────────────────────────────────────────────────────────────────
#  Order Admin
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = [
        "order_number_display", "owner_display", "status_badge",
        "item_count", "total_price_display", "delivery_person_display",
        "address_short", "created_at"
    ]
    list_filter   = ["status", "created_at", "shipping_address"]
    search_fields = ["order_number", "owner__user__username", "owner__name",
                     "shipping_address", "delivery_person", "phone"]
    date_hierarchy = "created_at"
    ordering       = ["-created_at"]

    readonly_fields = [
        "order_number", "created_at", "item_count", "total_price",
        "phone", "order_summary_card", "items_detail_card", "map_link"
    ]

    fieldsets = [
        ("📋 Order Info", {
            "fields": [
                "order_number", "owner", "status", "special_instraction",
                "created_at"
            ]
        }),
        ("📊 Summary", {
            "fields": ["order_summary_card"]
        }),
        ("🛍️ Items", {
            "fields": ["items_detail_card"]
        }),
        ("🚚 Delivery", {
            "fields": [
                "shipping_address", "phone", "delivery_person",
                "latitude", "longitude", "map_link"
            ]
        }),
        ("💳 Payment", {
            "fields": ["payment_screenshot"]
        }),
        ("⚙️ Raw Data", {
            "fields": ["items", "item_count", "total_price"],
            "classes": ["collapse"]
        }),
    ]

    # ── List display helpers ──────────────────────────────────────────────────

    def order_number_display(self, obj):
        return format_html(
            '<code style="background:#f0f4ff;color:#0984e3;padding:3px 8px;'
            'border-radius:6px;font-weight:700;font-size:12px;">{}</code>',
            obj.order_number
        )
    order_number_display.short_description = "Order #"

    def owner_display(self, obj):
        return format_html(
            '<div style="line-height:1.3;">'
            '<strong style="color:#1a1a2e;">{}</strong><br>'
            '<small style="color:#636e72;">@{}</small></div>',
            obj.owner.name or "—",
            obj.owner.user.username
        )
    owner_display.short_description = "Customer"

    def status_badge(self, obj):
        bg, fg = STATUS_COLORS.get(obj.status, ("#999", "#fff"))
        label  = obj.get_status_display()
        icons  = {"pending": "⏳", "confirmed": "✅", "delivered": "📦", "cancelled": "❌"}
        icon   = icons.get(obj.status, "")
        return _badge(f"{icon} {label}", bg, fg)
    status_badge.short_description = "Status"
    status_badge.allow_tags = True

    def total_price_display(self, obj):
        return format_html(
            '<strong style="color:#00b894;font-size:14px;">{} ETB</strong>',
            f"{obj.total_price:,}"
        )
    total_price_display.short_description = "Total"

    def delivery_person_display(self, obj):
        if obj.delivery_person:
            return format_html(
                '<span style="color:#6c5ce7;">🛵 {}</span>', obj.delivery_person
            )
        return format_html('<span style="color:#b2bec3;">Unassigned</span>')
    delivery_person_display.short_description = "Rider"

    def address_short(self, obj):
        addr = obj.shipping_address
        return format_html(
            '<span title="{}">{}</span>',
            addr,
            (addr[:22] + "…") if len(addr) > 22 else addr
        )
    address_short.short_description = "Address"

    # ── Detail view helpers ───────────────────────────────────────────────────

    def order_summary_card(self, obj):
        # Fallback values for new (unsaved) instances
        item_count = obj.item_count or 0
        total_price = obj.total_price or 0
        shipping_address = obj.shipping_address or "Not specified yet"
        
        items = self._get_items(obj)
        total_qty = sum(i.get("quantity", 1) for i in items)

        html = (
            f'<div style="display:flex;flex-wrap:wrap;gap:12px;'
            f'padding:20px;background:{PALETTE["surface"]};border-radius:12px;">'
            f'<div style="text-align:center;padding:14px 22px;background:#fff;border-radius:10px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.07);min-width:110px;">'
            f'<div style="font-size:32px;font-weight:800;color:{PALETTE["accent"]};">'
            f'{item_count}</div>'
            f'<div style="font-size:11px;color:{PALETTE["muted"]};margin-top:2px;">Products</div></div>'

            f'<div style="text-align:center;padding:14px 22px;background:#fff;border-radius:10px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.07);min-width:110px;">'
            f'<div style="font-size:32px;font-weight:800;color:{PALETTE["info"]};">'
            f'{total_qty}</div>'
            f'<div style="font-size:11px;color:{PALETTE["muted"]};margin-top:2px;">Total Qty</div></div>'

            f'<div style="text-align:center;padding:14px 22px;background:#fff;border-radius:10px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.07);min-width:110px;">'
            f'<div style="font-size:32px;font-weight:800;color:{PALETTE["success"]};">'
            f'{total_price:,}</div>'
            f'<div style="font-size:11px;color:{PALETTE["muted"]};margin-top:2px;">ETB Total</div></div>'

            f'<div style="text-align:center;padding:14px 22px;background:#fff;border-radius:10px;'
            f'box-shadow:0 2px 8px rgba(0,0,0,.07);min-width:140px;">'
            f'<div style="font-size:16px;font-weight:700;color:#1a1a2e;">'
            f'{shipping_address}</div>'
            f'<div style="font-size:11px;color:{PALETTE["muted"]};margin-top:2px;">📍 Delivery Address</div></div>'
            f'</div>'
        )
        return format_html(html)
    order_summary_card.short_description = "📊 Order Summary"

    def items_detail_card(self, obj):
        items = self._get_items(obj)
        if not items:
            return format_html(
                '<div style="text-align:center;color:#b2bec3;padding:30px;'
                'background:#f9f9f9;border-radius:10px;">No items found.</div>'
            )

        rows = ""
        for idx, item in enumerate(items, 1):
            img_url      = (item.get("images") or [{}])[0].get("image", "")
            name         = item.get("name", "Unknown")
            category     = (item.get("category") or {}).get("name", "—")
            location     = item.get("location", "—")
            price        = item.get("price", 0)
            qty          = item.get("quantity", 1)
            item_total   = price * qty
            desc         = item.get("description", "")[:110]
            if len(item.get("description", "")) > 110:
                desc += "…"

            img_html = (
                f'<img src="{img_url}" style="width:90px;height:90px;object-fit:cover;'
                f'border-radius:10px;border:2px solid #eee;flex-shrink:0;" />'
                if img_url else
                f'<div style="width:90px;height:90px;background:#f0f0f0;border-radius:10px;'
                f'display:flex;align-items:center;justify-content:center;color:#ccc;'
                f'font-size:11px;flex-shrink:0;border:1px dashed #ddd;">No Image</div>'
            )

            rows += (
                f'<div style="display:flex;gap:18px;padding:18px 20px;background:#fff;'
                f'border-radius:12px;border:1px solid #e8eaf0;'
                f'box-shadow:0 1px 6px rgba(0,0,0,.06);margin-bottom:14px;">'
                f'{img_html}'
                f'<div style="flex-grow:1;">'
                f'  <div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'    <div>'
                f'      <div style="font-size:16px;font-weight:700;color:#1a1a2e;">{name}</div>'
                f'      <div style="font-size:12px;color:#636e72;margin-top:3px;">'
                f'        🗂️ {category}&nbsp;&nbsp;📍 {location}'
                f'      </div>'
                f'    </div>'
                f'    <span style="background:#e8f4fd;color:#0984e3;padding:3px 10px;'
                f'    border-radius:20px;font-size:11px;font-weight:700;">#{idx}</span>'
                f'  </div>'
                f'  <div style="display:flex;gap:16px;flex-wrap:wrap;margin:10px 0;'
                f'  padding:10px 14px;background:#f8f9ff;border-radius:8px;">'
                f'    <div><div style="font-size:10px;color:#636e72;text-transform:uppercase;'
                f'    letter-spacing:.5px;">Unit Price</div>'
                f'    <div style="font-size:18px;font-weight:700;color:#1a1a2e;">{price:,} ETB</div></div>'
                f'    <div><div style="font-size:10px;color:#636e72;text-transform:uppercase;'
                f'    letter-spacing:.5px;">Qty</div>'
                f'    <div style="font-size:18px;font-weight:700;color:#1a1a2e;">{qty}</div></div>'
                f'    <div><div style="font-size:10px;color:#636e72;text-transform:uppercase;'
                f'    letter-spacing:.5px;">Subtotal</div>'
                f'    <div style="font-size:18px;font-weight:700;color:{PALETTE["success"]};">'
                f'    {item_total:,} ETB</div></div>'
                f'  </div>'
                f'  <div style="font-size:12px;color:#636e72;line-height:1.6;">{desc}</div>'
                f'</div>'
                f'</div>'
            )

        return format_html(
            '<div style="max-width:900px;">{}</div>', mark_safe(rows)
        )
    items_detail_card.short_description = "🛍️ Order Items"

    def map_link(self, obj):
        if obj.latitude and obj.longitude:
            url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
            return format_html(
                '<a href="{}" target="_blank" style="display:inline-flex;align-items:center;'
                'gap:6px;background:#34a853;color:#fff;padding:6px 14px;border-radius:8px;'
                'text-decoration:none;font-size:13px;font-weight:600;">'
                '🗺️ View on Google Maps</a>',
                url
            )
        return format_html('<span style="color:#b2bec3;">No coordinates</span>')
    map_link.short_description = "📍 Map"

    # ── Helper ────────────────────────────────────────────────────────────────

    def _get_items(self, obj):
        try:
            data = obj.items
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except Exception:
            pass
        return []


# ──────────────────────────────────────────────────────────────────────────────
#  ContactUs Admin
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(ContactUs)
class ContactUsAdmin(admin.ModelAdmin):
    list_display  = ["name_display", "contact_display", "message_preview"]
    search_fields = ["name", "contact", "message",'reason']
    ordering      = ["-id"]

    readonly_fields = ["message_formatted"]

    fieldsets = [
        ("📬 Sender", {
            "fields": ["name", "contact",'reason']
        }),
        ("💬 Message", {
            "fields": ["message_formatted", "message"]
        }),
    ]

    def name_display(self, obj):
        return format_html(
            '<strong style="color:#1a1a2e;">{}</strong>',
            obj.name or "Anonymous"
        )
    name_display.short_description = "Name"

    def contact_display(self, obj):
        if obj.contact:
            return format_html(
                '<a href="tel:{}" style="color:#0984e3;text-decoration:none;">📞 {}</a>',
                obj.contact, obj.contact
            )
        return "—"
    contact_display.short_description = "Contact"

    def message_preview(self, obj):
        msg = obj.message or ""
        preview = (msg[:80] + "…") if len(msg) > 80 else msg
        return format_html(
            '<span style="color:#636e72;font-style:italic;">{}</span>', preview
        )
    message_preview.short_description = "Message"

    def message_formatted(self, obj):
        return format_html(
            '<div style="background:#f8f9ff;padding:16px 20px;border-radius:10px;'
            'border-left:4px solid #0984e3;font-size:14px;line-height:1.7;'
            'color:#2d3436;white-space:pre-wrap;">{}</div>',
            obj.message or "—"
        )
    message_formatted.short_description = "Full Message"


# ──────────────────────────────────────────────────────────────────────────────
#  SpinPrize Admin — the wheel's price list
# ──────────────────────────────────────────────────────────────────────────────

SPIN_KIND_ICONS = {
    "coins":         "🪙",
    "extra_spin":    "🎟️",
    "free_delivery": "🚚",
    "thanks":        "🙏",
}


@admin.register(SpinPrize)
class SpinPrizeAdmin(admin.ModelAdmin):
    """
    This *is* the wheel — SpinWheelStatusView serves these rows straight to
    the frontend in `order`, and SpinWheelSpinView weighs the random draw by
    `probability`. Edit here, no deploy needed.
    """
    list_display  = ["order", "swatch", "label", "kind_badge", "value_display",
                      "probability_display", "active_badge"]
    list_display_links = ["label"]
    list_editable = ["order"]
    list_filter   = ["kind", "is_active"]
    search_fields = ["key", "label"]
    ordering      = ["order", "id"]

    fieldsets = [
        ("🎡 Prize", {
            "fields": ["key", "label", "kind", "value", "color"]
        }),
        ("⚖️ Odds & Placement", {
            "fields": ["probability", "order", "is_active"],
            "description": (
                "Probability is a relative weight, not a strict percentage — "
                "it doesn't need to sum to 100 across all prizes. "
                "'Order' controls the prize's position on the wheel and must "
                "stay in sync with however the frontend numbers its segments."
            )
        }),
    ]

    def swatch(self, obj):
        return format_html(
            '<div style="width:22px;height:22px;border-radius:6px;background:{};'
            'border:1px solid rgba(0,0,0,.15);"></div>',
            obj.color
        )
    swatch.short_description = "Color"

    def kind_badge(self, obj):
        icon = SPIN_KIND_ICONS.get(obj.kind, "")
        colors = {
            "coins":      PALETTE["success"],
            "extra_spin": PALETTE["info"],
            "lose_all":   PALETTE["accent"],
        }
        return _badge(f"{icon} {obj.get_kind_display()}", colors.get(obj.kind, PALETTE["muted"]))
    kind_badge.short_description = "Kind"

    def value_display(self, obj):
        if obj.kind == "coins":
            return format_html('<strong style="color:{};">{} ETB</strong>', PALETTE["success"], f"{obj.value:,}")
        if obj.kind == "extra_spin":
            suffix = "s" if obj.spin_count != 1 else ""
            return format_html('<strong style="color:{};">+{} spin{}</strong>', PALETTE["info"], obj.spin_count, suffix)
        if obj.kind == "free_delivery":
            return format_html('<strong style="color:{};">Free delivery</strong>', PALETTE["info"])
        return format_html('<span style="color:#b2bec3;">—</span>')

    def probability_display(self, obj):
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            PALETTE["info"], obj.probability
        )
    probability_display.short_description = "Weight"

    def active_badge(self, obj):
        if obj.is_active:
            return _badge("On Wheel", PALETTE["success"])
        return _badge("Hidden", PALETTE["muted"])
    active_badge.short_description = "Status"


# ──────────────────────────────────────────────────────────────────────────────
#  SpinWheelResult Admin — win history (read-only ledger)
# ──────────────────────────────────────────────────────────────────────────────

@admin.register(SpinWheelResult)
class SpinWheelResultAdmin(admin.ModelAdmin):
    """
    A log of real spins, written by SpinWheelSpinView. Nothing here should be
    hand-created — only `status` is editable, so ops can flip a coin prize to
    'Received' once it's actually been paid out to the customer.
    """
    list_display  = ["spun_at", "winner_display", "prize_badge",
                      "coins_awarded_display", "status_badge", "order_link"]
    list_filter   = ["status", "prize"]
    search_fields = ["profile__name", "profile__user__username", "prize__label"]
    date_hierarchy = "spun_at"
    ordering       = ["-spun_at"]

    readonly_fields = ["profile", "prize", "order", "coins_awarded", "spun_at"]

    fieldsets = [
        ("🎰 Spin", {
            "fields": ["profile", "prize", "coins_awarded", "spun_at"]
        }),
        ("🚚 Source Order", {
            "fields": ["order"]
        }),
        ("📦 Fulfillment", {
            "fields": ["status"]
        }),
    ]

    def has_add_permission(self, request):
        # Results only ever come from a real spin via the API.
        return False

    def winner_display(self, obj):
        return format_html(
            '<div style="line-height:1.3;">'
            '<strong style="color:#1a1a2e;">{}</strong><br>'
            '<small style="color:#636e72;">@{}</small></div>',
            obj.profile.name or "—",
            obj.profile.user.username
        )
    winner_display.short_description = "Winner"

    def prize_badge(self, obj):
        icon = SPIN_KIND_ICONS.get(obj.prize.kind, "") if obj.prize else ""
        label = obj.prize.label if obj.prize else "Deleted prize"
        color = obj.prize.color if obj.prize else PALETTE["muted"]
        return _badge(f"{icon} {label}", color)
    prize_badge.short_description = "Prize"

    def coins_awarded_display(self, obj):
        if not obj.coins_awarded:
            return format_html('<span style="color:#b2bec3;">—</span>')
        return format_html(
            '<strong style="color:{};">+{} ETB</strong>',
            PALETTE["success"], f"{obj.coins_awarded:,}"
        )
    coins_awarded_display.short_description = "Coins"

    def status_badge(self, obj):
        if obj.status == "received":
            return _badge("✅ Received", PALETTE["success"])
        return _badge("⏳ Not Received", PALETTE["warning"], fg="#2d3436")
    status_badge.short_description = "Fulfillment"

    def order_link(self, obj):
        if not obj.order:
            return format_html('<span style="color:#b2bec3;">—</span>')
        url = reverse("admin:delivery_order_change", args=[obj.order.pk])
        return format_html(
            '<a href="{}" style="color:#0984e3;text-decoration:none;">📋 {}</a>',
            url, obj.order.order_number
        )
    order_link.short_description = "Granting Order"


# ──────────────────────────────────────────────────────────────────────────────
#  Broadcast Admin — ads / discounts / recommendations sent to Telegram
# ──────────────────────────────────────────────────────────────────────────────

BROADCAST_TARGET_COLORS = {
    "all":       (PALETTE["info"],    "#ffffff"),
    "customers": (PALETTE["success"], "#ffffff"),
    "delivery":  (PALETTE["warning"], "#2d3436"),
}


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    """
    Draft an ad / discount / recommendation here, then select it in the
    list and run "Send to Telegram now". Nothing goes out just from
    saving — only the action sends, and it skips anything already sent
    so re-running it on an old broadcast is always safe.
    """
    list_display    = ["title", "target_badge", "message_preview", "status_badge", "recipient_count", "created_at"]
    list_filter     = ["target"]
    search_fields   = ["title", "message"]
    ordering        = ["-created_at"]
    readonly_fields = ["sent_at", "recipient_count"]
    actions         = ["send_broadcast"]

    fieldsets = [
        ("📣 Message", {
            "fields": ["title", "message", "target"],
            "description": (
                "Telegram Markdown is supported — *bold*, _italic_, etc. "
                "This is a draft until you run the send action below."
            ),
        }),
        ("📊 Delivery", {
            "fields": ["sent_at", "recipient_count"],
        }),
    ]

    def target_badge(self, obj):
        bg, fg = BROADCAST_TARGET_COLORS.get(obj.target, (PALETTE["muted"], "#fff"))
        return _badge(obj.get_target_display(), bg, fg=fg)
    target_badge.short_description = "Audience"

    def message_preview(self, obj):
        preview = (obj.message[:80] + "…") if len(obj.message) > 80 else obj.message
        return format_html(
            '<span style="color:#636e72;font-style:italic;">{}</span>', preview
        )
    message_preview.short_description = "Message"

    def status_badge(self, obj):
        if obj.sent_at:
            return _badge("✅ Sent", PALETTE["success"])
        return _badge("📝 Draft", PALETTE["muted"])
    status_badge.short_description = "Status"

    @admin.action(description="📤 Send to Telegram now")
    def send_broadcast(self, request, queryset):
        already_sent_count = 0
        newly_sent_count   = 0
        total_recipients   = 0

        for broadcast in queryset:
            if broadcast.sent_at:
                already_sent_count += 1
                continue

            profiles = Profile.objects.exclude(chat_id__isnull=True).exclude(chat_id="")
            if broadcast.target == "customers":
                profiles = profiles.filter(is_delivery=False)
            elif broadcast.target == "delivery":
                profiles = profiles.filter(is_delivery=True)

            sent_count = 0
            for profile in profiles:
                try:
                    send_telegram_message(broadcast.message, profile.chat_id, use_portal_bot=False)
                    sent_count += 1
                except Exception as e:
                    print(f"Broadcast send error (broadcast {broadcast.pk}, profile {profile.pk}): {e}")

            broadcast.sent_at = timezone.now()
            broadcast.recipient_count = sent_count
            broadcast.save(update_fields=["sent_at", "recipient_count"])

            newly_sent_count += 1
            total_recipients += sent_count

        if newly_sent_count:
            self.message_user(
                request,
                f"Sent {newly_sent_count} broadcast(s) to {total_recipients} recipient(s) total.",
                level=messages.SUCCESS,
            )
        if already_sent_count:
            self.message_user(
                request,
                f"Skipped {already_sent_count} broadcast(s) that were already sent.",
                level=messages.WARNING,
            )
