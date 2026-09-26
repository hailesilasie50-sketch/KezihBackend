"""
Kezih Delivery — Telegram Bot
------------------------------
Sends a welcome message (with an "Open Order Now" button that launches the
Liyu Delivery Mini App) when a user clicks "Start" (/start command), and
saves every user's chat_id into the TelegramChatId model (deduplicated —
one row per chat_id, upserted on every /start).

Requirements:
    pip install python-telegram-bot==21.* django asgiref

Environment variables:
    TELEGRAM_BOT_TOKEN     — your bot token (required)
    DJANGO_SETTINGS_MODULE — e.g. "kezih.settings" (required, so the bot can
                              use the Django ORM to save chat_ids)
    DJANGO_PROJECT_ROOT    — absolute path to the folder that contains
                              manage.py, if this script doesn't already live
                              there (optional — only needed if the script is
                              run from outside the Django project)
    MINI_APP_URL           — https URL of the Liyu Delivery Mini App /
                              "Order Now" page (required for the button to
                              work; falls back to a disabled-looking notice
                              if unset)

Run:
    export TELEGRAM_BOT_TOKEN="your-bot-token-here"
    export DJANGO_SETTINGS_MODULE="kezih.settings"
    export MINI_APP_URL="https://your-liyu-delivery-frontend.example/order"
    python send_notification.py
"""

import os
import sys
import logging

# --------------------------------------------------------------------------
# Django setup — must happen before importing any Django models, so the bot
# process can use the ORM (django.setup() configures apps/settings).
# --------------------------------------------------------------------------
_project_root = os.environ.get("DJANGO_PROJECT_ROOT")
if _project_root:
    sys.path.insert(0, _project_root)

if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    raise RuntimeError(
        "Set the DJANGO_SETTINGS_MODULE environment variable "
        "(e.g. 'kezih.settings') before running the bot."
    )

import django  # noqa: E402
django.setup()

from asgiref.sync import sync_to_async  # noqa: E402
from telegram import (  # noqa: E402
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (  # noqa: E402
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from delivery.models import TelegramChatId  # noqa: E402  — adjust app label if needed

# --------------------------------------------------------------------------
# Logging setup — logs to both console and a file (chat_ids.log)
# --------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("chat_ids.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # set this in your environment / .env
MINI_APP_URL = os.environ.get("MINI_APP_URL")  # e.g. https://liyu-delivery.example/order

WELCOME_MESSAGE = (
    "👋 Welcome to Kezih Delivery!\n\n"
    "Order food from your favorite restaurants and get it delivered "
    "right to your door. Tap the button below to get started."
)


def build_welcome_keyboard() -> InlineKeyboardMarkup | None:
    """Build the 'Open Order Now' button. Uses a Mini App button when
    MINI_APP_URL is set (opens inside Telegram); returns None otherwise so
    the bot doesn't ship a broken button."""
    if not MINI_APP_URL:
        logger.warning("MINI_APP_URL is not set — welcome message will have no button.")
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛍 Open Order Now", web_app=WebAppInfo(url=MINI_APP_URL))]]
    )


@sync_to_async
def save_chat_id(chat_id: str, username: str, first_name: str, last_name: str) -> None:
    """Upsert this chat_id into the TelegramChatId table (unique on chat_id)."""
    TelegramChatId.objects.update_or_create(
        chat_id=str(chat_id),
        defaults={
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
        },
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — save the chat_id, then send the welcome message."""
    chat = update.effective_chat
    user = update.effective_user

    chat_id = chat.id
    username = user.username or "N/A"
    first_name = user.first_name or ""
    last_name = user.last_name or ""

    logger.info(
        "New /start — chat_id=%s username=%s name=%s %s",
        chat_id, username, first_name, last_name,
    )

    await save_chat_id(chat_id, username, first_name, last_name)

    await context.bot.send_message(
        chat_id=chat_id,
        text=WELCOME_MESSAGE,
        reply_markup=build_welcome_keyboard(),
    )


async def debug_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches EVERY update so you can confirm Telegram is reaching this bot at all."""
    logger.info("RAW UPDATE RECEIVED: %s", update.to_dict())


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable before running the bot.")

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.ALL, debug_all), group=1)

    logger.info("Kezih Delivery bot is starting (polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
