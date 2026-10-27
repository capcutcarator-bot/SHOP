import os
import sys
import logging
import asyncio
import time
import datetime
import json
import random
import inspect
import re
import aiohttp
import uuid
import threading
from typing import Dict, Any, Union, List
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Bot
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ==========================================
# 🛑 CORE CONFIGURATION INTERFACES
# ==========================================

BOT_TOKEN: str = "8998820865:AAFz-IrX2Yb6cwmYDtKCYZFpJHOktKTVL0Y"
ADMIN_ID: int = 8600328303
SUPPORT_HANDLE: str = "@Shuvobhai"
FEEDBACK_LINK: str = ""

ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE: float = 600.0

# Local Storage Database JSON Paths
DB_USERS_FILE: str = "local_users_db.json"
DB_PRODUCTS_FILE: str = "local_products_db.json"
DB_CONFIG_FILE: str = "local_config_db.json"

# Dynamic FamPay Configuration Parameters
FAMPAY_UPI: str = "sunnysldemon@fam"
FAMPAY_API_KEY: str = "FAM_b223147132692653bf1e031efa0aaa332e85dd816213fc33"
FAMPAY_QR_URL: str = "https://fampay.anujbots.xyz/qr.php"
FAMPAY_VERIFY_URL: str = "https://fampay.anujbots.xyz/verify.php"

# Legacy Payment Signatures Mapping (Updated)
MERCHANT_UPI_ID: str = FAMPAY_UPI
API_BASE_URL: str = "https://fampay.anujbots.xyz"

# Static Assets Configuration
STATIC_MANUAL_QR_LINK: str = "https://t.me/demonpaymentproof"

# Dynamic Config Variables
BOT_TITLE = "𝐃𝐄𝐌𝐎𝐍 𝐌𝐎𝐃𝐙"
CURRENCY = "₹"
OWNER_USERNAME = "@SL_DEMON_OFC"
UPI_HOLDER_NAME = "SL DEMON PAPA"
PAYMENT_CHANNEL_ID = ""
HOME_INTRO = "Welcome to 𝐒𝐋 𝐃𝐄𝐌𝐎𝐍 𝐏𝐀𝐏𝐀!"
SUPPORT_TEXT = "Contact @SL_DEMON_OFC for any help."
PAYMENT_INSTRUCTIONS = "Scan QR & Pay exact amount."
ADDITIONAL_PAYMENT = "N/A"
PROOF_CHANNEL_URL = FEEDBACK_LINK
TUTORIAL_URL = "https://t.me/demonpaymentproof"
MAINTENANCE_MODE: bool = False
PHONE_VERIFY_ENABLED: bool = False
WEBSITE_PANEL_URL: str = ""
WEBSITE_SYNC_URL: str = ""
MANAGED_BOTS_STARTED: set[str] = set()
# Runtime controls for managed/co-admin bots. Each bot gets its own asyncio
# loop in its own thread so it can run reliably alongside the main bot.
MANAGED_BOT_STOP_EVENTS: dict[str, threading.Event] = {}
MANAGED_BOT_APPS: dict[str, Application] = {}

# Anti-Spam Middleware Tracker
SPAM_TRACKER: dict[str, float] = {}
RATE_LIMIT_DELAY: float = 0.5

# Custom emojis used only by the Admin Panel UI.
ADMIN_CUSTOM_EMOJI_IDS = [
    "6147460667281511517", "6309641239423622963", "6237579651066107302",
    "6235722567336859128", "6235646232883107337", "6238042150324409739",
    "6147565374289220368", "5251203410396458957", "5397782960512444700",
    "5210956306952758910", "6253672992308469333", "6156715484285770345",
    "6136308217761766184", "6156541396376361727", "6156936361568901831",
    "6129668331466135693", "6129692490657175257", "6129610250623393142",
    "5438496463044752972", "6314398126157340467", "6311983130471308119",
    "6314583342327011784", "6312139458690948101", "6235717714023814969",
    "6235252066554484059", "6147902731085420231",
]
_ADMIN_CUSTOM_EMOJI_MAP: dict[str, str] = {}

def _admin_button_emoji_id(key: str) -> str:
    if key not in _ADMIN_CUSTOM_EMOJI_MAP:
        _ADMIN_CUSTOM_EMOJI_MAP[key] = ADMIN_CUSTOM_EMOJI_IDS[len(_ADMIN_CUSTOM_EMOJI_MAP) % len(ADMIN_CUSTOM_EMOJI_IDS)]
    return _ADMIN_CUSTOM_EMOJI_MAP[key]


# Prevent the background verifier and the manual VERIFY PAYMENT button
# from crediting the same wallet top-up at the same time.
PAYMENT_VERIFY_LOCKS: dict[str, asyncio.Lock] = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ==========================================
# 💾 PERSISTENT LOCAL JSON DATABASE INTERFACE
# ==========================================

class LocalDatabaseRouter:
    @staticmethod
    def _read_file(filename: str) -> Dict[str, Any]:
        if not os.path.exists(filename):
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=4)
            return {}
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading local file {filename}: {e}")
            return {}

    @staticmethod
    def _write_file(filename: str, data: Dict[str, Any]):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Error writing local file {filename}: {e}")

    @classmethod
    async def get_node(cls, file: str, key_path: str) -> Any:
        data = cls._read_file(file)
        parts = key_path.strip('/').split('/') if key_path.strip('/') else []
        curr = data
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return None
        return curr

    @classmethod
    async def set_node(cls, file: str, key_path: str, value: Any):
        data = cls._read_file(file)
        parts = key_path.strip('/').split('/') if key_path.strip('/') else []
        if not parts:
            cls._write_file(file, value)
            return
        
        curr = data
        for part in parts[:-1]:
            if part not in curr or not isinstance(curr[part], dict):
                curr[part] = {}
            curr = curr[part]
        curr[parts[-1]] = value
        cls._write_file(file, data)

    @classmethod
    async def delete_node(cls, file: str, key_path: str):
        data = cls._read_file(file)
        parts = key_path.strip('/').split('/') if key_path.strip('/') else []
        if not parts:
            cls._write_file(file, {})
            return
            
        curr = data
        for part in parts[:-1]:
            if part not in curr or not isinstance(curr[part], dict):
                return
            curr = curr[part]
        if parts[-1] in curr:
            del curr[parts[-1]]
        cls._write_file(file, data)

async def load_system_settings(application: Application = None):
    global MERCHANT_UPI_ID, FAMPAY_API_KEY, STATIC_MANUAL_QR_LINK, FAMPAY_QR_URL, FAMPAY_VERIFY_URL, API_BASE_URL
    global BOT_TITLE, CURRENCY, OWNER_USERNAME, UPI_HOLDER_NAME, PAYMENT_CHANNEL_ID
    global HOME_INTRO, SUPPORT_TEXT, PAYMENT_INSTRUCTIONS, ADDITIONAL_PAYMENT, PROOF_CHANNEL_URL, TUTORIAL_URL, MAINTENANCE_MODE, PHONE_VERIFY_ENABLED, WEBSITE_PANEL_URL, WEBSITE_SYNC_URL
    
    cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
    MERCHANT_UPI_ID = cfg.get("upi_id", MERCHANT_UPI_ID)
    FAMPAY_API_KEY = cfg.get("api_key", FAMPAY_API_KEY)
    FAMPAY_QR_URL = str(cfg.get("fampay_qr_url", FAMPAY_QR_URL) or FAMPAY_QR_URL).strip()
    FAMPAY_VERIFY_URL = str(cfg.get("fampay_verify_url", FAMPAY_VERIFY_URL) or FAMPAY_VERIFY_URL).strip()
    API_BASE_URL = str(cfg.get("fampay_api_base_url", API_BASE_URL) or API_BASE_URL).strip()
    STATIC_MANUAL_QR_LINK = cfg.get("qr_link", STATIC_MANUAL_QR_LINK)
    BOT_TITLE = cfg.get("bot_title", BOT_TITLE)
    CURRENCY = cfg.get("currency", CURRENCY)
    OWNER_USERNAME = cfg.get("owner_username", OWNER_USERNAME)
    UPI_HOLDER_NAME = cfg.get("upi_holder_name", UPI_HOLDER_NAME)
    PAYMENT_CHANNEL_ID = cfg.get("payment_channel_id", PAYMENT_CHANNEL_ID)
    HOME_INTRO = cfg.get("home_intro", HOME_INTRO)
    SUPPORT_TEXT = cfg.get("support_text", SUPPORT_TEXT)
    PAYMENT_INSTRUCTIONS = cfg.get("payment_instructions", PAYMENT_INSTRUCTIONS)
    ADDITIONAL_PAYMENT = cfg.get("additional_payment", ADDITIONAL_PAYMENT)
    PROOF_CHANNEL_URL = cfg.get("proof_channel_url", PROOF_CHANNEL_URL)
    TUTORIAL_URL = cfg.get("tutorial_url", TUTORIAL_URL)
    MAINTENANCE_MODE = cfg.get("maintenance_mode", False)
    PHONE_VERIFY_ENABLED = bool(cfg.get("phone_verify_enabled", PHONE_VERIFY_ENABLED))
    WEBSITE_PANEL_URL = str(cfg.get("website_panel_url", WEBSITE_PANEL_URL) or "").strip()
    WEBSITE_SYNC_URL = str(cfg.get("website_sync_url", WEBSITE_SYNC_URL) or "").strip()

    # Migrate older config files without changing their existing settings.
    if not isinstance(cfg.get("co_admin_users"), dict):
        cfg["co_admin_users"] = {}
        LocalDatabaseRouter._write_file(DB_CONFIG_FILE, cfg)

if not os.path.exists(DB_USERS_FILE): LocalDatabaseRouter._write_file(DB_USERS_FILE, {})
if not os.path.exists(DB_PRODUCTS_FILE): LocalDatabaseRouter._write_file(DB_PRODUCTS_FILE, {})
if not os.path.exists(DB_CONFIG_FILE): 
    LocalDatabaseRouter._write_file(DB_CONFIG_FILE, {
        "upi_id": MERCHANT_UPI_ID,
        "api_key": FAMPAY_API_KEY,
        "fampay_qr_url": FAMPAY_QR_URL,
        "fampay_verify_url": FAMPAY_VERIFY_URL,
        "fampay_api_base_url": API_BASE_URL,
        "qr_link": STATIC_MANUAL_QR_LINK,
        "bot_title": BOT_TITLE,
        "currency": CURRENCY,
        "owner_username": OWNER_USERNAME,
        "upi_holder_name": UPI_HOLDER_NAME,
        "payment_channel_id": PAYMENT_CHANNEL_ID,
        "home_intro": HOME_INTRO,
        "support_text": SUPPORT_TEXT,
        "payment_instructions": PAYMENT_INSTRUCTIONS,
        "additional_payment": ADDITIONAL_PAYMENT,
        "proof_channel_url": PROOF_CHANNEL_URL,
        "tutorial_url": TUTORIAL_URL,
        "maintenance_mode": MAINTENANCE_MODE,
        "phone_verify_enabled": PHONE_VERIFY_ENABLED,
        "website_panel_url": WEBSITE_PANEL_URL,
        "website_sync_url": WEBSITE_SYNC_URL,
        "home_message_template": "",
        "co_admin_bots": {},
        "co_admin_users": {}
    })

async def initialize_user_registers(user_id: Union[int, str], username: str = "User", first_name: str = "", referred_by: str = None) -> Dict[str, Any]:
    user_id = str(user_id)
    profile_data = await LocalDatabaseRouter.get_node(DB_USERS_FILE, user_id)
    if not profile_data:
        profile_data = {
            'balance': 0.0,
            'credited_payment_orders': {},
            'username': username,
            'first_name': first_name,
            'registered_at': str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            'purchased_keys': {},
            'referred_by': referred_by,
            'referral_count': 0,
            'total_referral_earned': 0.0,
            'is_ʀᴇꜱᴇʟʟᴇʀ': False,
            'phone_number': '',
            'phone_verified': False
        }
        await LocalDatabaseRouter.set_node(DB_USERS_FILE, user_id, profile_data)
        
        if referred_by and referred_by != user_id:
            ref_parent = await LocalDatabaseRouter.get_node(DB_USERS_FILE, str(referred_by))
            if ref_parent:
                current_count = ref_parent.get('referral_count', 0)
                await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{referred_by}/referral_count", current_count + 1)
    else:
        if 'credited_payment_orders' not in profile_data or profile_data['credited_payment_orders'] is None:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/credited_payment_orders", {})
        if 'purchased_keys' not in profile_data or profile_data['purchased_keys'] is None:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/purchased_keys", {})
        if 'referral_count' not in profile_data:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/referral_count", 0)
        if 'total_referral_earned' not in profile_data:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/total_referral_earned", 0.0)
        if 'is_ʀᴇꜱᴇʟʟᴇʀ' not in profile_data:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/is_ʀᴇꜱᴇʟʟᴇʀ", False)
        if 'phone_number' not in profile_data:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/phone_number", '')
        if 'phone_verified' not in profile_data:
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/phone_verified", False)
    return profile_data

async def process_wallet_balance_mutation(user_id: Union[int, str], amount: float) -> float:
    user_id = str(user_id)
    current_snapshot = await LocalDatabaseRouter.get_node(DB_USERS_FILE, user_id) or {}
    old_balance = float(current_snapshot.get('balance', 0.0))
    new_balance = max(0.0, old_balance + amount)
    await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/balance", new_balance)
    return new_balance

async def award_referral_bonus_pipeline(bot: Bot, buyer_id: str):
    buyer_record = await LocalDatabaseRouter.get_node(DB_USERS_FILE, str(buyer_id))
    if not buyer_record: return
    
    parent_ref_id = buyer_record.get('referred_by')
    if parent_ref_id:
        parent_ref_id = str(parent_ref_id)
        parent_record = await LocalDatabaseRouter.get_node(DB_USERS_FILE, parent_ref_id)
        if parent_record:
            bonus_reward = 2.0
            await process_wallet_balance_mutation(parent_ref_id, bonus_reward)
            
            curr_total = float(parent_record.get('total_referral_earned', 0.0))
            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{parent_ref_id}/total_referral_earned", curr_total + bonus_reward)
            
            try:
                alert_text = (
                    f"💸 REFERRAL COMMISSION RECEIVED 💸\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 Your referral node (ID: {buyer_id}) executed a shop purchase.\n"
                    f"💰 Bonus Deposited: {CURRENCY} {bonus_reward:.2f}\n"
                    f"⚡ Keep sharing your invite system link to scale earnings!"
                )
                await bot.send_message(chat_id=int(parent_ref_id), text=alert_text)
            except Exception: pass

# ==========================================
# 👥 CO-ADMIN / MANAGED BOT HELPERS
# ==========================================
def get_managed_bot_records() -> dict:
    cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
    records = cfg.get("co_admin_bots", {})
    return records if isinstance(records, dict) else {}

def get_same_bot_admin_records() -> dict:
    cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
    records = cfg.get("co_admin_users", {})
    return records if isinstance(records, dict) else {}

def get_all_admin_ids() -> set[int]:
    # The configured ADMIN_ID is always the owner. Additional IDs are
    # explicitly granted access to this SAME bot by the owner.
    ids = {int(ADMIN_ID)}

    for admin_id in get_same_bot_admin_records().keys():
        try:
            ids.add(int(admin_id))
        except (TypeError, ValueError):
            continue

    # Keep backward compatibility with the existing managed-bot feature.
    for record in get_managed_bot_records().values():
        try:
            ids.add(int(record.get("admin_id")))
        except (TypeError, ValueError, AttributeError):
            continue
    return ids

def is_owner_user(user_id: int) -> bool:
    try:
        return int(user_id) == int(ADMIN_ID)
    except (TypeError, ValueError):
        return False

def is_admin_user(user_id: int) -> bool:
    try:
        return int(user_id) in get_all_admin_ids()
    except (TypeError, ValueError):
        return False

def build_application_for_bot(token: str) -> Application:
    """Build a managed bot with the exact same handlers/UI as the owner bot."""
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("admin", admin_panel_launcher))
    app.add_handler(CommandHandler("buybot", buybot_command_handler))
    # Dedicated CO-ADMIN menu route must be registered before the catch-all
    # callback handler so the button can never be swallowed by another route.
    app.add_handler(CallbackQueryHandler(coadmin_menu_callback_handler, pattern=r"^adm_coadmin_menu$"))
    app.add_handler(CallbackQueryHandler(global_callback_routing_engine))
    app.add_handler(MessageHandler(~filters.COMMAND, handle_text_messages))
    return app

async def _run_managed_bot_async(token: str, bot_key: str, stop_event: threading.Event):
    """Run one managed bot on its own asyncio loop.

    Application.run_polling() installs signal handlers and is unreliable from a
    background thread on mobile/Termux. Using initialize/start/updater directly
    avoids that problem and lets every managed bot receive /start and callbacks.
    """
    app = build_application_for_bot(token)
    MANAGED_BOT_APPS[bot_key] = app
    try:
        await app.initialize()
        await app.start()
        if app.updater is None:
            raise RuntimeError("Managed bot updater is unavailable")
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Managed co-admin bot polling started: %s", bot_key)

        while not stop_event.is_set():
            await asyncio.sleep(1.0)
    finally:
        try:
            if app.updater is not None:
                await app.updater.stop()
        except Exception:
            pass
        try:
            await app.stop()
        except Exception:
            pass
        try:
            await app.shutdown()
        except Exception:
            pass
        MANAGED_BOT_APPS.pop(bot_key, None)

def _run_managed_bot_thread(token: str, bot_key: str):
    """Run a managed bot in its own event loop and retry Telegram 429s safely."""
    stop_event = MANAGED_BOT_STOP_EVENTS.setdefault(bot_key, threading.Event())
    while not stop_event.is_set():
        try:
            asyncio.run(_run_managed_bot_async(token, bot_key, stop_event))
            return
        except Exception as exc:
            error_text = str(exc)
            retry_after = getattr(exc, "retry_after", None)

            # python-telegram-bot exposes RetryAfter.retry_after. Keep a
            # fallback parser for the textual Telegram error as well.
            if retry_after is None:
                match = re.search(r"Retry in (\d+(?:\.\d+)?) seconds", error_text, re.IGNORECASE)
                if match:
                    retry_after = float(match.group(1))
                elif "Flood control exceeded" in error_text:
                    retry_after = 60.0

            if retry_after is not None:
                try:
                    delay = max(5.0, min(float(retry_after) + 2.0, 900.0))
                except (TypeError, ValueError):
                    delay = 60.0
                logger.warning(
                    "Managed bot %s hit Telegram flood control; retrying in %.0f seconds.",
                    bot_key, delay,
                )
                if stop_event.wait(delay):
                    break
                continue

            logger.error("Managed bot %s stopped: %s", bot_key, exc)
            break

    MANAGED_BOTS_STARTED.discard(bot_key)
    MANAGED_BOT_STOP_EVENTS.pop(bot_key, None)
    MANAGED_BOT_APPS.pop(bot_key, None)

def start_managed_bot(token: str, bot_key: str) -> bool:
    """Start a saved co-admin bot once; each bot gets its own event loop."""
    token = str(token or "").strip()
    bot_key = str(bot_key or "").strip()
    if not token or not bot_key:
        return False
    if bot_key in MANAGED_BOTS_STARTED:
        return True

    stop_event = threading.Event()
    MANAGED_BOT_STOP_EVENTS[bot_key] = stop_event
    MANAGED_BOTS_STARTED.add(bot_key)
    thread = threading.Thread(
        target=_run_managed_bot_thread,
        args=(token, bot_key),
        daemon=True,
        name=f"managed-bot-{bot_key}",
    )
    thread.start()
    return True

def stop_managed_bot(bot_key: str) -> bool:
    """Request a managed bot to stop without changing any UI styling."""
    bot_key = str(bot_key or "").strip()
    event = MANAGED_BOT_STOP_EVENTS.get(bot_key)
    if event is None and bot_key not in MANAGED_BOTS_STARTED:
        return False
    if event is not None:
        event.set()
    MANAGED_BOTS_STARTED.discard(bot_key)
    return True


def _local_bot_token_parts(token: str) -> tuple[bool, str]:
    """Validate token shape locally without calling Telegram getMe."""
    token = str(token or "").strip()
    if token.count(":") != 1:
        return False, "Token must contain exactly one ':' separator."
    bot_id, secret = token.split(":", 1)
    if not bot_id.isdigit() or len(bot_id) < 6:
        return False, "Invalid bot ID part in token."
    if len(secret) < 20 or any(ch.isspace() for ch in secret):
        return False, "Invalid bot token secret part."
    return True, bot_id

async def sync_products_from_website(url: str) -> tuple[bool, str, int]:
    url = str(url or "").strip()
    if not url:
        return False, "Website sync URL is not configured.", 0
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20, headers={"Accept": "application/json"}) as resp:
                if resp.status != 200:
                    return False, f"Website returned HTTP {resp.status}.", 0
                payload = await resp.json(content_type=None)
    except Exception as exc:
        return False, f"Could not connect to website: {exc}", 0

    categories = None
    if isinstance(payload, dict):
        categories = payload.get("categories")
        if categories is None and isinstance(payload.get("data"), dict):
            categories = payload["data"].get("categories")
    if not isinstance(categories, dict):
        return False, 'Sync API must return JSON like {"categories": {...}}.', 0

    await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, "categories", categories)
    return True, "Website catalogue synced successfully.", len(categories)

# ==========================================
# 🎛️ UI KEYBOARD INTERFACES (COLOUR ENABLED)
# ==========================================

