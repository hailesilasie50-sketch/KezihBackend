from django.core.management.base import BaseCommand
from delivery.models import SpinPrize


# key              label               kind             value  spin_count  color      probability  order
PRIZES = [
    ("free_spin",     "Free Spin Chance",  "extra_spin",     0,    1,  "#e6396b", 18, 0),
    ("free_delivery", "Free Delivery",     "free_delivery",  0,    1,  "#2f7fe0", 12, 1),
    ("500",           "500 Birr",          "coins",          500,  1,  "#8e44e0", 8,  2),
    ("1000",          "1000 Birr",         "coins",          1000, 1,  "#e0393e", 4,  3),
    ("thanks",        "Thanks",            "thanks",         0,    1,  "#9a9aa4", 40, 4),
    ("double_spin",   "+2 Spin Chance",    "extra_spin",     0,    2,  "#3fb56a", 18, 5),
]


class Command(BaseCommand):
    help = "Seeds/updates the SpinPrize price list to match the current wheel design."

    def handle(self, *args, **options):
        # Prizes retired from this design (old key names, e.g. 'lose_all') are
        # deactivated rather than deleted, so past SpinWheelResult rows that
        # still point at them don't break.
        current_keys = {p[0] for p in PRIZES}
        retired = SpinPrize.objects.exclude(key__in=current_keys).filter(is_active=True)
        for prize in retired:
            prize.is_active = False
            prize.save(update_fields=["is_active"])
            self.stdout.write(self.style.WARNING(f"Deactivated (not in new list): {prize}"))

        for key, label, kind, value, spin_count, color, probability, order in PRIZES:
            obj, created = SpinPrize.objects.update_or_create(
                key=key,
                defaults={
                    "label": label,
                    "kind": kind,
                    "value": value,
                    "spin_count": spin_count,
                    "color": color,
                    "probability": probability,
                    "order": order,
                    "is_active": True,
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action}: {obj}"))
