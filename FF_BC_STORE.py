# ============================================================
# UMESH STORE BOT - FINAL COMPLETE (43 BUGS FIXED)
# ============================================================

import sqlite3
import json
import time
import threading
import urllib.request
import os
import math
import random
import re
import shutil
import sys
import csv
import io
import concurrent.futures
from datetime import datetime, date, timedelta, timezone
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import logging
import logging.handlers  # BUG #16 FIX: RotatingFileHandler
import html  # BUG #17, #18 FIX: HTML escape
# BUG #15 FIX: uuid import removed (unused)

# ============ CONFIG ============
BOT_TOKEN = "8872666357:AAGkwsDBA7ehSFlPd92SJSwogqOGO35dlWQ"  # Apna bot token yaha daalo (@BotFather se lo)
ADMIN_USER_ID = 6523688951  #Yaha Admin apna user id daalega (@userinfobot se lo)
SUCCESS_IMG = "AgACAgUAAxkBAAFVWfZqv0yf-FvrC3EvDMG8-Qyu9d1WoAACGhRrG_CQ-FV-3xIeIyg5DwEAAwIAA3kAAz0E" # @RawDataBot ko image bhejo, file_id copy karo
FAMPAY_UPI_ID = "Umeshxmodz@fam" #Apna famPay upi id yaha daalo
DB_PATH = "Umesh_database.db" #Database file ka naam (change kar sakte ho)
BACKUP_DIR = "backups"

API_URL = "https://bantibhaiya.to/api/reseller_v1.php" #Apna API endpoint yaha daalo
API_KEY = "9258be9436aa62c59709c04250eabebe" #Apna api key yaha daalo
MASTER_KEY = "a7f3e8b2c9d1f4a6b8c2d5e9f1a3b6c8" #Apna master key yaha daalo

FAMPAY_VERIFY_URL = "YOUR_FAMPAY_URL" #Apna verify URL yaha daalo
FAMPAY_QR_URL = "YOUR_FAMPAY_QR_URL" #Apna QR URL yaha daalo
FAMPAY_API_KEY = "fam_261f9ff76795f0683b408f73aba989d689d5d6a8" #Apna FAMPAY API key yaha daalo api lene ke liye admin @Umeshxmodz ko contact karo

FAMPAY_TIMEOUT_SECONDS = 300
FAMPAY_CHECK_INTERVAL = 5
PENDING_API_CHECK_INTERVAL = 60
SPIN_EXPIRY_CHECK_INTERVAL = 60
REVIEW_REMINDER_INTERVAL = 60
PROCESSING_RESET_INTERVAL = 300
MAX_REVIEW_REMINDERS = 3
BROADCAST_DELAY = 0.05
SPIN_COOLDOWN_SECONDS = 86400
TICKET_COOLDOWN_SECONDS = 120
USER_STATE_TTL_SECONDS = 3600
INACTIVE_DAYS = 7

# BUG #2, #29 FIX: max retry for pending API orders
MAX_PENDING_API_RETRIES = 3

last_api_call = 0
API_CALL_DELAY = 1.5

# BUG #12 FIX: bot username cache
_bot_username_cache = {"value": None, "ts": 0}

# ============ LOGGING ============
# BUG #16 FIX: RotatingFileHandler added
_log_handler = logging.handlers.RotatingFileHandler(
    'bot.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
)
_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])
logger = logging.getLogger(__name__)

_api_handler = logging.handlers.RotatingFileHandler(
    'api_errors.log', maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
)
_api_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
api_logger = logging.getLogger('api_logger')
api_logger.addHandler(_api_handler)
api_logger.setLevel(logging.ERROR)

_api_success_handler = logging.handlers.RotatingFileHandler(
    'api_success.log', maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
)
_api_success_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
api_success_logger = logging.getLogger('api_success')
api_success_logger.addHandler(_api_success_handler)
api_success_logger.setLevel(logging.INFO)

# ============ HELPERS ============
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def utc_now_str():
    return utc_now().strftime('%Y-%m-%d %H:%M:%S')

def epoch_now():
    return int(time.time())

# BUG #17 FIX: HTML escape helper
def esc(text):
    if text is None:
        return ""
    return html.escape(str(text))

def safe_send(chat_id, text, markup=None):
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.warning(f"safe_send HTML failed for {chat_id}: {e}")
        try:
            bot.send_message(chat_id, text, reply_markup=markup)
        except Exception as e2:
            logger.error(f"safe_send plain failed for {chat_id}: {e2}")

def safe_navigate(call, text, markup=None):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception:
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=markup)
            except Exception as e2:
                logger.error(f"safe_navigate fallback failed: {e2}")

# ============ USER STATES ============
user_states = {}
user_states_lock = threading.Lock()
user_state_timestamps = {}

def set_user_state(user_id, state):
    with user_states_lock:
        user_states[user_id] = state
        user_state_timestamps[user_id] = time.time()

def get_user_state(user_id):
    with user_states_lock:
        ts = user_state_timestamps.get(user_id, 0)
        if time.time() - ts > USER_STATE_TTL_SECONDS:
            user_states.pop(user_id, None)
            user_state_timestamps.pop(user_id, None)
            return {}
        return user_states.get(user_id, {})

def pop_user_state(user_id):
    with user_states_lock:
        user_states.pop(user_id, None)
        user_state_timestamps.pop(user_id, None)

def cleanup_user_states():
    while True:
        try:
            now = time.time()
            with user_states_lock:
                expired = [uid for uid, ts in user_state_timestamps.items() if now - ts > USER_STATE_TTL_SECONDS]
                for uid in expired:
                    user_states.pop(uid, None)
                    user_state_timestamps.pop(uid, None)
        except Exception as e:
            logger.error(f"cleanup_user_states error: {e}")
        time.sleep(300)

# ============ RATE LIMITER ============
# BUG #24 FIX: use plain dict + lock, no defaultdict race
rate_limit_buckets = {}
rate_limit_lock = threading.Lock()

def is_rate_limited(key, max_calls, window_seconds):
    with rate_limit_lock:
        now = time.time()
        bucket = rate_limit_buckets.get(key, [])
        bucket = [t for t in bucket if now - t < window_seconds]
        if len(bucket) >= max_calls:
            rate_limit_buckets[key] = bucket
            return True
        bucket.append(now)
        rate_limit_buckets[key] = bucket
        return False

# ============ DB ============
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

# ============ ADMIN ACTIVITY LOG ============
def log_admin_action(admin_id, action, details=""):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admin_logs (admin_id, action, details, created_at) VALUES (?,?,?,?)",
            (admin_id, action[:100], details[:500], utc_now_str())
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"log_admin_action error: {e}")

# ============ API ============
def fetch_key_from_api(product_id, duration):
    global last_api_call
    elapsed = time.time() - last_api_call
    if elapsed < API_CALL_DELAY:
        time.sleep(API_CALL_DELAY - elapsed)
    data = {'api_key': API_KEY, 'action': 'buy', 'product_id': str(product_id), 'duration': duration}
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'x-master-key': MASTER_KEY, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.post(API_URL, data=data, headers=headers, timeout=20, verify=True)
        last_api_call = time.time()
        text = response.text.strip()
        api_success_logger.info(f"API Call | PID: {product_id} | Duration: {duration} | Response: {text[:100]}")
        return text
    except requests.exceptions.Timeout:
        last_api_call = time.time()
        api_logger.error(f"API Timeout | PID: {product_id} | Duration: {duration}")
        return "error: API timeout"
    except requests.exceptions.ConnectionError as e:
        last_api_call = time.time()
        api_logger.error(f"API Connection Error | PID: {product_id} | Duration: {duration} | {e}")
        return "error: Connection error"
    except Exception as e:
        last_api_call = time.time()
        api_logger.error(f"API Exception | PID: {product_id} | Duration: {duration} | Error: {str(e)}")
        return f"error: {str(e)}"

def parse_api_response(api_response):
    if not api_response:
        return None, "Empty response"
    text = str(api_response).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            data = json.loads(text)
            status = data.get("status", "").lower()
            if status == "success":
                key = data.get("key") or data.get("license_key")
                if key:
                    return key.strip(), None
            elif status == "error":
                return None, data.get("message", "Unknown error")
        except Exception:
            pass
    if re.match(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', text):
        return text, None
    low = text.lower()
    if any(word in low for word in ["maintenance", "stock", "error", "invalid", "failed", "not found"]):
        return None, text
    if re.match(r'^[A-Za-z0-9_\-]{8,50}$', text):
        return text, None
    return None, text

# ============ DB INIT ============
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, status TEXT DEFAULT 'active',
        category TEXT DEFAULT 'nonroot', api_pid TEXT DEFAULT NULL, demo_video TEXT DEFAULT NULL,
        features TEXT DEFAULT NULL, download_link TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, duration TEXT NOT NULL,
        price INTEGER NOT NULL, reseller_price INTEGER DEFAULT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, verified INTEGER DEFAULT 0,
        phone_number TEXT DEFAULT NULL, total_orders INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0,
        last_active TIMESTAMP NULL DEFAULT NULL, is_reseller INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL, referral_earnings INTEGER DEFAULT 0,
        total_referrals INTEGER DEFAULT 0, last_spin_at TIMESTAMP NULL DEFAULT NULL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        type TEXT DEFAULT 'purchase', details TEXT, license_key TEXT DEFAULT NULL,
        product_name TEXT DEFAULT NULL, duration TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS pending_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, order_id TEXT NOT NULL UNIQUE,
        amount INTEGER NOT NULL, status TEXT DEFAULT 'pending', created_at INTEGER NOT NULL)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, subject TEXT NOT NULL,
        message TEXT NOT NULL, priority TEXT DEFAULT 'normal', status TEXT DEFAULT 'open',
        admin_reply TEXT DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS pending_api_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL, amount INTEGER NOT NULL, coupon_id INTEGER DEFAULT NULL,
        spin_reward_id INTEGER DEFAULT NULL, status TEXT DEFAULT 'pending',
        retry_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS manual_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER DEFAULT 0,
        utr TEXT NOT NULL, screenshot_file_id TEXT NOT NULL, status TEXT DEFAULT 'pending',
        admin_reason TEXT DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1), qr_code_file_id TEXT DEFAULT NULL,
        selling_proof_link TEXT DEFAULT NULL, reseller_fee INTEGER DEFAULT 399,
        reseller_min_balance INTEGER DEFAULT 2000, min_deposit INTEGER DEFAULT 500,
        support_name_1 TEXT DEFAULT 'Support',
        tutorial_video TEXT DEFAULT '', bot_maintenance TEXT DEFAULT 'off',
        support_url TEXT DEFAULT 'https://t.me/',
        manual_upi TEXT DEFAULT 'TERA_UPI_ID')""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS maintenance_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        notified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, product_id))""")  # BUG #30 FIX: UNIQUE constraint
    cursor.execute("""CREATE TABLE IF NOT EXISTS category_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, category TEXT NOT NULL,
        notified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, discount_percent INTEGER NOT NULL,
        used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        rating INTEGER NOT NULL, screenshot_file_id TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS review_reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
        last_reminder_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reminder_count INTEGER DEFAULT 0,
        review_submitted INTEGER DEFAULT 0)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, is_main INTEGER DEFAULT 0)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS support_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, user_id INTEGER)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS spin_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
        status TEXT DEFAULT 'active', expires_at TIMESTAMP NOT NULL, warning_sent INTEGER DEFAULT 0,
        expire_sent INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS faq (
        id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, answer TEXT NOT NULL,
        display_order INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL, action TEXT NOT NULL,
        details TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, is_main) VALUES (?, 1)", (ADMIN_USER_ID,))
    migrations = [
        "ALTER TABLE settings ADD COLUMN tutorial_video TEXT DEFAULT ''",
        "ALTER TABLE settings ADD COLUMN reseller_fee INTEGER DEFAULT 399",
        "ALTER TABLE settings ADD COLUMN reseller_min_balance INTEGER DEFAULT 2000",
        "ALTER TABLE settings ADD COLUMN min_deposit INTEGER DEFAULT 500",
        "ALTER TABLE settings ADD COLUMN support_name_1 TEXT DEFAULT 'Support'",
        "ALTER TABLE settings ADD COLUMN bot_maintenance TEXT DEFAULT 'off'",
        "ALTER TABLE settings ADD COLUMN support_url TEXT DEFAULT 'https://t.me/TERA_USERNAME'",
        "ALTER TABLE settings ADD COLUMN manual_upi TEXT DEFAULT 'TERA_UPI_ID'",
        "ALTER TABLE products ADD COLUMN api_pid TEXT DEFAULT NULL",
        "ALTER TABLE products ADD COLUMN download_link TEXT DEFAULT NULL",
        "ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'nonroot'",
        "ALTER TABLE users ADD COLUMN last_spin_at TIMESTAMP NULL DEFAULT NULL",
        "ALTER TABLE spin_rewards ADD COLUMN warning_sent INTEGER DEFAULT 0",
        "ALTER TABLE spin_rewards ADD COLUMN expire_sent INTEGER DEFAULT 0",
        "ALTER TABLE transactions ADD COLUMN license_key TEXT DEFAULT NULL",
        "ALTER TABLE transactions ADD COLUMN product_name TEXT DEFAULT NULL",
        "ALTER TABLE transactions ADD COLUMN duration TEXT DEFAULT NULL",
        "ALTER TABLE pending_api_orders ADD COLUMN coupon_id INTEGER DEFAULT NULL",
        "ALTER TABLE pending_api_orders ADD COLUMN spin_reward_id INTEGER DEFAULT NULL",
        "ALTER TABLE pending_api_orders ADD COLUMN retry_count INTEGER DEFAULT 0",  # BUG #2 FIX
        "ALTER TABLE review_reminders ADD COLUMN reminder_count INTEGER DEFAULT 0",
        "ALTER TABLE support_tickets ADD COLUMN priority TEXT DEFAULT 'normal'",
    ]
    for sql in migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass
        except Exception as e:
            logger.warning(f"migration skip: {sql} | {e}")

    # BUG #7 FIX: backfill NULL last_reminder_at
    try:
        cursor.execute("UPDATE review_reminders SET last_reminder_at=? WHERE last_reminder_at IS NULL", (utc_now_str(),))
        conn.commit()
    except Exception as e:
        logger.warning(f"backfill review_reminders failed: {e}")

    # BUG #30 FIX: add unique index (in case table already existed without it)
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_maint_notif_unique ON maintenance_notifications(user_id, product_id)")
        conn.commit()
    except Exception as e:
        logger.warning(f"unique index creation failed (may have dupes): {e}")

    cursor.execute("SELECT COUNT(*) as c FROM faq")
    if cursor.fetchone()["c"] == 0:
        defaults = [
            ("Balance kaise add karein?", "💰 Add Balance → FamPay (auto 5 min) ya Manual Deposit (admin verify)"),
            ("Key kaise milegi?", "🔑 Purchase ke baad automatically key mil jayegi — key pe click karke copy karo"),
            ("Refund milega?", "❌ Refund policy nahi hai. Balance safe rahta hai agar purchase fail ho."),
            ("Key kaam nahi kar rahi?", "📞 Support → Create Ticket banao. Admin respond karega."),
            ("Reseller kaise banein?", "🤝 Minimum ₹2000 balance deposit karo. ₹399 activation fee ke baad reseller ban jaoge. Baaki balance wallet mein safe rahega."),
        ]
        for i, (q, a) in enumerate(defaults, 1):
            cursor.execute("INSERT INTO faq (question, answer, display_order) VALUES (?,?,?)", (q, a, i))
    conn.commit()
    cursor.close()
    conn.close()

# ============ SETTINGS ============
ALLOWED_SETTINGS = {'qr_code_file_id', 'selling_proof_link', 'reseller_fee', 'reseller_min_balance', 'min_deposit', 'support_name_1', 'tutorial_video', 'bot_maintenance', 'support_url', 'manual_upi'}

# BUG #14 FIX: no f-string SQL — explicit mapping
_SETTINGS_COLS = {
    'qr_code_file_id': 'qr_code_file_id',
    'selling_proof_link': 'selling_proof_link',
    'reseller_fee': 'reseller_fee',
    'reseller_min_balance': 'reseller_min_balance',
    'min_deposit': 'min_deposit',
    'support_name_1': 'support_name_1',
    'tutorial_video': 'tutorial_video',
    'bot_maintenance': 'bot_maintenance',
    'support_url': 'support_url',
    'manual_upi': 'manual_upi',
}

def get_setting(key, default=None):
    col = _SETTINGS_COLS.get(key)
    if not col:
        logger.warning(f"get_setting blocked unknown key: {key}")
        return default
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT {col} FROM settings WHERE id=1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[col] if row and row[col] is not None else default
    except Exception as e:
        logger.error(f"get_setting error: {e}")
        return default

def update_setting(key, value):
    col = _SETTINGS_COLS.get(key)
    if not col:
        logger.warning(f"update_setting blocked unknown key: {key}")
        return False
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE settings SET {col}=? WHERE id=1", (value,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"update_setting error: {e}")
        return False