def render_main_menu_keyboard(is_ʀᴇꜱᴇʟʟᴇʀ: bool = False) -> InlineKeyboardMarkup:
    """Main menu: big Shop button, then compact two-column buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Shop / Store Product",
                callback_data="/buy_hack",
                style="danger",
                icon_custom_emoji_id="5866053971960929280",
            )
        ],
        [
            InlineKeyboardButton(
                "Add Balance",
                callback_data="/addfund",
                style="success",
                icon_custom_emoji_id="6147815702163102310",
            ),
            InlineKeyboardButton(
                "My Profile",
                callback_data="/profile",
                style="primary",
                icon_custom_emoji_id="5260399854500191689",
            ),
        ],
        [
            InlineKeyboardButton(
                "All History",
                callback_data="/mykey",
                style="primary",
                icon_custom_emoji_id="6113743082358841933",
            ),
            InlineKeyboardButton(
                "Refer & Earn",
                callback_data="main_referral",
                style="success",
                icon_custom_emoji_id="6147764669361692707",
            ),
        ],
        [
            InlineKeyboardButton(
                "Tutorial",
                callback_data="/how",
                style="primary",
                icon_custom_emoji_id="5334890573281114250",
            ),
            InlineKeyboardButton(
                "Support",
                callback_data="/support",
                style="primary",
                icon_custom_emoji_id="5436113877181941026",
            ),
        ],
    ])

def render_profile_keyboard(is_ʀᴇꜱᴇʟʟᴇʀ: bool = False) -> InlineKeyboardMarkup:
    # Existing button colours/styles are preserved.
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔐 My Keys", callback_data="ui_my_keys", style="primary"),
            InlineKeyboardButton("💳 Add Fund", callback_data="ui_route_auto", style="success"),
        ],
        [
            InlineKeyboardButton("📱 Verify Account", callback_data="ui_phone_verify", style="primary"),
        ],
        [
            InlineKeyboardButton("❌ Back", callback_data="back_main", style="danger")
        ],
    ])

def render_matrix_dialpad(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data=f"pad_{mode}_1", style="primary"), InlineKeyboardButton("2", callback_data=f"pad_{mode}_2", style="primary"), InlineKeyboardButton("3", callback_data=f"pad_{mode}_3", style="primary")],
        [InlineKeyboardButton("4", callback_data=f"pad_{mode}_4", style="primary"), InlineKeyboardButton("5", callback_data=f"pad_{mode}_5", style="primary"), InlineKeyboardButton("6", callback_data=f"pad_{mode}_6", style="primary")],
        [InlineKeyboardButton("7", callback_data=f"pad_{mode}_7", style="primary"), InlineKeyboardButton("8", callback_data=f"pad_{mode}_8", style="primary"), InlineKeyboardButton("9", callback_data=f"pad_{mode}_9", style="primary")],
        [InlineKeyboardButton("❌ Clear", callback_data=f"pad_{mode}_backspace", style="danger"), InlineKeyboardButton("0", callback_data=f"pad_{mode}_0", style="primary"), InlineKeyboardButton("✅ Process", callback_data=f"pad_{mode}_commit", style="success")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]
    ])

# Premium custom emoji IDs for the HOME/SHOP description.
# Every normal "✨" in the home message is replaced in order with these
# Telegram premium custom emojis. Existing UI colours/styles are untouched.
HOME_PREMIUM_EMOJI_IDS = [
    "5312361253610475399",
    "5312361253610475399",
    "6057721277001504261",
    "6208671660715809463",
    "6208671660715809463",
    "6285210748184434476",
    "6311823125759661445",
    "6055639815590781298",
    "6285253186756286288",
    "6057463342740542601",
    "5280894283090511593",
    "6208580981071288096",
    "6311799464784827510",
    "6235646232883107337",
    "6235449188373502693",
    "6235375710073000908",
    "6235403472741603087",
    "6235253239080555488",
    "6235646232883107337",
    "6235449188373502693",
]

DEFAULT_HOME_MESSAGE_TEMPLATE = (
    "✨ ——— **FF PANELS SHOP** ——— ✨\n\n"
    "✨ Wᴇʟᴄᴏᴍᴇ, **{USER_NAME}**\n\n"
    "✨ ——— **Sᴛᴏʀᴇ Hɪɢʜʟɪɢʜᴛꜱ** ——— ✨\n\n"
    "<blockquote>"
    "✨ Pʀᴇᴍɪᴜᴍ Gᴀᴍᴇꜱ Kᴇʏ\n"
    "✨ Iɴꜱᴛᴀɴᴛ Dᴇʟɪᴠᴇʀʏ 24/7\n"
    "✨ 100% Sᴇᴄᴜʀᴇ Pᴀʏᴍᴇɴᴛ\n"
    "✨ Bᴇꜱᴛ Pʀɪᴄᴇꜱ Gᴜᴀʀᴀɴᴛᴇᴇᴅ\n"
    "✨ Sᴀꜰᴇ Aɴᴅ Tʀᴜꜱᴛᴇᴅ\n"
    "✨ Pʀᴏꜰᴇꜱꜱɪᴏɴᴀʟ Sᴜᴩᴩᴏʀᴛ"
    "</blockquote>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "✨ <b>Wᴀʟʟᴇᴛ Bᴀʟᴀɴᴄᴇ:</b> {CURRENCY} {BALANCE:.2f}\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "✨ <i>Tᴀᴩ Sʜᴏᴩ Nᴏᴡ Tᴏ Sᴛᴀʀᴛ!</i>"
)

def _render_home_html(template: str) -> str:
    """Render the existing home text while replacing every ✨ with premium custom emoji."""
    emoji_index = 0

    def replace_sparkle(_match):
        nonlocal emoji_index
        emoji_id = HOME_PREMIUM_EMOJI_IDS[emoji_index % len(HOME_PREMIUM_EMOJI_IDS)]
        emoji_index += 1
        return f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji>'

    # Admin-configured JSON may contain literal \n characters.
    # Normalize them so Telegram receives real line breaks.
    rendered = template.replace("\\n", "\n")
    rendered = re.sub(r"✨", replace_sparkle, rendered)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", rendered)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    return rendered

def get_home_message_template() -> str:
    cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
    value = cfg.get("home_message_template")
    return str(value) if isinstance(value, str) and value.strip() else DEFAULT_HOME_MESSAGE_TEMPLATE

def render_home_message(user_id: int, balance: float, user_name: str = "User") -> str:
    template = get_home_message_template()
    try:
        rendered = template.format(
            USER_ID=user_id,
            USER_NAME=user_name,
            BALANCE=float(balance or 0),
            CURRENCY=CURRENCY,
        )
        return _render_home_html(rendered)
    except Exception as exc:
        logger.warning("Home message template format failed: %s", exc)
        fallback = DEFAULT_HOME_MESSAGE_TEMPLATE.format(
            USER_ID=user_id,
            USER_NAME=user_name,
            BALANCE=float(balance or 0),
            CURRENCY=CURRENCY,
        )
        return _render_home_html(fallback)


def render_admin_panel_keyboard() -> InlineKeyboardMarkup:
    m_status = "TURN OFF" if MAINTENANCE_MODE else "TURN ON"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ꜱᴛᴏʀᴇ ʙᴜɪʟᴅᴇʀ", callback_data="adm_store_builder", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("admin_button"))],
        [InlineKeyboardButton("ʀᴇꜱᴇʟʟᴇʀ ꜱᴇᴛᴜᴩ", callback_data="adm_reseller_setup", style="success", icon_custom_emoji_id=_admin_button_emoji_id("admin_button"))],
        [InlineKeyboardButton("PAYMENTS", callback_data="adm_upi_change_init", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("PAYMENTS")), InlineKeyboardButton("USERS & WALLET", callback_data="adm_manage_bal_menu", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("USERS_WALLET"))],
        [InlineKeyboardButton("STATISTICS", callback_data="adm_check_keys_all", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("STATISTICS")), InlineKeyboardButton("BROADCAST", callback_data="adm_trigger_bc", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("BROADCAST"))],
        [InlineKeyboardButton("BUY BOT MENU", callback_data="adm_buybot", style="success", icon_custom_emoji_id=_admin_button_emoji_id("BUY_BOT_MENU"))],
        [InlineKeyboardButton("ADD / CHANGE MESSAGE", callback_data="adm_home_message", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("ADD_CHANGE_MESSAGE"))],
        [InlineKeyboardButton(f"MAINTENANCE: {m_status}", callback_data="adm_toggle_maint", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("MAINTENANCE_m_status"))],
        [InlineKeyboardButton("BOT SETTINGS", callback_data="adm_bot_settings_menu", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("BOT_SETTINGS"))],
        [InlineKeyboardButton("HELP & COMMANDS", callback_data="ui_how_to_use", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("HELP_COMMANDS"))],
        [InlineKeyboardButton("USER MENU", callback_data="back_main", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("USER_MENU"))]
    ])
def render_fampay_settings_keyboard() -> InlineKeyboardMarkup:
    """Dedicated FamPay API configuration; keeps existing button colors/styles."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("FAMPAY UPI ID", callback_data="adm_fampay_upi", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FAMPAY_UPI_ID"))],
        [InlineKeyboardButton("FAMPAY API KEY", callback_data="adm_fampay_api_key", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FAMPAY_API_KEY"))],
        [InlineKeyboardButton("FAMPAY QR URL", callback_data="adm_fampay_qr_url", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FAMPAY_QR_URL"))],
        [InlineKeyboardButton("FAMPAY VERIFY URL", callback_data="adm_fampay_verify_url", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FAMPAY_VERIFY_URL"))],
        [InlineKeyboardButton("FAMPAY API BASE URL", callback_data="adm_fampay_base_url", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FAMPAY_API_BASE_URL"))],
        [InlineKeyboardButton("BOT SETTINGS", callback_data="adm_bot_settings_menu", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("BOT_SETTINGS"))],
    ])
def render_bot_settings_keyboard() -> InlineKeyboardMarkup:
    m_status = "OFF" if MAINTENANCE_MODE else "ON"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("BOT TITLE", callback_data="adm_set_title", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("BOT_TITLE")), InlineKeyboardButton("CURRENCY", callback_data="adm_set_curr", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("CURRENCY"))],
        [InlineKeyboardButton("OWNER USERNAME", callback_data="adm_set_owner", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("OWNER_USERNAME")), InlineKeyboardButton("UPI ID", callback_data="adm_upi_change_init", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("UPI_ID"))],
        [InlineKeyboardButton("UPI HOLDER NAME", callback_data="adm_set_upiname", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("UPI_HOLDER_NAME")), InlineKeyboardButton("PAYMENT CHANNEL ID", callback_data="adm_set_paychan", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("PAYMENT_CHANNEL_ID"))],
        [InlineKeyboardButton("HOME INTRO", callback_data="adm_set_intro", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("HOME_INTRO")), InlineKeyboardButton("SUPPORT TEXT", callback_data="adm_set_supp", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("SUPPORT_TEXT"))],
        [InlineKeyboardButton("PAYMENT INSTRUCTIONS", callback_data="adm_set_payinst", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("PAYMENT_INSTRUCTIONS")), InlineKeyboardButton("ADDITIONAL PAYMENT", callback_data="adm_set_addpay", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("ADDITIONAL_PAYMENT"))],
        [InlineKeyboardButton("PROOF CHANNEL URL", callback_data="adm_set_proof", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("PROOF_CHANNEL_URL")), InlineKeyboardButton("TUTORIAL URL", callback_data="adm_set_tut", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("TUTORIAL_URL"))],
        [InlineKeyboardButton(f"MAINTENANCE MODE ({m_status})", callback_data="adm_toggle_maint", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("MAINTENANCE_MODE_m_status"))],
        [InlineKeyboardButton(f"PHONE VERIFY ACCOUNT ({' ON' if PHONE_VERIFY_ENABLED else ' OFF'})", callback_data="adm_toggle_phone_verify", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("PHONE_VERIFY_ACCOUNT_ON_if_PHONE_VERIFY_ENABLED_else_OFF"))],
        [InlineKeyboardButton("CHANGE QR", callback_data="adm_qr_change_init", style="success", icon_custom_emoji_id=_admin_button_emoji_id("CHANGE_QR")), InlineKeyboardButton("REMOVE QR", callback_data="adm_qr_remove", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("REMOVE_QR"))],
        [InlineKeyboardButton("CO-ADMIN / BOT MANAGER", callback_data="adm_coadmin_menu", style="success", icon_custom_emoji_id=_admin_button_emoji_id("CO_ADMIN_BOT_MANAGER"))],
        [InlineKeyboardButton("ADMIN MANAGEMENT", callback_data="adm_admin_manage", style="success", icon_custom_emoji_id=_admin_button_emoji_id("ADMIN_MANAGEMENT"))],
        [InlineKeyboardButton("LINK WEBSITE PANEL", callback_data="adm_set_webpanel", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("LINK_WEBSITE_PANEL"))],
        [InlineKeyboardButton("🆔 FF ID STORE", callback_data="adm_ff_id_store", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FF_ID_STORE"))],
        [InlineKeyboardButton("FAMPAY SETTINGS", callback_data="adm_fampay_settings", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FAMPAY_SETTINGS"))],
        [InlineKeyboardButton("SYNC FROM WEBSITE", callback_data="adm_sync_website", style="success", icon_custom_emoji_id=_admin_button_emoji_id("SYNC_FROM_WEBSITE"))],
        ([InlineKeyboardButton("OPEN WEBSITE PANEL", url=WEBSITE_PANEL_URL, style="primary", icon_custom_emoji_id=_admin_button_emoji_id("OPEN_WEBSITE_PANEL"))] if WEBSITE_PANEL_URL else []),
        [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("ADMIN_PANEL"))]
    ])
def render_reseller_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ADD RESELLER", callback_data="adm_reseller_add", style="success", icon_custom_emoji_id=_admin_button_emoji_id("ADD_RESELLER")),
         InlineKeyboardButton("🆙 UPGRADE RESELLER", callback_data="adm_reseller_upgrade", style="success", icon_custom_emoji_id=_admin_button_emoji_id("UPGRADE_RESELLER"))],
        [InlineKeyboardButton("REMOVE RESELLER", callback_data="adm_reseller_remove", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("REMOVE_RESELLER")),
         InlineKeyboardButton("RESELLER USER LIST", callback_data="adm_reseller_list", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("RESELLER_USER_LIST"))],
        [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("ADMIN_PANEL"))]
    ])

def render_users_wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("FIND USER", callback_data="adm_bal_check", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("FIND_USER")), InlineKeyboardButton("LIST USERS", callback_data="adm_list_users", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("LIST_USERS"))],
        [InlineKeyboardButton("PHONE NUMBERS", callback_data="adm_phone_numbers", style="primary", icon_custom_emoji_id=_admin_button_emoji_id("PHONE_NUMBERS"))],
        [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("ADMIN_PANEL"))]
    ])
def _premium_button(text: str, callback_data: str = None, url: str = None, style: str = "primary", custom_emoji_id: str = "") -> InlineKeyboardButton:
    """Create a button with a Telegram custom/premium emoji icon when supported."""
    kwargs = {"text": text, "style": style}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if custom_emoji_id:
        try:
            return InlineKeyboardButton(**kwargs, icon_custom_emoji_id=str(custom_emoji_id).strip())
        except TypeError:
            pass
    return InlineKeyboardButton(**kwargs)


def _ff_id_store_keyboard() -> InlineKeyboardMarkup:
    """Dedicated FF ID Store admin controls; preserve existing button styles/colors."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD FF ACCOUNT 8 LEVEL ID + FACEBOOK ", callback_data="ffid_account_fb_google", style="success")],
        [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger")],
    ])


async def _ensure_ff_id_store_panel(panel_id: str, panel_name: str, plan_id: str):
    """Create the FF ID Store panel/package without overwriting existing price or stock."""
    categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, "categories") or {}
    cat = categories.get("ff_id_store")
    if not isinstance(cat, dict):
        cat = {"name": "FF ID STORE", "active": True, "emoji_id": "", "panels": {}}
    cat.setdefault("panels", {})
    panel = cat["panels"].get(panel_id)
    if not isinstance(panel, dict):
        panel = {
            "name": panel_name, "active": True, "emoji_id": "",
            "description": "", "plans": {}, "keys": {}
        }
    panel["name"] = panel.get("name") or panel_name
    panel.setdefault("active", True)
    panel.setdefault("emoji_id", "")
    panel.setdefault("description", "")
    panel.setdefault("plans", {})
    panel.setdefault("keys", {})
    if plan_id not in panel["plans"]:
        panel["plans"][plan_id] = {
            "standard": 0.0, "ʀᴇꜱᴇʟʟᴇʀ": 0.0,
            "active": True, "limit": 0, "ff_id_store": True
        }
    if plan_id not in panel["keys"] or not isinstance(panel["keys"].get(plan_id), dict):
        panel["keys"][plan_id] = {}
    cat["panels"][panel_id] = panel
    categories["ff_id_store"] = cat
    await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, "categories", categories)
    return cat, panel


def _ff_store_package_label(value: str) -> str:
    raw = str(value or "").strip()
    special = {
        "FB_GOOGLE": "8 LEVEL ID",
    }
    return special.get(raw, raw.replace("_", " ").upper())


def render_store_builder_keyboard(categories: dict) -> InlineKeyboardMarkup:
    buttons = []
    for cat_id, cat_info in categories.items():
        # FF ID Store is managed from BOT SETTINGS, not Store Builder.
        if str(cat_id).lower() == "ff_id_store":
            continue
        name = cat_info.get("name", cat_id.upper())
        status = "✅ " if cat_info.get("active", True) else "❌ "
        emoji_id = str(cat_info.get("emoji_id", "") or "").strip()
        buttons.append([_premium_button(
            f"{status}{name}", callback_data=f"sb_cat_{cat_id}",
            style="primary", custom_emoji_id=emoji_id
        )])
    if len(categories) < 10:
        buttons.append([_premium_button("➕ ADD CATEGORY", callback_data="sb_add_cat", style="success")])
    buttons.append([_premium_button("👁️ PREVIEW USER STORE", callback_data="ui_shop_prods", style="primary")])
    buttons.append([_premium_button("🔙 ADMIN PANEL", callback_data="back_to_admin", style="danger")])
    return InlineKeyboardMarkup(buttons)

def render_category_manage_keyboard(cat_id: str, cat_data: dict) -> InlineKeyboardMarkup:
    buttons = []
    panels = cat_data.get("panels", {})
    for p_id, p_info in panels.items():
        name = p_info.get("name", p_id.upper())
        status = "✅ " if p_info.get("active", True) else "❌ "
        emoji_id = str(p_info.get("emoji_id", "") or "").strip()
        buttons.append([_premium_button(
            f"{status}{name}", callback_data=f"sb_pnl_{cat_id}:{p_id}",
            style="primary", custom_emoji_id=emoji_id
        )])
    buttons.append([_premium_button("➕ ADD PANEL", callback_data=f"sb_add_pnl_{cat_id}", style="success")])
    buttons.append([_premium_button(
        "SET CATEGORY EMOJI",
        callback_data=f"sb_cat_emoji_{cat_id}",
        style="primary",
        custom_emoji_id=_admin_button_emoji_id("SET_CATEGORY_EMOJI")
    )])
    toggle_text = "⏸️ DISABLE" if cat_data.get("active", True) else "▶️ ENABLE"
    buttons.append([
        _premium_button("✏️ RENAME", callback_data=f"sb_ren_cat_{cat_id}", style="primary"),
        _premium_button(toggle_text, callback_data=f"sb_tog_cat_{cat_id}", style="danger")
    ])
    buttons.append([
        _premium_button("⬆️ MOVE UP", callback_data=f"sb_mup_cat_{cat_id}", style="primary"),
        _premium_button("⬇️ MOVE DOWN", callback_data=f"sb_mdn_cat_{cat_id}", style="primary")
    ])
    buttons.append([_premium_button("🗑️ DELETE CATEGORY", callback_data=f"sb_del_cat_{cat_id}", style="danger")])
    buttons.append([_premium_button("🔙 STORE BUILDER", callback_data="adm_store_builder", style="danger")])
    return InlineKeyboardMarkup(buttons)

def render_panel_manage_keyboard(cat_id: str, p_id: str, p_data: dict) -> InlineKeyboardMarkup:
    buttons = []
    plans = p_data.get('plans', {})
    keys = p_data.get('keys', {})
    for day, price in plans.items():
        stock_cnt = len([k for k in keys.get(day, {}).keys() if k != "init_node_secured"])
        std_p = price.get('standard', price) if isinstance(price, dict) else price
        buttons.append([_premium_button(
            f"✅ {_ff_store_package_label(day)} • ₹{std_p:.2f} • Stock {stock_cnt}",
            callback_data=f"sb_pkg_view_{cat_id}:{p_id}:{day}", style="primary"
        )])
    buttons.append([_premium_button("⚡ QUICK 1,2,3,7,30 DAYS", callback_data=f"sb_quick_days_{cat_id}:{p_id}", style="success")])
    buttons.append([_premium_button("⏱️ QUICK 1,3,7,12,24 HOURS", callback_data=f"sb_quick_hours_{cat_id}:{p_id}", style="success")])
    buttons.append([_premium_button("➕ ADD CUSTOM VALIDITY", callback_data=f"sb_add_val_{cat_id}:{p_id}", style="success")])
    buttons.append([_premium_button(
        "SET PANEL EMOJI",
        callback_data=f"sb_pnl_emoji_{cat_id}:{p_id}",
        style="primary",
        custom_emoji_id=_admin_button_emoji_id("SET_PANEL_EMOJI")
    )])
    toggle_text = "⏸️ DISABLE" if p_data.get("active", True) else "▶️ ENABLE"
    buttons.append([
        _premium_button("✏️ RENAME", callback_data=f"sb_ren_pnl_{cat_id}:{p_id}", style="primary"),
        _premium_button("📝 DESCRIPTION", callback_data=f"sb_desc_pnl_{cat_id}:{p_id}", style="primary")
    ])
    buttons.append([_premium_button(toggle_text, callback_data=f"sb_tog_pnl_{cat_id}:{p_id}", style="danger")])
    buttons.append([
        _premium_button("⬆️ MOVE UP", callback_data=f"sb_mup_pnl_{cat_id}:{p_id}", style="primary"),
        _premium_button("⬇️ MOVE DOWN", callback_data=f"sb_mdn_pnl_{cat_id}:{p_id}", style="primary")
    ])
    buttons.append([_premium_button("🗑️ DELETE PANEL", callback_data=f"sb_del_pnl_{cat_id}:{p_id}", style="danger")])
    buttons.append([_premium_button("🔙 CATEGORY", callback_data=f"sb_cat_{cat_id}", style="danger")])
    return InlineKeyboardMarkup(buttons)

def render_package_manage_keyboard(cat_id: str, p_id: str, day: str, p_data: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🥰 MANAGE STOCK", callback_data=f"sb_stk_manage_{cat_id}:{p_id}:{day}", style="success")],
        [InlineKeyboardButton("⏰ EDIT VALIDITY", callback_data=f"sb_edit_val_{cat_id}:{p_id}:{day}", style="primary"), InlineKeyboardButton("💰 EDIT PRICE", callback_data=f"sb_edit_prc_{cat_id}:{p_id}:{day}", style="primary")],
        [InlineKeyboardButton("💎 EDIT RESELLER PRICE", callback_data=f"sb_edit_res_prc_{cat_id}:{p_id}:{day}", style="success")],
        [InlineKeyboardButton("📱 EDIT LIMIT", callback_data=f"sb_edit_lmt_{cat_id}:{p_id}:{day}", style="primary"), InlineKeyboardButton("⏸️ DISABLE" if p_data.get("plans", {}).get(day, {}).get("active", True) else "▶️ ENABLE", callback_data=f"sb_tog_pkg_{cat_id}:{p_id}:{day}", style="danger")],
        [InlineKeyboardButton("⬆️ MOVE UP", callback_data=f"sb_mup_pkg_{cat_id}:{p_id}:{day}", style="primary"), InlineKeyboardButton("⬇️ MOVE DOWN", callback_data=f"sb_mdn_pkg_{cat_id}:{p_id}:{day}", style="primary")],
        [InlineKeyboardButton("🗑️ DELETE PACKAGE", callback_data=f"sb_del_pkg_{cat_id}:{p_id}:{day}", style="danger")],
        [InlineKeyboardButton("🔙 PANEL PACKAGES", callback_data=f"sb_pnl_{cat_id}:{p_id}", style="danger")]
    ])

def render_back_navigation_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]
    ])

def render_admin_back_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger", icon_custom_emoji_id=_admin_button_emoji_id("Return_Admin_Control_Panel"))]])
def render_sb_back_markup(callback_data: str, label: str) -> InlineKeyboardMarkup:
    """Store Builder contextual back button; keeps navigation inside Store Builder."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔙 {label}", callback_data=callback_data, style="danger")]
    ])

def render_confirmation_keyboard(confirm_action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_action, style="success"),
            InlineKeyboardButton("❌ Cancel", callback_data="back_main", style="danger")
        ]
    ])

def render_payment_cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ VERIFY PAYMENT", callback_data="verify_payment", style="success")],
        [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_payment", style="danger")]
    ])

def render_payment_cancelled_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main", style="success")]
    ])

