from environ import Env
import requests

env = Env()

Env.read_env()

TELEGRAM_BOT_TOKEN    = env("TELEGRAM_BOT_TOKEN")     # customer-facing bot
TELEGRAM_PORTAL_TOKEN = env("TELEGRAM_PORTAL_TOKEN")  # delivery portal bot


def escape_markdown(text) -> str:
    """
    Escape Telegram legacy Markdown (parse_mode="Markdown") reserved
    characters — _, *, `, [ — in untrusted/dynamic text (usernames,
    addresses, item names, special instructions, etc.) before
    interpolating it into a message template.

    Without this, a single unmatched character (a Telegram username
    like "john_doe" is enough — the lone "_" starts an italics run
    with no closing "_") makes Telegram reject the ENTIRE message with
    a 400 "can't parse entities" error — not just that fragment.

    Only wrap the DYNAMIC pieces you interpolate with this — never the
    literal *bold*/_italic_ markers you write yourself in a template,
    or you'll escape away your own formatting.
    """
    if text is None:
        return ""
    text = str(text)
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def send_telegram_message(message: str, chat_id: str, use_portal_bot: bool = False):
    """
    Send a Telegram message using the appropriate bot token.

    Args:
        message:         The text to send (Markdown formatted).
        chat_id:         Recipient's Telegram chat ID.
        use_portal_bot:  If True, send via TELEGRAM_PORTAL_TOKEN (delivery staff).
                         If False (default), send via TELEGRAM_BOT_TOKEN (customers).
    """
    token = TELEGRAM_PORTAL_TOKEN if use_portal_bot else TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"Failed to send message: {response.text}")
    return response.json()