def update_last_active(user_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active=? WHERE id=?", (utc_now_str(), user_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"update_last_active error: {e}")

def is_reseller(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_reseller FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return bool(row and row["is_reseller"] == 1)

def is_verified(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT verified FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return bool(row and row["verified"] == 1)

def set_verified(user_id, phone_number):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET verified=1, phone_number=? WHERE id=?", (phone_number, user_id))
    conn.commit()
    cursor.close()
    conn.close()

def is_banned(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT banned FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return bool(row and row["banned"] == 1)

def ban_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banned=1 WHERE id=?", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

def unban_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banned=0 WHERE id=?", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

def is_new_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE user_id=? AND type='add_money'", (user_id,))
    count = cursor.fetchone()["c"]
    cursor.close()
    conn.close()
    return count == 0

# ============ MAINTENANCE ============
_maintenance_cache = {"value": False, "ts": 0}
_maintenance_lock = threading.Lock()

def is_bot_maintenance():
    now = time.time()
    with _maintenance_lock:
        if now - _maintenance_cache["ts"] < 30:
            return _maintenance_cache["value"]
    value = get_setting("bot_maintenance", "off") == "on"
    with _maintenance_lock:
        _maintenance_cache["value"] = value
        _maintenance_cache["ts"] = now
    return value

# ============ ADMINS ============
_admin_cache = {"ids": [], "ts": 0}
_admin_lock = threading.Lock()

def get_admin_ids(force=False):
    now = time.time()
    with _admin_lock:
        if not force and now - _admin_cache["ts"] < 60 and _admin_cache["ids"]:
            return list(_admin_cache["ids"])
    ids = []
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        ids = [r["user_id"] for r in rows]
    except Exception as e:
        logger.error(f"get_admin_ids error: {e}")
    if ADMIN_USER_ID in ids:
        ids.remove(ADMIN_USER_ID)
    ids.insert(0, ADMIN_USER_ID)
    with _admin_lock:
        _admin_cache["ids"] = ids
        _admin_cache["ts"] = now
    return ids

def invalidate_admin_cache():
    with _admin_lock:
        _admin_cache["ts"] = 0

# BUG #12 FIX: bot username cache
def get_bot_username():
    now = time.time()
    if _bot_username_cache["value"] and now - _bot_username_cache["ts"] < 3600:
        return _bot_username_cache["value"]
    try:
        uname = bot.get_me().username
    except Exception:
        uname = "YourBot"
    _bot_username_cache["value"] = uname
    _bot_username_cache["ts"] = now
    return uname

# ============ HELPERS ============
def get_category_emoji(category):
    return {"root": "🤖", "nonroot": "📱", "iphone": "🍎"}.get(category, "📦")

def get_category_name(category):
    return {"root": "ANDROID ROOT", "nonroot": "ANDROID NON ROOT", "iphone": "IPHONE"}.get(category, category.upper())

def get_priority_emoji(priority):
    return {"low": "🟢", "normal": "🟡", "high": "🟠", "urgent": "🔴"}.get(priority, "🟡")

def get_user_display_name(user_id):
    try:
        user_chat = bot.get_chat(user_id)
        if user_chat.first_name:
            return user_chat.first_name
    except Exception:
        pass
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and user["username"]:
            return user["username"]
    except Exception:
        pass
    return "User"

# BUG #9 FIX: notify_admins with per-admin isolation (no long waits)
def notify_admins(text):
    for admin_id in get_admin_ids():
        try:
            safe_send(admin_id, text)
        except Exception as e:
            logger.error(f"notify_admins fail {admin_id}: {e}")
            
# ============ BROADCASTS ============
# BUG #10 FIX: batch fetch instead of loading all users in RAM
def broadcast_maintenance_on():
    offset = 0
    batch_size = 500
    text = """🔧 <b>BOT UNDER MAINTENANCE</b>

━━━━━━━━━━━━━━━

⚠️ Bot abhi maintenance mein hai.

Jald hi wapas aa jayega!

━━━━━━━━━━━━━━━

⏳ Thodi der baad try karo."""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary"))
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE banned=0 LIMIT ? OFFSET ?", (batch_size, offset))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            if not rows:
                break
            for user in rows:
                try:
                    safe_send(user["id"], text, markup)
                except Exception as e:
                    logger.warning(f"maintenance broadcast fail {user['id']}: {e}")
                time.sleep(BROADCAST_DELAY)
            offset += batch_size
            if len(rows) < batch_size:
                break
        except Exception as e:
            logger.error(f"broadcast_maintenance_on error: {e}")
            break

def broadcast_maintenance_off():
    offset = 0
    batch_size = 500
    text = """🎉 <b>BOT WAPAS AA GAYA!</b> 🎉

━━━━━━━━━━━━━━━

✅ Maintenance khatam ho gaya!

Ab aap phir se shopping kar sakte ho.

━━━━━━━━━━━━━━━

🚀 Tap Shop Now to Start!"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔑 Shop Key", callback_data="shop_now", style="danger"))
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE banned=0 LIMIT ? OFFSET ?", (batch_size, offset))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            if not rows:
                break
            for user in rows:
                try:
                    safe_send(user["id"], text, markup)
                except Exception as e:
                    logger.warning(f"maintenance-off broadcast fail {user['id']}: {e}")
                time.sleep(BROADCAST_DELAY)
            offset += batch_size
            if len(rows) < batch_size:
                break
        except Exception as e:
            logger.error(f"broadcast_maintenance_off error: {e}")
            break

# ============ BACKGROUND WORKERS ============
def verify_fampay_payment(order_id):
    verify_url = f"{FAMPAY_VERIFY_URL}?order_id={order_id}&api_key={FAMPAY_API_KEY}"
    try:
        req = urllib.request.Request(verify_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read().decode())
        return str(res.get("status", "")).lower() == "success"
    except Exception as e:
        logger.warning(f"verify_fampay_payment error: {e}")
        return False

def process_successful_fampay(row):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("UPDATE pending_payments SET status='processing' WHERE id=? AND status='pending'", (row["id"],))
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (row["amount"], row["user_id"]))
        cursor.execute("INSERT INTO transactions (user_id, amount, type, details) VALUES (?,?,'add_money','fam_pay')", (row["user_id"], row["amount"]))
        cursor.execute("UPDATE pending_payments SET status='success' WHERE id=?", (row["id"],))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"process_successful_fampay error: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# BUG #19 FIX: timeout check even during maintenance
def check_payments():
    while True:
        conn = None
        cursor = None
        try:
            maintenance = is_bot_maintenance()
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_payments WHERE status='pending'")
            rows = cursor.fetchall()
            for row in rows:
                elapsed = time.time() - row["created_at"]
                if elapsed > FAMPAY_TIMEOUT_SECONDS:
                    if verify_fampay_payment(row["order_id"]):
                        if process_successful_fampay(row):
                            try:
                                safe_send(row["user_id"], f"✅ Payment Successful!\n\n💰 ₹{row['amount']}\n\nBalance added!")
                            except Exception as e:
                                logger.warning(f"FamPay success notify fail | user={row['user_id']} | {e}")
                            try:
                                notify_admins(f"💰 Fam Pay Payment!\nUser: {row['user_id']}\n₹{row['amount']}")
                            except Exception as e:
                                logger.error(f"FamPay admin notify fail | {e}")
                        continue
                    conn2 = get_db()
                    cur2 = conn2.cursor()
                    try:
                        cur2.execute("UPDATE pending_payments SET status='failed' WHERE id=? AND status='pending'", (row["id"],))
                        conn2.commit()
                        if cur2.rowcount == 1:
                            try:
                                safe_send(row["user_id"], f"❌ Payment Timeout\n\n💰 ₹{row['amount']}\n\n5 minute mein payment confirm nahi hui.\n\nAgar paisa kata hai toh support se contact karo.")
                            except Exception as e:
                                logger.warning(f"FamPay timeout notify fail | user={row['user_id']} | {e}")
                    finally:
                        cur2.close()
                        conn2.close()
                    continue
                # BUG #19 FIX: don't skip verification during maintenance
                if verify_fampay_payment(row["order_id"]):
                    if process_successful_fampay(row):
                        try:
                            safe_send(row["user_id"], f"✅ Payment Successful!\n\n💰 ₹{row['amount']}\n\nBalance added!")
                        except Exception as e:
                            logger.warning(f"FamPay success notify fail | user={row['user_id']} | {e}")
                        try:
                            notify_admins(f"💰 Fam Pay Payment!\nUser: {row['user_id']}\n₹{row['amount']}")
                        except Exception as e:
                            logger.error(f"FamPay admin notify fail | {e}")
        except Exception as e:
            logger.error(f"check_payments error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(FAMPAY_CHECK_INTERVAL)

# BUG #2, #29 FIX: retry cap + release DB before API call + status guard
def check_pending_api_orders():
    while True:
        conn = None
        cursor = None
        try:
            if is_bot_maintenance():
                time.sleep(PENDING_API_CHECK_INTERVAL)
                continue
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_api_orders WHERE status='pending'")
            orders = cursor.fetchall()
            cursor.close()
            conn.close()
            conn = None
            cursor = None
            for order in orders:
                conn = get_db()
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT api_pid, name, download_link, demo_video FROM products WHERE id=?", (order["product_id"],))
                    product = cursor.fetchone()
                    cursor.execute("SELECT duration FROM plans WHERE id=?", (order["plan_id"],))
                    plan = cursor.fetchone()
                    if not product or not product["api_pid"] or not plan:
                        cursor.close()
                        conn.close()
                        conn = None
                        cursor = None
                        continue
                    # BUG #2 FIX: check retry count BEFORE doing anything
                    retry_count = order["retry_count"] if "retry_count" in order.keys() else 0
                    if retry_count >= MAX_PENDING_API_RETRIES:
                        cursor.execute("UPDATE pending_api_orders SET status='failed' WHERE id=? AND status='pending'", (order["id"],))
                        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (order["amount"], order["user_id"]))
                        cursor.execute("INSERT INTO transactions (user_id, amount, type, details) VALUES (?,?,'refund','api_failed')", (order["user_id"], order["amount"]))
                        if order["coupon_id"]:
                            cursor.execute("UPDATE coupons SET used=0 WHERE id=? AND used=2", (order["coupon_id"],))
                        if order["spin_reward_id"]:
                            cursor.execute("UPDATE spin_rewards SET status='active' WHERE id=? AND status='reserved'", (order["spin_reward_id"],))
                        conn.commit()
                        try:
                            safe_send(order["user_id"], f"❌ <b>ORDER FAILED</b>\n\n{product['name']}\n\n💰 ₹{order['amount']} refunded to balance.\n\n✅ Aapka paisa safe hai.")
                        except Exception:
                            pass
                        cursor.close()
                        conn.close()
                        conn = None
                        cursor = None
                        continue
                    # BUG #29 FIX: lock row, then release DB before API call
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.execute("UPDATE pending_api_orders SET status='processing' WHERE id=? AND status='pending'", (order["id"],))
                    if cursor.rowcount != 1:
                        conn.rollback()
                        cursor.close()
                        conn.close()
                        conn = None
                        cursor = None
                        continue
                    cursor.execute("SELECT balance FROM users WHERE id=?", (order["user_id"],))
                    user = cursor.fetchone()
                    if not user or user["balance"] < order["amount"]:
                        cursor.execute("UPDATE pending_api_orders SET status='pending' WHERE id=?", (order["id"],))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        conn = None
                        cursor = None
                        continue
                    conn.commit()
                except Exception as e:
                    logger.error(f"pending api order pre-check error: {e}")
                    try:
                        cursor.close()
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                    cursor = None
                    continue
                cursor.close()
                conn.close()
                conn = None
                cursor = None
                # BUG #28 FIX: API call OUTSIDE transaction/connection
                duration_str = plan["duration"]
                api_response = fetch_key_from_api(product["api_pid"], duration_str)
                license_key, error_msg = parse_api_response(api_response)
                conn = get_db()
                cursor = conn.cursor()
                if not license_key:
                    # BUG #2 FIX: increment retry_count, revert to pending
                    cursor.execute("UPDATE pending_api_orders SET status='pending', retry_count=retry_count+1 WHERE id=?", (order["id"],))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    conn = None
                    cursor = None
                    continue
                try:
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.execute("UPDATE users SET balance = balance - ? WHERE id=? AND balance >= ?", (order["amount"], order["user_id"], order["amount"]))
                    if cursor.rowcount != 1:
                        conn.rollback()
                        cursor.execute("UPDATE pending_api_orders SET status='pending' WHERE id=?", (order["id"],))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        conn = None
                        cursor = None
                        continue
                    cursor.execute("UPDATE users SET total_orders=total_orders+1, total_spent=total_spent+? WHERE id=?", (order["amount"], order["user_id"]))
                    cursor.execute("INSERT INTO transactions (user_id, amount, type, details, license_key, product_name, duration) VALUES (?,?,'purchase','api_pending',?,?,?)", (order["user_id"], order["amount"], license_key, product["name"], duration_str))
                    cursor.execute("INSERT OR IGNORE INTO review_reminders (user_id, product_id, last_reminder_at, reminder_count) VALUES (?,?,?,0)", (order["user_id"], order["product_id"], utc_now_str()))
                    cursor.execute("UPDATE pending_api_orders SET status='delivered' WHERE id=?", (order["id"],))
                    if order["coupon_id"]:
                        cursor.execute("UPDATE coupons SET used=1 WHERE id=?", (order["coupon_id"],))
                    if order["spin_reward_id"]:
                        cursor.execute("UPDATE spin_rewards SET status='used' WHERE id=?", (order["spin_reward_id"],))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"pending api order commit error: {e}")
                    cursor.execute("UPDATE pending_api_orders SET status='pending' WHERE id=?", (order["id"],))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    conn = None
                    cursor = None
                    continue
                cursor.close()
                conn.close()
                conn = None
                cursor = None
                caption = f"""✅ <b>PENDING ORDER DELIVERED!</b>

<b>{esc(product['name'])}</b>
⏰ <b>{esc(duration_str)}</b>

🔑 <b>YOUR KEY</b>
<code>{esc(license_key)}</code>

⚠️ Key pe click karo—copy ho jayegi!"""
                markup = InlineKeyboardMarkup(row_width=1)
                if product["download_link"]:
                    markup.add(InlineKeyboardButton("📥 Download Files", url=product["download_link"], style="primary"))
                if product["demo_video"]:
                    markup.add(InlineKeyboardButton("📺 Demo Video", url=product["demo_video"], style="primary"))
                markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
                try:
                    safe_send(order["user_id"], caption, markup)
                except Exception as e:
                    logger.warning(f"Pending order notify fail | user={order['user_id']} | {e}")
                # BUG #34 FIX: commit done, notify admin; failure is logged, not lost
                try:
                    notify_admins(f"✅ Pending Order Delivered\n\n👤 User: {order['user_id']}\n📦 {product['name']}\n💰 ₹{order['amount']}")
                except Exception as e:
                    logger.error(f"Pending order admin notify fail | {e}")
        except Exception as e:
            logger.error(f"check_pending_api_orders error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(PENDING_API_CHECK_INTERVAL)

def check_spin_reward_expiry():
    while True:
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            now_str = utc_now_str()
            cursor.execute(
                "UPDATE spin_rewards SET status='expired' WHERE status IN ('active','reserved') AND expires_at < ?",
                (now_str,)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"check_spin_reward_expiry error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(SPIN_EXPIRY_CHECK_INTERVAL)

def check_spin_reward_notifications():
    while True:
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            now = utc_now()
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')
            warning_time = (now + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "SELECT id, user_id, amount, expires_at FROM spin_rewards WHERE status='active' AND warning_sent=0 AND expires_at > ? AND expires_at <= ?",
                (now_str, warning_time)
            )
            for reward in cursor.fetchall():
                cursor.execute("UPDATE spin_rewards SET warning_sent=1 WHERE id=? AND warning_sent=0", (reward["id"],))
                conn.commit()
                if cursor.rowcount != 1:
                    continue
                try:
                    expiry_time_utc = datetime.strptime(reward["expires_at"], '%Y-%m-%d %H:%M:%S')
                    expiry_time_ist = expiry_time_utc + timedelta(hours=5, minutes=30)
                    expiry_display = expiry_time_ist.strftime('%I:%M %p')
                    warning_text = f"""⚠️ <b>Reward Expire Hone Wala Hai!</b>

💰 ₹{reward['amount']} Cash Reward
⏰ Sirf 5 minute bacha hai!
⏰ {expiry_display} tak valid

❌ Abhi purchase nahi kiya toh expire ho jaega!
👇 Jaldi karo!"""
                    markup = InlineKeyboardMarkup(row_width=1)
                    markup.add(InlineKeyboardButton("🛒 Shop Now", callback_data="shop_now", style="danger"))
                    safe_send(reward["user_id"], warning_text, markup)
                except Exception as e:
                    logger.error(f"spin warning send error: {e}")
            cursor.execute(
                "SELECT id, user_id, amount FROM spin_rewards WHERE status='expired' AND expire_sent=0",
            )
            for reward in cursor.fetchall():
                cursor.execute("UPDATE spin_rewards SET expire_sent=1 WHERE id=? AND expire_sent=0", (reward["id"],))
                conn.commit()
                if cursor.rowcount != 1:
                    continue
                try:
                    expire_text = f"""❌ <b>Spin Reward Expire Ho Gaya!</b>

💰 ₹{reward['amount']} Cash Reward

🍀 Kal phir spin karo — next time jaldi use karna!"""
                    markup = InlineKeyboardMarkup(row_width=1)
                    markup.add(InlineKeyboardButton("🎮 Lucky Spin", callback_data="lucky_spin", style="success"))
                    safe_send(reward["user_id"], expire_text, markup)
                except Exception as e:
                    logger.error(f"spin expiry send error: {e}")
        except Exception as e:
            logger.error(f"check_spin_reward_notifications error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(60)

def check_review_reminders():
    while True:
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM review_reminders WHERE review_submitted=0 AND reminder_count < ?", (MAX_REVIEW_REMINDERS,))
            for reminder in cursor.fetchall():
                last_reminder = reminder["last_reminder_at"]
                # BUG #7 FIX: NULL-safe — treat NULL as now
                if not last_reminder:
                    last_reminder = utc_now_str()
                    cursor.execute("UPDATE review_reminders SET last_reminder_at=? WHERE id=?", (last_reminder, reminder["id"]))
                    conn.commit()
                try:
                    last_time = datetime.strptime(last_reminder, '%Y-%m-%d %H:%M:%S')
                    if (utc_now() - last_time).total_seconds() >= 600:
                        cursor.execute("SELECT name FROM products WHERE id=?", (reminder["product_id"],))
                        product = cursor.fetchone()
                        product_name = product["name"] if product else "Product"
                        cursor.execute("UPDATE review_reminders SET reminder_count=reminder_count+1, last_reminder_at=? WHERE id=?", (utc_now_str(), reminder["id"]))
                        conn.commit()
                        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐ Rate Now", callback_data=f"review_{reminder['product_id']}_5", style="primary"))
                        safe_send(reminder["user_id"], f"⏰ REVIEW REMINDER\n\nAapne {esc(product_name)} purchase kiya tha.\n\nKaisa raha experience?\n\nPlease review de do!", markup)
                except Exception as e:
                    logger.error(f"review reminder inner error: {e}")
            cursor.execute("UPDATE review_reminders SET review_submitted=1 WHERE reminder_count >= ? AND review_submitted=0", (MAX_REVIEW_REMINDERS,))
            conn.commit()
        except Exception as e:
            logger.error(f"check_review_reminders error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(REVIEW_REMINDER_INTERVAL)

def cleanup_stale_pending_orders():
    while True:
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cutoff = (utc_now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("SELECT id, coupon_id, spin_reward_id FROM pending_api_orders WHERE status='pending' AND created_at < ?", (cutoff,))
            stale = cursor.fetchall()
            for o in stale:
                if o["coupon_id"]:
                    cursor.execute("UPDATE coupons SET used=0 WHERE id=? AND used=2", (o["coupon_id"],))
                if o["spin_reward_id"]:
                    cursor.execute("UPDATE spin_rewards SET status='expired' WHERE id=? AND status='reserved'", (o["spin_reward_id"],))
                cursor.execute("UPDATE pending_api_orders SET status='expired' WHERE id=?", (o["id"],))
            conn.commit()
        except Exception as e:
            logger.error(f"cleanup_stale_pending_orders error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(3600)

def reset_stuck_processing():
    while True:
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE pending_payments SET status='pending' WHERE status='processing'")
            cursor.execute("UPDATE pending_api_orders SET status='pending' WHERE status='processing'")
            conn.commit()
        except Exception as e:
            logger.error(f"reset_stuck_processing error: {e}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
        time.sleep(PROCESSING_RESET_INTERVAL)

def reset_stuck_processing_once():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE pending_payments SET status='pending' WHERE status='processing'")
        cursor.execute("UPDATE pending_api_orders SET status='pending' WHERE status='processing'")
        conn.commit()
    except Exception as e:
        logger.error(f"reset_stuck_processing_once error: {e}")
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

# BUG #27 FIX: use sqlite backup API instead of shutil.copy
def emergency_backup(reason="Unknown"):
    backup_path = None
    success = False
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = utc_now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f"emergency_backup_{timestamp}.db")
        src = get_db()
        dst = sqlite3.connect(backup_path)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        for admin_id in get_admin_ids():
            try:
                with open(backup_path, 'rb') as f:
                    bot.send_document(admin_id, f, caption=f"🚨 <b>EMERGENCY BACKUP</b>\n\n⚠️ Reason: {esc(reason)}\n📅 Time: {utc_now_str()}", parse_mode="HTML")
                success = True
            except Exception as e:
                logger.error(f"backup send fail {admin_id}: {e}")
        return success
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False
    finally:
        if success and backup_path and os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception as e:
                logger.error(f"backup cleanup fail: {e}")

# ============ BOT INIT ============
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# ============ UI TEXT ============
def get_welcome_text(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, balance FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    username = user["username"] if user and user["username"] else "User"
    balance = user["balance"] if user else 0
    return f"""🏪 <b>𝐅𝐅 𝐁𝐂 𝐏𝐀𝐍𝐄𝐋 𝐒𝐓𝐎𝐑𝐄</b> 🏪
━━━━━━━━━━━━━━━━━━━━━

👋 Welcome, <b>{esc(username)}</b>! 🤩

⭐ <b>STORE HIGHLIGHTS</b> ⭐

🔑 Premium Game Keys
⚡ Instant Delivery 24/7
🔒 100% Secure Payment
💸 Best Prices Guaranteed
📞 Professional Support

━━━━━━━━━━━━━━━━━━━━━
👤 ID: <code>{user_id}</code>
💰 Balance: ₹{balance}
━━━━━━━━━━━━━━━━━━━━━

🚀 <b>Tap Shop Now to Start!</b>"""

def get_main_menu(user_id):
    if is_banned(user_id):
        return InlineKeyboardMarkup().add(InlineKeyboardButton("📞 Support", callback_data="support", style="danger"))
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🔑 Shop Key", callback_data="shop_now", style="danger"), InlineKeyboardButton("👤 My Profile", callback_data="profile", style="primary"))
    markup.add(InlineKeyboardButton("💰 Add Balance", callback_data="add_balance", style="success"), InlineKeyboardButton("📜 All History", callback_data="history", style="primary"))
    markup.add(InlineKeyboardButton("🎬 Tutorial", callback_data="tutorial", style="danger"), InlineKeyboardButton("🤝 Become Reseller", callback_data="reseller_info" if not is_reseller(user_id) else "reseller_panel", style="success"))
    markup.add(InlineKeyboardButton("📸 Selling Proof", callback_data="selling_proof", style="danger"), InlineKeyboardButton("📞 Support", callback_data="support", style="success"))
    markup.add(InlineKeyboardButton("❓ FAQ", callback_data="faq_menu", style="primary"), InlineKeyboardButton("🎁 Referral", callback_data="referral", style="success"))
    if not is_reseller(user_id):
        markup.add(InlineKeyboardButton("🎮 Lucky Spin", callback_data="lucky_spin", style="success"))
    if user_id in get_admin_ids():
        markup.add(InlineKeyboardButton("🔧 Admin", callback_data="admin_panel", style="primary"))
    return markup

# ============ ADMIN PANEL ============
def build_admin_markup(buttons, back_callback="admin_panel", back_text="◀️ Back to Admin Panel"):
    markup = InlineKeyboardMarkup(row_width=2)
    if len(buttons) % 2 == 1:
        paired = buttons[:-1]
        last = buttons[-1]
        for i in range(0, len(paired), 2):
            markup.add(
                InlineKeyboardButton(paired[i][0], callback_data=paired[i][1], style=paired[i][2]),
                InlineKeyboardButton(paired[i+1][0], callback_data=paired[i+1][1], style=paired[i+1][2])
            )
        markup.add(InlineKeyboardButton(last[0], callback_data=last[1], style=last[2]))
    else:
        for i in range(0, len(buttons), 2):
            markup.add(
                InlineKeyboardButton(buttons[i][0], callback_data=buttons[i][1], style=buttons[i][2]),
                InlineKeyboardButton(buttons[i+1][0], callback_data=buttons[i+1][1], style=buttons[i+1][2])
            )
    markup.add(InlineKeyboardButton(back_text, callback_data=back_callback, style="danger"))
    return markup

def get_admin_panel(user_id):
    if user_id == ADMIN_USER_ID:
        buttons = [
            ("👑 Dashboard", "admin_dashboard", "primary"),
            ("📊 Analytics", "admin_analytics", "primary"),
            ("📦 Products", "admin_products", "primary"),
            ("💰 Payments", "admin_payments", "success"),
            ("👥 Users", "admin_users", "primary"),
            ("💬 Support", "admin_support", "success"),
            ("⚙️ Settings", "admin_settings", "primary"),
            ("📢 Broadcast", "admin_broadcast", "primary"),
        ]
    else:
        buttons = [
            ("👑 Dashboard", "admin_dashboard", "primary"),
            ("📊 Analytics", "admin_analytics", "primary"),
            ("📦 Products", "admin_products", "primary"),
            ("👥 Users", "admin_users", "primary"),
            ("💬 Support", "admin_support", "success"),
            ("📢 Broadcast", "admin_broadcast", "primary"),
        ]
    return build_admin_markup(buttons, "back_main", "◀️ Back to Main")

def get_admin_products_menu(user_id):
    if user_id == ADMIN_USER_ID:
        buttons = [
            ("➕ Add Product", "admin_add_product", "success"),
            ("📋 Manage", "admin_manage_products", "primary"),
            ("🔧 Maintenance", "admin_maintenance_products", "danger"),
            ("💰 Reseller", "admin_reseller_prices", "success"),
            ("🎬 Tutorial Video", "admin_tutorial_video", "danger"),
        ]
    else:
        buttons = [
            ("📋 Manage", "admin_manage_products", "primary"),
            ("🔧 Maintenance", "admin_maintenance_products", "danger"),
            ("🎬 Tutorial Video", "admin_tutorial_video", "danger"),
        ]
    return build_admin_markup(buttons, "admin_panel")

def get_admin_payments_menu(user_id):
    if user_id == ADMIN_USER_ID:
        buttons = [
            ("💰 Deposits", "admin_deposit_requests", "success"),
            ("📱 QR Code", "admin_change_qr", "primary"),
            ("🔗 Manual UPI", "admin_change_manual_upi", "primary"),
            ("💳 Min Deposit", "admin_min_deposit", "primary"),
            ("💸 Res Fee", "admin_reseller_fee", "success"),
            ("💳 Reseller Min Balance", "admin_min_balance", "primary"),
        ]
    else:
        buttons = [
            ("💸 Res Fee", "admin_reseller_fee", "success"),
            ("💳 Reseller Min Balance", "admin_min_balance", "primary"),
        ]
    return build_admin_markup(buttons, "admin_panel")

def get_admin_users_menu(user_id):
    if user_id == ADMIN_USER_ID:
        buttons = [
            ("💰 Add Balance", "admin_add_balance", "success"),
            ("🚫 Ban User", "admin_ban_user", "danger"),
            ("✅ Unban User", "admin_unban_user", "success"),
            ("👑 Admins", "manage_admins", "primary"),
            ("📸 Reviews", "admin_reviews", "primary"),
        ]
    else:
        buttons = [
            ("🚫 Ban User", "admin_ban_user", "danger"),
            ("✅ Unban User", "admin_unban_user", "success"),
            ("📸 Reviews", "admin_reviews", "primary"),
        ]
    return build_admin_markup(buttons, "admin_panel")

def get_admin_support_menu(user_id):
    if user_id == ADMIN_USER_ID:
        buttons = [
            ("🎫 Tickets", "admin_tickets", "success"),
            ("💬 Contacts", "admin_support_contacts", "primary"),
            ("📸 Selling Proof Link", "admin_selling_proof", "danger"),
            ("❓ FAQ Manager", "admin_faq_menu", "primary"),
        ]
    else:
        buttons = [
            ("🎫 Tickets", "admin_tickets", "success"),
            ("❓ FAQ Manager", "admin_faq_menu", "primary"),
        ]
    return build_admin_markup(buttons, "admin_panel")

def get_admin_settings_menu(user_id):
    if user_id == ADMIN_USER_ID:
        buttons = [
            ("🔧 Maintenance", "admin_bot_maintenance", "danger"),
            ("💾 Backup", "admin_backup", "success"),
            ("📂 Restore", "admin_restore", "danger"),
            ("📁 Export CSV", "admin_csv_menu", "primary"),
            ("📝 Admin Logs", "admin_logs_view", "primary"),
        ]
    else:
        buttons = []
    return build_admin_markup(buttons, "admin_panel")

def get_admin_analytics_menu():
    buttons = [
        ("📈 Today", "admin_today_stats", "primary"),
        ("📅 Weekly", "admin_weekly_stats", "primary"),
        ("🏆 Top Products", "admin_top_products", "primary"),
        ("👥 Users", "admin_user_growth", "primary"),
        ("💰 Revenue Report", "admin_revenue_report", "success"),
    ]
    return build_admin_markup(buttons, "admin_panel")

def get_admin_broadcast_menu():
    buttons = [
        ("📢 All Users", "admin_broadcast_all", "primary"),
        ("✅ Verified", "admin_broadcast_verified", "primary"),
        ("👥 Inactive", "admin_broadcast_inactive", "primary"),
        ("🤝 Resellers", "admin_broadcast_resellers", "primary"),
        ("💰 Has Balance", "admin_broadcast_balance", "primary"),
        ("📸 Media Broadcast", "admin_broadcast_media", "success"),
    ]
    return build_admin_markup(buttons, "admin_panel")

def get_admin_csv_menu():
    buttons = [
        ("👥 Users", "csv_export_users", "primary"),
        ("💰 Transactions", "csv_export_transactions", "primary"),
        ("📱 Deposits", "csv_export_deposits", "primary"),
        ("📦 Orders", "csv_export_orders", "primary"),
    ]
    return build_admin_markup(buttons, "admin_settings")

def get_admin_faq_menu():
    buttons = [
        ("📋 View All", "faq_view_all", "primary"),
        ("➕ Add FAQ", "faq_add", "success"),
        ("➖ Remove FAQ", "faq_remove_menu", "danger"),
    ]
    return build_admin_markup(buttons, "admin_support")

def get_admin_panel_header():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM users")
    total_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE type='purchase'")
    total_orders = cursor.fetchone()["c"]
    cursor.execute("SELECT COALESCE(SUM(balance),0) as t FROM users")
    total_balance = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='purchase'")
    lifetime_earnings = cursor.fetchone()["t"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE DATE(joined_at)=?", (date.today().isoformat(),))
    today_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE type='purchase' AND DATE(created_at)=?", (date.today().isoformat(),))
    today_orders = cursor.fetchone()["c"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='purchase' AND DATE(created_at)=?", (date.today().isoformat(),))
    today_revenue = cursor.fetchone()["t"]
    cursor.execute("SELECT COUNT(*) as c FROM manual_deposits WHERE status='pending'")
    pending_deposits = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM support_tickets WHERE status='open'")
    open_tickets = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM pending_api_orders WHERE status='pending'")
    pending_api = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM products WHERE status='maintenance'")
    maintenance_products = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE banned=1")
    banned_users = cursor.fetchone()["c"]
    cursor.execute("""SELECT p.name, COUNT(t.id) as sold FROM products p 
                      LEFT JOIN transactions t ON t.product_name = p.name AND t.type='purchase' 
                      GROUP BY p.id ORDER BY sold DESC LIMIT 1""")
    top_product = cursor.fetchone()
    cursor.close()
    conn.close()

    text = "🔧 <b>ADMIN PANEL</b>\n━━━━━━━━━━━━━━━\n\n"
    text += "Welcome back, Admin 👑\n\n"
    text += "📊 <b>OVERVIEW</b>\n"
    text += f"👥 Users: {total_users} | 📦 Orders: {total_orders}\n"
    text += f"💰 Balance: ₹{total_balance} | 💵 Lifetime: ₹{lifetime_earnings}\n"
    text += f"🆕 Today: {today_users} users | {today_orders} orders | ₹{today_revenue}\n"

    if pending_deposits or open_tickets or pending_api:
        text += "\n━━━━━━━━━━━━━━━\n\n⚠️ <b>ACTION REQUIRED</b>\n"
        if pending_deposits:
            text += f"💰 {pending_deposits} Pending Deposits\n"
        if open_tickets:
            text += f"🎫 {open_tickets} Open Tickets\n"
        if pending_api:
            text += f"⏳ {pending_api} Pending API Orders\n"

    if maintenance_products or banned_users:
        text += "\n━━━━━━━━━━━━━━━\n\n🚨 <b>ALERTS</b>\n"
        if maintenance_products:
            text += f"🔧 {maintenance_products} Products in Maintenance\n"
        if banned_users:
            text += f"🚫 {banned_users} Banned Users\n"

    if top_product and top_product["sold"] > 0:
        text += "\n━━━━━━━━━━━━━━━\n\n🏆 <b>TOP SELLING</b>\n"
        text += f"🥇 {esc(top_product['name'])} — {top_product['sold']} sold\n"

    text += "\n━━━━━━━━━━━━━━━"
    return text
    
    # ============ SPIN HELPERS ============
# BUG #5 FIX: single DB connection for all spin queries
def get_spin_time_left(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT last_spin_at FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row or not row["last_spin_at"]:
        return 0
    try:
        last_spin = datetime.strptime(row["last_spin_at"], '%Y-%m-%d %H:%M:%S')
        elapsed = (utc_now() - last_spin).total_seconds()
        remaining = SPIN_COOLDOWN_SECONDS - elapsed
        return max(0, int(remaining))
    except Exception:
        return 0

def format_time_remaining(seconds):
    if seconds <= 0:
        return "✅ Spin available hai!"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"⏰ {hours}h {minutes}m {secs}s baad spin milega"
    elif minutes > 0:
        return f"⏰ {minutes}m {secs}s baad spin milega"
    else:
        return f"⏰ {secs}s baad spin milega"

# BUG #5 FIX: single connection, combined query
def get_active_spin_reward(user_id):
    conn = get_db()
    cursor = conn.cursor()
    now_str = utc_now_str()
    cursor.execute("SELECT id, amount, expires_at FROM spin_rewards WHERE user_id=? AND status='active' AND expires_at > ? ORDER BY id DESC LIMIT 1", (user_id, now_str))
    reward = cursor.fetchone()
    cursor.close()
    conn.close()
    return reward

def get_spin_expiry_time(user_id):
    conn = get_db()
    cursor = conn.cursor()
    now_str = utc_now_str()
    cursor.execute("SELECT expires_at FROM spin_rewards WHERE user_id=? AND status='active' AND expires_at > ? ORDER BY id DESC LIMIT 1", (user_id, now_str))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        try:
            dt_utc = datetime.strptime(row["expires_at"], '%Y-%m-%d %H:%M:%S')
            dt_ist = dt_utc + timedelta(hours=5, minutes=30)
            return dt_ist.strftime('%I:%M %p')
        except Exception:
            pass
    return "N/A"

# ============ FAQ ============
def show_faq_menu(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, question FROM faq ORDER BY display_order ASC, id ASC")
    faqs = cursor.fetchall()
    cursor.close()
    conn.close()
    if not faqs:
        safe_navigate(call, "❓ FAQ\n\nAbhi koi FAQ nahi hai.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger")))
        return
    text = "❓ <b>FAQ — FREQUENTLY ASKED QUESTIONS</b>\n━━━━━━━━━━━━━━━\n\nNeeche question pe click karo:\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for f in faqs:
        q = f['question'][:58] if len(f['question']) > 58 else f['question']
        markup.add(InlineKeyboardButton(f"❓ {q}", callback_data=f"faq_show_{f['id']}", style="primary"))
    markup.add(InlineKeyboardButton("📞 Still need help?", callback_data="support", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def show_faq_answer(call, faq_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT question, answer FROM faq WHERE id=?", (faq_id,))
    f = cursor.fetchone()
    cursor.close()
    conn.close()
    if not f:
        bot.answer_callback_query(call.id, "❌ Not found", show_alert=True)
        return
    text = f"❓ <b>{esc(f['question'])}</b>\n━━━━━━━━━━━━━━━\n\n{esc(f['answer'])}"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("◀️ Back to FAQ", callback_data="faq_menu", style="primary"))
    markup.add(InlineKeyboardButton("📞 Support", callback_data="support", style="success"))
    safe_navigate(call, text, markup)

# ============ CSV EXPORT ============
def csv_export(call, export_type):
    try:
        conn = get_db()
        cursor = conn.cursor()
        output = io.StringIO()
        writer = csv.writer(output)
        if export_type == "users":
            cursor.execute("SELECT id, username, balance, banned, verified, phone_number, total_orders, total_spent, is_reseller, joined_at FROM users")
            writer.writerow(["ID", "Username", "Balance", "Banned", "Verified", "Phone", "Orders", "Spent", "Reseller", "Joined"])
            for r in cursor.fetchall():
                writer.writerow([r["id"], r["username"], r["balance"], r["banned"], r["verified"], r["phone_number"], r["total_orders"], r["total_spent"], r["is_reseller"], r["joined_at"]])
        elif export_type == "transactions":
            cursor.execute("SELECT id, user_id, amount, type, details, license_key, product_name, duration, created_at FROM transactions ORDER BY id DESC")
            writer.writerow(["ID", "User ID", "Amount", "Type", "Details", "Key", "Product", "Duration", "Date"])
            for r in cursor.fetchall():
                writer.writerow([r["id"], r["user_id"], r["amount"], r["type"], r["details"], r["license_key"], r["product_name"], r["duration"], r["created_at"]])
        elif export_type == "deposits":
            cursor.execute("SELECT id, user_id, amount, utr, status, admin_reason, created_at FROM manual_deposits ORDER BY id DESC")
            writer.writerow(["ID", "User ID", "Amount", "UTR", "Status", "Reason", "Date"])
            for r in cursor.fetchall():
                writer.writerow([r["id"], r["user_id"], r["amount"], r["utr"], r["status"], r["admin_reason"], r["created_at"]])
        elif export_type == "orders":
            cursor.execute("SELECT id, user_id, product_id, plan_id, amount, status, created_at FROM pending_api_orders ORDER BY id DESC")
            writer.writerow(["ID", "User ID", "Product ID", "Plan ID", "Amount", "Status", "Date"])
            for r in cursor.fetchall():
                writer.writerow([r["id"], r["user_id"], r["product_id"], r["plan_id"], r["amount"], r["status"], r["created_at"]])
        cursor.close()
        conn.close()
        data = output.getvalue().encode('utf-8')
        filename = f"{export_type}_{utc_now().strftime('%Y%m%d_%H%M%S')}.csv"
        buf = io.BytesIO(data)
        buf.name = filename
        bot.send_document(call.message.chat.id, buf, caption=f"📁 <b>{export_type.upper()} EXPORT</b>\n\n✅ {filename}", parse_mode="HTML")
        log_admin_action(call.from_user.id, "CSV Export", export_type)
        bot.answer_callback_query(call.id, "✅ Exported!", show_alert=True)
    except Exception as e:
        logger.error(f"csv_export error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

# ============ ADMIN LOGS VIEW ============
def show_admin_logs(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 20")
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    if not logs:
        safe_navigate(call, "📝 <b>ADMIN LOGS</b>\n━━━━━━━━━━━━━━━\n\nAbhi tak koi activity nahi.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_settings", style="danger")))
        return
    text = "📝 <b>ADMIN LOGS (last 20)</b>\n━━━━━━━━━━━━━━━\n\n"
    for l in logs:
        entry = f"🕐 {l['created_at'][:16]}\n👤 Admin: <code>{l['admin_id']}</code>\n📌 {esc(l['action'])}\n"
        if l["details"]:
            entry += f"💬 {esc(l['details'])}\n"
        entry += "\n━━━━━━━━━━━━━━━\n"
        if len(text) + len(entry) > 3800:
            break
        text += entry
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_settings", style="danger"))
    safe_navigate(call, text, markup)

# ============ START ============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    uid = message.from_user.id
    username = message.from_user.username
    referred_by = None
    parts = message.text.split()
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            ref_id = int(parts[1].replace("ref_", ""))
            if ref_id != uid:
                referred_by = ref_id
        except Exception:
            pass
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (id, username, balance, banned, verified, referred_by) VALUES (?,?,0,0,0,?)", (uid, username, referred_by))
    if username:
        cursor.execute("UPDATE users SET username=? WHERE id=?", (username, uid))
    if referred_by:
        cursor.execute("UPDATE users SET referred_by=? WHERE id=? AND referred_by IS NULL", (referred_by, uid))
    conn.commit()
    cursor.close()
    conn.close()
    if referred_by:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id=?", (referred_by,))
        if cursor.fetchone():
            safe_send(referred_by, f"🎉 New referral joined!\n\n👤 {uid}\n\nUnki pehli purchase pe tumhe reward milega!")
        cursor.close()
        conn.close()
    update_last_active(uid)
    if is_bot_maintenance() and uid not in get_admin_ids():
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary"))
        safe_send(message.chat.id, "🔧 <b>BOT UNDER MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\n⚠️ Bot abhi maintenance mein hai.\n\nJald hi wapas aa jayega!\n\n━━━━━━━━━━━━━━━\n\n⏳ Thodi der baad try karo.", markup)
        return
    if is_verified(uid):
        safe_send(message.chat.id, get_welcome_text(uid), get_main_menu(uid))
    else:
        send_verification_request(message.chat.id)

def send_verification_request(chat_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("📱 Share My Number", request_contact=True))
    safe_send(chat_id, "👋 Welcome!\n\nPlease share your phone number.", markup)

# BUG #35 FIX: contact user_id None safe + only own contact
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    user_id = message.from_user.id
    if message.contact and message.contact.user_id == user_id:
        set_verified(user_id, message.contact.phone_number)
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(KeyboardButton("/start"))
        safe_send(message.chat.id, "✅ Verified!", markup)
        if is_bot_maintenance() and user_id not in get_admin_ids():
            m = InlineKeyboardMarkup(row_width=1)
            m.add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary"))
            safe_send(message.chat.id, "🔧 <b>BOT UNDER MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\n⚠️ Bot abhi maintenance mein hai.\n\nJald hi wapas aa jayega!\n\n━━━━━━━━━━━━━━━", m)
            return
        safe_send(message.chat.id, get_welcome_text(user_id), get_main_menu(user_id))
    else:
        # BUG #35 FIX: not own contact — send verification again
        send_verification_request(message.chat.id)

# ============ MAIN MENU FUNCTIONS ============
def show_profile(call, user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if not user:
        return
    try:
        first_name = bot.get_chat(user_id).first_name or "N/A"
    except Exception:
        first_name = "N/A"
    account_type = "🤝 Reseller" if user["is_reseller"] else "👤 Regular"
    status = "✅ Active" if not user["banned"] else "🚫 Banned"
    text = f"""👤 ━━ YOUR PROFILE ━━ 👤

🆔 User ID: <code>{user_id}</code>
📛 Name: {esc(first_name)}
📱 Phone: {esc(user['phone_number'] or 'N/A')}
👑 Account: {account_type} | {status}

💰 ━ Balance ━
   💳 Current: ₹{user['balance'] or 0}

📊 ━ Statistics ━
   📦 Orders: {user['total_orders'] or 0}
   💸 Spent: ₹{user['total_spent'] or 0}
   👥 Referrals: {user['total_referrals'] or 0}
   🎁 Referral Earnings: ₹{user['referral_earnings'] or 0}

📅 Joined: {user['joined_at'][:10] if user['joined_at'] else 'N/A'}"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("💰 Add Balance", callback_data="add_balance", style="success"), InlineKeyboardButton("📜 History", callback_data="history", style="primary"))
    if not user["is_reseller"]:
        markup.add(InlineKeyboardButton("🤝 Upgrade to Reseller", callback_data="reseller_info", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def show_products(call):
    user_id = call.from_user.id
    display_name = get_user_display_name(user_id)
    text = f"""🛒 <b>SELECT YOUR DEVICE TYPE</b> ✨
━━━━━━━━━━━━━━━━━━━━━

👋 Yoo {esc(display_name)}!
Pehle apna device type chunein, uske baad products dikhenge.

━━━━━━━━━━━━━━━━━━━━━

⭐ <b>DEVICE TYPE</b> ⭐

🤖 <b>ROOT PANEL</b>
└─ Android Root Users ke liye

📱 <b>NON-ROOT PANEL</b>
└─ Android Non-Root Users ke liye

🍎 <b>IPHONE PANEL</b>
└─ iPhone Users ke liye

━━━━━━━━━━━━━━━━━━━━━

⚡ Instant Delivery | 🔒 100% Secure | 💰 Best Prices

━━━━━━━━━━━━━━━━━━━━━

👇 Apna panel select karo!"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🤖 Android Root Panel", callback_data="category_root", style="primary"))
    markup.add(InlineKeyboardButton("📱 Android Non Root Panel", callback_data="category_nonroot", style="primary"))
    markup.add(InlineKeyboardButton("🍎 iPhone", callback_data="category_iphone", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def show_products_by_category(call, category):
    user_id = call.from_user.id
    display_name = get_user_display_name(user_id)
    cat_name = get_category_name(category)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, status FROM products WHERE category=?", (category,))
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    if not products:
        text = f"""━━━ <b>{cat_name} PANEL</b> ━━━

━━━━━━━━━━━━━━━━━━━━━

📦 Available Products:

━━━━━━━━━━━━━━━━━━━━━

😔 Koi product nahi mila!

⚠️ Is category me abhi koi product available nahi hai.
Jald hi add kiya jayega!

━━━━━━━━━━━━━━━━━━━━━

🔥 Naye products jald aa rahe hain!
🔔 Notify Me dabao — product add hote hi notification pao!

━━━━━━━━━━━━━━━━━━━━━"""
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🔔 Notify Me", callback_data=f"notify_category_{category}", style="primary"))
        markup.add(InlineKeyboardButton("◀️ Back", callback_data="shop_now", style="danger"))
        safe_navigate(call, text, markup)
        return
    text = f"""{cat_name} — SELECT A PRODUCT
━━━━━━━━━━━━━━━━━━━━━

👋 Yoo {esc(display_name)}!
Choose any product below to view its price and available duration plans.

━━━━━━━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    for p in products:
        if p["status"] == "maintenance":
            markup.add(InlineKeyboardButton(f"🔧 {p['name']} (Maintenance)", callback_data=f"product_{p['id']}", style="danger"))
        else:
            markup.add(InlineKeyboardButton(f"{p['name']}", callback_data=f"product_{p['id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="shop_now", style="danger"))
    safe_navigate(call, text, markup)

def notify_category(call, category):
    user_id = call.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO category_notifications (user_id, category, notified) VALUES (?,?,0)", (user_id, category))
    conn.commit()
    cursor.close()
    conn.close()
    bot.answer_callback_query(call.id, "🔔 Notify kar diya! Product add hote hi notification milega!", show_alert=True)

def show_product_plans(call, product_id, reseller_mode=False):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, name, category FROM products WHERE id=?", (product_id,))
    ps = cursor.fetchone()
    if ps and ps["status"] == 'maintenance':
        cursor.close()
        conn.close()
        safe_navigate(call, f"🔧 UNDER MAINTENANCE\n\n{esc(ps['name'])}\n\n⚠️ Yeh product abhi maintenance pe hai.", InlineKeyboardMarkup().add(InlineKeyboardButton("🔔 Notify Me", callback_data=f"notify_{product_id}", style="primary"), InlineKeyboardButton("◀️ Back", callback_data=f"category_{ps['category']}", style="danger")))
        return
    cursor.execute("SELECT id, duration, price, reseller_price FROM plans WHERE product_id=?", (product_id,))
    plans = cursor.fetchall()
    cursor.execute("SELECT name, features, demo_video, download_link, category FROM products WHERE id=?", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    if not product:
        bot.answer_callback_query(call.id, "❌ Product not found", show_alert=True)
        return
    cat_info = {"root": "Available | Root Only", "nonroot": "Available | Non Root Only", "iphone": "Available | iPhone Only"}
    availability = cat_info.get(product["category"], "Available | All Devices")
    text = f"<b>{esc(product['name'])}</b>\n{availability}\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    if product["features"]:
        text += f"<blockquote>{esc(product['features'])}</blockquote>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n<b>Select Duration:</b>"
    markup = InlineKeyboardMarkup(row_width=1)
    for pl in plans:
        dtext = pl["duration"]
        # BUG #21 FIX: reseller price NULL — show normal + tag it's not reseller
        if reseller_mode and pl["reseller_price"] is not None:
            markup.add(InlineKeyboardButton(f"⭐ {dtext} | ₹{pl['reseller_price']}", callback_data=f"buy_{product_id}_{pl['id']}", style="success"))
        elif reseller_mode and pl["reseller_price"] is None:
            markup.add(InlineKeyboardButton(f"⏰ {dtext} | ₹{pl['price']} (no reseller price)", callback_data=f"buy_{product_id}_{pl['id']}", style="success"))
        else:
            markup.add(InlineKeyboardButton(f"⏰ {dtext} | ₹{pl['price']}", callback_data=f"buy_{product_id}_{pl['id']}", style="success"))
    if product["demo_video"]:
        markup.add(InlineKeyboardButton("📺 Demo Video", callback_data=f"demo_{product_id}", style="primary"))
    if product["download_link"]:
        markup.add(InlineKeyboardButton("📥 Download Files", url=product["download_link"], style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data=f"category_{product['category']}", style="danger"))
    safe_navigate(call, text, markup)

def show_demo_video(call, product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, demo_video FROM products WHERE id=?", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    if not product or not product["demo_video"]:
        bot.answer_callback_query(call.id, "❌ No demo video", show_alert=True)
        return
    demo = product["demo_video"].strip()
    try:
        if "t.me/c/" in demo:
            parts = demo.replace("https://t.me/c/", "").split("/")
            chat_id = f"-100{parts[0]}"
            message_id = int(parts[1])
        else:
            parts = demo.replace("https://t.me/", "").split("/")
            chat_id = f"@{parts[0]}"
            message_id = int(parts[1])
        bot.forward_message(call.message.chat.id, chat_id, message_id)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("🛒 BUY NOW", callback_data=f"product_{product_id}", style="success"), InlineKeyboardButton("◀️ BACK", callback_data=f"product_{product_id}", style="danger"))
        bot.send_message(call.message.chat.id, f"<b>{esc(product['name'])}</b>\n\n🔥 Dekho aur purchase karo!", parse_mode="HTML", reply_markup=markup)
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"demo video error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

# BUG #7 FIX: DB connection closed on all paths
def show_order_confirmation(call, product_id, plan_id):
    user_id = call.from_user.id
    if is_bot_maintenance() and user_id not in get_admin_ids():
        bot.answer_callback_query(call.id, "🔧 Bot maintenance mein hai!", show_alert=True)
        safe_navigate(call, "🔧 <b>BOT UNDER MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\n⚠️ Bot abhi maintenance mein hai.\n\nKoi bhi purchase abhi nahi ho sakti.\n\n━━━━━━━━━━━━━━━", InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary")))
        return
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
        cursor.execute("SELECT duration, price, reseller_price FROM plans WHERE id=?", (plan_id,))
        plan = cursor.fetchone()
        cursor.execute("SELECT name FROM products WHERE id=?", (product_id,))
        product = cursor.fetchone()
        if not plan or not product or not user:
            bot.answer_callback_query(call.id, "❌ Invalid", show_alert=True)
            return
        price = plan["reseller_price"] if is_reseller(user_id) and plan["reseller_price"] is not None else plan["price"]
        cursor.execute("SELECT id, discount_percent FROM coupons WHERE user_id=? AND used=0 ORDER BY id DESC LIMIT 1", (user_id,))
        coupon = cursor.fetchone()
        # BUG #5 FIX: single query already handled by get_active_spin_reward
        spin_reward = get_active_spin_reward(user_id)
    finally:
        cursor.close()
        conn.close()
    dtext = plan["duration"]
    total_discount = 0
    discount_text = ""
    if coupon:
        discount = math.ceil(price * coupon["discount_percent"] / 100)
        total_discount += discount
        discount_text += f"\n🎁 Coupon: {coupon['discount_percent']}% OFF (-₹{discount})"
    if spin_reward:
        spin_discount = spin_reward["amount"]
        total_discount += spin_discount
        expiry = get_spin_expiry_time(user_id)
        discount_text += f"\n🎰 Cash Spin Reward: -₹{spin_discount} (⏰ {expiry} tak valid)"
    final_price = max(0, price - total_discount)
    text = f"🛒 <b>ORDER CONFIRMATION</b>\n\n{esc(product['name'])}\n⏰ {esc(dtext)}\n\n💰 Original: ₹{price}{discount_text}\n\n✅ Final: ₹{final_price}\n\n💵 Balance: ₹{user['balance'] if user else 0}"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{product_id}_{plan_id}", style="success"), InlineKeyboardButton("❌ Cancel", callback_data=f"product_{product_id}", style="danger"))
    safe_navigate(call, text, markup)

# BUG #1, #28 FIX: balance locked first, then API call, on fail refund
# BUG #43 FIX: re-validate product/plan at purchase time
def process_purchase(call, product_id, plan_id):
    user_id = call.from_user.id
    if is_bot_maintenance() and user_id not in get_admin_ids():
        bot.answer_callback_query(call.id, "🔧 Bot maintenance mein hai! Purchase abhi band hai.", show_alert=True)
        safe_navigate(call, "🔧 <b>BOT UNDER MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\n⚠️ Bot abhi maintenance mein hai.\n\nKoi bhi purchase abhi nahi ho sakti.\n\n━━━━━━━━━━━━━━━", InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary")))
        return

    # ===== PHASE 1: fetch + validate =====
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
        cursor.execute("SELECT duration, price, reseller_price FROM plans WHERE id=?", (plan_id,))
        plan = cursor.fetchone()
        cursor.execute("SELECT name, api_pid, download_link, demo_video FROM products WHERE id=?", (product_id,))
        product = cursor.fetchone()
        if not plan or not product or not user:
            bot.answer_callback_query(call.id, "❌ Invalid or product no longer available", show_alert=True)
            return
        price = plan["reseller_price"] if is_reseller(user_id) and plan["reseller_price"] is not None else plan["price"]
        cursor.execute("SELECT id, discount_percent FROM coupons WHERE user_id=? AND used=0 ORDER BY id DESC LIMIT 1", (user_id,))
        coupon = cursor.fetchone()
        spin_reward = None if is_reseller(user_id) else get_active_spin_reward(user_id)
        total_discount = 0
        spin_reward_id = None
        coupon_id = None
        if coupon:
            discount = math.ceil(price * coupon["discount_percent"] / 100)
            total_discount += discount
            coupon_id = coupon["id"]
        if spin_reward:
            total_discount += spin_reward["amount"]
            spin_reward_id = spin_reward["id"]
        final_price = max(0, price - total_discount)
        if user["balance"] < final_price:
            bot.answer_callback_query(call.id, f"❌ Need ₹{final_price}", show_alert=True)
            return
        if not product["api_pid"]:
            bot.answer_callback_query(call.id, "❌ Product not configured", show_alert=True)
            safe_send(
                call.message.chat.id,
                f"❌ <b>PRODUCT NOT CONFIGURED</b>\n\n"
                f"{esc(product['name'])}\n\n"
                f"⚠️ Admin ne is product ka API PID set nahi kiya.\n\n"
                f"✅ <b>Aapka balance safe hai — koi paisa nahi kata.</b>\n\n"
                f"📞 Support se contact karo ya baad mein try karo.",
                InlineKeyboardMarkup().add(
                    InlineKeyboardButton("📞 Support", callback_data="support", style="success"),
                    InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger")
                )
            )
            return
    finally:
        cursor.close()
        conn.close()

    # ===== PHASE 2: LOCK balance + reserve coupon/spin =====
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        # lock balance
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id=? AND balance >= ?", (final_price, user_id, final_price))
        if cursor.rowcount != 1:
            conn.rollback()
            bot.answer_callback_query(call.id, "❌ Balance changed", show_alert=True)
            return
        if coupon_id:
            cursor.execute("UPDATE coupons SET used=2 WHERE id=? AND used=0", (coupon_id,))
            if cursor.rowcount != 1:
                conn.rollback()
                # refund the deducted balance
                cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (final_price, user_id))
                conn.commit()
                bot.answer_callback_query(call.id, "❌ Coupon already used", show_alert=True)
                return
        if spin_reward_id:
            cursor.execute("UPDATE spin_rewards SET status='reserved' WHERE id=? AND status='active'", (spin_reward_id,))
            if cursor.rowcount != 1:
                conn.rollback()
                cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (final_price, user_id))
                if coupon_id:
                    cursor.execute("UPDATE coupons SET used=0 WHERE id=? AND used=2", (coupon_id,))
                conn.commit()
                bot.answer_callback_query(call.id, "❌ Spin reward expired", show_alert=True)
                return
        # create pending order entry (so we can recover on failure)
        cursor.execute("INSERT INTO pending_api_orders (user_id, product_id, plan_id, amount, coupon_id, spin_reward_id, status, retry_count) VALUES (?,?,?,?,?,?,?,0)",
                       (user_id, product_id, plan_id, final_price, coupon_id, spin_reward_id, 'processing'))
        order_row_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"process_purchase phase2 error: {e}")
        cursor.close()
        conn.close()
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)
        return
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

    # ===== PHASE 3: API call OUTSIDE transaction =====
    duration_str = plan["duration"]
    api_response = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fetch_key_from_api, product["api_pid"], duration_str)
            api_response = future.result(timeout=30)
    except concurrent.futures.TimeoutError:
        api_response = "error: API timeout"
    except Exception as e:
        logger.error(f"API thread error: {e}")
        api_response = f"error: {e}"

    license_key, error_msg = parse_api_response(api_response)

    # ===== PHASE 4a: SUCCESS — deliver =====
    if license_key:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("UPDATE users SET total_orders=total_orders+1, total_spent=total_spent+? WHERE id=?", (final_price, user_id))
            cursor.execute("INSERT INTO transactions (user_id, amount, type, details, license_key, product_name, duration) VALUES (?,?,'purchase','api',?,?,?)", (user_id, final_price, license_key, product["name"], duration_str))
            cursor.execute("INSERT OR IGNORE INTO review_reminders (user_id, product_id, last_reminder_at, reminder_count) VALUES (?,?,?,0)", (user_id, product_id, utc_now_str()))
            if coupon_id:
                cursor.execute("UPDATE coupons SET used=1 WHERE id=?", (coupon_id,))
            if spin_reward_id:
                cursor.execute("UPDATE spin_rewards SET status='used' WHERE id=?", (spin_reward_id,))
            cursor.execute("SELECT referred_by, total_orders FROM users WHERE id=?", (user_id,))
            ref = cursor.fetchone()
            if ref and ref["referred_by"] and ref["total_orders"] == 1:
                reward = min(math.ceil(final_price * 5 / 100), 100)
                cursor.execute("UPDATE users SET balance = balance + ?, referral_earnings = referral_earnings + ?, total_referrals = total_referrals + 1 WHERE id=?", (reward, reward, ref["referred_by"]))
                ref_id = ref["referred_by"]
            else:
                ref_id = None
            cursor.execute("DELETE FROM pending_api_orders WHERE id=?", (order_row_id,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"purchase success commit error: {e}")
            cursor.close()
            conn.close()
            safe_send(call.message.chat.id, "⚠️ Order complete nahi ho paya. Balance refund kiya jayega. Support se contact karo.")
            return
        cursor.close()
        conn.close()
        if ref_id:
            safe_send(ref_id, f"🎁 Referral Reward!\n\n💰 ₹{reward}")
        caption = f"""✅ <b>PURCHASE SUCCESSFUL!</b>

<b>{esc(product['name'])}</b>
⏰ <b>{esc(duration_str)}</b>
💰 <b>₹{final_price}</b>

🔑 <b>YOUR KEY</b>
<code>{esc(license_key)}</code>

⚠️ Key pe click karo—copy ho jayegi!"""
        markup = InlineKeyboardMarkup(row_width=1)
        if product["download_link"]:
            markup.add(InlineKeyboardButton("📥 Download Files", url=product["download_link"], style="primary"))
        if product["demo_video"]:
            markup.add(InlineKeyboardButton("📺 Demo Video", url=product["demo_video"], style="primary"))
        markup.add(InlineKeyboardButton("⭐ Rate", callback_data=f"review_{product_id}_5", style="success"))
        markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
        try:
            bot.send_photo(call.message.chat.id, SUCCESS_IMG, caption=caption, parse_mode="HTML", reply_markup=markup)
        except Exception:
            safe_send(call.message.chat.id, caption, markup)
        return

    # ===== PHASE 4b: FAIL — refund + revert coupon/spin =====
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        # refund balance
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (final_price, user_id))
        # revert coupon
        if coupon_id:
            cursor.execute("UPDATE coupons SET used=0 WHERE id=? AND used=2", (coupon_id,))
        # revert spin reward
        if spin_reward_id:
            cursor.execute("UPDATE spin_rewards SET status='active' WHERE id=? AND status='reserved'", (spin_reward_id,))
        # BUG #2 FIX: keep order row as 'pending' with retry so worker can retry later
        cursor.execute("UPDATE pending_api_orders SET status='failed' WHERE id=?", (order_row_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"purchase fail refund error: {e}")
    finally:
        cursor.close()
        conn.close()
    bot.answer_callback_query(call.id, f"❌ {error_msg}", show_alert=True)
    safe_send(call.message.chat.id, f"❌ <b>OUT OF STOCK</b>\n\n{esc(product['name'])}\n\n⚠️ {esc(error_msg)}\n\n✅ <b>Aapka balance safe hai — koi paisa nahi kata.</b>\n\n🔔 Jab stock wapas aayega, aapko notify kiya jayega.", InlineKeyboardMarkup().add(InlineKeyboardButton("🔔 Notify Me", callback_data=f"notify_{product_id}", style="primary"), InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger")))

# BUG #30 FIX: INSERT OR IGNORE — unique constraint prevents dupes
def notify_me(call, product_id):
    user_id = call.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO maintenance_notifications (user_id, product_id, notified) VALUES (?,?,0)", (user_id, product_id))
    conn.commit()
    cursor.close()
    conn.close()
    bot.answer_callback_query(call.id, "🔔 Notified!", show_alert=True)

# BUG #18 FIX: escape license_key in code block
def show_history(call, user_id, page=0):
    PER_PAGE = 5
    offset = page * PER_PAGE
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""SELECT license_key, product_name, duration, amount, created_at FROM transactions WHERE user_id=? AND type='purchase' AND license_key IS NOT NULL AND license_key != '' ORDER BY id DESC LIMIT ? OFFSET ?""", (user_id, PER_PAGE, offset))
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE user_id=? AND type='purchase' AND license_key IS NOT NULL AND license_key != ''", (user_id,))
    total = cursor.fetchone()["c"]
    cursor.close()
    conn.close()
    if not rows and page == 0:
        text = """🛍️ ━━ MY ORDERS ━━ 🛍️

━━━━━━━━━━━━━━━

🚫 No orders yet!

🛒 Start shopping to see your orders here!
💎 All your keys will be saved here

━━━━━━━━━━━━━━━"""
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("🛒 Shop Key", callback_data="shop_now", style="danger"), InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
        safe_navigate(call, text, markup)
        return
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    text = f"🛍️ ━━ MY ORDERS ━━ 🛍️\n📄 Page {page + 1}/{total_pages}\n\n━━━━━━━━━━━━━━━\n\n"
    for r in rows:
        text += f"📦 {esc(r['product_name'])}\n⏰ {esc(r['duration'])}\n💰 ₹{r['amount']}\n🔑 <code>{esc(r['license_key'])}</code>\n📅 {r['created_at'][:16]}\n\n━━━━━━━━━━━━━━━\n\n"
    markup = InlineKeyboardMarkup(row_width=3)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"history_page_{page - 1}", style="primary"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"history_page_{page + 1}", style="primary"))
    if nav_buttons:
        markup.add(*nav_buttons)
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def show_add_balance_menu(call):
    text = """💰 <b>ADD BALANCE</b>
━━━━━━━━━━━━━━━

💳 Manual Deposit → Admin Verification Required
⚡ Fam Pay → Auto Detect 5 Min

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("📱 Manual Deposit", callback_data="manual_deposit", style="success"))
    markup.add(InlineKeyboardButton("⚡ Fam Pay (Instant Credit)", callback_data="auto_pay", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def show_keypad(call, user_id, amount):
    min_deposit = get_setting("min_deposit", 500)
    is_new = is_new_user(user_id)
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(InlineKeyboardButton("1", callback_data="pad_1", style="primary"), InlineKeyboardButton("2", callback_data="pad_2", style="primary"), InlineKeyboardButton("3", callback_data="pad_3", style="primary"))
    markup.add(InlineKeyboardButton("4", callback_data="pad_4", style="primary"), InlineKeyboardButton("5", callback_data="pad_5", style="primary"), InlineKeyboardButton("6", callback_data="pad_6", style="primary"))
    markup.add(InlineKeyboardButton("7", callback_data="pad_7", style="primary"), InlineKeyboardButton("8", callback_data="pad_8", style="primary"), InlineKeyboardButton("9", callback_data="pad_9", style="primary"))
    markup.add(InlineKeyboardButton("⌫", callback_data="pad_backspace", style="danger"), InlineKeyboardButton("0", callback_data="pad_0", style="primary"), InlineKeyboardButton("✅", callback_data="pad_enter", style="success"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="back_main", style="danger"))
    text = f"💰 <b>ADD BALANCE</b>\n\n━━━━━━━━━━━━━━━\n\n💳 Enter Amount:\n\n₹ {amount if amount else '0'}\n\n━━━━━━━━━━━━━━━"
    if is_new:
        text += f"\n\n⚠️ New user? Pehli baar ₹{min_deposit} minimum\n   deposit karna padega.\n\n❌ ₹{min_deposit} se kam raha toh payment\n   cancel ho jayega.\n\n━━━━━━━━━━━━━━━"
    safe_navigate(call, text, markup)

def handle_keypad(call, data, user_id):
    state = get_user_state(user_id)
    amount = state.get("keypad_amount", "")
    if data == "pad_backspace":
        amount = amount[:-1]
    elif data == "pad_enter":
        if amount:
            try:
                amt = int(amount)
            except ValueError:
                pop_user_state(user_id)
                bot.answer_callback_query(call.id, "❌ Invalid amount", show_alert=True)
                return
            min_deposit = get_setting("min_deposit", 500)
            if is_new_user(user_id) and amt < min_deposit:
                bot.answer_callback_query(call.id, f"❌ Minimum ₹{min_deposit} required!", show_alert=True)
                return
            generate_qr(call, amt, user_id)
            return
    else:
        digit = data.replace("pad_", "")
        if digit.isdigit():
            amount += digit
    set_user_state(user_id, {"keypad_amount": amount})
    show_keypad(call, user_id, amount)

# BUG #8 FIX: don't leave orphan pending_payments if QR send fails
def generate_qr(call, amount, user_id):
    qr_api = f"{FAMPAY_QR_URL}?upi={FAMPAY_UPI_ID}&amount={amount}"
    try:
        req = urllib.request.Request(qr_api, headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=20).read().decode()
        res = json.loads(raw)
        if str(res.get("status", "")).lower() != "success":
            raise ValueError("QR API failed")
        data = res.get("data", {})
        qr_url = data.get("qr_url")
        order_id = data.get("order_id")
        if not qr_url or not order_id:
            raise ValueError("Missing qr_url or order_id")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pending_payments (user_id, order_id, amount, status, created_at) VALUES (?,?,?,'pending',?)", (user_id, order_id, amount, epoch_now()))
        conn.commit()
        cursor.close()
        conn.close()
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        caption = (
            f"🛒 <b>FAM PAY — ₹{amount}</b>\n\n"
            f"💰 Amount: ₹{amount}\n"
            f"🆔 Order: <code>{order_id}</code>\n\n"
            f"Payment kar do — balance automatic add ho jaayega.\n\n"
            f"Max 10 minutes mein credit hoga."
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_qr_{order_id}", style="danger"))
        try:
            bot.send_photo(call.message.chat.id, qr_url, caption=caption, parse_mode="HTML", reply_markup=markup)
        except Exception as e:
            # BUG #8 FIX: mark pending payment cancelled if QR send fails
            logger.error(f"generate_qr send_photo failed: {e}")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE pending_payments SET status='cancelled' WHERE order_id=? AND status='pending'", (order_id,))
            conn.commit()
            cursor.close()
            conn.close()
            safe_send(call.message.chat.id, "❌ QR generate hua par bhej nahi paye. Dobara try karo.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="add_balance", style="danger")))
    except Exception as e:
        logger.error(f"generate_qr error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)
    finally:
        pop_user_state(user_id)

def show_manual_deposit(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT qr_code_file_id FROM settings WHERE id=1")
    setting = cursor.fetchone()
    cursor.close()
    conn.close()
    qr_file_id = setting["qr_code_file_id"] if setting else None
    manual_upi = get_setting("manual_upi", "")
    min_deposit = get_setting("min_deposit", 500)
    is_new = is_new_user(call.from_user.id)
    text = f"📱 <b>MANUAL DEPOSIT</b>\n\n━━━━━━━━━━━━━━━\n\nUPI: <code>{esc(manual_upi)}</code>\n\n━━━━━━━━━━━━━━━\n\n1. QR scan karo ya UPI pe pay karo\n2. Screenshot lo\n3. UTR copy karo\n\n━━━━━━━━━━━━━━━"
    if is_new:
        text += f"\n\n⚠️ New user? Pehli baar ₹{min_deposit} minimum\n   deposit karna padega.\n\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("📸 SEND PROOF", callback_data="manual_proof", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="add_balance", style="danger"))
    if qr_file_id:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        try:
            bot.send_photo(call.message.chat.id, qr_file_id, caption=text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            safe_send(call.message.chat.id, text, markup)
    else:
        safe_navigate(call, text, markup)

def show_reseller_info(call):
    fee = get_setting("reseller_fee", 399)
    min_balance = get_setting("reseller_min_balance", 2000)
    text = f"""🤝 <b>RESELLER PLAN</b>

━━━━━━━━━━━━━━━

💰 Minimum Balance: ₹{min_balance}
💸 Activation Fee: Sirf ₹{fee}

━━━━━━━━━━━━━━━

⚡ Kaise kaam karta hai?

₹{min_balance} deposit karo — sirf ₹{fee} katega!
Baaki wallet mein safe rahega
jisse koi bhi product khareed sakte ho!

━━━━━━━━━━━━━━━

✅ Reseller Benefits:

✅ Hamare sabhi products bahut saste price pe milenge!
✅ Jitna margin rakho utna profit
✅ Unlimited earning opportunity
✅ Special Reseller Tag milega

━━━━━━━━━━━━━━━

🔥 Aap becho aur karo mast profit!

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(f"✅ JOIN NOW - ₹{fee}", callback_data="join_reseller", style="success"), InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

# BUG #11 FIX: notify_admins failure is logged (not silent)
# BUG #36 FIX: cursor+conn close on every return path
def join_reseller(call):
    user_id = call.from_user.id
    fee = get_setting("reseller_fee", 399)
    min_balance = get_setting("reseller_min_balance", 2000)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT balance, is_reseller FROM users WHERE id=?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return
        if user["is_reseller"]:
            bot.answer_callback_query(call.id, "Already reseller!", show_alert=True)
            return
        if user["balance"] < min_balance:
            safe_navigate(call, f"❌ Minimum ₹{min_balance} balance chahiye.\n\nAapka balance: ₹{user['balance']}", InlineKeyboardMarkup().add(InlineKeyboardButton("💰 Add Balance", callback_data="add_balance", style="success"), InlineKeyboardButton("◀️ Back", callback_data="reseller_info", style="danger")))
            return
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("UPDATE users SET balance = balance - ?, is_reseller=1 WHERE id=? AND balance >= ? AND is_reseller=0", (fee, user_id, min_balance))
            if cursor.rowcount != 1:
                conn.rollback()
                bot.answer_callback_query(call.id, "❌ Failed, try again", show_alert=True)
                return
            cursor.execute("INSERT INTO transactions (user_id, amount, type) VALUES (?,?,'reseller_fee')", (user_id, fee))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"join_reseller error: {e}")
            bot.answer_callback_query(call.id, "❌ Error", show_alert=True)
            return
    finally:
        cursor.close()
        conn.close()
    safe_navigate(call, "🎉 Reseller Active!\n\nAap ab reseller ban gaye hain! 🤝", InlineKeyboardMarkup().add(InlineKeyboardButton("🤝 Reseller Panel", callback_data="reseller_panel", style="success"), InlineKeyboardButton("◀️ Menu", callback_data="back_main", style="danger")))
    # BUG #11 FIX: wrap admin notify, log failure
    try:
        notify_admins(f"🤝 New Reseller!\n\n👤 {user_id}\n💰 ₹{fee}")
    except Exception as e:
        logger.error(f"reseller admin notify failed: {e}")

def show_lucky_spin(call):
    user_id = call.from_user.id
    if is_reseller(user_id):
        safe_navigate(call, "❌ <b>Spin Sirf Regular Users Ke Liye</b>\n\nAap reseller hain — aapko already discounted prices milte hain.\n\nSpin se aapko extra discount nahi milega.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger")))
        return
    time_left = get_spin_time_left(user_id)
    if time_left > 0:
        wait_text = format_time_remaining(time_left)
        text = f"""🎰 ━━ <b>CASH SPIN</b> ━━

❌ Already Spun!

{wait_text}

━━━━━━━━━━━━━━━
🍀 Har 24 ghante mein ek free spin!
💰 Jeeto Cash Reward!

━━━━━━━━━━━━━━━"""
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🔄 Refresh", callback_data="lucky_spin", style="primary"))
        markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
        safe_navigate(call, text, markup)
        return
    text = """🎰 ━━ <b>CASH SPIN</b> ━━

🎁 Daily Free Spin!
💰 Jeeto Cash Reward!
🍀 Har 24 ghante mein ek free spin milega!
━━━━━━━━━━━━━━━
⏰ ✅ Spin available hai!

👇 Spin karo aur luck try karo!"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎮 Spin Karo (FREE)", callback_data="spin_now", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def do_spin(call):
    user_id = call.from_user.id
    if is_reseller(user_id):
        bot.answer_callback_query(call.id, "❌ Spin sirf regular users ke liye hai.", show_alert=True)
        return
    time_left = get_spin_time_left(user_id)
    if time_left > 0:
        wait_text = format_time_remaining(time_left)
        bot.answer_callback_query(call.id, f"❌ {wait_text}", show_alert=True)
        return
    if is_rate_limited(f"spin_{user_id}", 5, 60):
        bot.answer_callback_query(call.id, "❌ Too many spin attempts. Please wait 1 minute.", show_alert=True)
        return
    reward_amount = random.randint(1, 3)
    winning_emoji = random.choice(["💰", "💎", "⭐", "🎁", "🍀", "🔔"])
    symbols = ["🍓", "🍒", "🔔", "⭐", "💎", "💰", "🎁", "🍀", "7️⃣", "🍋"]
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    def build_reel(start_idx, length):
        reel = []
        for i in range(length):
            reel.append(symbols[(start_idx + i) % len(symbols)])
        return reel
    reel_len = 24
    reel1 = build_reel(random.randint(0, 9), reel_len)
    reel2 = build_reel(random.randint(0, 9), reel_len)
    reel3 = build_reel(random.randint(0, 9), reel_len)
    reel1[-3:] = [winning_emoji, winning_emoji, winning_emoji]
    reel2[-3:] = [winning_emoji, winning_emoji, winning_emoji]
    reel3[-3:] = [winning_emoji, winning_emoji, winning_emoji]
    total_frames = reel_len - 3
    delay_schedule = []
    for i in range(total_frames):
        progress = i / max(1, total_frames - 1)
        delay = 0.05 + (0.55 * (progress ** 2))
        delay_schedule.append(delay)
    for i in range(total_frames):
        idx1 = i
        idx2 = min(i + 1, total_frames - 1)
        idx3 = min(i + 2, total_frames - 1)
        s1_top, s1_mid, s1_bot = reel1[idx1], reel1[idx1 + 1], reel1[idx1 + 2]
        s2_top, s2_mid, s2_bot = reel2[idx2], reel2[idx2 + 1], reel2[idx2 + 2]
        s3_top, s3_mid, s3_bot = reel3[idx3], reel3[idx3 + 1], reel3[idx3 + 2]
        spin_text = (f"🎰 <b>CASH SPIN</b> 🎰\n━━━━━━━━━━━━━━━\n\n"
                     f"{s1_top}  ║  {s2_top}  ║  {s3_top}\n"
                     f"━━━━━━━━━━━━━━━\n"
                     f"{s1_mid}  ║  {s2_mid}  ║  {s3_mid}  ⬅️\n"
                     f"━━━━━━━━━━━━━━━\n"
                     f"{s1_bot}  ║  {s2_bot}  ║  {s3_bot}\n\n"
                     f"⏳ <i>Spinning...</i>")
        try:
            bot.edit_message_text(spin_text, chat_id, msg_id, parse_mode="HTML", reply_markup=None)
        except Exception as e:
            err = str(e).lower()
            if "too many requests" in err or "retry after" in err:
                time.sleep(1.2)
                try:
                    bot.edit_message_text(spin_text, chat_id, msg_id, parse_mode="HTML", reply_markup=None)
                except Exception:
                    pass
        time.sleep(delay_schedule[i])
    time.sleep(0.5)
    conn = get_db()
    cursor = conn.cursor()
    now_str = utc_now_str()
    cursor.execute("UPDATE users SET last_spin_at=? WHERE id=?", (now_str, user_id))
    expires_at = utc_now() + timedelta(hours=1)
    cursor.execute("INSERT INTO spin_rewards (user_id, amount, status, expires_at, warning_sent, expire_sent) VALUES (?,?,?,?,0,0)", (user_id, reward_amount, 'active', expires_at.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    cursor.close()
    conn.close()
    expiry_ist = expires_at + timedelta(hours=5, minutes=30)
    expiry_display = expiry_ist.strftime('%I:%M %p')
    result_text = (f"🎰 <b>CASH SPIN RESULT!</b> 🎰\n━━━━━━━━━━━━━━━\n\n"
                   f"{winning_emoji}  ║  {winning_emoji}  ║  {winning_emoji}\n"
                   f"━━━━━━━━━━━━━━━\n"
                   f"{winning_emoji}  ║  {winning_emoji}  ║  {winning_emoji}  ⬅️\n"
                   f"━━━━━━━━━━━━━━━\n"
                   f"{winning_emoji}  ║  {winning_emoji}  ║  {winning_emoji}\n\n"
                   f"━━━━━━━━━━━━━━━\n"
                   f"🎊 <b>JACKPOT!</b>\n\n"
                   f"💰 Aapko <b>₹{reward_amount}</b> Cash mila!\n\n"
                   f"⚠️ Sirf <b>1 Ghanta</b> Ka Time!\n"
                   f"⏰ <b>{expiry_display}</b> tak purchase karo\n"
                   f"toh yeh ₹{reward_amount} automatically discount milega!\n\n"
                   f"❌ Use nahi kiya toh reward expire ho jaega!\n"
                   f"━━━━━━━━━━━━━━━\n"
                   f"⏰ 24 Ghante baad phir spin milega!")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🛒 Shop Now", callback_data="shop_now", style="danger"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    try:
        bot.edit_message_text(result_text, chat_id, msg_id, parse_mode="HTML", reply_markup=markup)
    except Exception:
        safe_send(chat_id, result_text, markup)

# BUG #12 FIX: use cached bot username
def show_referral(call, user_id):
    bot_username = get_bot_username()
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT total_referrals, referral_earnings FROM users WHERE id=?", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    text = f"""👥 <b>REFERRAL SYSTEM</b>

━━━━━━━━━━━━━━━

🔗 Aapka Link:
{link}

📋 Tap on link to copy

━━━━━━━━━━━━━━━

👥 Total Referrals: {row['total_referrals'] if row else 0}
💰 Earnings: ₹{row['referral_earnings'] if row else 0}

━━━━━━━━━━━━━━━

💰 Dosto ko invite karo →
Unki pehli purchase pe bonus guaranteed!

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={link}", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, text, markup)

def show_selling_proof(call):
    link = get_setting("selling_proof_link", "https://t.me/")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("📸 Open Channel", url=link, style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, "📸 SELLING PROOF", markup)

def show_support_menu(call):
    name1 = get_setting("support_name_1", "Support")
    support_url = get_setting("support_url", "https://t.me/Umeshxmodz")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"👨‍💼 {name1}", url=support_url, style="primary"))
    markup.add(InlineKeyboardButton("🎫 Create Ticket", callback_data="create_ticket", style="success"))
    markup.add(InlineKeyboardButton("❓ FAQ", callback_data="faq_menu", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    safe_navigate(call, "💬 <b>SUPPORT CENTER</b> 💬\n\n👋 Need Any Help?\n\n━━━━━━━━━━━━━━━\n\n💬 Purchase Support\n💳 Payment Issues\n🔑 Key Problems\n⚡ Instant Assistance\n\n━━━━━━━━━━━━━━━", markup)

def show_tutorial_menu(call):
    video_link = get_setting("tutorial_video", "")
    markup = InlineKeyboardMarkup(row_width=1)
    if video_link:
        markup.add(InlineKeyboardButton("▶️ Watch Tutorial Video", url=video_link, style="primary"))
    markup.add(InlineKeyboardButton("📞 Support", callback_data="support", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger"))
    text = """<b>HOW TO USE BOT</b>

━━━━━━━━━━━━━━━━━

1️⃣ /start — Bot shuru karo

2️⃣ 📱 Phone verify karo

3️⃣ 💰 Add Balance karo
    • Fam Pay se turant
    • Manual Deposit se admin verify

4️⃣ 🔑 Shop Key se product kharido

5️⃣ 📋 Key copy karo

6️⃣ 🎮 Game mein use karo

━━━━━━━━━━━━━━━"""
    safe_navigate(call, text, markup)

def show_tutorial_video_menu(call):
    video_link = get_setting("tutorial_video", "")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✏️ Change Link", callback_data="change_tutorial_video", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, f"🎬 TUTORIAL VIDEO\n\nCurrent Link: {esc(video_link) or 'N/A'}", markup)

def request_review(call, product_id, rating):
    set_user_state(call.from_user.id, {"action": "review_screenshot", "product_id": product_id, "rating": rating})
    safe_navigate(call, "📸 REVIEW SCREENSHOT\n\n━━━━━━━━━━━━━━━\n\nGameplay ka screenshot bhejo.\n\n━━━━━━━━━━━━━━━", InlineKeyboardMarkup().add(InlineKeyboardButton("⏭ Skip", callback_data="skip_review", style="danger")))

def show_bot_maintenance_menu(call):
    status = get_setting("bot_maintenance", "off")
    status_text = "🔴 ON" if status == "on" else "🟢 OFF"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✅ ON Karo", callback_data="bot_maintenance_on", style="success"))
    markup.add(InlineKeyboardButton("❌ OFF Karo", callback_data="bot_maintenance_off", style="danger"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, f"🔧 <b>BOT MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\nCurrent Status: {status_text}\n\n━━━━━━━━━━━━━━━", markup)

def show_manage_admins(call):
    admin_ids = get_admin_ids(force=True)
    text = "👑 <b>MANAGE ADMINS</b>\n\n━━━━━━━━━━━━━━━\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    text += f"1️⃣ 👑 Admin 1 (Main) - ID: {ADMIN_USER_ID}\n\n"
    for i, admin_id in enumerate(admin_ids[1:], start=2):
        text += f"{i}️⃣ Admin {i} - ID: {admin_id}\n\n"
        markup.add(InlineKeyboardButton(f"➖ Remove Admin {i}", callback_data=f"remove_specific_admin_{admin_id}", style="danger"))
    text += "━━━━━━━━━━━━━━━"
    markup.add(InlineKeyboardButton("➕ Add Admin", callback_data="add_admin", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, text, markup)

def show_admin_dashboard(call):
    conn = get_db()
    cursor = conn.cursor()
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='add_money' AND details='fam_pay' AND DATE(created_at)=?", (today,))
    today_fam = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='add_money' AND (details IS NULL OR details != 'fam_pay') AND DATE(created_at)=?", (today,))
    today_manual = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='purchase' AND DATE(created_at)=?", (today,))
    today_sales = cursor.fetchone()["t"]
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE type='purchase' AND DATE(created_at)=?", (today,))
    today_orders = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE DATE(joined_at)=?", (today,))
    today_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='add_money' AND details='fam_pay' AND DATE(created_at) >= ?", (week_ago,))
    weekly_fam = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='add_money' AND (details IS NULL OR details != 'fam_pay') AND DATE(created_at) >= ?", (week_ago,))
    weekly_manual = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='purchase' AND DATE(created_at) >= ?", (week_ago,))
    weekly_sales = cursor.fetchone()["t"]
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE type='purchase' AND DATE(created_at) >= ?", (week_ago,))
    weekly_orders = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE DATE(joined_at) >= ?", (week_ago,))
    weekly_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM transactions WHERE type='purchase' AND license_key IS NOT NULL")
    sold_keys = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM manual_deposits WHERE status='pending'")
    pending_deposits = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM support_tickets WHERE status='open'")
    open_tickets = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM pending_api_orders WHERE status='pending'")
    pending_api = cursor.fetchone()["c"]
    cursor.execute("""SELECT p.name, COUNT(t.id) as sold FROM products p 
                      LEFT JOIN transactions t ON t.product_name = p.name AND t.type='purchase' 
                      GROUP BY p.id ORDER BY sold DESC LIMIT 1""")
    top_product = cursor.fetchone()
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='add_money' AND details='fam_pay'")
    lifetime_fam = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='add_money' AND (details IS NULL OR details != 'fam_pay')")
    lifetime_manual = cursor.fetchone()["t"]
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM transactions WHERE type='purchase'")
    lifetime_sales = cursor.fetchone()["t"]
    cursor.execute("SELECT COUNT(*) as c FROM users")
    lifetime_users = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE is_reseller=1")
    resellers = cursor.fetchone()["c"]
    cursor.close()
    conn.close()

    top_name = top_product["name"] if top_product else "N/A"
    top_sold = top_product["sold"] if top_product else 0

    # BUG #40 FIX: "PROFIT" renamed to "NET BALANCE" (revenue - sales is not profit)
    text = f"""👑 ━━━ <b>ADMIN DASHBOARD</b> ━━━ 👑

━━━━━━━━━━━━━━━━━━━━━

📊 <b>TODAY</b>

💳 Fam Pay: ₹{today_fam}
📱 Manual: ₹{today_manual}
🛒 Sales: ₹{today_sales}
📦 Orders: {today_orders}
👥 New Users: {today_users}

━━━━━━━━━━━━━━━━━━━━━

📅 <b>WEEKLY</b>

💳 Fam Pay: ₹{weekly_fam}
📱 Manual: ₹{weekly_manual}
🛒 Sales: ₹{weekly_sales}
📦 Orders: {weekly_orders}
👥 New Users: {weekly_users}

━━━━━━━━━━━━━━━━━━━━━

🔑 <b>KEYS</b>

✅ Sold: {sold_keys}

━━━━━━━━━━━━━━━━━━━━━

📊 <b>QUICK STATS</b>

🔔 Pending Deposits: {pending_deposits}
🎫 Open Tickets: {open_tickets}
⏳ Pending API Orders: {pending_api}

━━━━━━━━━━━━━━━━━━━━━

🏆 <b>TOP SELLING</b>

🥇 {esc(top_name)} — {top_sold} sold

━━━━━━━━━━━━━━━━━━━━━

👑 <b>LIFETIME</b>

💳 Fam Pay: ₹{lifetime_fam}
📱 Manual: ₹{lifetime_manual}
🛒 Total Sales: ₹{lifetime_sales}
👥 Total Users: {lifetime_users}
🤝 Resellers: {resellers}

━━━━━━━━━━━━━━━━━━━━━

💎 <b>NET BALANCE:</b> ₹{lifetime_fam + lifetime_manual - lifetime_sales}

━━━━━━━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🔄 Refresh", callback_data="admin_dashboard", style="primary"), InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, text, markup)

def show_admin_analytics(call):
    show_admin_dashboard(call)

def show_admin_today_stats(call):
    show_admin_dashboard(call)

def show_admin_weekly_stats(call):
    show_admin_dashboard(call)

def show_admin_top_products(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT product_name, COUNT(*) as c FROM transactions WHERE type='purchase' AND product_name IS NOT NULL GROUP BY product_name ORDER BY c DESC LIMIT 5")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    text = "🏆 <b>TOP PRODUCTS</b>\n━━━━━━━━━━━━━━━\n\n"
    if not rows:
        text += "No sales yet."
    else:
        for i, r in enumerate(rows, 1):
            text += f"{i}. {esc(r['product_name'])} — {r['c']} sold\n"
    text += "\n━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_analytics", style="danger"))
    safe_navigate(call, text, markup)

def show_admin_user_growth(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM users")
    total = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE DATE(joined_at)=?", (date.today().isoformat(),))
    today = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) as c FROM users WHERE DATE(joined_at) >= ?", ((date.today() - timedelta(days=7)).isoformat(),))
    week = cursor.fetchone()["c"]
    cursor.close()
    conn.close()
    text = f"""👥 <b>USER GROWTH</b>
━━━━━━━━━━━━━━━

📊 Total: {total}
🆕 Today: {today}
📅 This Week: {week}

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_analytics", style="danger"))
    safe_navigate(call, text, markup)

def show_admin_revenue_report(call):
    show_admin_dashboard(call)
    
def show_manage_products(call):
    text = """📦 <b>MANAGE PRODUCTS</b>
━━━━━━━━━━━━━━━

🔑 Apne products ko category ke hisaab se manage karo!

━━━━━━━━━━━━━━━

🤖 <b>ROOT PANEL</b>
   Root products yahan dikhenge

📱 <b>NON-ROOT PANEL</b>
   Non-Root products yahan dikhenge

🍎 <b>IPHONE PANEL</b>
   iPhone products yahan dikhenge

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🤖 Root Panel", callback_data="manage_category_root", style="primary"))
    markup.add(InlineKeyboardButton("📱 Non-Root Panel", callback_data="manage_category_nonroot", style="primary"))
    markup.add(InlineKeyboardButton("🍎 iPhone Panel", callback_data="manage_category_iphone", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger"))
    safe_navigate(call, text, markup)

def show_manage_products_by_category(call, category):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, status, api_pid FROM products WHERE category=?", (category,))
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    if not products:
        safe_navigate(call, f"❌ No {category.upper()} products.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
        return
    category_name = get_category_name(category)
    text = f"<b>MANAGE {category_name} PRODUCTS</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for p in products:
        status = "🔧 Maintenance" if p["status"] == "maintenance" else "✅ Active"
        api_pid = p["api_pid"] or "❌ No PID"
        text += f"<b>{esc(p['name'])}</b>\n📊 {status}\n🔗 PID: <code>{esc(api_pid)}</code>\n\n"
        markup.add(InlineKeyboardButton(f"{p['name']}", callback_data=f"manage_product_{p['id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger"))
    safe_navigate(call, text, markup)

def show_product_management_menu(call, product_id):
    user_id = call.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, category, status, api_pid FROM products WHERE id=?", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()
    if not product:
        bot.answer_callback_query(call.id, "❌ Not found", show_alert=True)
        return
    cat_map = {"root": "🤖 ROOT", "nonroot": "📱 NON-ROOT", "iphone": "🍎 IPHONE"}
    cat = cat_map.get(product["category"], product["category"].upper())
    status = "🔧 Maintenance" if product["status"] == "maintenance" else "✅ Active"
    api_pid_display = product["api_pid"] or "❌ Not Set"
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("✏️ Edit Name", f"edit_name_{product_id}", "primary"),
        ("📅 Add Plan", f"add_plan_menu_{product_id}", "success"),
        ("📋 Edit Plan", f"manage_plans_{product_id}", "primary"),
    ]
    if user_id == ADMIN_USER_ID:
        buttons.append(("🔗 Set API PID", f"set_api_pid_{product_id}", "primary"))
    buttons.extend([
        ("📺 Add Demo Video", f"add_video_menu_{product_id}", "primary"),
        ("📥 Download Files Link", f"add_download_link_{product_id}", "primary"),
        ("📝 Add Features", f"add_features_menu_{product_id}", "primary"),
        ("🔧 Toggle Maintenance", f"toggle_maint_{product_id}", "danger"),
        ("🗑️ Delete Product", f"del_product_{product_id}", "danger"),
    ])
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.add(
                InlineKeyboardButton(buttons[i][0], callback_data=buttons[i][1], style=buttons[i][2]),
                InlineKeyboardButton(buttons[i+1][0], callback_data=buttons[i+1][1], style=buttons[i+1][2])
            )
        else:
            markup.add(InlineKeyboardButton(buttons[i][0], callback_data=buttons[i][1], style=buttons[i][2]))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger"))
    text = f"""<b>PRODUCT MANAGEMENT</b>

━━━━━━━━━━━━━━━━━━━

{esc(product['name'])}
📂 {cat}
📊 {status}
🔗 API PID: <code>{esc(api_pid_display)}</code>

━━━━━━━━━━━━━━━━━━━

Choose action:"""
    safe_navigate(call, text, markup)

def show_plans_management(call, product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, duration, price FROM plans WHERE product_id=?", (product_id,))
    plans = cursor.fetchall()
    cursor.close()
    conn.close()
    if not plans:
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("📅 Add Plan", callback_data=f"add_plan_menu_{product_id}", style="success"))
        markup.add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{product_id}", style="danger"))
        safe_navigate(call, "⚠️ No plans.", markup)
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for pl in plans:
        markup.add(InlineKeyboardButton(f"✏️ {pl['duration']} | ₹{pl['price']}", callback_data=f"edit_plan_{pl['id']}", style="primary"))
        markup.add(InlineKeyboardButton(f"🗑️ {pl['duration']}", callback_data=f"del_plan_{pl['id']}", style="danger"))
    markup.add(InlineKeyboardButton("📅 Add Plan", callback_data=f"add_plan_menu_{product_id}", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{product_id}", style="danger"))
    safe_navigate(call, "📋 MANAGE PLANS", markup)

def show_plan_edit_menu(call, plan_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT pl.duration, pl.price, p.name FROM plans pl JOIN products p ON pl.product_id=p.id WHERE pl.id=?", (plan_id,))
    plan = cursor.fetchone()
    cursor.close()
    conn.close()
    if not plan:
        bot.answer_callback_query(call.id, "❌ Not found", show_alert=True)
        return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("💰 Edit Price", callback_data=f"edit_plan_price_{plan_id}", style="primary"))
    markup.add(InlineKeyboardButton("⏰ Edit Duration", callback_data=f"edit_plan_duration_{plan_id}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger"))
    safe_navigate(call, f"✏️ EDIT PLAN\n\n{esc(plan['name'])}\n⏰ {esc(plan['duration'])}\n💰 ₹{plan['price']}", markup)

def delete_plan(call, plan_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM plans WHERE id=?", (plan_id,))
    conn.commit()
    cursor.close()
    conn.close()
    log_admin_action(call.from_user.id, "Delete Plan", f"Plan ID: {plan_id}")
    bot.answer_callback_query(call.id, "✅ Deleted!", show_alert=True)

# BUG #33 FIX: notification rollback logic cleaned — commit before send, only revert on failure
def toggle_maintenance(call, product_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status, name FROM products WHERE id=?", (product_id,))
        row = cursor.fetchone()
        if row:
            new_status = 'maintenance' if row["status"] == 'active' else 'active'
            cursor.execute("UPDATE products SET status=? WHERE id=?", (new_status, product_id))
            conn.commit()
            if new_status == 'active':
                cursor.execute("SELECT id, user_id FROM maintenance_notifications WHERE product_id=? AND notified=0", (product_id,))
                pending = cursor.fetchall()
                for n in pending:
                    try:
                        safe_send(n["user_id"], f"🔥🔥🔥 HOT ALERT! 🔥🔥🔥\n\n{esc(row['name'])}\n\n⚡ ACTIVE HO GAYA!\n\n🚀 Jaldi Purchase Karo!")
                        cursor.execute("UPDATE maintenance_notifications SET notified=1 WHERE id=?", (n["id"],))
                        conn.commit()
                    except Exception as e:
                        logger.warning(f"maintenance notify fail user={n['user_id']}: {e}")
            log_admin_action(call.from_user.id, "Toggle Maintenance", f"Product {row['name']} → {new_status}")
            bot.answer_callback_query(call.id, f"✅ {new_status}!", show_alert=True)
    except Exception as e:
        logger.error(f"toggle_maintenance error: {e}")
    finally:
        cursor.close()
        conn.close()
    show_product_management_menu(call, product_id)

def delete_product(call, product_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM products WHERE id=?", (product_id,))
        prow = cursor.fetchone()
        pname = prow["name"] if prow else "Unknown"
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT id, coupon_id, spin_reward_id FROM pending_api_orders WHERE product_id=? AND status='pending'", (product_id,))
        pending = cursor.fetchall()
        for o in pending:
            if o["coupon_id"]:
                cursor.execute("UPDATE coupons SET used=0 WHERE id=? AND used=2", (o["coupon_id"],))
            if o["spin_reward_id"]:
                cursor.execute("UPDATE spin_rewards SET status='expired' WHERE id=? AND status='reserved'", (o["spin_reward_id"],))
            cursor.execute("UPDATE pending_api_orders SET status='cancelled' WHERE id=?", (o["id"],))
        cursor.execute("DELETE FROM plans WHERE product_id=?", (product_id,))
        cursor.execute("DELETE FROM maintenance_notifications WHERE product_id=?", (product_id,))
        cursor.execute("DELETE FROM review_reminders WHERE product_id=?", (product_id,))
        cursor.execute("DELETE FROM reviews WHERE product_id=?", (product_id,))
        cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
        log_admin_action(call.from_user.id, "Delete Product", f"{pname} (ID: {product_id})")
    except Exception as e:
        conn.rollback()
        logger.error(f"delete_product error: {e}")
    cursor.close()
    conn.close()
    bot.answer_callback_query(call.id, "✅ Deleted!", show_alert=True)

def show_maintenance_products(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category FROM products WHERE status='maintenance'")
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    if not products:
        safe_navigate(call, "✅ No maintenance products.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
        return
    text = """🔧 <b>MAINTENANCE PRODUCTS</b>

━━━━━━━━━━━━━━━

"""
    markup = InlineKeyboardMarkup(row_width=1)
    cat_map = {"root": "🤖 ROOT", "nonroot": "📱 NON-ROOT", "iphone": "🍎 IPHONE"}
    for p in products:
        cat = cat_map.get(p["category"], p["category"].upper())
        text += f"🔧 {esc(p['name'])}\n📂 {cat}\n\n"
        markup.add(InlineKeyboardButton(f"✅ Remove Maintenance - {p['name']}", callback_data=f"remove_maint_{p['id']}", style="success"))
    text += "━━━━━━━━━━━━━━━"
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, text, markup)

def show_add_product_category(call):
    text = """➕ ━━ <b>ADD PRODUCT</b> ━━

📦 Naya product kis category mein add karna hai?

━━━━━━━━━━━━━━━

🤖 <b>ROOT</b>
   Root panel ke liye product

📱 <b>NON-ROOT</b>
   Non-Root panel ke liye product

🍎 <b>IPHONE</b>
   iPhone panel ke liye product

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🤖 Root", callback_data="add_product_root", style="primary"))
    markup.add(InlineKeyboardButton("📱 Non-Root", callback_data="add_product_nonroot", style="primary"))
    markup.add(InlineKeyboardButton("🍎 iPhone", callback_data="add_product_iphone", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger"))
    safe_navigate(call, text, markup)

def show_deposit_requests(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM manual_deposits WHERE status='pending'")
    deposits = cursor.fetchall()
    if not deposits:
        cursor.close()
        conn.close()
        safe_navigate(call, "💰 No pending.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger")))
        return
    user_ids = [d["user_id"] for d in deposits]
    placeholders = ",".join("?" * len(user_ids))
    cursor.execute(f"SELECT id, phone_number, username FROM users WHERE id IN ({placeholders})", user_ids)
    info_map = {r["id"]: {"phone": r["phone_number"], "username": r["username"]} for r in cursor.fetchall()}
    cursor.close()
    conn.close()
    text = f"""💰 ━━━ <b>DEPOSIT REQUESTS</b> ━━━ 💰

━━━━━━━━━━━━━━━━━━━━━

📊 Pending: {len(deposits)}

━━━━━━━━━━━━━━━━━━━━━

"""
    markup = InlineKeyboardMarkup(row_width=1)
    for i, d in enumerate(deposits, 1):
        user_id = d["user_id"]
        info = info_map.get(user_id, {})
        phone = info.get("phone") or "N/A"
        uname = info.get("username") or "N/A"
        text += f"📌 <b>REQUEST {i}</b>\n👤 @{esc(uname)}\n🆔 User ID: {user_id}\n📱 Phone: {esc(phone)}\n💰 Amount: ₹{d['amount']}\n📝 UTR: {esc(d['utr'])}\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        markup.add(InlineKeyboardButton(f"👤 @{uname} - ₹{d['amount']}", callback_data=f"view_deposit_{d['id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, text, markup)

# BUG #32 FIX: no double answer_callback_query
def show_deposit_detail(call, deposit_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM manual_deposits WHERE id=?", (deposit_id,))
    d = cursor.fetchone()
    if not d:
        cursor.close()
        conn.close()
        bot.answer_callback_query(call.id, "❌ Not found", show_alert=True)
        return
    cursor.execute("SELECT phone_number, username FROM users WHERE id=?", (d["user_id"],))
    user_row = cursor.fetchone()
    cursor.close()
    conn.close()
    phone = user_row["phone_number"] if user_row and user_row["phone_number"] else "N/A"
    uname = user_row["username"] if user_row and user_row["username"] else "N/A"
    caption = f"""📱 ━━━ <b>DEPOSIT DETAILS</b> ━━━ 📱

━━━━━━━━━━━━━━━━━━━━━

👤 @{esc(uname)}
🆔 User ID: {d['user_id']}
📱 Phone: {esc(phone)}
💰 Amount: ₹{d['amount']}
📝 UTR: {esc(d['utr'])}

━━━━━━━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_deposit_{deposit_id}", style="success"))
    markup.add(InlineKeyboardButton("❌ Reject", callback_data=f"reject_deposit_{deposit_id}", style="danger"))
    markup.add(InlineKeyboardButton("📩 DM User", url=f"tg://user?id={d['user_id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_deposit_requests", style="danger"))
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    try:
        bot.send_photo(call.message.chat.id, d["screenshot_file_id"], caption=caption, parse_mode="HTML", reply_markup=markup)
    except Exception:
        safe_send(call.message.chat.id, caption, markup)

# BUG #31 FIX: no fallback 500 magic — use exact deposit amount
def approve_deposit(call, deposit_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT user_id, amount FROM manual_deposits WHERE id=? AND status='pending'", (deposit_id,))
        d = cursor.fetchone()
        if not d:
            conn.rollback()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "❌ Already processed", show_alert=True)
            return
        amount = d["amount"] if d["amount"] and d["amount"] > 0 else 0
        if amount <= 0:
            conn.rollback()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "❌ Invalid amount in deposit", show_alert=True)
            return
        cursor.execute("UPDATE manual_deposits SET status='approved' WHERE id=? AND status='pending'", (deposit_id,))
        if cursor.rowcount != 1:
            conn.rollback()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "❌ Already processed", show_alert=True)
            return
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, d["user_id"]))
        cursor.execute("INSERT INTO transactions (user_id, amount, type, details) VALUES (?,?,'add_money','manual')", (d["user_id"], amount))
        conn.commit()
        log_admin_action(call.from_user.id, "Approve Deposit", f"User {d['user_id']} — ₹{amount}")
    except Exception as e:
        conn.rollback()
        logger.error(f"approve_deposit error: {e}")
        cursor.close()
        conn.close()
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)
        return
    cursor.close()
    conn.close()
    safe_send(d["user_id"], f"✅ PAYMENT APPROVED!\n\n💰 ₹{amount} added to balance.")
    bot.answer_callback_query(call.id, "✅ Approved!", show_alert=True)

def show_reject_options(call, deposit_id):
    safe_navigate(call, "❌ Reject?", InlineKeyboardMarkup().add(InlineKeyboardButton("📝 Reason", callback_data=f"reject_with_reason_{deposit_id}", style="primary"), InlineKeyboardButton("❌ No Reason", callback_data=f"reject_no_reason_{deposit_id}", style="danger")))

def reject_deposit_no_reason(call, deposit_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM manual_deposits WHERE id=?", (deposit_id,))
    d = cursor.fetchone()
    cursor.execute("UPDATE manual_deposits SET status='rejected' WHERE id=? AND status='pending'", (deposit_id,))
    conn.commit()
    if cursor.rowcount == 1 and d:
        safe_send(d["user_id"], "❌ PAYMENT REJECTED\n\nSupport se contact karo.")
        log_admin_action(call.from_user.id, "Reject Deposit", f"User {d['user_id']}")
    cursor.close()
    conn.close()
    bot.answer_callback_query(call.id, "✅ Rejected!", show_alert=True)

def show_admin_tickets(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM support_tickets WHERE status='open' ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END ASC, id DESC")
    tickets = cursor.fetchall()
    cursor.close()
    conn.close()
    if not tickets:
        safe_navigate(call, "🎫 No open tickets.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger")))
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for t in tickets:
        pri = get_priority_emoji(t["priority"])
        markup.add(InlineKeyboardButton(f"{pri} #{t['id']} - {t['subject'][:30]}", callback_data=f"view_ticket_{t['id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger"))
    safe_navigate(call, f"🎫 Tickets (Priority Sorted)\n\nOpen: {len(tickets)}", markup)

def show_ticket_detail(call, ticket_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM support_tickets WHERE id=?", (ticket_id,))
    t = cursor.fetchone()
    cursor.close()
    conn.close()
    if not t:
        bot.answer_callback_query(call.id, "❌ Not found", show_alert=True)
        return
    pri = get_priority_emoji(t["priority"])
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("💬 Reply", callback_data=f"reply_ticket_{ticket_id}", style="primary"))
    markup.add(InlineKeyboardButton("📩 DM User", url=f"tg://user?id={t['user_id']}", style="primary"))
    markup.add(InlineKeyboardButton("✅ Close", callback_data=f"close_ticket_{ticket_id}", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_tickets", style="danger"))
    safe_navigate(call, f"🎫 TICKET #{ticket_id}\n\n{pri} Priority: {t['priority'].upper()}\n👤 ID: {t['user_id']}\n\n📝 Subject: {esc(t['subject'])}\n💬 Message: {esc(t['message'])}", markup)

def show_reviews(call):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT r.* FROM reviews r ORDER BY r.id DESC LIMIT 20")
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    if not reviews:
        safe_navigate(call, "📸 No reviews.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger")))
        return
    text = "📸 <b>REVIEWS</b>\n\n"
    for r in reviews:
        stars = "⭐" * r["rating"]
        text += f"{stars} | 👤 {r['user_id']}\n📦 Product: {r['product_id']}\n\n"
    safe_navigate(call, text, InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger")))

def show_reseller_price_products(call):
    text = """🤝 ━━ <b>RESELLER PRICES</b> ━━

💎 Reseller prices ko category ke hisaab se manage karo!

━━━━━━━━━━━━━━━

🤖 <b>ROOT PANEL</b>
   Root products ke reseller prices

📱 <b>NON-ROOT PANEL</b>
   Non-Root products ke reseller prices

🍎 <b>IPHONE PANEL</b>
   iPhone products ke reseller prices

━━━━━━━━━━━━━━━"""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🤖 Root Panel", callback_data="reseller_category_root", style="primary"))
    markup.add(InlineKeyboardButton("📱 Non-Root Panel", callback_data="reseller_category_nonroot", style="primary"))
    markup.add(InlineKeyboardButton("🍎 iPhone Panel", callback_data="reseller_category_iphone", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger"))
    safe_navigate(call, text, markup)

def show_reseller_price_products_by_category(call, category):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM products WHERE category=?", (category,))
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    if not products:
        safe_navigate(call, f"❌ No {category.upper()} products.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_reseller_prices", style="danger")))
        return
    category_name = get_category_name(category)
    text = f"🤝 <b>RESELLER PRICES - {category_name}</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    for p in products:
        markup.add(InlineKeyboardButton(f"{p['name']}", callback_data=f"reseller_price_product_{p['id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_reseller_prices", style="danger"))
    safe_navigate(call, text, markup)

def show_reseller_price_plans(call, product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, duration, reseller_price FROM plans WHERE product_id=?", (product_id,))
    plans = cursor.fetchall()
    cursor.close()
    conn.close()
    markup = InlineKeyboardMarkup(row_width=1)
    for pl in plans:
        markup.add(InlineKeyboardButton(f"⏰ {pl['duration']} | ₹{pl['reseller_price'] or 'Not Set'}", callback_data=f"edit_reseller_price_{pl['id']}", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_reseller_prices", style="danger"))
    safe_navigate(call, "💰 Select plan:", markup)

def show_reseller_fee_menu(call):
    fee = get_setting("reseller_fee", 399)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✏️ Change Fee", callback_data="change_reseller_fee", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_payments", style="danger"))
    safe_navigate(call, f"🤝 RESELLER FEE\n\nCurrent Fee: ₹{fee}", markup)

def show_min_balance_menu(call):
    min_balance = get_setting("reseller_min_balance", 2000)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✏️ Change Min Balance", callback_data="change_min_balance", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_payments", style="danger"))
    safe_navigate(call, f"💳 MIN BALANCE\n\nCurrent: ₹{min_balance}", markup)

def show_min_deposit_menu(call):
    min_dep = get_setting("min_deposit", 500)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✏️ Change Amount", callback_data="change_min_deposit", style="primary"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_payments", style="danger"))
    safe_navigate(call, f"💰 MINIMUM DEPOSIT\n\nCurrent: ₹{min_dep}", markup)

def show_support_contacts_menu(call):
    text = "💬 <b>SUPPORT CONTACTS</b>\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    name1 = get_setting("support_name_1", "Support")
    support_url = get_setting("support_url", "https://t.me//")
    text += f"1️⃣ {esc(name1)}\n🔗 {esc(support_url)}\n\n"
    markup.add(InlineKeyboardButton("✏️ Edit Name", callback_data="edit_support_contact_default_1", style="primary"))
    markup.add(InlineKeyboardButton("✏️ Edit URL", callback_data="edit_support_url", style="primary"))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM support_contacts")
    contacts = cursor.fetchall()
    cursor.close()
    conn.close()
    for i, c in enumerate(contacts):
        text += f"{i+2}️⃣ {esc(c['name'])} → ID: {c['user_id']}\n\n"
        markup.add(InlineKeyboardButton(f"✏️ Edit {c['name']}", callback_data=f"edit_support_contact_{c['id']}", style="primary"))
        markup.add(InlineKeyboardButton(f"➖ Remove {c['name']}", callback_data=f"remove_support_contact_{c['id']}", style="danger"))
    markup.add(InlineKeyboardButton("➕ Add Contact", callback_data="add_support_contact", style="success"))
    markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_support", style="danger"))
    safe_navigate(call, text, markup)

def backup_database(call):
    try:
        conn = get_db()
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.close()
        with open(DB_PATH, "rb") as f:
            bot.send_document(call.message.chat.id, f, caption="💾 Backup Ready!")
        log_admin_action(call.from_user.id, "Database Backup")
        bot.answer_callback_query(call.id, "✅ Sent!", show_alert=True)
    except Exception as e:
        logger.error(f"backup_database error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)

def prompt_restore(call):
    if call.from_user.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "⛔ Only Admin 1", show_alert=True)
        return
    set_user_state(call.from_user.id, {"action": "restore_db"})
    safe_navigate(call, "📂 RESTORE DATA\n\nBackup file bhejo (.db)", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_panel", style="danger")))

# ============ BROADCAST CATEGORY SENDERS ============
# BUG #41 FIX: dedup user_ids
def _dedup(ids):
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out

def send_broadcast_to_users(user_ids, broadcast_text):
    count = 0
    for uid in _dedup(user_ids):
        try:
            safe_send(uid, broadcast_text)
            count += 1
        except Exception:
            pass
        time.sleep(BROADCAST_DELAY)
    return count

def send_photo_broadcast(user_ids, file_id, caption=""):
    count = 0
    for uid in _dedup(user_ids):
        try:
            bot.send_photo(uid, file_id, caption=caption, parse_mode="HTML")
            count += 1
        except Exception:
            pass
        time.sleep(BROADCAST_DELAY)
    return count

def send_video_broadcast(user_ids, file_id, caption=""):
    count = 0
    for uid in _dedup(user_ids):
        try:
            bot.send_video(uid, file_id, caption=caption, parse_mode="HTML")
            count += 1
        except Exception:
            pass
        time.sleep(BROADCAST_DELAY)
    return count

def send_voice_broadcast(user_ids, file_id, caption=""):
    count = 0
    for uid in _dedup(user_ids):
        try:
            bot.send_voice(uid, file_id, caption=caption, parse_mode="HTML")
            count += 1
        except Exception:
            pass
        time.sleep(BROADCAST_DELAY)
    return count

def send_audio_broadcast(user_ids, file_id, caption=""):
    count = 0
    for uid in _dedup(user_ids):
        try:
            bot.send_audio(uid, file_id, caption=caption, parse_mode="HTML")
            count += 1
        except Exception:
            pass
        time.sleep(BROADCAST_DELAY)
    return count

def send_document_broadcast(user_ids, file_id, caption=""):
    count = 0
    for uid in _dedup(user_ids):
        try:
            bot.send_document(uid, file_id, caption=caption, parse_mode="HTML")
            count += 1
        except Exception:
            pass
        time.sleep(BROADCAST_DELAY)
    return count

def get_broadcast_targets(category):
    conn = get_db()
    cursor = conn.cursor()
    ids = []
    if category == "all":
        cursor.execute("SELECT id FROM users WHERE banned=0")
        ids = [r["id"] for r in cursor.fetchall()]
    elif category == "verified":
        cursor.execute("SELECT id FROM users WHERE banned=0 AND verified=1")
        ids = [r["id"] for r in cursor.fetchall()]
    elif category == "inactive":
        cutoff = (utc_now() - timedelta(days=INACTIVE_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT id FROM users WHERE banned=0 AND (last_active IS NULL OR last_active < ?)", (cutoff,))
        ids = [r["id"] for r in cursor.fetchall()]
    elif category == "resellers":
        cursor.execute("SELECT id FROM users WHERE banned=0 AND is_reseller=1")
        ids = [r["id"] for r in cursor.fetchall()]
    elif category == "balance":
        cursor.execute("SELECT id FROM users WHERE banned=0 AND balance > 0")
        ids = [r["id"] for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return ids
    
    # ============ PHOTO HANDLER ============
# BUG #6 FIX: admin check BEFORE state pop, state not silently cleared for non-admin
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    action = state.get("action", "")
    if action == "change_qr":
        if user_id == ADMIN_USER_ID:
            update_setting("qr_code_file_id", message.photo[-1].file_id)
            pop_user_state(user_id)
            safe_send(message.chat.id, "✅ QR Updated!")
            log_admin_action(user_id, "Update QR Code")
        else:
            pop_user_state(user_id)
            safe_send(message.chat.id, "⛔ Sirf Admin 1 change kar sakta hai!")
        return
    if action == "manual_screenshot":
        set_user_state(user_id, {"action": "manual_amount", "screenshot_file_id": message.photo[-1].file_id})
        safe_send(message.chat.id, "✅ Screenshot received!\n\nAb amount bhejo (sirf number):\n\nExample: 500")
        return
    if action == "review_screenshot":
        product_id = state.get("product_id")
        rating = state.get("rating")
        if not product_id or not rating:
            pop_user_state(user_id)
            safe_send(message.chat.id, "❌ Session expired. Dobara try karo.")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reviews (user_id, product_id, rating, screenshot_file_id) VALUES (?,?,?,?)", (user_id, product_id, rating, message.photo[-1].file_id))
        cursor.execute("UPDATE review_reminders SET review_submitted=1 WHERE user_id=? AND product_id=?", (user_id, product_id))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        safe_send(message.chat.id, "✅ Review Submitted!")
        return
    if action == "admin_broadcast_media":
        # BUG #6 FIX: admin check FIRST, then state pop in finally
        try:
            if user_id != ADMIN_USER_ID:
                safe_send(message.chat.id, "⛔ Only Main Admin")
                return
            file_id = message.photo[-1].file_id
            caption = message.caption or ""
            safe_send(message.chat.id, "📢 Sending image broadcast to all users...")
            targets = get_broadcast_targets("all")
            count = send_photo_broadcast(targets, file_id, caption)
            log_admin_action(user_id, "Media Broadcast", f"Image | {count} users")
            safe_send(message.chat.id, f"📢 Image broadcast sent to {count} users!")
        finally:
            pop_user_state(user_id)
        return

# ============ VIDEO HANDLER ============
@bot.message_handler(content_types=['video'])
def handle_video(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    action = state.get("action", "")
    if action == "admin_broadcast_media":
        try:
            if user_id != ADMIN_USER_ID:
                safe_send(message.chat.id, "⛔ Only Main Admin")
                return
            file_id = message.video.file_id
            caption = message.caption or ""
            safe_send(message.chat.id, "📢 Sending video broadcast to all users...")
            targets = get_broadcast_targets("all")
            count = send_video_broadcast(targets, file_id, caption)
            log_admin_action(user_id, "Media Broadcast", f"Video | {count} users")
            safe_send(message.chat.id, f"📢 Video broadcast sent to {count} users!")
        finally:
            pop_user_state(user_id)
        return

# ============ VOICE HANDLER ============
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    action = state.get("action", "")
    if action == "admin_broadcast_media":
        try:
            if user_id != ADMIN_USER_ID:
                safe_send(message.chat.id, "⛔ Only Main Admin")
                return
            file_id = message.voice.file_id
            caption = message.caption or ""
            safe_send(message.chat.id, "📢 Sending voice broadcast to all users...")
            targets = get_broadcast_targets("all")
            count = send_voice_broadcast(targets, file_id, caption)
            log_admin_action(user_id, "Media Broadcast", f"Voice | {count} users")
            safe_send(message.chat.id, f"📢 Voice broadcast sent to {count} users!")
        finally:
            pop_user_state(user_id)
        return

# ============ AUDIO HANDLER ============
@bot.message_handler(content_types=['audio'])
def handle_audio(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    action = state.get("action", "")
    if action == "admin_broadcast_media":
        try:
            if user_id != ADMIN_USER_ID:
                safe_send(message.chat.id, "⛔ Only Main Admin")
                return
            file_id = message.audio.file_id
            caption = message.caption or ""
            safe_send(message.chat.id, "📢 Sending audio broadcast to all users...")
            targets = get_broadcast_targets("all")
            count = send_audio_broadcast(targets, file_id, caption)
            log_admin_action(user_id, "Media Broadcast", f"Audio | {count} users")
            safe_send(message.chat.id, f"📢 Audio broadcast sent to {count} users!")
        finally:
            pop_user_state(user_id)
        return

# ============ DOCUMENT HANDLER ============
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    action = state.get("action", "")
    if action == "restore_db":
        if user_id != ADMIN_USER_ID:
            pop_user_state(user_id)
            safe_send(message.chat.id, "⛔ Only Admin 1")
            return
        if not message.document.file_name.endswith('.db'):
            safe_send(message.chat.id, "❌ Only .db files")
            return
        # BUG #34 FIX: size check before download
        if message.document.file_size and message.document.file_size > 50 * 1024 * 1024:
            safe_send(message.chat.id, "❌ File too large (max 50MB)")
            return
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            if not downloaded.startswith(b"SQLite format 3\x00"):
                safe_send(message.chat.id, "❌ Not a valid SQLite DB")
                pop_user_state(user_id)
                return
            emergency_backup(reason="Before restore")
            with open(DB_PATH, 'wb') as f:
                f.write(downloaded)
            pop_user_state(user_id)
            init_db()
            safe_send(message.chat.id, "✅ DATA RESTORED!")
            log_admin_action(user_id, "Restore Database")
        except Exception as e:
            logger.error(f"restore error: {e}")
            safe_send(message.chat.id, "❌ Restore failed")
        return
    if action == "admin_broadcast_media":
        try:
            if user_id != ADMIN_USER_ID:
                safe_send(message.chat.id, "⛔ Only Main Admin")
                return
            file_id = message.document.file_id
            caption = message.caption or ""
            safe_send(message.chat.id, "📢 Sending document broadcast to all users...")
            targets = get_broadcast_targets("all")
            count = send_document_broadcast(targets, file_id, caption)
            log_admin_action(user_id, "Media Broadcast", f"Document | {count} users")
            safe_send(message.chat.id, f"📢 Document broadcast sent to {count} users!")
        finally:
            pop_user_state(user_id)
        return

# ============ TEXT HANDLER ============
@bot.message_handler(func=lambda m: True)
def handle_non_contact(message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    action = state.get("action", "")
    text = (message.text or "").strip()

    if action == "admin_add_balance":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Sirf Main Admin balance add kar sakta hai!")
            pop_user_state(user_id)
            return
        parts = text.split()
        if len(parts) == 2:
            try:
                uid = int(parts[0])
                amt = int(parts[1])
            except ValueError:
                safe_send(message.chat.id, "❌ Invalid numbers. Use: user_id amount")
                pop_user_state(user_id)
                return
            if amt <= 0 or amt > 1000000:
                safe_send(message.chat.id, "❌ Amount 1 - 10,00,000 ke beech hona chahiye")
                pop_user_state(user_id)
                return
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amt, uid))
            if cursor.rowcount == 0:
                cursor.execute("INSERT INTO users (id, balance) VALUES (?,?)", (uid, amt))
            conn.commit()
            cursor.close()
            conn.close()
            log_admin_action(user_id, "Add Balance", f"User {uid} +₹{amt}")
            safe_send(message.chat.id, f"💰 Balance Updated\n\n👤 {uid}\n💵 ₹{amt}")
        else:
            safe_send(message.chat.id, "❌ Format: user_id amount")
        pop_user_state(user_id)
        return

    if action == "manual_amount":
        try:
            amt = int(text)
            min_dep = get_setting("min_deposit", 500)
            if amt < min_dep or amt > 100000:
                safe_send(message.chat.id, f"❌ Amount ₹{min_dep} - ₹1,00,000 ke beech hona chahiye")
                return
            set_user_state(user_id, {"action": "manual_utr", "screenshot_file_id": state.get("screenshot_file_id"), "amount": amt})
            safe_send(message.chat.id, f"✅ Amount: ₹{amt}\n\nAb UTR number bhejo:\n\nUTR: 123456789012")
        except ValueError:
            safe_send(message.chat.id, "❌ Sirf number bhejo")
        return

    if action == "manual_utr":
        utr = text.replace("UTR:", "").strip()
        if not re.match(r'^[A-Za-z0-9]{6,30}$', utr):
            safe_send(message.chat.id, "❌ Invalid UTR. 6-30 alphanumeric characters.")
            return
        screenshot_file_id = state.get("screenshot_file_id", "")
        amount = state.get("amount", 0)
        if not screenshot_file_id or amount <= 0:
            safe_send(message.chat.id, "❌ Missing data. Dobara try karo.")
            pop_user_state(user_id)
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO manual_deposits (user_id, amount, utr, screenshot_file_id) VALUES (?,?,?,?)", (user_id, amount, utr, screenshot_file_id))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        safe_send(message.chat.id, "📤 REQUEST SUBMITTED!\n\n✅ Admin verification pending...")
        notify_admins(f"💰 New manual deposit\n👤 {user_id}\n💰 ₹{amount}\n📝 UTR: {utr}")
        return

    if action == "ticket_subject":
        if is_rate_limited(f"ticket_subject_{user_id}", 1, TICKET_COOLDOWN_SECONDS):
            safe_send(message.chat.id, "❌ Please wait.")
            pop_user_state(user_id)
            return
        if len(text) < 2 or len(text) > 200:
            safe_send(message.chat.id, "❌ Subject 2-200 chars")
            return
        set_user_state(user_id, {"action": "ticket_message", "subject": text})
        safe_send(message.chat.id, "📝 Subject saved!\n\nAb message likho:")
        return

    if action == "ticket_message":
        subject = state.get("subject", "General")
        msg_text = text
        if len(msg_text) < 2 or len(msg_text) > 2000:
            safe_send(message.chat.id, "❌ Message 2-2000 chars")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO support_tickets (user_id, subject, message) VALUES (?,?,?)", (user_id, subject, msg_text))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        safe_send(message.chat.id, f"✅ Ticket created!\n\n📝 {subject}")
        notify_admins(f"🎫 New Ticket\n👤 {user_id}\n📝 {subject}")
        return

    # BUG #22 FIX: None check for ticket_id
    if action == "admin_ticket_reply":
        ticket_id = state.get("ticket_id")
        if not ticket_id:
            pop_user_state(user_id)
            safe_send(message.chat.id, "❌ Session expired. Dobara try karo.")
            return
        reply = text
        if not reply or len(reply) > 2000:
            safe_send(message.chat.id, "❌ Invalid reply")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, subject FROM support_tickets WHERE id=?", (ticket_id,))
        t = cursor.fetchone()
        cursor.execute("UPDATE support_tickets SET admin_reply=?, status='closed' WHERE id=?", (reply, ticket_id))
        conn.commit()
        cursor.close()
        conn.close()
        if t:
            safe_send(t["user_id"], f"💬 <b>Ticket Reply</b>\n\n📝 {esc(t['subject'])}\n\n{esc(reply)}")
        pop_user_state(user_id)
        log_admin_action(user_id, "Ticket Reply", f"Ticket #{ticket_id}")
        safe_send(message.chat.id, "✅ Reply sent!")
        return

    if action == "admin_reject_reason":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Access denied")
            pop_user_state(user_id)
            return
        deposit_id = state.get("deposit_id")
        reason = text
        if not reason or len(reason) > 500:
            safe_send(message.chat.id, "❌ Invalid reason")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM manual_deposits WHERE id=?", (deposit_id,))
        d = cursor.fetchone()
        cursor.execute("UPDATE manual_deposits SET status='rejected', admin_reason=? WHERE id=? AND status='pending'", (reason, deposit_id))
        conn.commit()
        if cursor.rowcount == 1 and d:
            safe_send(d["user_id"], f"❌ PAYMENT REJECTED\n\n📝 Reason: {esc(reason)}\n\nSupport se contact karo.")
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        log_admin_action(user_id, "Reject Deposit", f"Reason: {reason}")
        safe_send(message.chat.id, "✅ Rejected!")
        return

    if action == "add_admin_id":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Only Main Admin can add admins")
            pop_user_state(user_id)
            return
        try:
            new_admin_id = int(text)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
            conn.commit()
            cursor.close()
            conn.close()
            invalidate_admin_cache()
            log_admin_action(user_id, "Add Admin", f"ID: {new_admin_id}")
            safe_send(message.chat.id, "✅ ADMIN ADDED!")
        except Exception as e:
            logger.error(f"add_admin error: {e}")
            safe_send(message.chat.id, "❌ Invalid ID")
        pop_user_state(user_id)
        return

    if action == "add_support_contact":
        parts = text.split("|")
        if len(parts) == 2:
            name = parts[0].strip()[:50]
            try:
                uid = int(parts[1].strip())
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO support_contacts (name, user_id) VALUES (?,?)", (name, uid))
                conn.commit()
                cursor.close()
                conn.close()
                safe_send(message.chat.id, f"✅ Contact added: {esc(name)}")
            except Exception as e:
                logger.error(f"add_contact error: {e}")
                safe_send(message.chat.id, "❌ Invalid ID")
        else:
            safe_send(message.chat.id, "❌ Format: Name | UserID")
        pop_user_state(user_id)
        return

    if action == "edit_support_contact_default_1":
        name = text[:50]
        update_setting("support_name_1", name)
        pop_user_state(user_id)
        log_admin_action(user_id, "Edit Support Name", name)
        safe_send(message.chat.id, f"✅ Contact updated: {esc(name)}")
        return

    if action == "edit_support_url":
        url = text[:200]
        if not url.startswith("https://"):
            safe_send(message.chat.id, "❌ URL https:// se start hona chahiye")
            pop_user_state(user_id)
            return
        update_setting("support_url", url)
        pop_user_state(user_id)
        log_admin_action(user_id, "Edit Support URL", url)
        safe_send(message.chat.id, f"✅ URL updated: {esc(url)}")
        return

    if action == "edit_support_contact":
        contact_id = state.get("contact_id")
        parts = text.split("|")
        if len(parts) == 2:
            name = parts[0].strip()[:50]
            try:
                uid = int(parts[1].strip())
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE support_contacts SET name=?, user_id=? WHERE id=?", (name, uid, contact_id))
                conn.commit()
                cursor.close()
                conn.close()
                safe_send(message.chat.id, f"✅ Contact updated: {esc(name)}")
            except Exception as e:
                logger.error(f"edit_contact error: {e}")
                safe_send(message.chat.id, "❌ Invalid ID")
        else:
            safe_send(message.chat.id, "❌ Format: Name | UserID")
        pop_user_state(user_id)
        return

    if action == "change_reseller_fee":
        try:
            new_fee = int(text)
            if new_fee < 0 or new_fee > 100000:
                raise ValueError
            update_setting("reseller_fee", new_fee)
            log_admin_action(user_id, "Change Reseller Fee", f"₹{new_fee}")
            safe_send(message.chat.id, f"✅ Reseller Fee updated to ₹{new_fee}!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid amount")
        pop_user_state(user_id)
        return

    if action == "change_min_balance":
        try:
            new_min = int(text)
            if new_min < 0 or new_min > 1000000:
                raise ValueError
            update_setting("reseller_min_balance", new_min)
            log_admin_action(user_id, "Change Min Balance", f"₹{new_min}")
            safe_send(message.chat.id, f"✅ Min Balance updated to ₹{new_min}!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid amount")
        pop_user_state(user_id)
        return

    if action == "change_min_deposit":
        try:
            new_min = int(text)
            if new_min < 1 or new_min > 100000:
                raise ValueError
            update_setting("min_deposit", new_min)
            log_admin_action(user_id, "Change Min Deposit", f"₹{new_min}")
            safe_send(message.chat.id, f"✅ Min Deposit updated to ₹{new_min}!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid amount")
        pop_user_state(user_id)
        return

    if action == "change_tutorial_video":
        update_setting("tutorial_video", text[:500])
        pop_user_state(user_id)
        log_admin_action(user_id, "Change Tutorial Video")
        safe_send(message.chat.id, "✅ Tutorial video link updated!")
        return

    if action == "add_download_link":
        product_id = state.get("product_id")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET download_link=? WHERE id=?", (text[:500], product_id))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        log_admin_action(user_id, "Add Download Link", f"Product {product_id}")
        safe_send(message.chat.id, "✅ Download files link saved!")
        return

    if action == "set_api_pid":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Only Main Admin can set API PID")
            pop_user_state(user_id)
            return
        product_id = state.get("product_id")
        api_pid = text[:50]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET api_pid=? WHERE id=?", (api_pid, product_id))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        log_admin_action(user_id, "Set API PID", f"Product {product_id} → {api_pid}")
        safe_send(message.chat.id, f"✅ API PID saved: {esc(api_pid)}")
        return

    if action == "edit_reseller_price":
        try:
            price = int(text)
            if price < 0 or price > 1000000:
                raise ValueError
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE plans SET reseller_price=? WHERE id=?", (price, state.get("plan_id")))
            conn.commit()
            cursor.close()
            conn.close()
            safe_send(message.chat.id, "✅ Updated!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid price")
        pop_user_state(user_id)
        return

    if action == "edit_plan_price":
        try:
            new_price = int(text)
            if new_price < 0 or new_price > 1000000:
                raise ValueError
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE plans SET price=? WHERE id=?", (new_price, state.get("plan_id")))
            conn.commit()
            cursor.close()
            conn.close()
            log_admin_action(user_id, "Edit Plan Price", f"Plan {state.get('plan_id')} → ₹{new_price}")
            safe_send(message.chat.id, f"✅ Price updated to ₹{new_price}!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid price")
        pop_user_state(user_id)
        return

    if action == "edit_plan_duration":
        new_duration = text[:50]
        if not new_duration:
            safe_send(message.chat.id, "❌ Invalid duration")
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE plans SET duration=? WHERE id=?", (new_duration, state.get("plan_id")))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        safe_send(message.chat.id, f"✅ Duration updated to {esc(new_duration)}!")
        return

    if action == "edit_name":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET name=? WHERE id=?", (text[:100], state.get("product_id")))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        log_admin_action(user_id, "Edit Product Name", text[:100])
        safe_send(message.chat.id, "✅ Renamed!")
        return

    # BUG #13 FIX: parse duration with spaces (duration + price + optional reseller_price)
    if action == "add_plan_menu":
        added = 0
        conn = get_db()
        cursor = conn.cursor()
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # last token = price, second-last optional = reseller_price, rest = duration
            parts = line.rsplit(None, 2) if len(line.split()) >= 3 else line.rsplit(None, 1)
            duration = None
            price = None
            reseller_price = None
            try:
                if len(parts) == 3:
                    # duration may have spaces: "1 Day 70 50"
                    try:
                        reseller_price = int(parts[2])
                        price = int(parts[1])
                        duration = parts[0].strip()[:50]
                    except ValueError:
                        # parts[2] not int — treat as duration+price only
                        reseller_price = None
                        price = int(parts[-1])
                        duration = " ".join(parts[:-1]).strip()[:50]
                elif len(parts) == 2:
                    price = int(parts[1])
                    duration = parts[0].strip()[:50]
                else:
                    continue
                if not duration or price < 0 or price > 1000000:
                    continue
                if reseller_price is not None and (reseller_price < 0 or reseller_price > 1000000):
                    reseller_price = None
                cursor.execute("INSERT INTO plans (product_id, duration, price, reseller_price) VALUES (?,?,?,?)", (state.get("product_id"), duration, price, reseller_price))
                added += 1
            except Exception:
                continue
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        log_admin_action(user_id, "Add Plans", f"{added} plans to product {state.get('product_id')}")
        safe_send(message.chat.id, f"✅ {added} plans added!")
        return

    if action == "add_video":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET demo_video=? WHERE id=?", (text[:500], state.get("product_id")))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        safe_send(message.chat.id, "✅ Video saved!")
        return

    if action == "add_features":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET features=? WHERE id=?", (text[:2000], state.get("product_id")))
        conn.commit()
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        safe_send(message.chat.id, "✅ Features added!")
        return

    if action == "add_product":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Only Main Admin can add products")
            pop_user_state(user_id)
            return
        category = state.get("category", "nonroot")
        conn = get_db()
        cursor = conn.cursor()
        added = 0
        for name in text.split('\n'):
            name = name.strip()[:100]
            if name:
                cursor.execute("INSERT INTO products (name, category) VALUES (?,?)", (name, category))
                added += 1
        conn.commit()
        cursor.execute("SELECT user_id FROM category_notifications WHERE category=? AND notified=0", (category,))
        notified_users = cursor.fetchall()
        cursor.execute("UPDATE category_notifications SET notified=1 WHERE category=? AND notified=0", (category,))
        conn.commit()
        cat_emoji = get_category_emoji(category)
        cat_name = get_category_name(category)
        for user_row in notified_users:
            notif_text = f"""🔥🔥🔥 <b>HOT ALERT!</b> 🔥🔥🔥

{cat_emoji} <b>{cat_name} PANEL</b>

⚡ New products available!

🚀 Jaldi Purchase Karo!"""
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("🛒 Shop Now", callback_data="shop_now", style="danger"))
            try:
                safe_send(user_row["user_id"], notif_text, markup)
            except Exception:
                pass
            time.sleep(BROADCAST_DELAY)
        cursor.close()
        conn.close()
        pop_user_state(user_id)
        log_admin_action(user_id, "Add Product", f"{added} {category} products")
        safe_send(message.chat.id, f"✅ {added} {category.upper()} products added!\n\n🔗 Ab har product ka API PID set karo.")
        return

    if action == "faq_add":
        parts = text.split("|", 1)
        if len(parts) == 2:
            q = parts[0].strip()[:200]
            a = parts[1].strip()[:2000]
            if not q or not a:
                safe_send(message.chat.id, "❌ Question and answer required")
                pop_user_state(user_id)
                return
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(display_order), 0) as m FROM faq")
            next_order = cursor.fetchone()["m"] + 1
            cursor.execute("INSERT INTO faq (question, answer, display_order) VALUES (?,?,?)", (q, a, next_order))
            conn.commit()
            cursor.close()
            conn.close()
            log_admin_action(user_id, "Add FAQ", q)
            safe_send(message.chat.id, "✅ FAQ added!")
        else:
            safe_send(message.chat.id, "❌ Format: Question | Answer")
        pop_user_state(user_id)
        return

    if action == "admin_selling_proof":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Only Main Admin can change selling proof link")
            pop_user_state(user_id)
            return
        update_setting("selling_proof_link", text[:500])
        pop_user_state(user_id)
        log_admin_action(user_id, "Change Selling Proof Link")
        safe_send(message.chat.id, "✅ Link updated!")
        return

    if action == "change_manual_upi":
        if user_id != ADMIN_USER_ID:
            safe_send(message.chat.id, "⛔ Only Main Admin can change Manual UPI")
            pop_user_state(user_id)
            return
        upi = text.strip()
        if not re.match(r'^[\w.\-]+@[\w\-]+$', upi):
            safe_send(message.chat.id, "❌ Invalid UPI format. Example: yourname@paytm")
            pop_user_state(user_id)
            return
        update_setting("manual_upi", upi)
        pop_user_state(user_id)
        log_admin_action(user_id, "Change Manual UPI", upi)
        safe_send(message.chat.id, f"✅ Manual UPI updated: {esc(upi)}")
        return

    if action == "admin_ban":
        try:
            uid = int(text)
            ban_user(uid)
            log_admin_action(user_id, "Ban User", f"ID: {uid}")
            safe_send(message.chat.id, f"🚫 User {uid} banned!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid ID")
        pop_user_state(user_id)
        return

    if action == "admin_unban":
        try:
            uid = int(text)
            unban_user(uid)
            log_admin_action(user_id, "Unban User", f"ID: {uid}")
            safe_send(message.chat.id, f"✅ User {uid} unbanned!")
        except Exception:
            safe_send(message.chat.id, "❌ Invalid ID")
        pop_user_state(user_id)
        return

    if action.startswith("admin_broadcast_"):
        broadcast_text = text[:4000]
        if not broadcast_text:
            pop_user_state(user_id)
            return
        category = action.replace("admin_broadcast_", "")
        targets = get_broadcast_targets(category)
        safe_send(message.chat.id, f"📢 Sending to {len(targets)} users...")
        count = send_broadcast_to_users(targets, broadcast_text)
        log_admin_action(user_id, "Broadcast", f"{category} — {count} users")
        safe_send(message.chat.id, f"📢 Broadcast sent to {count} users!")
        pop_user_state(user_id)
        return

    if not is_verified(user_id):
        send_verification_request(message.chat.id)

# ============ CALLBACK HANDLER ============
# BUG #4 FIX: check_maintenance allowed even in maintenance
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    update_last_active(user_id)

    data = call.data

    # BUG #4 FIX: allow check_maintenance to pass through always
    if data == "check_maintenance":
        if is_bot_maintenance() and user_id not in get_admin_ids():
            bot.answer_callback_query(call.id, "🔧 Abhi bhi maintenance mein hai!", show_alert=True)
            return
        if not is_verified(user_id):
            bot.answer_callback_query(call.id, "🔐 Pehle verify karo. /start bhejo.", show_alert=True)
            return
        safe_navigate(call, get_welcome_text(user_id), get_main_menu(user_id))
        return

    if is_bot_maintenance() and user_id not in get_admin_ids():
        bot.answer_callback_query(call.id, "🔧 Bot maintenance mein hai!", show_alert=True)
        return

    if not is_verified(user_id):
        bot.answer_callback_query(call.id, "🔐 Verify first", show_alert=True)
        return

    if data == "shop_now":
        show_products(call)
    elif data == "profile":
        show_profile(call, user_id)
    elif data == "add_balance":
        show_add_balance_menu(call)
    elif data == "auto_pay":
        set_user_state(user_id, {"keypad_amount": ""})
        show_keypad(call, user_id, "")
    elif data == "manual_deposit":
        show_manual_deposit(call)
    elif data == "manual_proof":
        set_user_state(user_id, {"action": "manual_screenshot"})
        safe_navigate(call, "📸 PAYMENT PROOF\n\n━━━━━━━━━━━━━━━\n\nAb payment ka screenshot bhejo.\n\n━━━━━━━━━━━━━━━\n\n1. UPI app se payment karo\n2. Screenshot lo\n3. Screenshot yahan bhejo\n\n━━━━━━━━━━━━━━━", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Cancel", callback_data="manual_deposit", style="danger")))
    elif data.startswith("pad_"):
        handle_keypad(call, data, user_id)
    elif data == "history":
        show_history(call, user_id, 0)
    elif data.startswith("history_page_"):
        try:
            show_history(call, user_id, int(data.split("_")[2]))
        except Exception:
            pass
    elif data == "tutorial":
        show_tutorial_menu(call)
    elif data == "reseller_info":
        show_reseller_info(call)
    elif data == "join_reseller":
        join_reseller(call)
    elif data == "reseller_panel":
        safe_navigate(call, "🤝 Reseller Panel", InlineKeyboardMarkup().add(InlineKeyboardButton("🔑 Shop Key", callback_data="shop_now", style="danger"), InlineKeyboardButton("◀️ Back", callback_data="back_main", style="danger")))
    elif data == "selling_proof":
        show_selling_proof(call)
    elif data == "support":
        show_support_menu(call)
    elif data == "faq_menu":
        show_faq_menu(call)
    elif data.startswith("faq_show_"):
        try:
            show_faq_answer(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data == "lucky_spin":
        show_lucky_spin(call)
    elif data == "spin_now":
        do_spin(call)
    elif data == "referral":
        show_referral(call, user_id)
    elif data == "back_main":
        safe_navigate(call, get_welcome_text(user_id), get_main_menu(user_id))
    elif data.startswith("cancel_qr_"):
        order_id = data.replace("cancel_qr_", "")
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE pending_payments SET status='cancelled' WHERE order_id=? AND status='pending'", (order_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"cancel_qr error: {e}")
        bot.answer_callback_query(call.id, "✅ Payment cancelled", show_alert=True)
        safe_navigate(call, get_welcome_text(user_id), get_main_menu(user_id))
    elif data == "category_root":
        show_products_by_category(call, "root")
    elif data == "category_nonroot":
        show_products_by_category(call, "nonroot")
    elif data == "category_iphone":
        show_products_by_category(call, "iphone")
    elif data.startswith("notify_category_"):
        parts = data.split("_", 2)
        if len(parts) >= 3:
            notify_category(call, parts[2])
    elif data.startswith("product_"):
        try:
            show_product_plans(call, int(data.split("_")[1]), is_reseller(user_id))
        except Exception:
            pass
    elif data.startswith("demo_"):
        try:
            show_demo_video(call, int(data.split("_")[1]))
        except Exception:
            pass
    elif data.startswith("buy_"):
        parts = data.split("_")
        if len(parts) == 3:
            if is_bot_maintenance() and user_id not in get_admin_ids():
                bot.answer_callback_query(call.id, "🔧 Bot maintenance mein hai!", show_alert=True)
                safe_navigate(call, "🔧 <b>BOT UNDER MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\n⚠️ Bot abhi maintenance mein hai.\n\nKoi bhi purchase abhi nahi ho sakti.\n\n━━━━━━━━━━━━━━━", InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary")))
                return
            try:
                show_order_confirmation(call, int(parts[1]), int(parts[2]))
            except Exception:
                pass
    elif data.startswith("confirm_"):
        parts = data.split("_")
        if len(parts) == 3:
            if is_bot_maintenance() and user_id not in get_admin_ids():
                bot.answer_callback_query(call.id, "🔧 Bot maintenance mein hai!", show_alert=True)
                safe_navigate(call, "🔧 <b>BOT UNDER MAINTENANCE</b>\n\n━━━━━━━━━━━━━━━\n\n⚠️ Bot abhi maintenance mein hai.\n\nKoi bhi purchase abhi nahi ho sakti.\n\n━━━━━━━━━━━━━━━", InlineKeyboardMarkup().add(InlineKeyboardButton("🔄 Check Again", callback_data="check_maintenance", style="primary")))
                return
            if is_rate_limited(f"purchase_{user_id}", 5, 60):
                bot.answer_callback_query(call.id, "❌ Too many attempts", show_alert=True)
                return
            try:
                process_purchase(call, int(parts[1]), int(parts[2]))
            except Exception as e:
                logger.error(f"process_purchase error: {e}")
    elif data.startswith("review_"):
        parts = data.split("_")
        if len(parts) == 3:
            try:
                request_review(call, int(parts[1]), int(parts[2]))
            except Exception:
                pass
    elif data == "skip_review":
        pop_user_state(user_id)
        safe_navigate(call, get_welcome_text(user_id), get_main_menu(user_id))
    elif data == "admin_panel":
        if user_id in get_admin_ids():
            safe_navigate(call, get_admin_panel_header(), get_admin_panel(user_id))
        else:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
    elif data == "admin_dashboard":
        show_admin_dashboard(call)
    elif data == "admin_analytics":
        safe_navigate(call, "📊 <b>ANALYTICS</b>\n━━━━━━━━━━━━━━━\n\nDetailed stats and reports\nfor your business.\n\n━━━━━━━━━━━━━━━", get_admin_analytics_menu())
    elif data == "admin_today_stats":
        show_admin_today_stats(call)
    elif data == "admin_weekly_stats":
        show_admin_weekly_stats(call)
    elif data == "admin_top_products":
        show_admin_top_products(call)
    elif data == "admin_user_growth":
        show_admin_user_growth(call)
    elif data == "admin_revenue_report":
        show_admin_revenue_report(call)
    elif data == "admin_products":
        text = """📦 <b>PRODUCTS MANAGEMENT</b>
━━━━━━━━━━━━━━━

Manage your products, plans,
prices and maintenance.

━━━━━━━━━━━━━━━"""
        safe_navigate(call, text, get_admin_products_menu(user_id))
    elif data == "admin_payments":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM manual_deposits WHERE status='pending'")
        pending = cursor.fetchone()["c"]
        cursor.close()
        conn.close()
        min_dep = get_setting("min_deposit", 500)
        fee = get_setting("reseller_fee", 399)
        text = f"""💰 <b>PAYMENTS & BALANCE</b>
━━━━━━━━━━━━━━━

Manage deposits, QR, fees
and balance limits.

⏳ Pending Deposits: {pending}
💳 Min Deposit: ₹{min_dep}
💸 Reseller Fee: ₹{fee}

━━━━━━━━━━━━━━━"""
        safe_navigate(call, text, get_admin_payments_menu(user_id))
    elif data == "admin_users":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM users")
        total = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) as c FROM users WHERE banned=1")
        banned = cursor.fetchone()["c"]
        cursor.execute("SELECT COUNT(*) as c FROM admins")
        admins = cursor.fetchone()["c"]
        cursor.close()
        conn.close()
        text = f"""👥 <b>USER MANAGEMENT</b>
━━━━━━━━━━━━━━━

Manage users, balances,
bans and admins.

👥 Total: {total}
🚫 Banned: {banned}
👑 Admins: {admins}

━━━━━━━━━━━━━━━"""
        safe_navigate(call, text, get_admin_users_menu(user_id))
    elif data == "admin_support":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM support_tickets WHERE status='open'")
        open_t = cursor.fetchone()["c"]
        cursor.close()
        conn.close()
        text = f"""💬 <b>SUPPORT CENTER</b>
━━━━━━━━━━━━━━━

Manage tickets, contacts,
FAQ and selling proof.

🎫 Open Tickets: {open_t}

━━━━━━━━━━━━━━━"""
        safe_navigate(call, text, get_admin_support_menu(user_id))
    elif data == "admin_settings":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        status = get_setting("bot_maintenance", "off")
        status_text = "🔴 ON" if status == "on" else "🟢 OFF"
        text = f"""⚙️ <b>SYSTEM SETTINGS</b>
━━━━━━━━━━━━━━━

Bot maintenance, backup,
restore and logs.

🔧 Bot Status: {status_text}

━━━━━━━━━━━━━━━"""
        safe_navigate(call, text, get_admin_settings_menu(user_id))
    elif data == "admin_broadcast":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as c FROM users")
        total = cursor.fetchone()["c"]
        cursor.close()
        conn.close()
        text = f"""📢 <b>BROADCAST</b>
━━━━━━━━━━━━━━━

Send messages to users.

👥 Total Users: {total}

━━━━━━━━━━━━━━━"""
        safe_navigate(call, text, get_admin_broadcast_menu())
    elif data == "admin_bot_maintenance":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        show_bot_maintenance_menu(call)
    elif data == "bot_maintenance_on":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        update_setting("bot_maintenance", "on")
        log_admin_action(user_id, "Maintenance ON")
        bot.answer_callback_query(call.id, "✅ Bot Maintenance ON!", show_alert=True)
        threading.Thread(target=broadcast_maintenance_on, daemon=True).start()
        show_bot_maintenance_menu(call)
    elif data == "bot_maintenance_off":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        update_setting("bot_maintenance", "off")
        log_admin_action(user_id, "Maintenance OFF")
        bot.answer_callback_query(call.id, "✅ Bot Maintenance OFF!", show_alert=True)
        threading.Thread(target=broadcast_maintenance_off, daemon=True).start()
        show_bot_maintenance_menu(call)
    elif data == "manage_admins":
        if user_id == ADMIN_USER_ID:
            show_manage_admins(call)
        else:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
    elif data == "add_admin":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin can add admins", show_alert=True)
            return
        set_user_state(user_id, {"action": "add_admin_id"})
        safe_navigate(call, "➕ ADD ADMIN\n\nSend new admin ka User ID:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Cancel", callback_data="manage_admins", style="danger")))
    elif data.startswith("remove_specific_admin_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin can remove admins", show_alert=True)
            return
        try:
            admin_id = int(data.split("_")[3])
            if admin_id == ADMIN_USER_ID:
                bot.answer_callback_query(call.id, "❌ Main admin remove nahi ho sakta", show_alert=True)
            else:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM admins WHERE user_id=?", (admin_id,))
                conn.commit()
                cursor.close()
                conn.close()
                invalidate_admin_cache()
                log_admin_action(user_id, "Remove Admin", f"ID: {admin_id}")
                bot.answer_callback_query(call.id, f"✅ Admin {admin_id} removed!", show_alert=True)
                show_manage_admins(call)
        except Exception:
            pass
    elif data == "admin_manage_products":
        show_manage_products(call)
    elif data == "manage_category_root":
        show_manage_products_by_category(call, "root")
    elif data == "manage_category_nonroot":
        show_manage_products_by_category(call, "nonroot")
    elif data == "manage_category_iphone":
        show_manage_products_by_category(call, "iphone")
    elif data == "admin_maintenance_products":
        show_maintenance_products(call)
    elif data.startswith("remove_maint_"):
        try:
            product_id = int(data.split("_")[2])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE products SET status='active' WHERE id=?", (product_id,))
            conn.commit()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "✅ Product Active!", show_alert=True)
            show_maintenance_products(call)
        except Exception:
            pass
    elif data == "admin_deposit_requests":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        show_deposit_requests(call)
    elif data == "admin_tickets":
        show_admin_tickets(call)
    elif data.startswith("view_ticket_"):
        try:
            show_ticket_detail(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("reply_ticket_"):
        set_user_state(user_id, {"action": "admin_ticket_reply", "ticket_id": int(data.split("_")[2])})
        safe_navigate(call, "💬 Reply likho:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_tickets", style="danger")))
    elif data.startswith("close_ticket_"):
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE support_tickets SET status='closed' WHERE id=?", (int(data.split("_")[2]),))
            conn.commit()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "✅ Closed!", show_alert=True)
            show_admin_tickets(call)
        except Exception:
            pass
    elif data == "admin_change_qr":
        if user_id == ADMIN_USER_ID:
            set_user_state(user_id, {"action": "change_qr"})
            safe_navigate(call, "📱 Send new QR:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_payments", style="danger")))
        else:
            bot.answer_callback_query(call.id, "⛔ Sirf Admin 1 change kar sakta hai!", show_alert=True)
    elif data == "admin_change_manual_upi":
        if user_id == ADMIN_USER_ID:
            set_user_state(user_id, {"action": "change_manual_upi"})
            safe_navigate(call, "🔗 Send new Manual UPI ID:\n\nExample: yourname@paytm", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_payments", style="danger")))
        else:
            bot.answer_callback_query(call.id, "⛔ Sirf Admin 1 change kar sakta hai!", show_alert=True)
    elif data == "admin_selling_proof":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "admin_selling_proof"})
        safe_navigate(call, "📸 Send channel link:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_support", style="danger")))
    elif data == "admin_tutorial_video":
        show_tutorial_video_menu(call)
    elif data == "change_tutorial_video":
        set_user_state(user_id, {"action": "change_tutorial_video"})
        safe_navigate(call, "🎬 Send new video link:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_tutorial_video", style="danger")))
    elif data == "admin_reseller_prices":
        show_reseller_price_products(call)
    elif data == "reseller_category_root":
        show_reseller_price_products_by_category(call, "root")
    elif data == "reseller_category_nonroot":
        show_reseller_price_products_by_category(call, "nonroot")
    elif data == "reseller_category_iphone":
        show_reseller_price_products_by_category(call, "iphone")
    elif data.startswith("reseller_price_product_"):
        try:
            show_reseller_price_plans(call, int(data.split("_")[3]))
        except Exception:
            pass
    elif data.startswith("edit_reseller_price_"):
        set_user_state(user_id, {"action": "edit_reseller_price", "plan_id": int(data.split("_")[3])})
        safe_navigate(call, "💰 Send price:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_reseller_prices", style="danger")))
    elif data == "admin_reseller_fee":
        show_reseller_fee_menu(call)
    elif data == "change_reseller_fee":
        set_user_state(user_id, {"action": "change_reseller_fee"})
        safe_navigate(call, "💰 Send new fee:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_reseller_fee", style="danger")))
    elif data == "admin_min_balance":
        show_min_balance_menu(call)
    elif data == "change_min_balance":
        set_user_state(user_id, {"action": "change_min_balance"})
        safe_navigate(call, "💳 Send new minimum balance:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_min_balance", style="danger")))
    elif data == "admin_min_deposit":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        show_min_deposit_menu(call)
    elif data == "change_min_deposit":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "change_min_deposit"})
        safe_navigate(call, "💰 Send new minimum deposit:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_min_deposit", style="danger")))
    elif data == "admin_support_contacts":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        show_support_contacts_menu(call)
    elif data == "add_support_contact":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "add_support_contact"})
        safe_navigate(call, "➕ ADD CONTACT\n\nSend format:\n\nName | UserID", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_support_contacts", style="danger")))
    elif data == "edit_support_contact_default_1":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "edit_support_contact_default_1"})
        safe_navigate(call, "✏️ EDIT NAME\n\nSend new name:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_support_contacts", style="danger")))
    elif data == "edit_support_url":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "edit_support_url"})
        safe_navigate(call, "✏️ EDIT URL\n\nSend new URL (https://...):", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_support_contacts", style="danger")))
    elif data.startswith("edit_support_contact_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        try:
            contact_id = int(data.split("_")[3])
            set_user_state(user_id, {"action": "edit_support_contact", "contact_id": contact_id})
            safe_navigate(call, "✏️ EDIT CONTACT\n\nSend format:\n\nName | UserID", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_support_contacts", style="danger")))
        except Exception:
            pass
    elif data.startswith("remove_support_contact_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        try:
            contact_id = int(data.split("_")[3])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM support_contacts WHERE id=?", (contact_id,))
            conn.commit()
            cursor.close()
            conn.close()
            bot.answer_callback_query(call.id, "✅ Removed!", show_alert=True)
            show_support_contacts_menu(call)
        except Exception:
            pass
    elif data == "admin_reviews":
        show_reviews(call)
    elif data == "admin_backup":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        backup_database(call)
    elif data == "admin_restore":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        prompt_restore(call)
    elif data == "admin_csv_menu":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        safe_navigate(call, "📁 <b>CSV EXPORT</b>\n━━━━━━━━━━━━━━━\n\nKya export karna hai?\n\n━━━━━━━━━━━━━━━", get_admin_csv_menu())
    elif data == "csv_export_users":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        csv_export(call, "users")
    elif data == "csv_export_transactions":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        csv_export(call, "transactions")
    elif data == "csv_export_deposits":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        csv_export(call, "deposits")
    elif data == "csv_export_orders":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        csv_export(call, "orders")
    elif data == "admin_logs_view":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        show_admin_logs(call)
    elif data == "admin_faq_menu":
        safe_navigate(call, "❓ <b>FAQ MANAGER</b>\n━━━━━━━━━━━━━━━\n\nManage Frequently Asked Questions.\n\n━━━━━━━━━━━━━━━", get_admin_faq_menu())
    elif data == "faq_view_all":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM faq ORDER BY display_order ASC, id ASC LIMIT 20")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        text = "📋 <b>ALL FAQ (first 20)</b>\n━━━━━━━━━━━━━━━\n\n"
        for f in rows:
            entry = f"❓ <b>{esc(f['question'])}</b>\n💬 {esc(f['answer'])}\n\n"
            if len(text) + len(entry) > 3800:
                break
            text += entry
        text += "━━━━━━━━━━━━━━━"
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_faq_menu", style="danger"))
        safe_navigate(call, text, markup)
    elif data == "faq_add":
        set_user_state(user_id, {"action": "faq_add"})
        safe_navigate(call, "➕ ADD FAQ\n\nSend format:\n\nQuestion | Answer", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_faq_menu", style="danger")))
    elif data == "faq_remove_menu":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, question FROM faq ORDER BY id ASC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if not rows:
            safe_navigate(call, "❌ No FAQ to remove.", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_faq_menu", style="danger")))
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for f in rows:
            markup.add(InlineKeyboardButton(f"🗑️ {f['question'][:40]}", callback_data=f"faq_delete_{f['id']}", style="danger"))
        markup.add(InlineKeyboardButton("◀️ Back", callback_data="admin_faq_menu", style="danger"))
        safe_navigate(call, "➖ REMOVE FAQ\n\nSelect to delete:", markup)
    elif data.startswith("faq_delete_"):
        try:
            fid = int(data.split("_")[2])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM faq WHERE id=?", (fid,))
            conn.commit()
            cursor.close()
            conn.close()
            log_admin_action(user_id, "Delete FAQ", f"ID: {fid}")
            bot.answer_callback_query(call.id, "✅ Deleted!", show_alert=True)
            safe_navigate(call, "➖ REMOVE FAQ\n\nDeleted. Select another or go back.", get_admin_faq_menu())
        except Exception:
            pass
    elif data == "admin_add_product":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        show_add_product_category(call)
    elif data == "add_product_root":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "add_product", "category": "root"})
        safe_navigate(call, "📝 Send ROOT product name(s):", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
    elif data == "add_product_nonroot":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "add_product", "category": "nonroot"})
        safe_navigate(call, "📝 Send NON-ROOT product name(s):", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
    elif data == "add_product_iphone":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "add_product", "category": "iphone"})
        safe_navigate(call, "📝 Send IPHONE product name(s):", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
    elif data == "admin_add_balance":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "admin_add_balance"})
        safe_navigate(call, "💰 Send: user_id amount", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_users", style="danger")))
    elif data == "admin_ban_user":
        set_user_state(user_id, {"action": "admin_ban"})
        safe_navigate(call, "🚫 Send user ID:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_users", style="danger")))
    elif data == "admin_unban_user":
        set_user_state(user_id, {"action": "admin_unban"})
        safe_navigate(call, "✅ Send user ID:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_users", style="danger")))
    elif data == "admin_broadcast_all":
        set_user_state(user_id, {"action": "admin_broadcast_all"})
        safe_navigate(call, "📢 Send broadcast message for ALL users:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_broadcast", style="danger")))
    elif data == "admin_broadcast_verified":
        set_user_state(user_id, {"action": "admin_broadcast_verified"})
        safe_navigate(call, "📢 Send broadcast message for VERIFIED users:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_broadcast", style="danger")))
    elif data == "admin_broadcast_inactive":
        set_user_state(user_id, {"action": "admin_broadcast_inactive"})
        safe_navigate(call, "📢 Send broadcast message for INACTIVE users:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_broadcast", style="danger")))
    elif data == "admin_broadcast_resellers":
        set_user_state(user_id, {"action": "admin_broadcast_resellers"})
        safe_navigate(call, "📢 Send broadcast message for RESELLERS:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_broadcast", style="danger")))
    elif data == "admin_broadcast_balance":
        set_user_state(user_id, {"action": "admin_broadcast_balance"})
        safe_navigate(call, "📢 Send broadcast message for users with BALANCE:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_broadcast", style="danger")))
    elif data == "admin_broadcast_media":
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        set_user_state(user_id, {"action": "admin_broadcast_media"})
        safe_navigate(
            call,
            "📸 <b>MEDIA BROADCAST</b>\n\n"
            "Ab koi bhi media bhejo:\n\n"
            "🖼 Image\n"
            "🎬 Video\n"
            "🎤 Voice\n"
            "🎵 Audio\n"
            "📄 Document\n\n"
            "Caption ke saath ya bina caption.\n\n"
            "Bot sab users ko broadcast karega.",
            InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Cancel", callback_data="admin_broadcast", style="danger"))
        )
    elif data.startswith("manage_product_"):
        try:
            show_product_management_menu(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("manage_plans_"):
        try:
            show_plans_management(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("edit_plan_"):
        try:
            show_plan_edit_menu(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("edit_plan_price_"):
        set_user_state(user_id, {"action": "edit_plan_price", "plan_id": int(data.split("_")[3])})
        safe_navigate(call, "💰 Send new price:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
    elif data.startswith("edit_plan_duration_"):
        set_user_state(user_id, {"action": "edit_plan_duration", "plan_id": int(data.split("_")[3])})
        safe_navigate(call, "⏰ Send duration (e.g. 1 Hour, 7 Days):", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_products", style="danger")))
    elif data.startswith("del_plan_"):
        try:
            delete_plan(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("edit_name_"):
        set_user_state(user_id, {"action": "edit_name", "product_id": int(data.split("_")[2])})
        safe_navigate(call, "📝 Send name:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{data.split('_')[2]}", style="danger")))
    elif data.startswith("add_plan_menu_"):
        set_user_state(user_id, {"action": "add_plan_menu", "product_id": int(data.split("_")[3])})
        safe_navigate(call, "📅 Send plans:\n\nFormat: duration price\n\nExample:\n1 Hour 10\n3 Hours 20\n1 Day 70\n7 Days 261", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{data.split('_')[3]}", style="danger")))
    elif data.startswith("set_api_pid_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Only Main Admin", show_alert=True)
            return
        try:
            product_id = int(data.split("_")[3])
            set_user_state(user_id, {"action": "set_api_pid", "product_id": product_id})
            safe_navigate(call, "🔗 Send API PID (from website):", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{product_id}", style="danger")))
        except Exception:
            pass
    elif data.startswith("add_video_menu_"):
        try:
            set_user_state(user_id, {"action": "add_video", "product_id": int(data.split("_")[3])})
            safe_navigate(call, "📺 Send video link:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{data.split('_')[3]}", style="danger")))
        except Exception:
            pass
    elif data.startswith("add_download_link_"):
        try:
            product_id = int(data.split("_")[3])
            set_user_state(user_id, {"action": "add_download_link", "product_id": product_id})
            safe_navigate(call, "📥 Send channel link:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{product_id}", style="danger")))
        except Exception:
            pass
    elif data.startswith("add_features_menu_"):
        try:
            set_user_state(user_id, {"action": "add_features", "product_id": int(data.split("_")[3])})
            safe_navigate(call, "📝 Send features:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data=f"manage_product_{data.split('_')[3]}", style="danger")))
        except Exception:
            pass
    elif data.startswith("toggle_maint_"):
        try:
            toggle_maintenance(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("del_product_"):
        try:
            delete_product(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("view_deposit_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        try:
            show_deposit_detail(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("approve_deposit_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        try:
            approve_deposit(call, int(data.split("_")[2]))
        except Exception as e:
            logger.error(f"approve_deposit error: {e}")
    elif data.startswith("reject_deposit_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        try:
            show_reject_options(call, int(data.split("_")[2]))
        except Exception:
            pass
    elif data.startswith("reject_no_reason_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        try:
            reject_deposit_no_reason(call, int(data.split("_")[3]))
        except Exception:
            pass
    elif data.startswith("reject_with_reason_"):
        if user_id != ADMIN_USER_ID:
            bot.answer_callback_query(call.id, "⛔ Access denied", show_alert=True)
            return
        set_user_state(user_id, {"action": "admin_reject_reason", "deposit_id": int(data.split("_")[3])})
        safe_navigate(call, "📝 Reason:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="admin_deposit_requests", style="danger")))
    elif data.startswith("copy_key_"):
        bot.answer_callback_query(call.id, "✅ Key pe click karo—copy ho jayegi!", show_alert=True)
    elif data.startswith("notify_"):
        try:
            notify_me(call, int(data.split("_")[1]))
        except Exception:
            pass
    elif data == "create_ticket":
        if is_rate_limited(f"ticket_{user_id}", 1, TICKET_COOLDOWN_SECONDS):
            bot.answer_callback_query(call.id, "❌ Please wait before creating another ticket.", show_alert=True)
            return
        set_user_state(user_id, {"action": "ticket_subject"})
        safe_navigate(call, "🎫 Subject likho:", InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Back", callback_data="support", style="danger")))
    else:
        bot.answer_callback_query(call.id, "🔜 Coming soon")

# ============ MAIN ============
if __name__ == "__main__":
    init_db()
    reset_stuck_processing_once()
    threads = [
        threading.Thread(target=check_payments, daemon=True),
        threading.Thread(target=check_pending_api_orders, daemon=True),
        threading.Thread(target=check_spin_reward_expiry, daemon=True),
        threading.Thread(target=check_review_reminders, daemon=True),
        threading.Thread(target=check_spin_reward_notifications, daemon=True),
        threading.Thread(target=cleanup_user_states, daemon=True),
        threading.Thread(target=cleanup_stale_pending_orders, daemon=True),
        threading.Thread(target=reset_stuck_processing, daemon=True),
    ]
    for t in threads:
        t.start()
    logger.info("🚀 Bot running...")
    print("🚀 Bot running...")
    try:
        while True:
            try:
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(5)
    except Exception as e:
        emergency_backup(reason=str(e))
        logger.error(f"Fatal error: {e}")
        sys.exit(1)