def _payment_amount_text(amount: Union[int, float, str]) -> str:
    try:
        normalized = Decimal(str(amount).strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        normalized = Decimal("0.00")
    amount_text = format(normalized, "f")
    if "." in amount_text:
        amount_text = amount_text.rstrip("0").rstrip(".")
    return amount_text or "0"

def build_fampay_qr_url(upi_id: str, amount: Union[int, float, str]) -> str:
    amount_text = _payment_amount_text(amount)
    return f"{FAMPAY_QR_URL}?upi={quote(str(upi_id).strip())}&amount={quote(amount_text)}"

def build_fampay_verify_url(order_id: str) -> str:
    return f"{FAMPAY_VERIFY_URL}?order_id={quote(str(order_id).strip())}&api_key={quote(FAMPAY_API_KEY.strip())}"

def extract_fampay_success_payload(res_data: Dict[str, Any]) -> tuple[bool, Dict[str, Any], str]:
    status = str(res_data.get("status", "")).strip().lower()
    success_statuses = {"success", "completed", "true", "1", "paid", "verified", "ok"}
    if status in success_statuses:
        data = res_data.get("data", {}) or {}
        return True, data if isinstance(data, dict) else {}, status
    data = res_data.get("data", {})
    if isinstance(data, dict):
        nested_status = str(data.get("status", "")).strip().lower()
        if nested_status in success_statuses:
            return True, data, nested_status
    return False, data if isinstance(data, dict) else {}, status

def payment_channel_active() -> bool:
    return bool(str(PAYMENT_CHANNEL_ID or "").strip())

async def send_payment_approval_log(
    bot: Bot,
    *,
    user_id: int,
    username: str,
    amount_text: str,
    order_id: str,
    utr: str = "",
    sender_name: str = "",
    payment_time_ist: str = "",
    transaction_id: str = "",
    context_label: str = "TOPUP",
) -> None:
    if not payment_channel_active():
        return

    lines = [
        "✅ PAYMENT VERIFIED",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 Type: {context_label}",
        f"👤 User: {user_id} | @{username}",
        f"💰 Amount: {CURRENCY} {amount_text}",
        f"🧾 Order ID: `{order_id}`",
    ]
    if transaction_id:
        lines.append(f"🔢 Transaction ID: `{transaction_id}`")
    if utr:
        lines.append(f"🔎 UTR: `{utr}`")
    if sender_name:
        lines.append(f"👤 Sender: {sender_name}")
    if payment_time_ist:
        lines.append(f"🕒 Time: {payment_time_ist}")

    try:
        await bot.send_message(
            chat_id=PAYMENT_CHANNEL_ID,
            text="\n".join(lines),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.error(f"Failed to send payment approval log: {exc}")

async def send_payment_timeout_message(bot: Bot, chat_id: int) -> None:
    timeout_msg = (
        f"❌ PAYMENT NOT RECEIVED\n\n"
        f"Yᴏᴜʀ QR ꜱᴇꜱꜱɪᴏɴ ʜᴀꜱ ʙᴇᴇɴ ᴄʟᴏꜱᴇᴅ.\n"
        f"Please try again if payment was not completed.\n\n"
        f"If any problem so, contact : @SL_DEMON_OFC"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=timeout_msg,
        reply_markup=render_payment_cancelled_markup(),
    )

# ==========================================
# 🔄 PAYMENT GATEWAY POLLING GATES
# ==========================================

async def verify_fampay_topup_now(
    bot: Bot,
    chat_id: int,
    user_id: int,
    username: str,
    amount: float,
    order_id: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[bool, str, float]:
    """
    Verify one top-up order immediately.
    Returns: (paid, message_status, new_balance)

    A per-user asyncio lock + persistent credited_payment_orders map
    prevents duplicate wallet credits when polling and VERIFY PAYMENT
    happen at nearly the same time.
    """
    order_id = str(order_id).strip()
    if not order_id:
        return False, "invalid_order", 0.0

    lock_key = str(user_id)
    lock = PAYMENT_VERIFY_LOCKS.setdefault(lock_key, asyncio.Lock())

    async with lock:
        user_record = await initialize_user_registers(user_id)
        credited_orders = user_record.get("credited_payment_orders", {}) or {}

        if order_id in credited_orders:
            return True, "already_credited", float(user_record.get("balance", 0.0))

        verify_url = build_fampay_verify_url(order_id)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(verify_url, timeout=15) as resp:
                    if resp.status != 200:
                        return False, f"http_{resp.status}", float(user_record.get("balance", 0.0))
                    res_json = await resp.json(content_type=None)
        except Exception as exc:
            logger.error(f"Manual FamPay verification error: {exc}")
            return False, "network_error", float(user_record.get("balance", 0.0))

        is_paid, data, status = extract_fampay_success_payload(res_json)
        if not is_paid:
            return False, status or "pending", float(user_record.get("balance", 0.0))

        credited_orders[order_id] = {
            "amount": float(amount),
            "credited_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "transaction_id": str(
                data.get("transaction_id")
                or data.get("txn_id")
                or data.get("utr")
                or ""
            ),
        }
        await LocalDatabaseRouter.set_node(
            DB_USERS_FILE,
            f"{user_id}/credited_payment_orders",
            credited_orders,
        )

        new_bal = await process_wallet_balance_mutation(user_id, float(amount))
        return True, "credited", new_bal


async def poll_fampay_topup_gate(
    bot: Bot, chat_id: int, user_id: int, username: str,
    amount: float, order_id: str, tx_state_id: str, context: ContextTypes.DEFAULT_TYPE
):
    start_time = time.time()

    while time.time() - start_time < 300:  # 5 min timeout
        if context.user_data.get("current_tx_state_id") != tx_state_id:
            return

        is_paid, status, new_bal = await verify_fampay_topup_now(
            bot, chat_id, user_id, username, amount, order_id, context
        )

        if is_paid:
            msg_id = context.user_data.get("active_payment_message_id")
            if msg_id:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass

            context.user_data.pop("current_tx_state_id", None)
            context.user_data.pop("active_payment_message_id", None)
            context.user_data.pop("active_payment_order_id", None)
            context.user_data.pop("active_payment_amount", None)
            context.user_data.pop("active_payment_mode", None)

            # Avoid sending a duplicate success message if the VERIFY button
            # already completed the transaction.
            if status == "credited":
                success_text = (
                    f"✅ PAYMENT SUCCESSFUL!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Amount Deposited: {CURRENCY} {amount:.2f}\n"
                    f"💵 Updated Balance: {CURRENCY} {new_bal:.2f}\n"
                    f"🧾 Order ID: `{order_id}`\n\n"
                    f"Thank you for your top-up!"
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=success_text,
                    parse_mode="Markdown",
                    reply_markup=render_back_navigation_markup(),
                )
                await send_payment_approval_log(
                    bot,
                    user_id=user_id,
                    username=username,
                    amount_text=f"{amount:.2f}",
                    order_id=order_id,
                    context_label="TOPUP",
                )
            return

        await asyncio.sleep(5)

    if context.user_data.get("current_tx_state_id") == tx_state_id:
        msg_id = context.user_data.get("active_payment_message_id")
        if msg_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        context.user_data.pop("current_tx_state_id", None)
        context.user_data.pop("active_payment_message_id", None)
        context.user_data.pop("active_payment_order_id", None)
        context.user_data.pop("active_payment_amount", None)
        context.user_data.pop("active_payment_mode", None)
        await send_payment_timeout_message(bot, chat_id)


async def poll_fampay_checkout_gate(
    bot: Bot, chat_id: int, user_id: int, username: str,
    needed_amount: float, prod_key_path: str, day: str,
    selected_serial_key: str, target_key_id: str, total_price: float,
    order_id: str, tx_state_id: str, context: ContextTypes.DEFAULT_TYPE
):
    poll_url = build_fampay_verify_url(order_id)
    start_time = time.time()
    
    while time.time() - start_time < 300:
        if context.user_data.get("current_tx_state_id") != tx_state_id:
            return
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(poll_url, timeout=10) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        is_paid, data, _ = extract_fampay_success_payload(res_json)
                        if is_paid:
                            msg_id = context.user_data.get("active_payment_message_id")
                            if msg_id:
                                try: await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                                except Exception: pass

                            key_path = f"categories/{prod_key_path}" if ":" in prod_key_path else prod_key_path
                            prod_node = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, key_path) or {}
                            
                            await LocalDatabaseRouter.delete_node(DB_PRODUCTS_FILE, f"{key_path}/keys/{day}/{target_key_id}")
                            user_record = await initialize_user_registers(user_id)
                            
                            await award_referral_bonus_pipeline(bot, str(user_id))
                            
                            purchased_dict = user_record.get('purchased_keys', {}) or {}
                            new_purchase_id = f"key_{int(time.time() * 1000)}"
                            item_title = f"{prod_node.get('name', 'Product')}"
                            purchased_dict[new_purchase_id] = {
                                "item": f"{item_title} ({day} Days)",
                                "key": selected_serial_key,
                                "date": str(datetime.date.today())
                            }
                            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/purchased_keys", purchased_dict)
                            context.user_data.pop("current_tx_state_id", None)
                            
                            success_txt = (
                                f"🔐 Your License Keys 🔐\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🥰 Product Name : {item_title}\n"
                                f"⏰ Product Duration : {day} Days\n"
                                f"🔐 License Key : `{selected_serial_key}`\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            )
                            await bot.send_message(chat_id=chat_id, text=success_txt, reply_markup=render_back_navigation_markup(), parse_mode="Markdown")
                            await send_payment_approval_log(bot, user_id=user_id, username=username, amount_text=f"{needed_amount:.2f}", order_id=order_id, context_label="CHECKOUT")
                            return
            except Exception as e:
                logger.error(f"Polling checkout gate error: {e}")
                
        await asyncio.sleep(5)

    if context.user_data.get("current_tx_state_id") == tx_state_id:
        msg_id = context.user_data.get("active_payment_message_id")
        if msg_id:
            try: await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception: pass
        context.user_data.pop("current_tx_state_id", None)
        await send_payment_timeout_message(bot, chat_id)

# ==========================================
# 🧭 CORE TELEGRAM TELEMETRY HANDLERS
# ==========================================

def render_phone_verify_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Share Your Phone Number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Tap to share your phone number"
    )


async def require_phone_verification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_record: Dict[str, Any]) -> bool:
    if not PHONE_VERIFY_ENABLED:
        return False
    if bool(user_record.get("phone_verified", False)) and str(user_record.get("phone_number", "")).strip():
        return False

    await update.message.reply_text(
        "📱 **VERIFY YOUR ACCOUNT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please share your phone number to verify your account and continue.\n\n"
        "🔒 Your number is stored only for account verification.",
        reply_markup=render_phone_verify_keyboard(),
        parse_mode="Markdown"
    )
    return True


async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user = update.effective_user

    if MAINTENANCE_MODE and not is_admin_user(user.id):
        m_msg = (
            f"🛠️ **BOT UNDER MAINTENANCE** 🛠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The store system is currently undergoing scheduled maintenance.\n"
            f"Please try again later. Contact support for urgent issues:\n"
            f"📞 Support: {SUPPORT_HANDLE}"
        )
        await update.message.reply_text(m_msg, parse_mode="Markdown")
        return

    curr_time = time.time()
    if user.id in SPAM_TRACKER and (curr_time - SPAM_TRACKER[user.id]) < RATE_LIMIT_DELAY: 
        return 
    SPAM_TRACKER[user.id] = curr_time 
    
    referred_by = None
    if context.args and len(context.args) > 0:
        possible_ref = context.args[0].replace("ref_", "").strip()
        if possible_ref.isdigit() and int(possible_ref) != user.id:
            referred_by = str(possible_ref)

    username = user.username if user.username else user.first_name
    user_record = await initialize_user_registers(user.id, username, user.first_name, referred_by=referred_by)

    if await require_phone_verification(update, context, user_record):
        return

    await build_and_transmit_main_frame(context.bot, update.message.chat_id, user.id, username) 


def render_buybot_keyboard(admin_mode: bool = False) -> InlineKeyboardMarkup:
    """Dedicated Buy Bot menu; admin mode uses a Back button to Admin Panel."""
    back_button = (
        InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger")
        if admin_mode else
        InlineKeyboardButton("🔙 Back to Shop", callback_data="buybot_back_shop", style="danger")
    )
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠️ Create Your Bot", callback_data="buybot_create", style="primary")],
        [InlineKeyboardButton("💻 Buy Source Code", callback_data="buybot_source", style="primary")],
        [back_button],
    ])


async def send_buybot_menu(bot: Bot, chat_id: int, edit_message=None, admin_mode: bool = False):
    """Show the Buy Bot screen shown in the supplied reference image."""
    text = (
        "🤖 **GET YOUR OWN BOT**\n\n"
        "Start your own business with this bot 🚀\n\n"
        "Choose option below:"
    )
    markup = render_buybot_keyboard(admin_mode=admin_mode)
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
            return
        except Exception:
            pass
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")


async def buybot_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    if MAINTENANCE_MODE and not is_admin_user(user.id):
        await update.message.reply_text(
            "🛠️ **BOT UNDER MAINTENANCE**\n\nPlease try again later.",
            parse_mode="Markdown"
        )
        return
    await send_buybot_menu(context.bot, update.message.chat_id)


async def buybot_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dedicated /buybot callback router for normal users.

    These callbacks are registered before the global router so the Buy Bot
    menu cannot be swallowed by maintenance/admin/profile routing or the
    general anti-spam gate. Existing button styles/colors are unchanged.
    """
    query = update.callback_query
    if not query or not query.message:
        return

    data = query.data or ""
    if data not in {"buybot_create", "buybot_source", "buybot_back", "buybot_back_shop"}:
        return

    try:
        await query.answer()
    except Exception:
        pass

    chat_id = query.message.chat_id

    if data == "buybot_create":
        await query.edit_message_text(
            "🛠️ **CREATE YOUR BOT**\n\n"
            "To create your own bot, contact the support/admin and send your required bot name and setup details.\n\n"
            f"📞 Support: {SUPPORT_HANDLE}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📞 Contact Support",
                    url=f"https://t.me/{SUPPORT_HANDLE.replace('@', '')}",
                    style="primary"
                )],
                [InlineKeyboardButton("🔙 Back", callback_data="buybot_back", style="danger")],
            ]),
            parse_mode="Markdown",
        )
        return

    if data == "buybot_source":
        await query.edit_message_text(
            "💻 **BUY SOURCE CODE**\n\n"
            "For the source-code package and current price, contact the admin/support.\n\n"
            f"📞 Support: {SUPPORT_HANDLE}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📞 Contact Support",
                    url=f"https://t.me/{SUPPORT_HANDLE.replace('@', '')}",
                    style="primary"
                )],
                [InlineKeyboardButton("🔙 Back", callback_data="buybot_back", style="danger")],
            ]),
            parse_mode="Markdown",
        )
        return

    if data == "buybot_back":
        await send_buybot_menu(context.bot, chat_id, edit_message=query.message)
        return

    if data == "buybot_back_shop":
        await _send_new_menu_shop(context.bot, chat_id)
        return


async def admin_panel_launcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    # Owner + the admin ID assigned to any saved co-admin bot can open /admin.
    if not is_admin_user(update.effective_user.id): return
    
    users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, '') or {}
    total_users = len(users)
    ʀᴇꜱᴇʟʟᴇʀs_count = sum(1 for u in users.values() if u.get('is_ʀᴇꜱᴇʟʟᴇʀ'))
    
    categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
    total_stock = 0
    for c in categories.values():
        for p in c.get('panels', {}).values():
            for klist in p.get('keys', {}).values():
                if isinstance(klist, dict):
                    total_stock += len([k for k in klist.keys() if k != "init_node_secured"])
                    
    m_txt = "🔴 ACTIVE (Users Blocked)" if MAINTENANCE_MODE else "🟢 INACTIVE (Bot Live)"
    admin_text = (
        f"⚙️ **ADMIN CONTROL PANEL**\n\n"
        f"Complete button control is enabled. Commands are optional backups.\n\n"
        f"🧑‍✈️ Loaded Admin IDs: **{len(get_all_admin_ids())}**\n"
        f"🛠️ Maintenance Mode: **{m_txt}**\n\n"
        f"👥 Users: **{total_users}**\n"
        f"💎 ʀᴇꜱᴇʟʟᴇʀs: **{ʀᴇꜱᴇʟʟᴇʀs_count}**\n"
        f"🥰 Available Stock: **{total_stock}**\n"
        f"🛒 Completed Orders: **0**\n"
        f"⏳ Pending Payments: **0**"
    )
    await update.message.reply_text(admin_text, reply_markup=render_admin_panel_keyboard(), parse_mode="Markdown")

async def build_and_transmit_main_frame(bot: Bot, chat_id: int, user_id: int, username: str, edit_msg_id: int = None):
    """Send the new main screen while keeping the existing theme/settings."""
    user_record = await initialize_user_registers(user_id)

    dashboard_text = render_home_message(user_id, user_record.get("balance", 0.0), username)

    if edit_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=edit_msg_id)
        except Exception:
            pass

    await bot.send_message(
        chat_id=chat_id,
        text=dashboard_text,
        reply_markup=render_main_menu_keyboard(user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False)),
        parse_mode="HTML",
    )

# ==========================================
# 🎚 CALLBACK ROUTING INTERFACE ENGINE
# ==========================================

async def coadmin_menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dedicated CO-ADMIN menu callback so the button is always routed before
    the catch-all callback handler. UI button styles/colors are unchanged."""
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    if not is_admin_user(user_id):
        await query.answer("⛔ Admin access only.", show_alert=True)
        return

    try:
        await query.answer()
    except Exception:
        pass

    records = get_managed_bot_records()
    lines = [
        "👥 CO-ADMIN / BOT MANAGER",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "Send a bot token + admin ID to connect a managed bot.",
        "Format: BOT_TOKEN | ADMIN_ID",
        "",
    ]

    if records:
        lines.append(f"Connected bots: {len(records)}")
        for key, rec in list(records.items())[:10]:
            lines.append(
                f"• @{rec.get('username', 'unknown')} — Admin ID {rec.get('admin_id')}"
            )
    else:
        lines.append("No co-admin bots connected yet.")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD CO-ADMIN BOT", callback_data="adm_coadmin_add", style="success")],
        [InlineKeyboardButton("🔄 START SAVED BOTS", callback_data="adm_coadmin_start", style="primary")],
        [InlineKeyboardButton("🗑️ REMOVE CO-ADMIN BOT", callback_data="adm_coadmin_remove", style="danger")],
        [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger")],
    ])

    chat_id = query.message.chat_id if query.message else user_id
    try:
        if query.message:
            await query.edit_message_text("\n".join(lines), reply_markup=kb)
        else:
            await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), reply_markup=kb)
    except Exception as exc:
        logger.warning("CO-ADMIN menu edit failed, sending new message: %s", exc)
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), reply_markup=kb)


async def global_callback_routing_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE, PHONE_VERIFY_ENABLED, MERCHANT_UPI_ID, STATIC_MANUAL_QR_LINK
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id 
    first_name = query.from_user.first_name
    username = query.from_user.username if query.from_user.username else query.from_user.first_name 
    chat_id = query.message.chat_id 
    data = query.data
    t_now = time.time()

    # Main dashboard buttons are inline and must be handled first.
    if data in MAIN_MENU_CALLBACKS:
        await handle_new_main_menu_callback(update, context)
        return

    # Admin navigation callbacks must never be swallowed by the general
    # anti-spam gate.  This keeps BOT SETTINGS -> CO-ADMIN responsive.
    admin_navigation_callbacks = {
        "adm_bot_settings_menu",
        "adm_coadmin_menu",
        "adm_coadmin_add",
        "adm_coadmin_start",
        "adm_coadmin_remove",
        "adm_buybot",
        "adm_admin_manage",
        "adm_admin_add",
        "adm_admin_remove",
        # Users & Wallet buttons must bypass the global anti-spam gate.
        "adm_manage_bal_menu",
        "adm_bal_check",
        "adm_list_users",
        "adm_phone_numbers",
        # Statistics must bypass the global anti-spam/rate-limit gate.
        "adm_check_keys_all",
    }

    # Profile controls must never be swallowed by the global anti-spam gate.
    # These buttons are also used from a photo-based profile message.
    profile_navigation_callbacks = {
        "ui_my_keys",
        "ui_route_auto",
        "ui_route_manual",
        "ui_phone_verify",
        "back_main",
    }

    if data in admin_navigation_callbacks and not is_admin_user(user_id):
        await query.answer("⛔ Admin access only.", show_alert=True)
        return

    if MAINTENANCE_MODE and not is_admin_user(user_id):
        m_msg = (
            f"🛠️ **BOT UNDER MAINTENANCE** 🛠️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"The store system is currently undergoing scheduled maintenance.\n"
            f"Please try again later. Contact support for urgent issues:\n"
            f"📞 Support: {SUPPORT_HANDLE}"
        )
        try:
            await query.edit_message_text(m_msg, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=m_msg, parse_mode="Markdown")
        return
    
    if data not in admin_navigation_callbacks and data not in profile_navigation_callbacks:
        if user_id in SPAM_TRACKER and (t_now - SPAM_TRACKER[user_id]) < RATE_LIMIT_DELAY:
            return
        SPAM_TRACKER[user_id] = t_now
    
    if data == "back_main":
        try:
            await query.message.delete()
        except Exception: pass
        await build_and_transmit_main_frame(context.bot, chat_id, user_id, username)
        return

    elif data == "verify_payment":
        active_order_id = str(context.user_data.get("active_payment_order_id", "")).strip()
        active_amount = float(context.user_data.get("active_payment_amount", 0) or 0)
        active_mode = context.user_data.get("active_payment_mode")

        if active_mode != "topup" or not active_order_id or active_amount <= 0:
            await query.answer("No active top-up payment found.", show_alert=True)
            return

        # Stop the background poller for this transaction while the manual
        # verification request is being handled.
        context.user_data["verify_button_busy"] = True
        await query.answer("Checking payment...")

        try:
            await query.edit_message_caption(
                caption=(
                    f"💳 PAYMENT INSTRUCTIONS\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Amount : {CURRENCY} {active_amount:.2f}\n"
                    f"🧾 Order ID : {active_order_id}\n\n"
                    f"⏳ VERIFYING PAYMENT...\n"
                    f"Please wait..."
                ),
                reply_markup=render_payment_cancel_markup(),
            )
        except Exception:
            pass

        is_paid, status, new_bal = await verify_fampay_topup_now(
            context.bot,
            chat_id,
            user_id,
            username,
            active_amount,
            active_order_id,
            context,
        )

        context.user_data["verify_button_busy"] = False

        if is_paid:
            msg_id = context.user_data.get("active_payment_message_id")
            if msg_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass

            context.user_data.pop("current_tx_state_id", None)
            context.user_data.pop("active_payment_message_id", None)
            context.user_data.pop("active_payment_order_id", None)
            context.user_data.pop("active_payment_amount", None)
            context.user_data.pop("active_payment_mode", None)

            if status == "credited":
                success_text = (
                    f"✅ PAYMENT SUCCESSFUL!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 Amount Deposited: {CURRENCY} {active_amount:.2f}\n"
                    f"💵 Updated Balance: {CURRENCY} {new_bal:.2f}\n"
                    f"🧾 Order ID: `{active_order_id}`\n\n"
                    f"Wallet balance has been updated automatically."
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=success_text,
                    parse_mode="Markdown",
                    reply_markup=render_back_navigation_markup(),
                )
                await send_payment_approval_log(
                    context.bot,
                    user_id=user_id,
                    username=username,
                    amount_text=f"{active_amount:.2f}",
                    order_id=active_order_id,
                    context_label="TOPUP",
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ PAYMENT ALREADY VERIFIED\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Amount: {CURRENCY} {active_amount:.2f}\n"
                        f"💵 Current Balance: {CURRENCY} {new_bal:.2f}\n"
                        f"🧾 Order ID: `{active_order_id}`"
                    ),
                    parse_mode="Markdown",
                    reply_markup=render_back_navigation_markup(),
                )
            return

        # Payment is not confirmed yet: keep the QR + VERIFY button alive.
        status_text = (
            "Payment is not confirmed yet."
            if status in {"pending", "", "ok"}
            else "Payment could not be verified right now."
        )
        try:
            await query.edit_message_caption(
                caption=(
                    f"💳 PAYMENT INSTRUCTIONS\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Amount : {CURRENCY} {active_amount:.2f}\n"
                    f"🧾 Order ID : {active_order_id}\n\n"
                    f"⚠️ {status_text}\n"
                    f"After completing payment, tap VERIFY PAYMENT again."
                ),
                reply_markup=render_payment_cancel_markup(),
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ {status_text}\n"
                    f"💰 Amount: {CURRENCY} {active_amount:.2f}\n"
                    f"🧾 Order ID: `{active_order_id}`\n\n"
                    f"Tap VERIFY PAYMENT again after payment."
                ),
                reply_markup=render_payment_cancel_markup(),
            )
        return

    elif data == "cancel_payment":
        try:
            await query.message.delete()
        except Exception:
            pass
        context.user_data.pop("current_tx_state_id", None)
        context.user_data.pop("active_payment_message_id", None)
        context.user_data.pop("active_payment_order_id", None)
        context.user_data.pop("active_payment_amount", None)
        context.user_data.pop("active_payment_mode", None)
        cancel_text = (
            f"❌ PAYMENT CANCELLED\n\n"
            f"Yᴏᴜʀ QR ꜱᴇꜱꜱɪᴏɴ ʜᴀꜱ ʙᴇᴇɴ ᴄʟᴏꜱᴇᴅ.\n"
            f"ɪꜰ ᴀɴʏ ᴘʀᴏʙʟᴇᴍ ꜱᴏ, ᴄᴏɴᴛᴀᴄᴛ : @SL_DEMON_OFC"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=cancel_text,
            reply_markup=render_payment_cancelled_markup(),
        )
        return

    elif data == "ui_profile":
        user_record = await initialize_user_registers(user_id)
        role_label = "VIP ʀᴇꜱᴇʟʟᴇʀ" if user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False) else "User"

        display_name = first_name or user_record.get("first_name") or "User"
        display_username = username or user_record.get("username") or "N/A"
        joined_at = str(user_record.get("registered_at", "N/A"))
        if joined_at != "N/A" and len(joined_at) >= 10:
            joined_at = joined_at[:10]

        profile_caption = (
            f"🎯 USER PROFILE 🎯\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Name: {display_name}\n"
            f"🏷️ Username: @{display_username}\n"
            f"🔗 Joined: {joined_at}\n"
            f"✅ Account Type: {role_label}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Balance: {CURRENCY} {user_record['balance']:.2f}\n"
            f"💸 Spent: {CURRENCY} 0.00\n"
            f"🔐 Keys: {len(user_record.get('purchased_keys', {}) or {})}\n"
            f"📱 Phone: {'Verified ✅' if user_record.get('phone_verified') and user_record.get('phone_number') else 'Not Verified ❌'}\n\n"
            f"📸 Profile photo fetched from Telegram."
        )

        profile_markup = render_profile_keyboard(user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False))

        # Replace the old text-only profile with a Telegram profile-photo card.
        try:
            photos = await context.bot.get_user_profile_photos(user_id=user_id, limit=1)
            if photos.total_count and photos.photos and photos.photos[0]:
                profile_photo_id = photos.photos[0][-1].file_id
                try:
                    await query.message.delete()
                except Exception:
                    pass

                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=profile_photo_id,
                    caption=profile_caption,
                    reply_markup=profile_markup,
                )
            else:
                await query.edit_message_text(
                    profile_caption.replace(
                        "📸 Profile photo fetched from Telegram.",
                        "📸 Profile photo not set on this Telegram account."
                    ),
                    reply_markup=profile_markup,
                )
        except Exception as exc:
            logger.warning(f"Could not fetch Telegram profile photo for {user_id}: {exc}")
            try:
                await query.edit_message_text(profile_caption, reply_markup=profile_markup)
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=profile_caption,
                    reply_markup=profile_markup,
                )
        
    elif data == "ui_phone_verify":
        user_record = await initialize_user_registers(user_id)
        if user_record.get("phone_verified") and str(user_record.get("phone_number", "")).strip():
            await query.edit_message_text(
                "📱 **PHONE VERIFICATION**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ Your account is already verified.\n"
                f"📱 Number: `{user_record.get('phone_number')}`",
                reply_markup=render_back_navigation_markup(),
                parse_mode="Markdown",
            )
            return
        if not PHONE_VERIFY_ENABLED:
            await query.edit_message_text(
                "📱 **PHONE VERIFICATION**\n\n"
                "❌ Phone verification is currently disabled by admin.",
                reply_markup=render_back_navigation_markup(),
            )
            return
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "📱 **VERIFY YOUR ACCOUNT**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please share your own phone number using the button below.\n\n"
                "🔒 It will be stored for account verification."
            ),
            reply_markup=render_phone_verify_keyboard(),
            parse_mode="Markdown",
        )
        return

    elif data == "ui_how_to_use":
        guide_text = (
            "📖 STORE OPERATIONAL GUIDE 📖\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1. Fund Your Store Wallet:\n"
            " - Click Add Fund (Auto) for automated dynamic UPI QR allocations.\n"
            " - Choose Manual Deposit to submit external payments using standard 12-digit UTR verification hashes.\n\n"
            "2. Procure License Assets:\n"
            " - Open the SHOP portal and find your desired software packaging.\n"
            " - Choose your license duration plan to trigger an instant key emission loop.\n\n"
            "3. Access Your Vault History:\n"
            " - Every single key you buy is permanently backed up and stored within your secure My Keys archive.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(
            guide_text,
            reply_markup=(
                render_admin_back_markup() if is_admin_user(user_id)
                else render_back_navigation_markup()
            )
        )
        
    elif data == "ui_my_keys":
        user_record = await initialize_user_registers(user_id)
        keys_dict = user_record.get('purchased_keys', {})
        if not keys_dict:
            await query.edit_message_text(
                "🪅 No Keys Found\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\nYour dynamic license history log index contains no records. Purchase a plan to populate this partition.", 
                reply_markup=render_back_navigation_markup()
            )
            return
        
        txt = "🔐 **YOUR LICENSE KEYS VAULT** 🔐\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        count = 1
        for kid, k_info in keys_dict.items():
            raw_item_title = k_info.get('item', 'N/A')
            p_name = raw_item_title.split(" (")[0] if " (" in raw_item_title else raw_item_title
            p_dur = raw_item_title.split(" (")[1].replace(")", "") if " (" in raw_item_title else "N/A"
            key_val = k_info.get('key', 'UNKNOWN_KEY')
            purchased_date = k_info.get('date', 'N/A')
            
            txt += (
                f"**#{count} | {p_name}**\n"
                f"⏱️ Duration: `{p_dur}`\n"
                f"📅 Date: `{purchased_date}`\n"
                f"🔑 Key: `{key_val}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            count += 1
            
        # The profile is rendered as a Telegram photo message. Telegram does
        # not allow edit_message_text() on photo messages, so replace that
        # message with a normal text message when necessary.
        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=txt,
                reply_markup=render_back_navigation_markup(),
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(
                txt,
                reply_markup=render_back_navigation_markup(),
                parse_mode="Markdown",
            )

    elif data == "ui_refer_earn":
        bot_info = await context.bot.get_me()
        referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        user_record = await initialize_user_registers(user_id)
        
        ref_text = (
            f"🤝 REFER & EARN SYSTEM 🤝\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Invite friends & earn ₹2.00 per successful referral.\n\n"
            f"📊 LIVE Referral:\n"
            f" ├── Total Referrals: {user_record.get('referral_count', 0)} Users\n"
            f" └── Safe Earnings: {CURRENCY} {user_record.get('total_referral_earned', 0.0):.2f}\n\n"
            f"💸 Refer Now:\n"
            f"Get ₹2.00 into your wallet for every successful referral!\n\n"
            f"💸 Reward Per Referral: {CURRENCY} 2.00\n\n"
            f"🔗 LINK: `{referral_link}`"
        )
        share_url = f"https://t.me/share/url?url={referral_link}&text=Join%20this%20store%20bot%20and%20earn%20Rs%202%20per%20successful%20referral!"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Link", url=share_url, style="primary")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]
        ])
        await query.edit_message_text(ref_text, reply_markup=markup)

    elif data == "ui_ʀᴇꜱᴇʟʟᴇʀ_hub":
        user_record = await initialize_user_registers(user_id)
        if user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False):
            await query.edit_message_text(
                f"⭐️ VIP ʀᴇꜱᴇʟʟᴇʀ PORTAL active ⭐️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Status: Fully Authorized ʀᴇꜱᴇʟʟᴇʀ Module\n\n"
                f"Enjoy deep dynamic discount matrix prices on all stock items across our database system catalog automatons.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]])
            )
            return
            
        ʀᴇꜱᴇʟʟᴇʀ_pitch = (
            f"⭐️ UPGRADE TO ʀᴇꜱᴇʟʟᴇʀ ⭐️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Upgrade Fee: {CURRENCY} {ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:.2f} (One-Time Activation License)\n\n"
            f"🚀 EXCLUSIVE UNLOCKED BENEFITS:\n"
            f" ├── All Products Price Is Low.\n"
            f" ├── Instant Buy To Any Key 🔑.\n"
            f" └── Very Low Price.\n\n"
            f"Current Balance: {CURRENCY} {user_record['balance']:.2f}"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Buy Now & Upgrade", callback_data="ui_confirm_ʀᴇꜱᴇʟʟᴇʀ_upgrade", style="success")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]
        ])
        await query.edit_message_text(ʀᴇꜱᴇʟʟᴇʀ_pitch, reply_markup=markup)

    elif data == "ui_confirm_ʀᴇꜱᴇʟʟᴇʀ_upgrade":
        user_record = await initialize_user_registers(user_id)
        if user_record['balance'] < ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:
            deficit = int(ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE - user_record['balance'])
            insufficient_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Add Fund (Auto)", callback_data="ui_route_auto", style="success")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]
            ])
            await query.edit_message_text(
                f"❌ INSUFFICIENT BALANCE DETECTED\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Required Core Activation Amount: {CURRENCY} {ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:.2f}\n"
                f"Your Current Account Liquid Assets: {CURRENCY} {user_record['balance']:.2f}\n"
                f"Required Deficit Core Refunding: {CURRENCY} {deficit:.2f}\n\n"
                f"Please select payment route channels or top-up your system wallet assets code parameters.",
                reply_markup=insufficient_markup
            )
            return
        
        confirm_text = (
            f"🛡️ CONFIRM ʀᴇꜱᴇʟʟᴇʀ MODULE ACTIVATION 🛡️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Purchase Core Value: {CURRENCY} {ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:.2f}\n"
            f"💳 Balance Account Debit Vector: {CURRENCY} {user_record['balance']:.2f} -> {CURRENCY} {(user_record['balance'] - ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE):.2f}\n\n"
            f"Are you sure you want to initialize authorization structural changes?"
        )
        await query.edit_message_text(confirm_text, reply_markup=render_confirmation_keyboard("act_buy_ʀᴇꜱᴇʟʟᴇʀ"))

    elif data == "act_buy_ʀᴇꜱᴇʟʟᴇʀ":
        user_record = await initialize_user_registers(user_id)
        if user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False):
            await query.edit_message_text("❌ Configuration Error: Your account already possesses an active ʀᴇꜱᴇʟʟᴇʀ node signature matrix.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")]]))
            return
            
        if user_record['balance'] < ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:
            await query.edit_message_text("❌ Action Timed out or Balance modified abnormally.", reply_markup=render_back_navigation_markup())
            return
            
        new_bal = await process_wallet_balance_mutation(user_id, -ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE)
        await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/is_ʀᴇꜱᴇʟʟᴇʀ", True)
        
        await query.edit_message_text(
            f"🎉 UPGRADE SUCCESSFUL 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐️ Welcome to the Inner Circle ʀᴇꜱᴇʟʟᴇʀ Network!\n"
            f"Deducted Fee: {CURRENCY} {ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:.2f}\n"
            f"Remaining Account Ledger: {CURRENCY} {new_bal:.2f}\n\n"
            f"Your dynamic store catalog discount completely updated and synchronized.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Enter Shop Hub", callback_data="ui_shop_prods", style="success")]])
        )
        
        admin_res_alert = (
            f"⭐️ NEW PREMIUM ʀᴇꜱᴇʟʟᴇʀ ACCOUNT ACTIVATED ⭐️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User Profile: @{username}\n"
            f"🆔 Numerical Identity Signature: {user_id}\n"
            f"💰 Paid Processing Fee: {CURRENCY} {ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:.2f}\n"
            f"📊 Account Balance Updated: {CURRENCY} {new_bal:.2f}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_res_alert)
        except Exception: pass

    elif data in ["ui_route_manual", "ui_route_auto"]:
        mode = "manual" if data == "ui_route_manual" else "auto"
        context.user_data['dial_string'] = ""

        amount_text = (
            f"Enter Your Amount\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👉 Current Amount: {CURRENCY} 0"
        )
        amount_markup = render_matrix_dialpad(mode)

        # Profile is a photo message, and Telegram cannot convert a photo
        # message into a text message with edit_message_text(). Replace it
        # cleanly so Add Fund works from the profile screen.
        if query.message and query.message.photo:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=chat_id,
                text=amount_text,
                reply_markup=amount_markup,
            )
        else:
            await query.edit_message_text(
                amount_text,
                reply_markup=amount_markup,
            )
        
    elif data.startswith("pad_"):
        parts = data.split("_")
        mode, action = parts[1], parts[2]
        current_str = context.user_data.get('dial_string', "")
        
        if action.isdigit():
            current_str += action
            context.user_data['dial_string'] = current_str
            try:
                await query.edit_message_text(f"Enter Your Amount\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n👉 Current Amount: {CURRENCY} {current_str}", reply_markup=render_matrix_dialpad(mode))
            except Exception: pass
        elif action == "backspace":
            if current_str:
                current_str = current_str[:-1]
            context.user_data['dial_string'] = current_str
            display = current_str if current_str else "0"
            try:
                await query.edit_message_text(f"Enter Your Amount\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n👉 Current Amount: {CURRENCY} {display}", reply_markup=render_matrix_dialpad(mode))
            except Exception: pass
        elif action == "commit":
            if not current_str or int(current_str) <= 0: return
            final_amount = int(current_str)
            try:
                await query.message.delete()
            except Exception: pass
            
            if mode == "manual":
                context.user_data['state_route'] = 'EXPECTING_MANUAL_UTR'
                context.user_data['pending_deposit_amt'] = float(final_amount)
                
                caption = (
                    f"⚙️ Manual Deposit System\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💰 Selected Value: {CURRENCY} {final_amount}.00\n"
                    f"🎯 Target Channel: {MERCHANT_UPI_ID}\n\n"
                    f"👉 Please pay exactly {CURRENCY} {final_amount} via the provided channel QR.\n\n"
                    f"Once completed, reply directly to this message by pasting your 12-digit transaction UTR number:"
                )
                await context.bot.send_photo(
                    chat_id=chat_id, 
                    photo=STATIC_MANUAL_QR_LINK, 
                    caption=caption, 
                    reply_markup=render_back_navigation_markup()
                )
            
            else:
                processing_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="⏳ GENERATING PAYMENT QR..."
                )
                request_api_url = build_fampay_qr_url(MERCHANT_UPI_ID, final_amount)
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(request_api_url, timeout=15) as response:
                            if response.status == 200:
                                payload = await response.json()
                                if payload.get("status") == "success":
                                    core_data = payload.get("data", {}) or {}
                                    live_qr_link = core_data.get("qr_url") or core_data.get("qr_image") or core_data.get("qr")
                                    order_id = str(core_data.get("order_id", "")).strip()

                                    if not live_qr_link or not order_id:
                                        raise ValueError("QR API response missing qr_url or order_id")

                                    caption = (
                                        f"💳 PAYMENT INSTRUCTIONS\n"
                                        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                        f"💰 Amount : {CURRENCY} {final_amount:.2f}\n"
                                        f"🔗 UPI ID : {MERCHANT_UPI_ID}\n"
                                        f"👤 Holder Name : {UPI_HOLDER_NAME}\n"
                                        f"🧾 Order ID : {order_id}\n"
                                        f"⏳ QR Expires In : 5 Minutes\n\n"
                                        f"Payment by QR\n\n"
                                        f"If any problem so, contact : {SUPPORT_HANDLE}"
                                    )

                                    try:
                                        await processing_msg.delete()
                                    except Exception:
                                        pass

                                    tx_state_id = str(uuid.uuid4())
                                    context.user_data["current_tx_state_id"] = tx_state_id
                                    context.user_data["active_payment_order_id"] = order_id
                                    context.user_data["active_payment_amount"] = float(final_amount)
                                    context.user_data["active_payment_mode"] = "topup"

                                    sent_msg = await context.bot.send_photo(
                                        chat_id=chat_id,
                                        photo=live_qr_link,
                                        caption=caption,
                                        reply_markup=render_payment_cancel_markup(),
                                    )
                                    context.user_data["active_payment_message_id"] = sent_msg.message_id

                                    asyncio.create_task(
                                        poll_fampay_topup_gate(
                                            context.bot,
                                            chat_id,
                                            user_id,
                                            username,
                                            final_amount,
                                            order_id,
                                            tx_state_id,
                                            context,
                                        )
                                    )
                                    return
                    except Exception as e:
                        logger.error(f"Error requesting Auto QR: {e}")
                try:
                    await processing_msg.edit_text("❌ Payment QR generation failed. Please try again.")
                except Exception:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ Payment QR generation failed. Please try again.",
                        reply_markup=render_payment_cancelled_markup(),
                    )

    elif data == "ui_shop_prods":
        categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
        active_categories = {k: v for k, v in categories.items() if v.get('active', True)}
        
        if not active_categories:
            await query.edit_message_text("❌ No active store categories found right now.", reply_markup=render_back_navigation_markup())
            return
            
        buttons = []
        for cat_id, cat_info in active_categories.items():
            display_name = cat_info.get('name', cat_id.upper())
            cat_emoji_id = str(cat_info.get("emoji_id", "") or "").strip()
            buttons.append([_premium_button(
                display_name,
                callback_data=f"user_view_cat_{cat_id}",
                style="primary",
                custom_emoji_id=cat_emoji_id
            )])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")])
        await query.edit_message_text(f"🛒 Select A Category 👇", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("user_view_cat_"):
        cat_id = data.replace("user_view_cat_", "").strip()
        cat_info = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        panels = cat_info.get("panels", {}) if isinstance(cat_info, dict) else {}
        active_panels = {
            k: v for k, v in panels.items()
            if isinstance(v, dict) and v.get("active", True)
        }

        if not active_panels:
            await query.edit_message_text(
                "❌ No active panels in this category.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 BACK", callback_data="ui_shop_prods", style="danger")
                ]]),
            )
            return

        category_name = str(cat_info.get("name", cat_id.upper())).strip()
        buttons = []
        for p_id, p_info in active_panels.items():
            display_name = str(p_info.get("name", p_id.upper())).strip()
            panel_emoji_id = str(p_info.get("emoji_id", "") or "").strip()
            buttons.append([_premium_button(
                display_name,
                callback_data=f"user_flat_days_{cat_id}:{p_id}",
                style="primary",
                custom_emoji_id=panel_emoji_id
            )])
        buttons.append([
            InlineKeyboardButton("🔙 BACK", callback_data="ui_shop_prods", style="danger")
        ])

        panel_list_text = (
            f"✨ **{category_name.upper()} PANELS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✨ **Choose a panel name:**"
        )
        await query.edit_message_text(
            panel_list_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )

    elif data.startswith("user_flat_days_"):
        payload = data.replace("user_flat_days_", "").strip()
        if ":" in payload:
            cat_id, p_id = payload.split(":", 1)
        else:
            cat_id, p_id = "", payload

        prod_node = (
            await LocalDatabaseRouter.get_node(
                DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}"
            )
            if cat_id
            else await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, p_id)
        )
        if not prod_node:
            await query.edit_message_text(
                "❌ Product/Panel not found.",
                reply_markup=render_back_navigation_markup(),
            )
            return

        plans = prod_node.get("plans", {})
        if not isinstance(plans, dict) or not plans:
            back_target = f"user_view_cat_{cat_id}" if cat_id else "ui_shop_prods"
            await query.edit_message_text(
                "❌ No duration plans have been added for this product.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 BACK", callback_data=back_target, style="danger")
                ]]),
            )
            return

        user_record = await initialize_user_registers(user_id)
        is_user_reseller = bool(user_record.get("is_ʀᴇꜱᴇʟʟᴇʀ", False))

        category_node = (
            await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}")
            if cat_id else {}
        ) or {}
        category_name = str(
            category_node.get("name", cat_id.upper() if cat_id else "PRODUCT")
        ).strip()
        product_name = str(prod_node.get("name", p_id.upper())).strip()
        card_title = f"{category_name.upper()} - {product_name.upper()} PACKAGES"

        card_lines = [
            f"✨ **{card_title}**",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        buttons = []
        for day, pricing in plans.items():
            if isinstance(pricing, dict) and not pricing.get("active", True):
                continue

            price = _user_store_price(pricing, is_user_reseller)
            stock = _user_store_stock_count(prod_node, day)
            # Keep unavailable plans hidden, but do not display stock counts.
            if stock <= 0:
                continue

            validity = _user_store_validity(day)
            card_lines.append(f"💰 {CURRENCY}{price:.2f} — 💰 {validity}")

            button_text = f"✅ {validity} • {CURRENCY} {price:.2f}"
            button_style = "success"

            buttons.append([InlineKeyboardButton(
                button_text,
                callback_data=f"user_buy_confirm_{cat_id}:{p_id}:{day}",
                style=button_style,
            )])

        if not buttons:
            back_target = f"user_view_cat_{cat_id}" if cat_id else "ui_shop_prods"
            await query.edit_message_text(
                "❌ No active packages are available for this product.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 BACK", callback_data=back_target, style="danger")
                ]]),
            )
            return

        card_lines.extend(["", "✨ **Select package below to instantly purchase:**"])

        back_target = f"user_view_cat_{cat_id}" if cat_id else "ui_shop_prods"
        buttons.append([
            InlineKeyboardButton("🔙 BACK", callback_data=back_target, style="danger")
        ])

        await query.edit_message_text(
            "\n".join(card_lines),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )

    elif data.startswith("user_buy_confirm_"):
        raw_payload = data.replace("user_buy_confirm_", "")
        parts = raw_payload.split(":", 2)
        cat_id, pid, day = parts[0], parts[1], parts[2]
        
        prod_node = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{pid}") if cat_id else await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, pid)
        
        if not prod_node or 'plans' not in prod_node or day not in prod_node['plans']:
            await query.edit_message_text("❌ Selected execution plan contains configuration faults.", reply_markup=render_back_navigation_markup())
            return
            
        pricing_node = prod_node['plans'][day]
        user_record = await initialize_user_registers(user_id)
        is_user_ʀᴇꜱᴇʟʟᴇʀ = user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False)
        
        if isinstance(pricing_node, dict):
            price = float(pricing_node.get('ʀᴇꜱᴇʟʟᴇʀ', pricing_node.get('standard', 0.0))) if is_user_ʀᴇꜱᴇʟʟᴇʀ else float(pricing_node.get('standard', 0.0))
        else:
            price = float(pricing_node)
            
        keys_pool_dict = prod_node.get('keys', {}).get(day, {})
        if isinstance(keys_pool_dict, dict):
            keys_pool_dict = {k: v for k, v in keys_pool_dict.items() if k != "init_node_secured"}
            
        if not keys_pool_dict or len(keys_pool_dict) == 0:
            await query.edit_message_text("❌ Low Stock! Please check back later.", reply_markup=render_back_navigation_markup())
            return
            
        product_name_str = prod_node.get('name', pid.upper())
        
        if user_record['balance'] < price:
            needed_amount = int(price - user_record['balance'])
            processing_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text="⏳ GENERATING PAYMENT QR..."
                )
            request_api_url = build_fampay_qr_url(MERCHANT_UPI_ID, needed_amount)
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(request_api_url, timeout=15) as response:
                        if response.status == 200:
                            payload = await response.json()
                            if payload.get("status") == "success":
                                core_data = payload.get("data", {}) or {}
                                live_qr_link = core_data.get("qr_url") or core_data.get("qr_image") or core_data.get("qr")
                                order_id = str(core_data.get("order_id", "")).strip()

                                if not live_qr_link or not order_id:
                                    raise ValueError("QR API response missing qr_url or order_id")

                                caption = (
                                    f"💳 PAYMENT INSTRUCTIONS\n"
                                    f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                    f"🥰 Selected Product: {product_name_str}\n"
                                    f"⏳ Selected Plan: {day} Days\n"
                                    f"💰 Total Amount: {CURRENCY} {price:.2f}\n"
                                    f"💳 Required Topup: {CURRENCY} {needed_amount:.2f}\n"
                                    f"🧾 Order ID: {order_id}\n"
                                    f"⏳ QR Expires In : 5 Minutes\n\n"
                                    f"Payment by QR\n\n"
                                    f"If any problem so, contact : {SUPPORT_HANDLE}"
                                )
                                try:
                                    await processing_msg.delete()
                                    await query.message.delete()
                                except Exception:
                                    pass

                                target_key_id = next(iter(keys_pool_dict))
                                selected_serial_key = keys_pool_dict[target_key_id]

                                tx_state_id = str(uuid.uuid4())
                                context.user_data["current_tx_state_id"] = tx_state_id
                                context.user_data["active_payment_order_id"] = order_id
                                context.user_data["active_payment_mode"] = "checkout"

                                sent_msg = await context.bot.send_photo(
                                    chat_id=chat_id,
                                    photo=live_qr_link,
                                    caption=caption,
                                    reply_markup=render_payment_cancel_markup(),
                                )
                                context.user_data["active_payment_message_id"] = sent_msg.message_id

                                asyncio.create_task(
                                    poll_fampay_checkout_gate(
                                        context.bot,
                                        chat_id,
                                        user_id,
                                        username,
                                        needed_amount,
                                        f"{cat_id}:{pid}",
                                        day,
                                        selected_serial_key,
                                        target_key_id,
                                        price,
                                        order_id,
                                        tx_state_id,
                                        context,
                                    )
                                )
                                return
                except Exception as e:
                    logger.error(f"Error in custom checkout: {e}")
            try:
                await processing_msg.edit_text("❌ Checkout pipeline automation fault. Failed to synchronize state tracking logic.")
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Checkout pipeline automation fault. Failed to synchronize state tracking logic.",
                    reply_markup=render_payment_cancelled_markup(),
                )

            return

        confirm_text = (
            f"🛒 CONFIRM PURCHASE ORDER 🛒\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥰 Product Name : {product_name_str}\n"
            f"⏰ Product Duration : {day} Days\n"
            f"💰 Product Price : {CURRENCY} {price:.2f}\n"
            f"💵 Your Wallet Balance : {CURRENCY} {user_record['balance']:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\"Please click the button below and let us know whether you would like to purchase the product or not.\""
        )
        await query.edit_message_text(confirm_text, reply_markup=render_confirmation_keyboard(f"user_buy_flat_key_{cat_id}:{pid}:{day}"))
        
    elif data.startswith("user_buy_flat_key_"):
        raw_payload = data.replace("user_buy_flat_key_", "")
        parts = raw_payload.split(":", 2)
        cat_id, pid, day = parts[0], parts[1], parts[2]
        
        key_path = f"categories/{cat_id}/panels/{pid}" if cat_id else pid
        prod_node = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, key_path) or {}
        
        pricing_node = prod_node['plans'][day]
        user_record = await initialize_user_registers(user_id)
        is_user_ʀᴇꜱᴇʟʟᴇʀ = user_record.get('is_ʀᴇꜱᴇʟʟᴇʀ', False)
        
        if isinstance(pricing_node, dict):
            price = float(pricing_node.get('ʀᴇꜱᴇʟʟᴇʀ', pricing_node.get('standard', 0.0))) if is_user_ʀᴇꜱᴇʟʟᴇʀ else float(pricing_node.get('standard', 0.0))
        else:
            price = float(pricing_node)
            
        keys_pool_dict = prod_node.get('keys', {}).get(day, {})
        if isinstance(keys_pool_dict, dict):
            keys_pool_dict = {k: v for k, v in keys_pool_dict.items() if k != "init_node_secured"}
            
        if not keys_pool_dict or len(keys_pool_dict) == 0:
            await query.edit_message_text("❌ Low Stock! Critical operational exception during execution phase.", reply_markup=render_back_navigation_markup())
            return
            
        if user_record['balance'] < price:
            await query.edit_message_text("❌ Insufficient ledger configuration changes detected.", reply_markup=render_back_navigation_markup())
            return
            
        target_key_id = next(iter(keys_pool_dict))
        selected_serial_key = keys_pool_dict[target_key_id]
        
        await LocalDatabaseRouter.delete_node(DB_PRODUCTS_FILE, f"{key_path}/keys/{day}/{target_key_id}")
        await process_wallet_balance_mutation(user_id, -price)
        
        await award_referral_bonus_pipeline(context.bot, str(user_id))
        
        purchased_dict = user_record.get('purchased_keys', {})
        if purchased_dict is None or isinstance(purchased_dict, list):
            purchased_dict = {}
        new_purchase_id = f"key_{int(time.time() * 1000)}"
        item_title = f"{prod_node.get('name', pid.upper())}"
        purchased_dict[new_purchase_id] = {
            "item": f"{item_title} ({day} Days)",
            "key": selected_serial_key,
            "date": str(datetime.date.today())
        }
        await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user_id}/purchased_keys", purchased_dict)
        
        success_txt = (
            f"🔐 Your License Keys 🔐\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🥰 Product Name : {item_title}\n"
            f"⏰ Product Duration : {day} Days\n"
            f"🔐 License Key : `{selected_serial_key}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(success_txt, reply_markup=render_back_navigation_markup())
        
        admin_alert = (
            f"🔔 VIP TRANSACTION NOTIFICATION\n\n"
            f"👤 Buyer ID: {user_id} | @{username}\n"
            f"🥰 Product: {item_title}\n"
            f"⏱️ Plan: {day} Days\n"
            f"💰 Price Charged: {CURRENCY} {price:.2f}" + (" [ʀᴇꜱᴇʟʟᴇʀ RATE]" if is_user_ʀᴇꜱᴇʟʟᴇʀ else " [STANDARD RATE]") + f"\n"
            f"🔑 Key Issued: {selected_serial_key}"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert)
        except Exception: pass
        return

    # ==========================================
    # 👑 ADMINISTRATIVE INTERFACES & STORE BUILDER
    # ==========================================
    if not is_admin_user(user_id): return
    
    if data == "adm_reseller_setup":
        users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, "") or {}
        reseller_count = sum(1 for u in users.values() if isinstance(u, dict) and u.get("is_ʀᴇꜱᴇʟʟᴇʀ"))
        await query.edit_message_text(
            f"💎 **RESELLER MANAGEMENT**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Total Resellers: **{reseller_count}**\n"
            f"💰 Reseller pricing is used automatically for reseller accounts.\n"
            f"🆓 Admin can activate a reseller for free from this panel.",
            reply_markup=render_reseller_admin_keyboard(), parse_mode="Markdown"
        )
        return

    elif data == "adm_reseller_add":
        context.user_data["admin_state"] = "ADM_RESELLER_ADD"
        await query.edit_message_text(
            "➕ **ADD RESELLER**\n\nSend User ID or @username to make the user a reseller for free.",
            reply_markup=render_admin_back_markup(), parse_mode="Markdown"
        )
        return

    elif data == "adm_reseller_upgrade":
        context.user_data["admin_state"] = "ADM_RESELLER_UPGRADE"
        await query.edit_message_text(
            "🆙 **UPGRADE RESELLER**\n\nSend User ID or @username.\n\nThe user will be upgraded for **FREE** and will immediately see reseller prices.",
            reply_markup=render_admin_back_markup(), parse_mode="Markdown"
        )
        return

    elif data == "adm_reseller_remove":
        context.user_data["admin_state"] = "ADM_RESELLER_REMOVE"
        await query.edit_message_text(
            "➖ **REMOVE RESELLER**\n\nSend User ID or @username to remove reseller access.",
            reply_markup=render_admin_back_markup(), parse_mode="Markdown"
        )
        return

    elif data == "adm_reseller_list":
        users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, "") or {}
        rows = []
        for uid, uinfo in users.items():
            if not isinstance(uinfo, dict) or not uinfo.get("is_ʀᴇꜱᴇʟʟᴇʀ"):
                continue
            uname = str(uinfo.get("username") or "").strip()
            name = str(uinfo.get("first_name") or "User").strip()
            rows.append(f"💎 `{uid}` | @{uname if uname else '-'} | {name}")
        header = f"📋 **RESELLER USER LIST**\n━━━━━━━━━━━━━━━━━━━━━━━\n👥 Total: **{len(rows)}**\n\n"
        text = header + ("\n".join(rows) if rows else "No reseller users found.")
        await query.edit_message_text(text, reply_markup=render_reseller_admin_keyboard(), parse_mode="Markdown")
        return

    if data == "adm_toggle_phone_verify":
        PHONE_VERIFY_ENABLED = not PHONE_VERIFY_ENABLED
        await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "phone_verify_enabled", PHONE_VERIFY_ENABLED)
        status_txt = "ENABLED 🟢" if PHONE_VERIFY_ENABLED else "DISABLED 🔴"
        try:
            await query.edit_message_text(
                f"⚙️ **BOT SETTINGS**\n\n"
                f"📱 Phone Number Account Verification: **{status_txt}**\n\n"
                f"Users will be asked to share their phone number on /start when this is ON.",
                reply_markup=render_bot_settings_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    if data == "adm_toggle_maint":
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "maintenance_mode", MAINTENANCE_MODE)
        status_txt = "ENABLED 🔴" if MAINTENANCE_MODE else "DISABLED 🟢"
        
        try:
            if query.message and "BOT SETTINGS" in (query.message.text or ""):
                await query.edit_message_text(f"⚙️ **BOT SETTINGS**\n\nMaintenance Mode status changed to **{status_txt}**.", reply_markup=render_bot_settings_keyboard(), parse_mode="Markdown")
            else:
                users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, '') or {}
                total_users = len(users)
                ʀᴇꜱᴇʟʟᴇʀs_count = sum(1 for u in users.values() if u.get('is_ʀᴇꜱᴇʟʟᴇʀ'))
                categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
                total_stock = 0
                for c in categories.values():
                    for p in c.get('panels', {}).values():
                        for klist in p.get('keys', {}).values():
                            if isinstance(klist, dict):
                                total_stock += len([k for k in klist.keys() if k != "init_node_secured"])
                
                m_txt = "🔴 ACTIVE (Users Blocked)" if MAINTENANCE_MODE else "🟢 INACTIVE (Bot Live)"
                admin_text = (
                    f"⚙️ **ADMIN CONTROL PANEL**\n\n"
                    f"Complete button control is enabled. Commands are optional backups.\n\n"
                    f"🧑‍✈️ Loaded Admin IDs: **{len(get_all_admin_ids())}**\n"
                    f"🛠️ Maintenance Mode: **{m_txt}**\n\n"
                    f"👥 Users: **{total_users}**\n"
                    f"💎 ʀᴇꜱᴇʟʟᴇʀs: **{ʀᴇꜱᴇʟʟᴇʀs_count}**\n"
                    f"🥰 Available Stock: **{total_stock}**\n"
                    f"🛒 Completed Orders: **0**\n"
                    f"⏳ Pending Payments: **0**"
                )
                await query.edit_message_text(admin_text, reply_markup=render_admin_panel_keyboard(), parse_mode="Markdown")
        except Exception: pass
        return

    if data == "back_to_admin":
        context.user_data['admin_state'] = None
        users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, '') or {}
        total_users = len(users)
        ʀᴇꜱᴇʟʟᴇʀs_count = sum(1 for u in users.values() if u.get('is_ʀᴇꜱᴇʟʟᴇʀ'))
        
        categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
        total_stock = 0
        for c in categories.values():
            for p in c.get('panels', {}).values():
                for klist in p.get('keys', {}).values():
                    if isinstance(klist, dict):
                        total_stock += len([k for k in klist.keys() if k != "init_node_secured"])

        m_txt = "🔴 ACTIVE (Users Blocked)" if MAINTENANCE_MODE else "🟢 INACTIVE (Bot Live)"
        admin_text = (
            f"⚙️ **ADMIN CONTROL PANEL**\n\n"
            f"Complete button control is enabled. Commands are optional backups.\n\n"
            f"🧑‍✈️ Loaded Admin IDs: **1 Owner**\n"
            f"🛠️ Maintenance Mode: **{m_txt}**\n\n"
            f"👥 Users: **{total_users}**\n"
            f"💎 ʀᴇꜱᴇʟʟᴇʀs: **{ʀᴇꜱᴇʟʟᴇʀs_count}**\n"
            f"🥰 Available Stock: **{total_stock}**\n"
            f"🛒 Completed Orders: **0**\n"
            f"⏳ Pending Payments: **0**"
        )
        await query.edit_message_text(admin_text, reply_markup=render_admin_panel_keyboard(), parse_mode="Markdown")

    elif data == "adm_buybot":
        await send_buybot_menu(
            context.bot, chat_id, edit_message=query.message, admin_mode=True
        )

    elif data == "adm_home_message_set_new":
        # SET NEW MSG HOME: start the same home-message editing flow.
        context.user_data["admin_state"] = "WAIT_HOME_MESSAGE"
        current = get_home_message_template()
        preview = current if len(current) <= 2500 else current[:2500] + "\n..."
        await query.edit_message_text(
            "📝 **SET NEW MSG HOME**\n\n"
            "Send the new message…\n"
            "Your next message will be saved as the HOME MESSAGE.\n\n"
            f"**Current message:**\n{preview}\n\n"
            "**Placeholders:**\n"
            "`{USER_ID}` = user ID\n"
            "`{BALANCE}` = wallet balance\n"
            "`{CURRENCY}` = currency\n\n"
            "Button colors/layout will stay exactly the same.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 RESET DEFAULT", callback_data="adm_home_message_reset", style="danger")],
                [InlineKeyboardButton("🔙 ADMIN CONTROL", callback_data="back_to_admin", style="danger")],
            ]),
            parse_mode="Markdown",
        )

    elif data == "adm_home_message":
        context.user_data["admin_state"] = "WAIT_HOME_MESSAGE"
        current = get_home_message_template()
        preview = current if len(current) <= 2500 else current[:2500] + "\n..."
        await query.edit_message_text(
            "📝 **ADD / CHANGE MESSAGE**\n\n"
            "Send the new message…\n"
            "Your next message will be saved as the HOME MESSAGE.\n\n"
            f"**Current message:**\n{preview}\n\n"
            "**Placeholders:**\n"
            "`{USER_ID}` = user ID\n"
            "`{BALANCE}` = wallet balance\n"
            "`{CURRENCY}` = currency\n\n"
            "Button colors/layout will stay exactly the same.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 SET NEW MSG HOME", callback_data="adm_home_message_set_new", style="primary")],
                [InlineKeyboardButton("🔄 RESET DEFAULT", callback_data="adm_home_message_reset", style="danger")],
                [InlineKeyboardButton("🔙 ADMIN CONTROL", callback_data="back_to_admin", style="danger")],
            ]),
            parse_mode="Markdown",
        )

    elif data == "adm_home_message_reset":
        context.user_data["admin_state"] = None
        await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "home_message_template", DEFAULT_HOME_MESSAGE_TEMPLATE)
        await query.edit_message_text(
            "✅ **HOME MESSAGE RESET**\n\nDefault main-screen message restored.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 SET NEW MSG HOME", callback_data="adm_home_message_set_new", style="primary")],
                [InlineKeyboardButton("📝 EDIT AGAIN", callback_data="adm_home_message", style="primary")],
                [InlineKeyboardButton("🔙 ADMIN CONTROL", callback_data="back_to_admin", style="danger")],
            ]),
            parse_mode="Markdown",
        )

    elif data == "buybot_create":
        await query.edit_message_text(
            "🛠️ **CREATE YOUR BOT**\n\n"
            "To create your own bot, contact the support/admin and send your required bot name and setup details.\n\n"
            f"📞 Support: {SUPPORT_HANDLE}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Contact Support", url=f"https://t.me/{SUPPORT_HANDLE.replace('@', '')}", style="primary")],
                [InlineKeyboardButton("🔙 Back", callback_data="buybot_back", style="danger")],
            ]),
            parse_mode="Markdown",
        )

    elif data == "buybot_source":
        await query.edit_message_text(
            "💻 **BUY SOURCE CODE**\n\n"
            "For the source-code package and current price, contact the admin/support.\n\n"
            f"📞 Support: {SUPPORT_HANDLE}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Contact Support", url=f"https://t.me/{SUPPORT_HANDLE.replace('@', '')}", style="primary")],
                [InlineKeyboardButton("🔙 Back", callback_data="buybot_back", style="danger")],
            ]),
            parse_mode="Markdown",
        )

    elif data == "buybot_back":
        await send_buybot_menu(context.bot, chat_id, edit_message=query.message)

    elif data == "buybot_back_shop":
        await _send_new_menu_shop(context.bot, chat_id)

    elif data == "adm_bot_settings_menu":
        await query.edit_message_text("⚙️ **BOT SETTINGS**\n\nSelect any setting to edit it from buttons.", reply_markup=render_bot_settings_keyboard(), parse_mode="Markdown")

    elif data == "adm_fampay_settings":
        await query.edit_message_text(
            "💠 **FAMPAY SETTINGS**\\n\\nConfigure every FamPay API value used by QR generation and payment verification.",
            reply_markup=render_fampay_settings_keyboard(), parse_mode="Markdown"
        )

    elif data == "adm_fampay_upi":
        context.user_data["admin_state"] = "WAIT_FAMPAY_UPI"
        await query.edit_message_text(f"💳 **CURRENT FAMPAY UPI ID:**\\n`{MERCHANT_UPI_ID}`\\n\\nEnter new FamPay UPI ID:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_fampay_api_key":
        context.user_data["admin_state"] = "WAIT_FAMPAY_API_KEY"
        await query.edit_message_text(f"🔑 **CURRENT FAMPAY API KEY:**\\n`{FAMPAY_API_KEY}`\\n\\nEnter new FamPay API key:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_fampay_qr_url":
        context.user_data["admin_state"] = "WAIT_FAMPAY_QR_URL"
        await query.edit_message_text(f"🧾 **CURRENT FAMPAY QR URL:**\\n`{FAMPAY_QR_URL}`\\n\\nEnter new QR API URL:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_fampay_verify_url":
        context.user_data["admin_state"] = "WAIT_FAMPAY_VERIFY_URL"
        await query.edit_message_text(f"✅ **CURRENT FAMPAY VERIFY URL:**\\n`{FAMPAY_VERIFY_URL}`\\n\\nEnter new Verify API URL:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_fampay_base_url":
        context.user_data["admin_state"] = "WAIT_FAMPAY_BASE_URL"
        await query.edit_message_text(f"🌐 **CURRENT FAMPAY API BASE URL:**\\n`{API_BASE_URL}`\\n\\nEnter new API base URL:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_coadmin_menu":
        records = get_managed_bot_records()
        lines = ["👥 **CO-ADMIN / BOT MANAGER**", "━━━━━━━━━━━━━━━━━━━━━━", "Send a bot token + admin ID to connect a managed bot.", "Format: `BOT_TOKEN | ADMIN_ID`", ""]
        if records:
            lines.append(f"Connected bots: **{len(records)}**")
            for key, rec in list(records.items())[:10]:
                lines.append(f"• @{rec.get('username', 'unknown')} — Admin ID `{rec.get('admin_id')}`")
        else:
            lines.append("No co-admin bots connected yet.")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ADD CO-ADMIN BOT", callback_data="adm_coadmin_add", style="success")],
            [InlineKeyboardButton("🔄 START SAVED BOTS", callback_data="adm_coadmin_start", style="primary")],
            [InlineKeyboardButton("🗑️ REMOVE CO-ADMIN BOT", callback_data="adm_coadmin_remove", style="danger")],
            [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger")],
        ])
        try:
            await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="Markdown")
        except Exception as exc:
            logger.warning("Could not edit CO-ADMIN menu message: %s", exc)
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                reply_markup=kb,
                parse_mode="Markdown",
            )
        return

    elif data == "adm_coadmin_add":
        context.user_data['admin_state'] = 'WAIT_COADMIN_TOKEN_ID'
        await query.edit_message_text(
            "👥 **ADD CO-ADMIN BOT**\n\nSend the bot token and its admin Telegram ID in one message.\n\nFormat:\n`BOT_TOKEN | 123456789`\n\nThe token is sensitive; do not share it anywhere else.",
            reply_markup=render_admin_back_markup(), parse_mode="Markdown"
        )

    elif data == "adm_coadmin_start":
        records = get_managed_bot_records()
        started = 0
        for bot_key, record in records.items():
            token = str(record.get("token", "")).strip()
            if token and bot_key not in MANAGED_BOTS_STARTED:
                start_managed_bot(token, bot_key)
                started += 1
        await query.edit_message_text(f"✅ Saved managed bots started: **{started}**", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_coadmin_remove":
        context.user_data['admin_state'] = 'WAIT_COADMIN_REMOVE'
        await query.edit_message_text("🗑️ **REMOVE CO-ADMIN BOT**\n\nSend the bot username (without @) or bot key to remove it from the manager.", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_admin_manage":
        admin_records = get_same_bot_admin_records()
        rows = [
            "👑 **ADMIN MANAGEMENT**",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👑 Owner ID: `{ADMIN_ID}`",
            f"👥 Same-bot admins: **{len(admin_records)}**",
            "",
        ]
        if admin_records:
            for aid, rec in list(admin_records.items())[:20]:
                uname = str(rec.get("username", "") or "").strip()
                label = f"@{uname}" if uname and not uname.startswith("@") else (uname or "No username")
                rows.append(f"• `{aid}` — {label}")
        else:
            rows.append("No additional admins added yet.")

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ADD ADMIN", callback_data="adm_admin_add", style="success"),
             InlineKeyboardButton("➖ REMOVE ADMIN", callback_data="adm_admin_remove", style="danger")],
            [InlineKeyboardButton("🔙 BACK", callback_data="back_to_admin", style="danger")],
        ])
        await query.edit_message_text(
            "\n".join(rows),
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return

    elif data == "adm_admin_add":
        if not is_owner_user(user_id):
            await query.answer("⛔ Only the owner can add admins.", show_alert=True)
            return
        context.user_data["admin_state"] = "WAIT_SAME_BOT_ADMIN_ADD"
        await query.edit_message_text(
            "➕ **ADD ADMIN TO THIS BOT**\n\n"
            "Send the Telegram User ID of the person you want to make admin.\n\n"
            "Example: `123456789`\n\n"
            "This gives that user access to `/admin` and the same admin controls on this bot.",
            reply_markup=render_admin_back_markup(),
            parse_mode="Markdown"
        )
        return

    elif data == "adm_admin_remove":
        if not is_owner_user(user_id):
            await query.answer("⛔ Only the owner can remove admins.", show_alert=True)
            return
        context.user_data["admin_state"] = "WAIT_SAME_BOT_ADMIN_REMOVE"
        await query.edit_message_text(
            "➖ **REMOVE ADMIN FROM THIS BOT**\n\n"
            "Send the Telegram User ID to remove.\n\n"
            f"Owner ID `{ADMIN_ID}` cannot be removed.",
            reply_markup=render_admin_back_markup(),
            parse_mode="Markdown"
        )
        return

    elif data == "adm_set_webpanel":
        context.user_data['admin_state'] = 'WAIT_WEBSITE_PANEL_URL'
        current = WEBSITE_PANEL_URL or "Not set"
        await query.edit_message_text(f"🌐 **WEBSITE PANEL LINK**\n\nCurrent: `{current}`\n\nSend the website panel URL:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_sync_website":
        sync_url = WEBSITE_SYNC_URL or WEBSITE_PANEL_URL
        if not sync_url:
            context.user_data['admin_state'] = 'WAIT_WEBSITE_SYNC_URL'
            await query.edit_message_text(
                "🔄 **SYNC FROM WEBSITE**\n\nSend the JSON sync/API URL. It should return a JSON object with a categories field.",
                reply_markup=render_admin_back_markup(), parse_mode="Markdown"
            )
            return
        ok, msg, count = await sync_products_from_website(sync_url)
        await query.edit_message_text(
            f"{'✅' if ok else '❌'} **WEBSITE SYNC**\n\n{msg}" + (f"\nCategories synced: **{count}**" if ok else ""),
            reply_markup=render_bot_settings_keyboard(), parse_mode="Markdown"
        )

    # ==========================================
    # 🛠️ BOT SETTINGS BUTTON CALLBACKS
    # ==========================================
    elif data == "adm_set_title":
        context.user_data['admin_state'] = 'WAIT_BOT_TITLE'
        await query.edit_message_text(f"📝 **CURRENT BOT TITLE:**\n`{BOT_TITLE}`\n\nEnter new Bot Title:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_curr":
        context.user_data['admin_state'] = 'WAIT_CURRENCY'
        await query.edit_message_text(f"💱 **CURRENT CURRENCY:**\n`{CURRENCY}`\n\nEnter new Currency Symbol/Code (e.g. INR, USD, ₹, $):", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_owner":
        context.user_data['admin_state'] = 'WAIT_OWNER_USER'
        await query.edit_message_text(f"👤 **CURRENT OWNER USERNAME:**\n`{OWNER_USERNAME}`\n\nEnter new Owner Username (with @):", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_upiname":
        context.user_data['admin_state'] = 'WAIT_UPI_NAME'
        await query.edit_message_text(f"💳 **CURRENT UPI HOLDER NAME:**\n`{UPI_HOLDER_NAME}`\n\nEnter new UPI Holder Name:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_upi_change_init":
        context.user_data['admin_state'] = 'WAIT_UPI_ID'
        await query.edit_message_text(f"💳 **CURRENT UPI ID:**\n`{MERCHANT_UPI_ID}`\n\nEnter new UPI ID:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_qr_change_init":
        context.user_data['admin_state'] = 'WAIT_MANUAL_QR'
        await query.edit_message_text(f"🖼️ **CURRENT MANUAL QR URL:**\n`{STATIC_MANUAL_QR_LINK}`\n\nSend new Image or Image URL for Manual Payment QR:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_paychan":
        context.user_data['admin_state'] = 'WAIT_PAY_CHAN'
        await query.edit_message_text(f"📢 **CURRENT PAYMENT CHANNEL ID:**\n`{PAYMENT_CHANNEL_ID}`\n\nEnter new Payment Channel ID or @username:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_intro":
        context.user_data['admin_state'] = 'WAIT_HOME_INTRO'
        await query.edit_message_text(f"🏠 **CURRENT HOME INTRO:**\n{HOME_INTRO}\n\nEnter new Home Intro Text:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_supp":
        context.user_data['admin_state'] = 'WAIT_SUPP_TXT'
        await query.edit_message_text(f"📞 **CURRENT SUPPORT TEXT:**\n{SUPPORT_TEXT}\n\nEnter new Support Text:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_payinst":
        context.user_data['admin_state'] = 'WAIT_PAY_INST'
        await query.edit_message_text(f"ℹ️ **CURRENT PAYMENT INSTRUCTIONS:**\n{PAYMENT_INSTRUCTIONS}\n\nEnter new Payment Instructions:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_addpay":
        context.user_data['admin_state'] = 'WAIT_ADD_PAY'
        await query.edit_message_text(f"➕ **CURRENT ADDITIONAL PAYMENT TEXT:**\n{ADDITIONAL_PAYMENT}\n\nEnter new Additional Payment Info:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_proof":
        context.user_data['admin_state'] = 'WAIT_PROOF_URL'
        await query.edit_message_text(f"📈 **CURRENT PROOF CHANNEL URL:**\n`{PROOF_CHANNEL_URL}`\n\nEnter new Proof Channel Link:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_set_tut":
        context.user_data['admin_state'] = 'WAIT_TUT_URL'
        await query.edit_message_text(f"🎥 **CURRENT TUTORIAL URL:**\n`{TUTORIAL_URL}`\n\nEnter new Tutorial Video/Channel Link:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_qr_remove":
        STATIC_MANUAL_QR_LINK = "https://i.ibb.co/N2qMTwmK/b13b33345a4c.jpg"
        await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "qr_link", "https://i.ibb.co/N2qMTwmK/b13b33345a4c.jpg")
        await query.edit_message_text("🗑️ **QR Code Link reset successfully!**", reply_markup=render_bot_settings_keyboard(), parse_mode="Markdown")

    # ==========================================
    # 🏗️ STORE BUILDER & CATEGORY CALLBACKS
    # ==========================================
    elif data == "adm_ff_id_store":
        await query.edit_message_text(
            "🆔 **FF ID STORE CONTROL**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Manage FF ID levels and FF accounts below.\n"
            "Open a package to set price and manage stock.",
            reply_markup=_ff_id_store_keyboard(),
            parse_mode="Markdown",
        )

    elif data == "ffid_account_fb_google":
        ff_map = {
            "ffid_account_fb_google": ("fb_google", "FF ACCOUNT FACEBOOK + GOOGLE", "FB_GOOGLE"),
        }
        panel_id, panel_name, plan_id = ff_map[data]
        cat_data, p_data = await _ensure_ff_id_store_panel(panel_id, panel_name, plan_id)
        await query.edit_message_text(
            f"🆔 **{panel_name}**\n\n"
            f"💰 Price: **₹{float(p_data['plans'][plan_id].get('standard', 0)):.2f}**\n"
            f"📦 Stock: **{_user_store_stock_count(p_data, plan_id)}**\n\n"
            "Use the controls below to set price, add stock, or edit the package.",
            reply_markup=render_package_manage_keyboard("ff_id_store", panel_id, plan_id, p_data),
            parse_mode="Markdown",
        )

    elif data == "adm_store_builder":
        categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
        await query.edit_message_text(
            "🏗️ **STORE BUILDER SYSTEM**\n\nSelect a category to manage, or click Add Category below:",
            reply_markup=render_store_builder_keyboard(categories),
            parse_mode="Markdown"
        )

    elif data == "sb_add_cat":
        context.user_data['admin_state'] = 'SB_ADD_CAT_NAME'
        await query.edit_message_text("➕ **ADD NEW CATEGORY**\n\nEnter Category Name:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data.startswith("sb_cat_emoji_"):
        cat_id = data.replace("sb_cat_emoji_", "").strip()
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        current_emoji = str(cat_data.get("emoji_id", "") or "").strip()
        context.user_data['admin_state'] = f"SB_SET_CAT_EMOJI|{cat_id}"
        await query.edit_message_text(
            f"✨ **CATEGORY PREMIUM EMOJI**\n\nCurrent Emoji ID: `{current_emoji or 'Not Set'}`\n\n"
            f"Send Telegram Custom Emoji ID. Example: `5368324170671202286`",
            reply_markup=render_admin_back_markup(), parse_mode="Markdown"
        )

    elif data.startswith("sb_pnl_emoji_"):
        payload = data.replace("sb_pnl_emoji_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
        current_emoji = str(p_data.get("emoji_id", "") or "").strip()
        context.user_data['admin_state'] = f"SB_SET_PNL_EMOJI|{cat_id}:{p_id}"
        await query.edit_message_text(
            f"✨ **PANEL PREMIUM EMOJI**\n\nCurrent Emoji ID: `{current_emoji or 'Not Set'}`\n\n"
            f"Send Telegram Custom Emoji ID. Example: `5368324170671202286`",
            reply_markup=render_admin_back_markup(), parse_mode="Markdown"
        )

    elif data.startswith("sb_cat_"):
        cat_id = data.replace("sb_cat_", "").strip()
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        await query.edit_message_text(
            f"❤️ **CATEGORY MANAGEMENT**\n\nName: **{cat_data.get('name')}**\nStatus: **{'ACTIVE ✅' if cat_data.get('active', True) else 'DISABLED ❌'}**",
            reply_markup=render_category_manage_keyboard(cat_id, cat_data),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_add_pnl_"):
        cat_id = data.replace("sb_add_pnl_", "").strip()
        context.user_data['admin_state'] = f"SB_ADD_PNL_NAME|{cat_id}"
        await query.edit_message_text("➕ **ADD NEW PANEL**\n\nEnter Panel Name:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data.startswith("sb_ren_cat_"):
        cat_id = data.replace("sb_ren_cat_", "").strip()
        context.user_data['admin_state'] = f"SB_RENAME_CAT|{cat_id}"
        await query.edit_message_text("✏️ **RENAME CATEGORY**\n\nEnter new Category Name:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data.startswith("sb_tog_cat_"):
        cat_id = data.replace("sb_tog_cat_", "").strip()
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        cat_data["active"] = not cat_data.get("active", True)
        await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/active", cat_data["active"])
        await query.edit_message_reply_markup(reply_markup=render_category_manage_keyboard(cat_id, cat_data))

    elif data.startswith("sb_del_cat_"):
        cat_id = data.replace("sb_del_cat_", "").strip()
        await LocalDatabaseRouter.delete_node(DB_PRODUCTS_FILE, f"categories/{cat_id}")
        categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
        await query.edit_message_text("🗑️ Category deleted successfully!", reply_markup=render_store_builder_keyboard(categories))

    # ==========================================
    # 🏗️ PANEL & PACKAGE MANAGEMENT CALLBACKS
    # ==========================================
    elif data.startswith("sb_pnl_"):
        payload = data.replace("sb_pnl_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        p_data = cat_data.get("panels", {}).get(p_id, {})
        p_name = p_data.get("name", p_id.upper())
        val_count = len(p_data.get("plans", {}))
        
        text = (
            f"📝 **VALIDITY PACKAGES CONTROL**\n\n"
            f"❤️ Category: **{cat_data.get('name')}**\n"
            f"🥰 Panel: **{p_name}**\n"
            f"⏱️ Validity Packages: **{val_count}**\n"
            f"📌 Status: **{'ACTIVE ✅' if p_data.get('active', True) else 'DISABLED ❌'}**\n\n"
            f"Use quick ꜱᴇᴛᴜᴩ or add single validity below."
        )
        await query.edit_message_text(text, reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data), parse_mode="Markdown")

    elif data.startswith("sb_quick_days_"):
        payload = data.replace("sb_quick_days_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        p_data = cat_data.get("panels", {}).get(p_id, {})
        
        default_days = ["1", "2", "3", "7", "30"]
        if "plans" not in p_data: p_data["plans"] = {}
        if "keys" not in p_data: p_data["keys"] = {}
        
        for d in default_days:
            if d not in p_data["plans"]:
                p_data["plans"][d] = {"standard": 50.0, "ʀᴇꜱᴇʟʟᴇʀ": 40.0}
            if d not in p_data["keys"]:
                p_data["keys"][d] = {}

        await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}", p_data)
        await query.edit_message_text("⚡ **Quick 1, 2, 3, 7, 30 Days added successfully!**", reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data), parse_mode="Markdown")

    elif data.startswith("sb_quick_hours_"):
        payload = data.replace("sb_quick_hours_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        p_data = cat_data.get("panels", {}).get(p_id, {})
        quick_hours = ["1", "3", "7", "12", "24"]
        if "plans" not in p_data: p_data["plans"] = {}
        if "keys" not in p_data: p_data["keys"] = {}
        for h in quick_hours:
            key = f"{h}H"
            if key not in p_data["plans"]:
                p_data["plans"][key] = {"standard": 20.0, "ʀᴇꜱᴇʟʟᴇʀ": 15.0, "unit": "hours"}
            elif isinstance(p_data["plans"][key], dict):
                p_data["plans"][key].setdefault("unit", "hours")
            if key not in p_data["keys"]:
                p_data["keys"][key] = {}
        await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}", p_data)
        await query.edit_message_text("⏱️ **Quick 1, 3, 7, 12, 24 Hours added successfully!**", reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data), parse_mode="Markdown")

    elif data.startswith("sb_add_val_"):
        payload = data.replace("sb_add_val_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        context.user_data['admin_state'] = f"SB_WAITING_VAL_DAYS|{cat_id}:{p_id}"
        await query.edit_message_text(
            "➕ **ADD CUSTOM VALIDITY**\n\n"
            "Enter your duration, for example:\n"
            "• `1H` = 1 hour\n"
            "• `2H` = 2 hours\n"
            "• `1D` = 1 day\n"
            "• `7D` = 7 days\n\n"
            "You can also type `1 hour`, `2 hours`, or `1 day`.",
            reply_markup=render_admin_back_markup(),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_ren_pnl_"):
        payload = data.replace("sb_ren_pnl_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        context.user_data['admin_state'] = f"SB_RENAME_PNL|{cat_id}:{p_id}"
        await query.edit_message_text("✏️ **RENAME PANEL**\n\nEnter new Panel Name:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data.startswith("sb_desc_pnl_"):
        payload = data.replace("sb_desc_pnl_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        context.user_data['admin_state'] = f"SB_DESC_PNL|{cat_id}:{p_id}"
        await query.edit_message_text("📝 **EDIT DESCRIPTION**\n\nEnter Panel Description:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data.startswith("sb_tog_pnl_"):
        payload = data.replace("sb_tog_pnl_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
        p_data["active"] = not p_data.get("active", True)
        await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/active", p_data["active"])
        await query.edit_message_reply_markup(reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data))

    elif data.startswith("sb_del_pnl_"):
        payload = data.replace("sb_del_pnl_", "").strip()
        cat_id, p_id = payload.split(":", 1)
        await LocalDatabaseRouter.delete_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}")
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}")
        await query.edit_message_text("🗑️ Panel deleted successfully!", reply_markup=render_category_manage_keyboard(cat_id, cat_data))

    elif data.startswith("sb_pkg_view_"):
        payload = data.replace("sb_pkg_view_", "").strip()
        cat_id, p_id, day = payload.split(":", 2)
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        p_data = cat_data.get("panels", {}).get(p_id, {})
        
        prc = p_data.get("plans", {}).get(day, 0.0)
        std_p = prc.get('standard', prc) if isinstance(prc, dict) else prc
        stk_len = len([k for k in p_data.get("keys", {}).get(day, {}).keys() if k != "init_node_secured"])
        
        text = (
            f"📦 **PACKAGE CONTROL**\n\n"
            f"❤️ Category: **{cat_data.get('name')}**\n"
            f"🥰 Panel: **{p_data.get('name')}**\n"
            f"⏱️ Package: **{_ff_store_package_label(day)}**\n"
            f"💰 Price: **₹{std_p:.2f}**\n"
            f"📱 Available Stock: **{stk_len}**\n"
            f"📌 Status: **ACTIVE ✅**"
        )
        await query.edit_message_text(text, reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data), parse_mode="Markdown")

    elif data.startswith("sb_stk_manage_"):
        payload = data.replace("sb_stk_manage_", "").strip()
        cat_id, p_id, day = payload.split(":", 2)
        context.user_data['admin_state'] = f"SB_ADD_KEYS_TEXT|{cat_id}:{p_id}:{day}"
        await query.edit_message_text("🥰 **MANAGE STOCK**\n\nPlease send keys line by line (1 key per line) to add into stock:", reply_markup=render_sb_back_markup(f"sb_pkg_view_{cat_id}:{p_id}:{day}", "BACK TO PACKAGE"), parse_mode="Markdown")

    elif data.startswith("sb_edit_prc_"):
        payload = data.replace("sb_edit_prc_", "").strip()
        cat_id, p_id, day = payload.split(":", 2)
        context.user_data['admin_state'] = f"SB_EDIT_PRICE_VAL|{cat_id}:{p_id}:{day}"
        await query.edit_message_text(
            "💰 **EDIT PRICE**\n\nEnter new Standard Price (e.g. 50):",
            reply_markup=render_sb_back_markup(f"sb_pkg_view_{cat_id}:{p_id}:{day}", "BACK TO PACKAGE"),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_edit_res_prc_"):
        payload = data.replace("sb_edit_res_prc_", "").strip()
        cat_id, p_id, day = payload.split(":", 2)
        p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
        pricing = p_data.get("plans", {}).get(day, {})
        current = pricing.get("ʀᴇꜱᴇʟʟᴇʀ", pricing.get("standard", 0.0)) if isinstance(pricing, dict) else pricing
        context.user_data['admin_state'] = f"SB_EDIT_RESELLER_PRICE|{cat_id}:{p_id}:{day}"
        await query.edit_message_text(
            f"💎 **EDIT RESELLER PRICE**\n\nCurrent Reseller Price: **{CURRENCY} {float(current):.2f}**\n\nEnter new Reseller Price:",
            reply_markup=render_sb_back_markup(f"sb_pkg_view_{cat_id}:{p_id}:{day}", "BACK TO PACKAGE"), parse_mode="Markdown"
        )

    elif data.startswith("sb_del_pkg_"):
        payload = data.replace("sb_del_pkg_", "").strip()
        cat_id, p_id, day = payload.split(":", 2)
        await LocalDatabaseRouter.delete_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/plans/{day}")
        await LocalDatabaseRouter.delete_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/keys/{day}")
        p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}")
        await query.edit_message_text("🗑️ Validity package deleted!", reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data))

    # ==========================================
    # 🧭 STORE BUILDER NAVIGATION / MISSING CALLBACKS
    # ==========================================
    elif data.startswith("sb_back_pkg_"):
        payload = data.replace("sb_back_pkg_", "", 1).strip()
        cat_id, p_id, day = payload.split(":", 2)
        context.user_data["admin_state"] = None
        p_data = await LocalDatabaseRouter.get_node(
            DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}"
        ) or {}
        prc = p_data.get("plans", {}).get(day, 0.0)
        std_p = prc.get("standard", prc) if isinstance(prc, dict) else prc
        stk_len = len([
            k for k in p_data.get("keys", {}).get(day, {}).keys()
            if k != "init_node_secured"
        ])
        cat_data = await LocalDatabaseRouter.get_node(
            DB_PRODUCTS_FILE, f"categories/{cat_id}"
        ) or {}
        text = (
            f"⏱️ **VALIDITY PACKAGE CONTROL**\n\n"
            f"❤️ Category: **{cat_data.get('name')}**\n"
            f"🥰 Panel: **{p_data.get('name')}**\n"
            f"⏱️ Package: **{_ff_store_package_label(day)}**\n"
            f"💰 Price: **₹{float(std_p or 0):.2f}**\n"
            f"📱 Available Stock: **{stk_len}**\n"
            f"📌 Status: **ACTIVE ✅**"
        )
        await query.edit_message_text(
            text, reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_edit_val_"):
        payload = data.replace("sb_edit_val_", "", 1).strip()
        cat_id, p_id, day = payload.split(":", 2)
        context.user_data["admin_state"] = f"SB_EDIT_VALIDITY|{cat_id}:{p_id}:{day}"
        await query.edit_message_text(
            f"⏰ **EDIT VALIDITY**\n\nCurrent: **{day}**\n\nEnter new validity (example: 7 or 24H):",
            reply_markup=render_sb_back_markup(f"sb_pkg_view_{cat_id}:{p_id}:{day}", "BACK TO PACKAGE"),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_edit_lmt_"):
        payload = data.replace("sb_edit_lmt_", "", 1).strip()
        cat_id, p_id, day = payload.split(":", 2)
        p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
        current = p_data.get("plans", {}).get(day, {})
        current_limit = current.get("limit", 0) if isinstance(current, dict) else 0
        context.user_data["admin_state"] = f"SB_EDIT_LIMIT|{cat_id}:{p_id}:{day}"
        await query.edit_message_text(
            f"📱 **EDIT LIMIT**\n\nCurrent Limit: **{current_limit or 'Unlimited'}**\n\nEnter max purchase limit (0 = Unlimited):",
            reply_markup=render_sb_back_markup(f"sb_pkg_view_{cat_id}:{p_id}:{day}", "BACK TO PACKAGE"),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_tog_pkg_"):
        payload = data.replace("sb_tog_pkg_", "", 1).strip()
        cat_id, p_id, day = payload.split(":", 2)
        plan_path = f"categories/{cat_id}/panels/{p_id}/plans/{day}"
        pricing = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, plan_path)
        if not isinstance(pricing, dict):
            pricing = {"standard": float(pricing or 0)}
        pricing["active"] = not pricing.get("active", True)
        await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, plan_path, pricing)
        p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
        status = "enabled ✅" if pricing["active"] else "disabled ❌"
        await query.edit_message_text(
            f"✅ Validity package **{day}** is now **{status}**.",
            reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_mup_cat_") or data.startswith("sb_mdn_cat_"):
        move_up = data.startswith("sb_mup_cat_")
        cat_id = data.split("sb_mup_cat_", 1)[-1] if move_up else data.split("sb_mdn_cat_", 1)[-1]
        categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, "categories") or {}
        items = list(categories.items())
        idx = next((i for i, (k, _) in enumerate(items) if k == cat_id), -1)
        target = idx - 1 if move_up else idx + 1
        if idx >= 0 and 0 <= target < len(items):
            items[idx], items[target] = items[target], items[idx]
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, "categories", dict(items))
        cat_data = categories.get(cat_id, {})
        await query.edit_message_text(
            f"❤️ **CATEGORY MANAGEMENT**\n\nName: **{cat_data.get('name', cat_id)}**\nStatus: **{'ACTIVE ✅' if cat_data.get('active', True) else 'DISABLED ❌'}**",
            reply_markup=render_category_manage_keyboard(cat_id, cat_data),
            parse_mode="Markdown"
        )

    elif data.startswith("sb_mup_pnl_") or data.startswith("sb_mdn_pnl_"):
        move_up = data.startswith("sb_mup_pnl_")
        payload = data.split("sb_mup_pnl_", 1)[-1] if move_up else data.split("sb_mdn_pnl_", 1)[-1]
        cat_id, p_id = payload.split(":", 1)
        cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
        panels = cat_data.get("panels", {})
        items = list(panels.items())
        idx = next((i for i, (k, _) in enumerate(items) if k == p_id), -1)
        target = idx - 1 if move_up else idx + 1
        if idx >= 0 and 0 <= target < len(items):
            items[idx], items[target] = items[target], items[idx]
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels", dict(items))
        await query.edit_message_text(
            f"📝 **VALIDITY PACKAGES CONTROL**\n\n"
            f"❤️ Category: **{cat_data.get('name')}**\n"
            f"🥰 Panel: **{panels.get(p_id, {}).get('name', p_id)}**",
            reply_markup=render_panel_manage_keyboard(cat_id, p_id, panels.get(p_id, {})),
            parse_mode="Markdown"
        )

    elif data == "adm_manage_bal_menu":
        if not is_admin_user(user_id):
            await query.answer("⛔ Admin access only.", show_alert=True)
            return
        context.user_data["admin_state"] = None
        await query.edit_message_text(
            "👥 **USERS & WALLET MANAGEMENT**\n\nSelect search option below:",
            reply_markup=render_users_wallet_keyboard(),
            parse_mode="Markdown"
        )
        return

    elif data == "adm_bal_check":
        if not is_admin_user(user_id):
            await query.answer("⛔ Admin access only.", show_alert=True)
            return
        context.user_data['admin_state'] = 'ADM_BAL_SEARCH'
        await query.edit_message_text(
            "🔍 **SEARCH USER**\n\nEnter User ID or Username:",
            reply_markup=render_admin_back_markup(),
            parse_mode="Markdown"
        )
        return

    elif data == "adm_phone_numbers":
        # Admin-only phone-number list. Never expose this data to normal users.
        users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, "") or {}
        phone_rows = []
        for uid, uinfo in users.items():
            if not isinstance(uinfo, dict):
                continue
            phone = str(uinfo.get("phone_number", "")).strip()
            if not phone:
                continue
            name = str(uinfo.get("first_name") or uinfo.get("username") or "User").strip()
            username_value = str(uinfo.get("username") or "").strip()
            username_text = f"@{username_value}" if username_value else "-"
            verified = "✅" if uinfo.get("phone_verified") else "⚠️"
            phone_rows.append(f"{verified} `{uid}` | {username_text} | {name} | `{phone}`")

        header = (
            "📱 **PHONE NUMBER LIST**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total saved numbers: **{len(phone_rows)}**\n\n"
        )
        if not phone_rows:
            await query.edit_message_text(
                header + "No phone numbers have been saved yet.",
                reply_markup=render_users_wallet_keyboard(),
                parse_mode="Markdown",
            )
            return

        chunks = []
        current = header
        for row in phone_rows:
            if len(current) + len(row) + 1 > 3800:
                chunks.append(current.rstrip())
                current = "📱 **PHONE NUMBER LIST — CONTINUED**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            current += row + "\n"
        if current.strip():
            chunks.append(current.rstrip())

        await query.edit_message_text(chunks[0], reply_markup=render_users_wallet_keyboard(), parse_mode="Markdown")
        for chunk in chunks[1:]:
            await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
        return

    elif data == "adm_list_users":
        users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, '') or {}
        txt = f"📋 **TOTAL REGISTERED USERS:** {len(users)}\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        cnt = 1
        for uid, uinfo in list(users.items())[:15]:
            if not isinstance(uinfo, dict):
                uinfo = {}
            uname = str(uinfo.get("username") or "N/A").lstrip("@")
            try:
                balance = float(uinfo.get("balance", 0) or 0)
            except (TypeError, ValueError):
                balance = 0.0
            txt += f"{cnt}. ID: `{uid}` | @{uname} | Bal: ₹{balance:.2f}\n"
            cnt += 1
        await query.edit_message_text(txt, reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_trigger_bc":
        context.user_data['admin_state'] = 'ADM_BROADCAST_MSG'
        await query.edit_message_text("📢 **BROADCAST MESSAGE**\n\nSend message or text to broadcast to all users:", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

    elif data == "adm_check_keys_all":
        try:
            categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
            if not isinstance(categories, dict):
                categories = {}

            txt = "📊 **DETAILED STORE STATISTICS**\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            if not categories:
                txt += "No store categories found.\n"
            else:
                for cid, cinfo in categories.items():
                    if not isinstance(cinfo, dict):
                        continue
                    txt += f"❤️ Category: **{cinfo.get('name', cid)}**\n"
                    panels = cinfo.get('panels', {}) or {}
                    if not isinstance(panels, dict):
                        continue
                    for pid, pinfo in panels.items():
                        if not isinstance(pinfo, dict):
                            continue
                        txt += f" └── Panel: **{pinfo.get('name', pid)}**\n"
                        keys_by_day = pinfo.get('keys', {}) or {}
                        if not isinstance(keys_by_day, dict):
                            continue
                        for day, kdict in keys_by_day.items():
                            if not isinstance(kdict, dict):
                                continue
                            cnt = len([k for k in kdict.keys() if k != "init_node_secured"])
                            txt += f"      ├── {day} Days -> Stock: {cnt}\n"

            await query.edit_message_text(
                txt,
                reply_markup=render_admin_back_markup(),
                parse_mode="Markdown"
            )
        except Exception as exc:
            logger.exception("Statistics callback failed: %s", exc)
            await query.answer("Statistics could not be loaded. Please try again.", show_alert=True)


# ==========================================
# 🧭 INLINE MAIN-MENU CALLBACK ROUTER
# ==========================================

MAIN_MENU_CALLBACKS = {
    "/buy_hack",
    "/profile",
    "/addfund",
    "/mykey",
    "main_referral",
    "/ludospin",
    "/how",
    "/support",
    "/ff_id_menu",
}

async def handle_new_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle every coloured inline button on the main dashboard."""
    query = update.callback_query
    data = query.data if query else ""
    if data not in MAIN_MENU_CALLBACKS:
        return False

    user = query.from_user
    chat_id = query.message.chat_id if query.message else user.id
    user_id = user.id
    username = user.username or user.first_name or "User"

    try:
        await query.answer()
    except Exception:
        pass

    if query.message:
        try:
            await query.message.delete()
        except Exception:
            pass

    if data == "/buy_hack":
        await _send_new_menu_shop(context.bot, chat_id)
    elif data == "/profile":
        await _send_new_menu_profile(context.bot, chat_id, user_id, user.first_name or "User", username)
    elif data == "/addfund":
        context.user_data["dial_string"] = ""
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Enter Your Amount\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 Current Amount: {CURRENCY} 0"
            ),
            reply_markup=render_matrix_dialpad("auto"),
        )
    elif data == "/mykey":
        await _send_new_menu_history(context.bot, chat_id, user_id)
    elif data == "main_referral":
        await _send_new_menu_referral(context.bot, chat_id, user_id)
    elif data == "/how":
        await _send_new_menu_tutorial(context.bot, chat_id)
    elif data == "/support":
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🆘 **SUPPORT**\n\nContact support admin: {SUPPORT_HANDLE}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Contact Support", url=f"https://t.me/{SUPPORT_HANDLE.replace('@', '')}", style="danger")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
            ]),
            parse_mode="Markdown",
        )
    elif data in {"/ludospin", "main_referral"}:
        await _send_new_menu_referral(context.bot, chat_id, user_id)
    elif data == "main_download_files":
        download_url = (TUTORIAL_URL or PROOF_CHANNEL_URL or "").strip()
        if download_url:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📥 **DOWNLOAD FILES**\n\nOpen the latest available file/resource link below.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Open Files", url=download_url, style="primary")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
                ]),
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📥 No download link has been configured by admin.",
                reply_markup=render_back_navigation_markup(),
            )
    elif data == "main_reseller_panel":
        await _send_new_menu_reseller(context.bot, chat_id, user_id)

    elif data == "/ff_id_menu":
        cat_info = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, "categories/ff_id_store") or {}
        panels = cat_info.get("panels", {}) if isinstance(cat_info, dict) else {}
        active_panels = {
            k: v for k, v in panels.items()
            if isinstance(v, dict) and v.get("active", True)
        }
        if not active_panels:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🆔 **FF ID STORE**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "No FF ID products are available right now."
                ),
                reply_markup=render_back_navigation_markup(),
                parse_mode="Markdown",
            )
        else:
            buttons = []
            for p_id, p_info in active_panels.items():
                display_name = str(p_info.get("name", p_id.upper())).strip()
                panel_emoji_id = str(p_info.get("emoji_id", "") or "").strip()
                buttons.append([_premium_button(
                    display_name,
                    callback_data=f"user_flat_days_ff_id_store:{p_id}",
                    style="primary",
                    custom_emoji_id=panel_emoji_id
                )])
            buttons.append([InlineKeyboardButton("🔙 BACK", callback_data="back_main", style="danger")])
            await context.bot.send_message(
                chat_id=chat_id,
                text="🆔 **FF ID STORE**\n\nSelect your product below:",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown",
            )

    return True

# ==========================================
# 🧭 NEW REPLY-MENU ROUTER
# ==========================================


# ==========================================

MAIN_MENU_TEXT_ROUTES = {
    "🛒 Product Store",
    "👤 My Profile",
    "💰 Add Balance",
    "📜 All History",
    "🤝 Referral",
    "📚 Tutorials",
    "🆘 Support",
    "🤝 Refer & Earn",
    "📥 Download Files",
    "⭐ Reseller Panel",
}

async def _send_new_menu_profile(
    bot: Bot,
    chat_id: int,
    user_id: int,
    first_name: str,
    username: str,
):
    user_record = await initialize_user_registers(user_id)
    role_label = "VIP ʀᴇꜱᴇʟʟᴇʀ" if user_record.get("is_ʀᴇꜱᴇʟʟᴇʀ", False) else "User"
    display_name = first_name or user_record.get("first_name") or "User"
    display_username = username or user_record.get("username") or "N/A"
    joined_at = str(user_record.get("registered_at", "N/A"))
    if joined_at != "N/A" and len(joined_at) >= 10:
        joined_at = joined_at[:10]

    profile_caption = (
        f"🎯 USER PROFILE 🎯\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Name: {display_name}\n"
        f"🏷️ Username: @{display_username}\n"
        f"🔗 Joined: {joined_at}\n"
        f"✅ Account Type: {role_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Balance: {CURRENCY} {user_record['balance']:.2f}\n"
        f"💸 Spent: {CURRENCY} 0.00\n"
        f"🔐 Keys: {len(user_record.get('purchased_keys', {}) or {})}\n"
        f"📱 Phone: {'Verified ✅' if user_record.get('phone_verified') and user_record.get('phone_number') else 'Not Verified ❌'}"
    )
    markup = render_profile_keyboard(user_record.get("is_ʀᴇꜱᴇʟʟᴇʀ", False))

    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if photos.total_count and photos.photos and photos.photos[0]:
            photo_id = photos.photos[0][-1].file_id
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_id,
                caption=profile_caption,
                reply_markup=markup,
            )
            return
    except Exception as exc:
        logger.warning("New-menu profile photo failed for %s: %s", user_id, exc)

    await bot.send_message(chat_id=chat_id, text=profile_caption, reply_markup=markup, parse_mode="Markdown")


def _user_store_stock_count(p_data: dict, day: str) -> int:
    """Return the number of usable keys for a package."""
    keys = p_data.get("keys", {}) if isinstance(p_data, dict) else {}
    day_keys = keys.get(day, {}) if isinstance(keys, dict) else {}
    if not isinstance(day_keys, dict):
        return 0
    return len([k for k in day_keys.keys() if str(k) != "init_node_secured"])


def _user_store_validity(day: str) -> str:
    """Format normal validity and FF ID Store package labels."""
    raw = str(day).strip()
    if raw == "FB_GOOGLE":
        return _ff_store_package_label(raw)
    if raw.upper().endswith("H"):
        return f"{raw[:-1]} HOURS"
    try:
        return f"{int(float(raw))} DAY"
    except (TypeError, ValueError):
        return raw.replace("_", " ").upper()


def _user_store_limit(pricing: Any) -> str:
    if not isinstance(pricing, dict):
        return "UNLIMITED"
    limit = pricing.get("limit", 0)
    try:
        limit_int = int(limit or 0)
        return str(limit_int) if limit_int > 0 else "UNLIMITED"
    except (TypeError, ValueError):
        return str(limit).strip() or "UNLIMITED"


def _user_store_price(pricing: Any, is_reseller: bool = False) -> float:
    if isinstance(pricing, dict):
        key = "ʀᴇꜱᴇʟʟᴇʀ" if is_reseller else "standard"
        try:
            return float(pricing.get(key, pricing.get("standard", 0)) or 0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(pricing or 0)
    except (TypeError, ValueError):
        return 0.0


async def _send_new_menu_shop(bot: Bot, chat_id: int):
    """Reference-style Product Store: category -> panel -> package card.

    Existing button colours are intentionally preserved:
    blue/primary for selectable store items and red/danger for Back.
    """
    categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, "categories") or {}
    active_categories = {
        k: v for k, v in categories.items()
        if isinstance(v, dict) and v.get("active", True)
    }
    if not active_categories:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ No active store categories found right now.",
            reply_markup=render_back_navigation_markup(),
        )
        return

    buttons = []
    for cat_id, cat_info in active_categories.items():
        display_name = str(cat_info.get("name", cat_id.upper())).strip()
        cat_emoji_id = str(cat_info.get("emoji_id", "") or "").strip()
        buttons.append([_premium_button(
            display_name,
            callback_data=f"user_view_cat_{cat_id}",
            style="primary",
            custom_emoji_id=cat_emoji_id
        )])
    buttons.append([
        InlineKeyboardButton("🔙 BACK", callback_data="back_main", style="danger")
    ])

    store_text = (
        "✨ **SELECT PRODUCT PANEL**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ **Choose a panel to view its packages:**"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=store_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def _send_new_menu_history(bot: Bot, chat_id: int, user_id: int):
    user_record = await initialize_user_registers(user_id)
    keys = user_record.get("purchased_keys", {}) or {}
    payments = user_record.get("credited_payment_orders", {}) or {}

    out = ["📜 **ALL HISTORY**", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    out.append(f"🛒 Purchases: **{len(keys)}**")
    if keys:
        for n, (_, info) in enumerate(keys.items(), 1):
            if not isinstance(info, dict):
                continue
            item = info.get("item", "Product")
            date = info.get("date", "N/A")
            key = info.get("key", "N/A")
            out.append(f"#{n} • {item}\n📅 {date}\n🔑 `{key}`")
    else:
        out.append("No purchase history yet.")

    out.extend(["", f"💳 Successful top-ups: **{len(payments)}**"])
    if payments:
        for order_id, info in payments.items():
            if not isinstance(info, dict):
                info = {}
            amount = float(info.get("amount", 0) or 0)
            when = info.get("credited_at", "N/A")
            out.append(f"• {order_id} — {CURRENCY} {amount:.2f} — {when}")

    await bot.send_message(
        chat_id=chat_id,
        text="\n".join(out),
        reply_markup=render_back_navigation_markup(),
        parse_mode="Markdown",
    )


async def _send_new_menu_referral(bot: Bot, chat_id: int, user_id: int):
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    user_record = await initialize_user_registers(user_id)
    ref_text = (
        "🤝 **REFERRAL**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Invite friends & earn ₹2.00 per successful referral.\n\n"
        f"📊 Total Referrals: {user_record.get('referral_count', 0)}\n"
        f"💰 Total Earned: {CURRENCY} {float(user_record.get('total_referral_earned', 0.0)):.2f}\n\n"
        f"💸 Reward Per Referral: {CURRENCY} 2.00\n\n"
        f"💸 Reward Per Referral: {CURRENCY} 2.00\n\n"
        f"🔗 Link: `{referral_link}`"
    )
    share_url = f"https://t.me/share/url?url={referral_link}&text=Join%20this%20store%20bot%20and%20earn%20Rs%202%20per%20successful%20referral!"
    await bot.send_message(
        chat_id=chat_id,
        text=ref_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Share Link", url=share_url, style="primary")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
        ]),
        parse_mode="Markdown",
    )


async def _send_new_menu_tutorial(bot: Bot, chat_id: int):
    guide_text = (
        "📚 **TUTORIALS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. **Add Balance**\n"
        "Choose Add Balance, enter the amount and complete the payment QR.\n\n"
        "2. **Product Store**\n"
        "Open Product Store, select a category, panel and plan, then follow the purchase steps.\n\n"
        "3. **All History / My Keys**\n"
        "Use All History to view purchases and successful top-ups. Your delivered keys are also available from My Profile.\n\n"
        "4. **Support**\n"
        "Contact the support admin if a payment or order needs help."
    )
    await bot.send_message(
        chat_id=chat_id,
        text=guide_text,
        reply_markup=render_back_navigation_markup(),
        parse_mode="Markdown",
    )


async def _send_new_menu_reseller(bot: Bot, chat_id: int, user_id: int):
    user_record = await initialize_user_registers(user_id)
    if user_record.get("is_ʀᴇꜱᴇʟʟᴇʀ", False):
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⭐️ VIP RESELLER PANEL ⭐️\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Status: Fully Authorized Reseller\n\n"
                "Your reseller pricing is active across the store."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Open Store", callback_data="ui_shop_prods", style="success")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
            ]),
        )
        return

    pitch = (
        "⭐️ **RESELLER PANEL** ⭐️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Upgrade Fee: {CURRENCY} {ʀᴇꜱᴇʟʟᴇʀ_UPGRADE_PRICE:.2f}\n\n"
        "🚀 Benefits:\n"
        "├── Lower product prices\n"
        "├── Instant key purchase\n"
        "└── Reseller pricing\n\n"
        f"Current Balance: {CURRENCY} {user_record['balance']:.2f}"
    )
    await bot.send_message(
        chat_id=chat_id,
        text=pitch,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Buy Now & Upgrade", callback_data="ui_confirm_ʀᴇꜱᴇʟʟᴇʀ_upgrade", style="success")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
        ]),
        parse_mode="Markdown",
    )


async def handle_new_main_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Handle every button from the new reference-style main menu."""
    if text not in MAIN_MENU_TEXT_ROUTES:
        return False

    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id = user.id
    username = user.username or user.first_name or "User"

    if text == "🛒 Product Store":
        await _send_new_menu_shop(context.bot, chat_id)
    elif text == "👤 My Profile":
        await _send_new_menu_profile(context.bot, chat_id, user_id, user.first_name or "User", username)
    elif text == "💰 Add Balance":
        context.user_data["dial_string"] = ""
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Enter Your Amount\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 Current Amount: {CURRENCY} 0"
            ),
            reply_markup=render_matrix_dialpad("auto"),
        )
    elif text == "📜 All History":
        await _send_new_menu_history(context.bot, chat_id, user_id)
    elif text == "🤝 Referral":
        await _send_new_menu_referral(context.bot, chat_id, user_id)
    elif text == "📚 Tutorials":
        await _send_new_menu_tutorial(context.bot, chat_id)
    elif text == "🆘 Support":
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🆘 **SUPPORT**\n\nContact support admin: {SUPPORT_HANDLE}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "📞 Contact Support",
                    url=f"https://t.me/{SUPPORT_HANDLE.replace('@', '')}",
                    style="danger",
                )],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
            ]),
            parse_mode="Markdown",
        )
    elif text == "🤝 Refer & Earn":
        await _send_new_menu_referral(context.bot, chat_id, user_id)
    elif text == "📥 Download Files":
        download_url = (TUTORIAL_URL or PROOF_CHANNEL_URL or "").strip()
        if download_url:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📥 **DOWNLOAD FILES**\n\nOpen the latest available file/resource link below.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Open Files", url=download_url, style="primary")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main", style="danger")],
                ]),
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📥 No download link has been configured by admin.",
                reply_markup=render_back_navigation_markup(),
            )
    elif text == "⭐ Reseller Panel":
        await _send_new_menu_reseller(context.bot, chat_id, user_id)

    return True

# ==========================================
# 💬 TEXT MESSAGE & ADMIN STATE HANDLER
# ==========================================

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global WEBSITE_PANEL_URL, WEBSITE_SYNC_URL, BOT_TITLE, OWNER_USERNAME, UPI_HOLDER_NAME
    global MERCHANT_UPI_ID, FAMPAY_API_KEY, FAMPAY_QR_URL, FAMPAY_VERIFY_URL, API_BASE_URL, STATIC_MANUAL_QR_LINK
    global PAYMENT_CHANNEL_ID, HOME_INTRO, SUPPORT_TEXT, PAYMENT_INSTRUCTIONS, ADDITIONAL_PAYMENT, PROOF_CHANNEL_URL, TUTORIAL_URL
    if not update.message: return
    user = update.effective_user

    # Broadcast accepts the complete Telegram message (text/photo/video/document/etc.)
    # so users receive the same content the admin sent, including caption/media.
    if user and is_admin_user(user.id) and context.user_data.get('admin_state') == 'ADM_BROADCAST_MSG':
        context.user_data['admin_state'] = None
        users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, '') or {}
        success, fail = 0, 0

        status_msg = await update.message.reply_text("⏳ Broadcasting message to all users...")
        for uid in users.keys():
            try:
                await update.message.copy(chat_id=int(uid))
                success += 1
            except Exception as exc:
                fail += 1
                logger.warning(f"Broadcast failed for {uid}: {exc}")
            await asyncio.sleep(0.05)

        await status_msg.edit_text(
            f"📢 **BROADCAST COMPLETED**\n\n"
            f"✅ Sent: {success}\n"
            f"❌ Failed: {fail}",
            reply_markup=render_admin_back_markup(),
            parse_mode="Markdown",
        )
        return

    # Phone-number verification flow. Handle Telegram contact messages first.
    if update.message.contact:
        contact = update.message.contact

        # Only accept a contact shared by the account owner.
        if contact.user_id and contact.user_id != user.id:
            await update.message.reply_text(
                "❌ Please use the **Share Your Phone Number** button to share your own number.",
                reply_markup=render_phone_verify_keyboard(),
                parse_mode="Markdown"
            )
            return

        if not PHONE_VERIFY_ENABLED:
            await update.message.reply_text(
                "ℹ️ Phone verification is currently disabled by admin.",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        phone_number = str(contact.phone_number or "").strip()
        if not phone_number:
            await update.message.reply_text(
                "❌ Phone number was not received. Please try again.",
                reply_markup=render_phone_verify_keyboard()
            )
            return

        await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user.id}/phone_number", phone_number)
        await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{user.id}/phone_verified", True)

        await update.message.reply_text(
            "✅ **ACCOUNT VERIFIED SUCCESSFULLY!**\n\n"
            "Your phone number has been verified. Welcome to the store.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await build_and_transmit_main_frame(
            context.bot,
            update.message.chat_id,
            user.id,
            user.username or user.first_name
        )
        return

    # The remaining admin/user flows below require plain text.
    if not update.message.text: return
    text = update.message.text.strip()
    # New reference-style main menu buttons are handled here before any
    # state-specific admin/payment input routing. This keeps every visible
    # main-menu button responsive while preserving existing callbacks.
    if (
        not context.user_data.get("admin_state")
        and not context.user_data.get("state_route")
        and await handle_new_main_menu_text(update, context, text)
    ):
        return

    
    # 1. User Manual UTR Verification Route
    if context.user_data.get('state_route') == 'EXPECTING_MANUAL_UTR':
        amt = context.user_data.get('pending_deposit_amt', 0.0)
        context.user_data['state_route'] = None
        
        utr_text = (
            f"📩 **MANUAL DEPOSIT REQUEST SUBMITTED**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: {user.id} | @{user.username or user.first_name}\n"
            f"💰 Amount: {CURRENCY} {amt:.2f}\n"
            f"🔎 UTR / Transaction Hash: `{text}`\n\n"
            f"Your request is under verification."
        )
        await update.message.reply_text("✅ Transaction UTR submitted! Admin will verify and process your balance.", reply_markup=render_back_navigation_markup())
        
        admin_utr_alert = (
            f"🚨 **NEW MANUAL UTR SUBMISSION**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User ID: `{user.id}` | @{user.username or user.first_name}\n"
            f"💰 Amount: {CURRENCY} {amt:.2f}\n"
            f"🔎 UTR: `{text}`\n\n"
            f"To approve, add balance manually via Admin Panel."
        )
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=admin_utr_alert, parse_mode="Markdown")
        except Exception: pass
        return

    # 2. Admin State Routing Engine
    if is_admin_user(user.id) and 'admin_state' in context.user_data and context.user_data['admin_state']:
        astate = context.user_data['admin_state']
        
        if astate in ("ADM_RESELLER_ADD", "ADM_RESELLER_UPGRADE", "ADM_RESELLER_REMOVE"):
            target = text.strip().lstrip("@")
            users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, "") or {}
            found_uid = None
            found_data = None
            for uid, uinfo in users.items():
                if str(uid) == target or str(uinfo.get("username", "")).lstrip("@").lower() == target.lower():
                    found_uid = str(uid)
                    found_data = uinfo
                    break

            if not found_uid or not isinstance(found_data, dict):
                await update.message.reply_text("❌ User not found. Send a valid User ID or @username.", reply_markup=render_admin_back_markup())
                return

            if astate == "ADM_RESELLER_REMOVE":
                if not found_data.get("is_ʀᴇꜱᴇʟʟᴇʀ", False):
                    await update.message.reply_text("ℹ️ This user is not a reseller.", reply_markup=render_reseller_admin_keyboard())
                    context.user_data["admin_state"] = None
                    return
                await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{found_uid}/is_ʀᴇꜱᴇʟʟᴇʀ", False)
                context.user_data["admin_state"] = None
                await update.message.reply_text(f"✅ Reseller removed from User `{found_uid}`.", reply_markup=render_reseller_admin_keyboard(), parse_mode="Markdown")
                try:
                    await context.bot.send_message(chat_id=int(found_uid), text="ℹ️ Your reseller access has been removed by admin. Standard prices are now active.")
                except Exception:
                    pass
                return

            await LocalDatabaseRouter.set_node(DB_USERS_FILE, f"{found_uid}/is_ʀᴇꜱᴇʟʟᴇʀ", True)
            context.user_data["admin_state"] = None
            action_text = "added" if astate == "ADM_RESELLER_ADD" else "upgraded"
            await update.message.reply_text(
                f"✅ Reseller **{action_text} successfully** for User `{found_uid}`.\n\n"
                f"💎 Reseller prices are now active for this account.",
                reply_markup=render_reseller_admin_keyboard(), parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    chat_id=int(found_uid),
                    text="🎉 **RESELLER ACCESS ACTIVATED**\n\nYour account has been upgraded to reseller for free by admin. Reseller prices are now active in the shop.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        elif astate == "WAIT_HOME_MESSAGE":
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "home_message_template", text)
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                "✅ **HOME MESSAGE SAVED**\n\n"
                "The new message will be shown to users on /start.\n"
                "Button colors/layout were not changed.",
                reply_markup=render_admin_panel_keyboard(),
                parse_mode="Markdown",
            )
            return

        elif astate == 'WAIT_WEBSITE_PANEL_URL':

            WEBSITE_PANEL_URL = text.strip()
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "website_panel_url", WEBSITE_PANEL_URL)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ Website panel link saved.", reply_markup=render_bot_settings_keyboard())

        elif astate == 'WAIT_WEBSITE_SYNC_URL':

            WEBSITE_SYNC_URL = text.strip()
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "website_sync_url", WEBSITE_SYNC_URL)
            context.user_data['admin_state'] = None
            ok, msg, count = await sync_products_from_website(WEBSITE_SYNC_URL)
            await update.message.reply_text(f"{'✅' if ok else '❌'} {msg}" + (f"\nCategories synced: {count}" if ok else ""), reply_markup=render_bot_settings_keyboard())

        elif astate == "WAIT_SAME_BOT_ADMIN_ADD":
            if not is_owner_user(user.id):
                context.user_data["admin_state"] = None
                await update.message.reply_text(
                    "⛔ Only the owner can add admins.",
                    reply_markup=render_admin_back_markup()
                )
                return

            target_id = text.strip()
            if not target_id.isdigit():
                await update.message.reply_text(
                    "❌ Invalid User ID. Send numbers only, for example: `123456789`.",
                    reply_markup=render_admin_back_markup(),
                    parse_mode="Markdown"
                )
                return

            target_id_int = int(target_id)
            if target_id_int == int(ADMIN_ID):
                context.user_data["admin_state"] = None
                await update.message.reply_text(
                    "ℹ️ That User ID is already the owner.",
                    reply_markup=render_admin_back_markup()
                )
                return

            cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
            records = cfg.get("co_admin_users", {})
            if not isinstance(records, dict):
                records = {}

            records[str(target_id_int)] = {
                "username": "",
                "added_by": int(ADMIN_ID),
                "added_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            cfg["co_admin_users"] = records
            LocalDatabaseRouter._write_file(DB_CONFIG_FILE, cfg)
            context.user_data["admin_state"] = None

            await update.message.reply_text(
                f"✅ **ADMIN ADDED SUCCESSFULLY**\n\n"
                f"👤 Admin ID: `{target_id_int}`\n"
                f"🤖 Access: This same bot\n"
                f"⚙️ The admin can now use `/admin` and the admin buttons.",
                reply_markup=render_admin_back_markup(),
                parse_mode="Markdown"
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id_int,
                    text="👑 **ADMIN ACCESS GRANTED**\n\nYou have been added as an admin of this bot. Use /admin to open the Admin Control Panel.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return

        elif astate == "WAIT_SAME_BOT_ADMIN_REMOVE":
            if not is_owner_user(user.id):
                context.user_data["admin_state"] = None
                await update.message.reply_text(
                    "⛔ Only the owner can remove admins.",
                    reply_markup=render_admin_back_markup()
                )
                return

            target_id = text.strip()
            if not target_id.isdigit():
                await update.message.reply_text(
                    "❌ Invalid User ID. Send numbers only.",
                    reply_markup=render_admin_back_markup()
                )
                return

            target_id_int = int(target_id)
            if target_id_int == int(ADMIN_ID):
                await update.message.reply_text(
                    "⛔ The owner cannot be removed.",
                    reply_markup=render_admin_back_markup()
                )
                return

            cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
            records = cfg.get("co_admin_users", {})
            if not isinstance(records, dict):
                records = {}

            if str(target_id_int) not in records:
                await update.message.reply_text(
                    "❌ This User ID is not an admin of this bot.",
                    reply_markup=render_admin_back_markup()
                )
                return

            records.pop(str(target_id_int), None)
            cfg["co_admin_users"] = records
            LocalDatabaseRouter._write_file(DB_CONFIG_FILE, cfg)
            context.user_data["admin_state"] = None

            await update.message.reply_text(
                f"✅ Admin access removed for User `{target_id_int}`.",
                reply_markup=render_admin_back_markup(),
                parse_mode="Markdown"
            )
            return

        elif astate == 'WAIT_COADMIN_TOKEN_ID':
            parts = [part.strip() for part in text.split('|', 1)]
            if len(parts) != 2 or not parts[0] or not parts[1].isdigit():
                await update.message.reply_text(
                    "❌ Invalid format. Use: BOT_TOKEN | ADMIN_ID",
                    reply_markup=render_admin_back_markup(),
                )
                return

            token, admin_id = parts

            # Do NOT call Bot.get_me() here. Every ADD attempt was making an
            # immediate Telegram API request; repeated attempts can trigger
            # HTTP 429 / "Flood control exceeded". Validate the token shape
            # locally and let the managed polling worker authenticate it.
            token_ok, bot_key = _local_bot_token_parts(token)
            if not token_ok:
                await update.message.reply_text(
                    f"❌ Invalid bot token format: {bot_key}",
                    reply_markup=render_admin_back_markup(),
                )
                return

            cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
            records = cfg.get("co_admin_bots", {})
            if not isinstance(records, dict):
                records = {}

            records[bot_key] = {
                "token": token,
                "admin_id": int(admin_id),
                "username": bot_key,
                "bot_name": "Managed Bot",
            }
            cfg["co_admin_bots"] = records
            LocalDatabaseRouter._write_file(DB_CONFIG_FILE, cfg)
            context.user_data['admin_state'] = None
            start_managed_bot(token, bot_key)

            await update.message.reply_text(
                f"✅ Co-admin bot added successfully!\n"
                f"🤖 Bot ID: `{bot_key}`\n"
                f"👤 Admin ID: `{admin_id}`\n"
                f"🚀 Bot polling started.\n\n"
                f"If Telegram is temporarily rate-limiting this bot, it will retry automatically.",
                reply_markup=render_admin_back_markup(),
                parse_mode="Markdown",
            )
            return

        elif astate == 'WAIT_COADMIN_REMOVE':
            target = text.lstrip('@').strip().lower()
            cfg = LocalDatabaseRouter._read_file(DB_CONFIG_FILE)
            records = cfg.get("co_admin_bots", {})
            found = None
            for key, record in records.items():
                if str(key).lower() == target or str(record.get("username", "")).lstrip('@').lower() == target:
                    found = key
                    break
            if not found:
                await update.message.reply_text("❌ Co-admin bot not found.", reply_markup=render_admin_back_markup())
                return
            records.pop(found, None)
            cfg["co_admin_bots"] = records
            LocalDatabaseRouter._write_file(DB_CONFIG_FILE, cfg)
            stop_managed_bot(found)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ Co-admin bot removed successfully and its polling has been stopped.", reply_markup=render_admin_back_markup())

        elif astate == 'WAIT_BOT_TITLE':

            BOT_TITLE = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "bot_title", BOT_TITLE)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Bot Title updated to: `{BOT_TITLE}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_CURRENCY':
            CURRENCY = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "currency", CURRENCY)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Currency updated to: `{CURRENCY}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_OWNER_USER':

            OWNER_USERNAME = text if text.startswith('@') else f"@{text}"
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "owner_username", OWNER_USERNAME)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Owner Username updated to: `{OWNER_USERNAME}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_UPI_NAME':

            UPI_HOLDER_NAME = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "upi_holder_name", UPI_HOLDER_NAME)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ UPI Holder Name updated to: `{UPI_HOLDER_NAME}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_UPI_ID':

            MERCHANT_UPI_ID = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "upi_id", MERCHANT_UPI_ID)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ UPI ID updated to: `{MERCHANT_UPI_ID}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_FAMPAY_UPI':

            MERCHANT_UPI_ID = text.strip()
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "upi_id", MERCHANT_UPI_ID)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ FamPay UPI ID updated: `{MERCHANT_UPI_ID}`", reply_markup=render_fampay_settings_keyboard(), parse_mode="Markdown")

        elif astate == 'WAIT_FAMPAY_API_KEY':

            FAMPAY_API_KEY = text.strip()
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "api_key", FAMPAY_API_KEY)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ FamPay API Key updated.", reply_markup=render_fampay_settings_keyboard(), parse_mode="Markdown")

        elif astate == 'WAIT_FAMPAY_QR_URL':

            FAMPAY_QR_URL = text.strip()
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "fampay_qr_url", FAMPAY_QR_URL)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ FamPay QR URL updated: `{FAMPAY_QR_URL}`", reply_markup=render_fampay_settings_keyboard(), parse_mode="Markdown")

        elif astate == 'WAIT_FAMPAY_VERIFY_URL':

            FAMPAY_VERIFY_URL = text.strip()
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "fampay_verify_url", FAMPAY_VERIFY_URL)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ FamPay Verify URL updated: `{FAMPAY_VERIFY_URL}`", reply_markup=render_fampay_settings_keyboard(), parse_mode="Markdown")

        elif astate == 'WAIT_FAMPAY_BASE_URL':

            API_BASE_URL = text.strip().rstrip("/")
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "fampay_api_base_url", API_BASE_URL)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ FamPay API Base URL updated: `{API_BASE_URL}`", reply_markup=render_fampay_settings_keyboard(), parse_mode="Markdown")

        elif astate == 'WAIT_MANUAL_QR':

            STATIC_MANUAL_QR_LINK = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "qr_link", STATIC_MANUAL_QR_LINK)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Manual QR Link updated to: `{STATIC_MANUAL_QR_LINK}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_PAY_CHAN':

            PAYMENT_CHANNEL_ID = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "payment_channel_id", PAYMENT_CHANNEL_ID)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Payment Channel ID updated to: `{PAYMENT_CHANNEL_ID}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_HOME_INTRO':

            HOME_INTRO = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "home_intro", HOME_INTRO)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ Home Intro text updated!", reply_markup=render_admin_back_markup())

        elif astate == 'WAIT_SUPP_TXT':

            SUPPORT_TEXT = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "support_text", SUPPORT_TEXT)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ Support Text updated!", reply_markup=render_admin_back_markup())

        elif astate == 'WAIT_PAY_INST':

            PAYMENT_INSTRUCTIONS = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "payment_instructions", PAYMENT_INSTRUCTIONS)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ Payment Instructions updated!", reply_markup=render_admin_back_markup())

        elif astate == 'WAIT_ADD_PAY':

            ADDITIONAL_PAYMENT = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "additional_payment", ADDITIONAL_PAYMENT)
            context.user_data['admin_state'] = None
            await update.message.reply_text("✅ Additional Payment Info updated!", reply_markup=render_admin_back_markup())

        elif astate == 'WAIT_PROOF_URL':

            PROOF_CHANNEL_URL = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "proof_channel_url", PROOF_CHANNEL_URL)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Proof Channel Link updated to: `{PROOF_CHANNEL_URL}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'WAIT_TUT_URL':

            TUTORIAL_URL = text
            await LocalDatabaseRouter.set_node(DB_CONFIG_FILE, "tutorial_url", TUTORIAL_URL)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Tutorial Link updated to: `{TUTORIAL_URL}`", reply_markup=render_admin_back_markup(), parse_mode="Markdown")

        elif astate == 'SB_ADD_CAT_NAME':
            cat_id = f"cat_{int(time.time())}"
            new_cat = {"name": text, "active": True, "emoji_id": "", "panels": {}}
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}", new_cat)
            context.user_data['admin_state'] = f"SB_SET_CAT_EMOJI|{cat_id}"
            await update.message.reply_text(
                f"✅ Category **{text}** created.\n\n"
                f"✨ Send the Telegram Custom Emoji ID for this category.\n"
                f"Example: `5368324170671202286`",
                reply_markup=render_admin_back_markup(), parse_mode="Markdown"
            )

        elif astate.startswith('SB_SET_CAT_EMOJI|'):
            cat_id = astate.split('|', 1)[1]
            emoji_id = text.strip()
            if not emoji_id.isdigit():
                await update.message.reply_text(
                    "❌ Invalid Emoji ID. Please send numbers only.",
                    reply_markup=render_admin_back_markup()
                )
                return
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/emoji_id", emoji_id)
            context.user_data['admin_state'] = None
            categories = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, 'categories') or {}
            await update.message.reply_text(
                "✨ Premium Emoji ID saved successfully!",
                reply_markup=render_store_builder_keyboard(categories)
            )

        elif astate.startswith('SB_ADD_PNL_NAME|'):
            cat_id = astate.split('|')[1]
            p_id = f"pnl_{int(time.time())}"
            new_pnl = {"name": text, "active": True, "emoji_id": "", "plans": {}, "keys": {}}
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}", new_pnl)
            context.user_data['admin_state'] = f"SB_SET_PNL_EMOJI|{cat_id}:{p_id}"
            await update.message.reply_text(
                f"✅ Panel **{text}** created.\n\n"
                f"✨ Send the Telegram Custom Emoji ID for this panel.\n"
                f"Example: `5368324170671202286`",
                reply_markup=render_admin_back_markup(), parse_mode="Markdown"
            )

        elif astate.startswith('SB_SET_PNL_EMOJI|'):
            payload = astate.split('|', 1)[1]
            cat_id, p_id = payload.split(':', 1)
            emoji_id = text.strip()
            if not emoji_id.isdigit():
                await update.message.reply_text(
                    "❌ Invalid Emoji ID. Please send numbers only.",
                    reply_markup=render_admin_back_markup()
                )
                return
            await LocalDatabaseRouter.set_node(
                DB_PRODUCTS_FILE,
                f"categories/{cat_id}/panels/{p_id}/emoji_id",
                emoji_id
            )
            context.user_data['admin_state'] = None
            cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
            await update.message.reply_text(
                "✨ Premium Emoji ID saved successfully!",
                reply_markup=render_category_manage_keyboard(cat_id, cat_data)
            )

        elif astate.startswith('SB_RENAME_CAT|'):
            cat_id = astate.split('|')[1]
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/name", text)
            context.user_data['admin_state'] = None
            cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
            await update.message.reply_text(f"✅ Category renamed to **{text}**!", reply_markup=render_category_manage_keyboard(cat_id, cat_data), parse_mode="Markdown")

        elif astate.startswith('SB_RENAME_PNL|'):
            payload = astate.split('|')[1]
            cat_id, p_id = payload.split(':', 1)
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/name", text)
            context.user_data['admin_state'] = None
            cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
            p_data = cat_data.get("panels", {}).get(p_id, {})
            await update.message.reply_text(f"✅ Panel renamed to **{text}**!", reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data), parse_mode="Markdown")

        elif astate.startswith('SB_DESC_PNL|'):
            payload = astate.split('|')[1]
            cat_id, p_id = payload.split(':', 1)
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/description", text)
            context.user_data['admin_state'] = None
            cat_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}") or {}
            p_data = cat_data.get("panels", {}).get(p_id, {})
            await update.message.reply_text("✅ Panel description updated!", reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data))

        elif astate.startswith('SB_WAITING_VAL_DAYS|'):
            payload = astate.split('|')[1]
            cat_id, p_id = payload.split(':', 1)
            raw_duration = text.strip().lower()
            raw_duration = re.sub(r"\s+", " ", raw_duration).strip()

            # Accept flexible input such as 1H, 2 hours, 1D, 7 days.
            m = re.fullmatch(r"(\d+)\s*(h|hr|hrs|hour|hours|d|day|days)?", raw_duration)
            if not m or int(m.group(1)) <= 0:
                await update.message.reply_text(
                    "❌ Invalid duration. Examples: `1H`, `2H`, `1D`, `7D`, `1 hour`, `2 hours`, `1 day`.",
                    reply_markup=render_admin_back_markup(),
                    parse_mode="Markdown"
                )
                return

            amount = int(m.group(1))
            unit = (m.group(2) or "d").lower()
            is_hours = unit in {"h", "hr", "hrs", "hour", "hours"}

            # Existing day packages use plain numeric keys; hour packages use H.
            day = f"{amount}H" if is_hours else str(amount)

            p_data = await LocalDatabaseRouter.get_node(
                DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}"
            ) or {}
            if "plans" not in p_data:
                p_data["plans"] = {}
            if "keys" not in p_data:
                p_data["keys"] = {}

            if day in p_data["plans"]:
                await update.message.reply_text(
                    f"❌ Validity package **{day}** already exists.",
                    reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data),
                    parse_mode="Markdown"
                )
                return

            if is_hours:
                p_data["plans"][day] = {
                    "standard": 50.0,
                    "ʀᴇꜱᴇʟʟᴇʀ": 40.0,
                    "unit": "hours"
                }
            else:
                p_data["plans"][day] = {
                    "standard": 50.0,
                    "ʀᴇꜱᴇʟʟᴇʀ": 40.0
                }

            p_data["keys"][day] = {}
            await LocalDatabaseRouter.set_node(
                DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}", p_data
            )
            context.user_data['admin_state'] = None
            label = f"{amount} HOUR(S)" if is_hours else f"{amount} DAY(S)"
            await update.message.reply_text(
                f"✅ Custom validity **{label}** added!",
                reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data),
                parse_mode="Markdown"
            )

        elif astate.startswith('SB_EDIT_VALIDITY|'):
            payload = astate.split('|', 1)[1]
            cat_id, p_id, old_day = payload.split(':', 2)
            new_day = text.strip()
            if not re.fullmatch(r"\d+(?:H)?", new_day):
                await update.message.reply_text(
                    "❌ Invalid validity. Use values like 1, 7, 30 or 24H.",
                    reply_markup=render_sb_back_markup(
                        f"sb_pkg_view_{cat_id}:{p_id}:{old_day}", "BACK TO PACKAGE"
                    )
                )
                return
            p_data = await LocalDatabaseRouter.get_node(
                DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}"
            ) or {}
            plans = p_data.setdefault("plans", {})
            keys = p_data.setdefault("keys", {})
            if new_day != old_day:
                if new_day in plans:
                    await update.message.reply_text(
                        "❌ That validity already exists.",
                        reply_markup=render_sb_back_markup(
                            f"sb_pkg_view_{cat_id}:{p_id}:{old_day}", "BACK TO PACKAGE"
                        )
                    )
                    return
                plans[new_day] = plans.pop(old_day)
                if old_day in keys:
                    keys[new_day] = keys.pop(old_day)
                await LocalDatabaseRouter.set_node(
                    DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}", p_data
                )
            context.user_data["admin_state"] = None
            await update.message.reply_text(
                f"✅ Validity updated to **{new_day}**.",
                reply_markup=render_panel_manage_keyboard(cat_id, p_id, p_data),
                parse_mode="Markdown"
            )

        elif astate.startswith('SB_EDIT_LIMIT|'):
            payload = astate.split('|', 1)[1]
            cat_id, p_id, day = payload.split(':', 2)
            try:
                limit = int(text.strip())
                if limit < 0:
                    raise ValueError
                path = f"categories/{cat_id}/panels/{p_id}/plans/{day}"
                pricing = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, path)
                if not isinstance(pricing, dict):
                    pricing = {"standard": float(pricing or 0)}
                pricing["limit"] = limit
                await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, path, pricing)
                context.user_data["admin_state"] = None
                p_data = await LocalDatabaseRouter.get_node(
                    DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}"
                ) or {}
                await update.message.reply_text(
                    f"✅ Purchase limit set to **{limit if limit else 'Unlimited'}**.",
                    reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data),
                    parse_mode="Markdown"
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Enter a whole number. Use 0 for Unlimited.",
                    reply_markup=render_sb_back_markup(
                        f"sb_pkg_view_{cat_id}:{p_id}:{day}", "BACK TO PACKAGE"
                    )
                )

        elif astate.startswith('SB_EDIT_PRICE_VAL|'):
            payload = astate.split('|')[1]
            cat_id, p_id, day = payload.split(':', 2)
            try:
                new_price = float(text)
                await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/plans/{day}/standard", new_price)
                context.user_data['admin_state'] = None
                p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
                await update.message.reply_text(f"✅ Price updated to **₹{new_price:.2f}**!", reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data), parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("❌ Invalid price number. Enter a valid number:")

        elif astate.startswith('SB_EDIT_RESELLER_PRICE|'):
            payload = astate.split('|', 1)[1]
            cat_id, p_id, day = payload.split(':', 2)
            try:
                new_price = float(text)
                if new_price < 0:
                    raise ValueError
                pricing = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/plans/{day}")
                if not isinstance(pricing, dict):
                    pricing = {"standard": float(pricing or 0.0)}
                pricing["ʀᴇꜱᴇʟʟᴇʀ"] = new_price
                await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/plans/{day}", pricing)
                context.user_data['admin_state'] = None
                p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
                await update.message.reply_text(
                    f"✅ Reseller price updated to **{CURRENCY} {new_price:.2f}**.",
                    reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data), parse_mode="Markdown"
                )
            except ValueError:
                await update.message.reply_text("❌ Invalid price. Enter a valid non-negative number:", reply_markup=render_admin_back_markup())

        elif astate.startswith('SB_ADD_KEYS_TEXT|'):
            payload = astate.split('|')[1]
            cat_id, p_id, day = payload.split(':', 2)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            p_data = await LocalDatabaseRouter.get_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}") or {}
            existing_keys = p_data.get("keys", {}).get(day, {})
            if not isinstance(existing_keys, dict): existing_keys = {}
            
            added_count = 0
            for k in lines:
                k_id = f"k_{int(time.time() * 1000)}_{random.randint(100, 999)}"
                existing_keys[k_id] = k
                added_count += 1
                
            await LocalDatabaseRouter.set_node(DB_PRODUCTS_FILE, f"categories/{cat_id}/panels/{p_id}/keys/{day}", existing_keys)
            context.user_data['admin_state'] = None
            await update.message.reply_text(f"✅ Added **{added_count}** keys to stock!", reply_markup=render_package_manage_keyboard(cat_id, p_id, day, p_data), parse_mode="Markdown")

        elif astate == 'ADM_BAL_SEARCH':
            target = text.replace('@', '').strip()
            users = await LocalDatabaseRouter.get_node(DB_USERS_FILE, '') or {}
            found_uid = None
            found_data = None
            
            for uid, uinfo in users.items():
                if not isinstance(uinfo, dict):
                    continue
                stored_username = str(uinfo.get("username") or "").lstrip("@")
                if str(uid) == target or stored_username.lower() == target.lower():
                    found_uid = uid
                    found_data = uinfo
                    break
                    
            if not found_data:
                await update.message.reply_text("❌ User not found in database.", reply_markup=render_admin_back_markup())
                return
                
            context.user_data['admin_state'] = f"ADM_BAL_ADD_AMT|{found_uid}"
            await update.message.reply_text(
                f"👤 **USER FOUND:**\n"
                f"ID: `{found_uid}`\n"
                f"Username: @{found_data.get('username')}\n"
                f"Current Balance: ₹{found_data.get('balance', 0):.2f}\n\n"
                f"Enter amount to ADD (use negative sign to deduct, e.g., 100 or -50):",
                reply_markup=render_admin_back_markup(),
                parse_mode="Markdown"
            )

        elif astate.startswith('ADM_BAL_ADD_AMT|'):
            target_uid = astate.split('|')[1]
            try:
                amt = float(text)
                new_bal = await process_wallet_balance_mutation(target_uid, amt)
                context.user_data['admin_state'] = None
                await update.message.reply_text(f"✅ Balance updated successfully! New Balance: **₹{new_bal:.2f}**", reply_markup=render_admin_back_markup(), parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("❌ Invalid amount format. Enter a valid number:")


# ==========================================
# 🚀 SYSTEM BOOTSTRAP & APPLICATION RUNNER
# ==========================================

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # System Settings Pre-Load
    asyncio.run(load_system_settings(application))

    # Command Handlers
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("admin", admin_panel_launcher))
    application.add_handler(CommandHandler("buybot", buybot_command_handler))

    # Callback & Message Handlers
    # Dedicated Buy Bot route is registered first so normal-user /buybot
    # buttons are always handled independently of the admin/global router.
    application.add_handler(
        CallbackQueryHandler(
            buybot_callback_handler,
            pattern=r"^buybot_(?:create|source|back|back_shop)$"
        )
    )
    # Dedicated CO-ADMIN menu route is registered before the global router.
    application.add_handler(CallbackQueryHandler(coadmin_menu_callback_handler, pattern=r"^adm_coadmin_menu$"))
    application.add_handler(CallbackQueryHandler(global_callback_routing_engine))
    # Accept all non-command messages so broadcast can copy photos, captions,
    # videos, documents, and other Telegram message types exactly as sent.
    application.add_handler(MessageHandler(~filters.COMMAND, handle_text_messages))

    # Start any saved co-admin bots in background threads.
    saved_bots = get_managed_bot_records()
    for bot_key, record in saved_bots.items():
        token = str(record.get("token", "")).strip()
        if token:
            start_managed_bot(token, bot_key)

    logger.info("Bot starting polling loop...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
