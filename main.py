import telebot
from telebot import types
from requests import post, get
import requests, os, re, uuid, time
from datetime import datetime, timedelta
import threading
import json
from instagrapi import Client
try:
    from instagrapi.exceptions import LoginRequired, BadPassword, TwoFactorRequired, SelectContactPointRecoveryForm
except ImportError:
    from instagrapi.exceptions import LoginRequired, BadPassword, TwoFactorRequired
    SelectContactPointRecoveryForm = Exception

# ---------------- CONFIGURATION ---------------- #
BOT_TOKEN = "7974707386:AAFP_bgCGVY9aIwtwQYhh4iQWRo-EJ1dTuQ" 
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

ADMIN_IDS = [7387793694]  

expiration_date = datetime(2027, 12, 31)
if datetime.now() > expiration_date:
    print("❌ Tool License Expired.")
    exit()

uid = str(uuid.uuid4())
sessions = {}
report_threads = {}
known_users = set()

# ---------------- USER ACCESS MANAGEMENT ---------------- #
authorized_users = {}
user_database = {}
USER_DATA_FILE = "authorized_users.json"
USER_DB_FILE = "user_database.json"

def load_authorized_users():
    global authorized_users
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r') as f:
                data = json.load(f)
                for user_id, expiry in data.items():
                    if expiry:
                        authorized_users[int(user_id)] = datetime.fromisoformat(expiry)
                    else:
                        authorized_users[int(user_id)] = None
    except Exception as e:
        print(f"Error loading users: {e}")
        authorized_users = {}

def save_authorized_users():
    try:
        data = {}
        for user_id, expiry in authorized_users.items():
            if expiry:
                data[str(user_id)] = expiry.isoformat()
            else:
                data[str(user_id)] = None
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving users: {e}")

def load_user_database():
    global user_database
    try:
        if os.path.exists(USER_DB_FILE):
            with open(USER_DB_FILE, 'r') as f:
                data = json.load(f)
                for user_id, info in data.items():
                    user_database[int(user_id)] = info
    except Exception as e:
        print(f"Error loading user database: {e}")
        user_database = {}

def save_user_database():
    try:
        data = {}
        for user_id, info in user_database.items():
            data[str(user_id)] = info
        with open(USER_DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving user database: {e}")

def update_user_database(user):
    user_id = user.id
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if user_id not in user_database:
        user_database[user_id] = {
            'first_name': user.first_name,
            'last_name': user.last_name if user.last_name else '',
            'username': user.username if user.username else '',
            'first_seen': current_time,
            'last_seen': current_time
        }
        save_user_database()
        
        access_status = "✅ AUTHORIZED" if is_user_authorized(user_id) else "🚫 UNAUTHORIZED"
        expiry_info = ""
        if user_id in authorized_users:
            if authorized_users[user_id]:
                days_left = (authorized_users[user_id] - datetime.now()).days
                expiry_info = f"\n⏰ Access expires in: {days_left} days"
            else:
                expiry_info = "\n⏰ Access: Permanent"
        
        notify_admins(
            f"🆕 <b>NEW USER DETECTED</b>\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 👤 Name: {user.first_name} {user.last_name if user.last_name else ''}\n"
            f"┃ 🆔 ID: <code>{user.id}</code>\n"
            f"┃ 🏷 Username: @{user.username if user.username else 'None'}\n"
            f"┃ 🔐 Status: {access_status}\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛"
            f"{expiry_info}"
        )
    else:
        user_database[user_id]['last_seen'] = current_time
        user_database[user_id]['first_name'] = user.first_name
        user_database[user_id]['last_name'] = user.last_name if user.last_name else ''
        user_database[user_id]['username'] = user.username if user.username else ''
        save_user_database()

def is_user_authorized(user_id):
    if user_id in ADMIN_IDS:
        return True
    if user_id not in authorized_users:
        return False
    expiry = authorized_users[user_id]
    if expiry is None:
        return True
    if datetime.now() > expiry:
        return False
    return True

def add_user(user_id, days=None):
    if days:
        expiry = datetime.now() + timedelta(days=days)
        authorized_users[user_id] = expiry
    else:
        authorized_users[user_id] = None
    save_authorized_users()

def remove_user(user_id):
    if user_id in authorized_users:
        del authorized_users[user_id]
        save_authorized_users()
        return True
    return False

load_authorized_users()
load_user_database()

# ---------------- NOTIFICATION HELPERS ---------------- #
def notify_admins(text):
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, text)
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

def get_tg_username(chat_id):
    try:
        chat = bot.get_chat(chat_id)
        return f"@{chat.username}" if chat.username else f"{chat.first_name}"
    except:
        return "Unknown"

# ---------------- ENHANCED UI HELPERS ---------------- #
def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton("🔑 Login (Pass)")
    btn2 = types.KeyboardButton("🍪 Login (Session)")
    btn3 = types.KeyboardButton("🚀 Start Report")
    btn4 = types.KeyboardButton("👤 My Info")
    btn5 = types.KeyboardButton("📜 Terms")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

def back_home_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔙 Back to Menu"))
    return markup

def stop_report_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    btn = types.KeyboardButton("🛑 Stop Report")
    markup.add(btn)
    return markup

def send_animated_message(chat_id, frames, final_text, delay=0.5, markup=None):
    """Send an animated message by editing through multiple frames"""
    msg = bot.send_message(chat_id, frames[0])
    for frame in frames[1:]:
        time.sleep(delay)
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=frame)
        except:
            pass
    time.sleep(delay)
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=final_text, reply_markup=markup)
    except:
        bot.send_message(chat_id, final_text, reply_markup=markup)

# ---------------- ENHANCED REPORTING ANIMATION ---------------- #
def animate_message(chat_id, msg_id, stop_event):
    """Enhanced reporting animation with progress indicators"""
    animations = [
        ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        ["◐", "◓", "◑", "◒"],
        ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"],
        ["◢", "◣", "◤", "◥"]
    ]
    
    i = 0
    last_edit = 0
    animation_set = 0
    
    time.sleep(1.5)
    
    while not stop_event.is_set():
        try:
            current_time = time.time()
            if current_time - last_edit >= 1.2:
                current_animation = animations[animation_set % len(animations)]
                spinner = current_animation[i % len(current_animation)]
                
                # Rotating status messages
                status_messages = [
                    "Initializing attack sequence",
                    "Establishing connection",
                    "Processing reports",
                    "Maintaining stream"
                ]
                status = status_messages[(i // 4) % len(status_messages)]
                
                text = (
                    f"<b>┏━━━━━━━━━━━━━━━━━━━┓</b>\n"
                    f"<b>┃ {spinner} {status}...</b>\n"
                    f"<b>┗━━━━━━━━━━━━━━━━━━━┛</b>\n"
                    f"<i>Active reporting in progress</i>"
                )
                bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text)
                i += 1
                if i % 10 == 0:
                    animation_set += 1
                last_edit = current_time
            time.sleep(0.4)
        except Exception as e:
            time.sleep(1)
            continue

def report_instagram(chat_id, target_id, sessionid, csrftoken, reportType, delay, stop_event):
    # Initial sleek animation
    init_msg = bot.send_message(
        chat_id, 
        "🚀 <b>Launching attack...</b>",
        reply_markup=stop_report_keyboard()
    )
    time.sleep(0.5)
    
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=init_msg.message_id,
            text="⚡ <b>Initializing Attack Protocol</b>\n"
                 "<code>▓▓▓░░░░░░░</code> <i>30%</i>"
        )
    except:
        pass
    time.sleep(0.5)
    
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=init_msg.message_id,
            text="⚡ <b>Initializing Attack Protocol</b>\n"
                 "<code>▓▓▓▓▓▓▓▓▓▓</code> <i>100%</i>"
        )
    except:
        pass
    time.sleep(0.5)
    
    # Main progress message with modern design
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=init_msg.message_id,
            text="💥 <b>ATTACK ACTIVE</b>\n\n"
                 "╔═══════════════════╗\n"
                 "║ 📊 Reports: <code>0</code>\n"
                 "║ ⚡ Status: <i>Running</i>\n"
                 "║ 🔄 Progress: <code>[░░░░░░░░░░]</code>\n"
                 "╚═══════════════════╝\n\n"
                 "💡 <i>Tap Stop to terminate</i>",
            reply_markup=stop_report_keyboard()
        )
    except:
        pass
    
    progress_msg = init_msg  # Reuse same message
    count = 0
    errors = 0
    last_update = time.time()
    
    # Animation states
    status_emojis = ["💥", "⚡", "🔥", "💫", "⭐"]
    anim_index = 0

    while not stop_event.is_set():
        try:
            # Animate every 1.5 seconds
            current_time = time.time()
            if current_time - last_update >= 1.5:
                try:
                    # Create animated progress bar
                    bar_length = 10
                    filled = min(count // 5, bar_length)
                    pulse_pos = anim_index % bar_length
                    
                    bar = ""
                    for i in range(bar_length):
                        if i < filled:
                            bar += "▓"
                        elif i == pulse_pos:
                            bar += "▒"
                        else:
                            bar += "░"
                    
                    status_emoji = status_emojis[anim_index % len(status_emojis)]
                    
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg.message_id,
                        text=f"{status_emoji} <b>ATTACK ACTIVE</b>\n\n"
                             f"╔═══════════════════╗\n"
                             f"║ 📊 Reports: <code>{count}</code>\n"
                             f"║ ⚡ Status: <i>Running</i>\n"
                             f"║ 🔄 Progress: <code>[{bar}]</code>\n"
                             f"╚═══════════════════╝\n\n"
                             f"💡 <i>Tap Stop to terminate</i>",
                        reply_markup=stop_report_keyboard()
                    )
                    
                    last_update = current_time
                    anim_index += 1
                except:
                    pass
            
            # Send actual report
            url = f"https://i.instagram.com/users/{target_id}/flag/"
            headers = {
                "User-Agent": "Instagram 114.0.0.38.120 Android",
                "Host": "i.instagram.com",
                'Cookie': f"sessionid={sessionid}; csrftoken={csrftoken}",
                "X-CSRFToken": csrftoken,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Connection": "keep-alive"
            }
            data = f'source_name=&reason_id={reportType}&frx_context='
            r3 = post(url, headers=headers, data=data, allow_redirects=False)
            
            if r3.status_code == 429:
                stop_event.set()
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg.message_id,
                        text="🛑 <b>RATE LIMIT REACHED</b>\n\n"
                             "╔═══════════════════╗\n"
                             f"║ ✅ Reports: <code>{count}</code>\n"
                             "║ 🚫 Status: <i>Blocked</i>\n"
                             "║ 🔄 Progress: <code>[▓▓▓▓▓▓▓▓▓▓]</code>\n"
                             "╚═══════════════════╝\n\n"
                             "⏰ <i>Wait 30-60 minutes</i>"
                    )
                except:
                    pass
                
                # Send summary message
                time.sleep(1)
                bot.send_message(
                    chat_id,
                    "📊 <b>OPERATION SUMMARY</b>\n\n"
                    "╔═══════════════════╗\n"
                    f"║ 📈 Total Reports: <code>{count}</code>\n"
                    "║ 🎯 Target: <i>Rate Limited</i>\n"
                    "║ 💤 Status: <i>Cooldown</i>\n"
                    "╚═══════════════════╝",
                    reply_markup=main_menu_keyboard()
                )
                break
                
            elif r3.status_code in [200, 201]:
                count += 1
                    
            elif r3.status_code == 404:
                stop_event.set()
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_msg.message_id,
                        text="❌ <b>TARGET NOT FOUND</b>\n\n"
                             "╔═══════════════════╗\n"
                             f"║ 📊 Reports: <code>{count}</code>\n"
                             "║ 🔍 Status: <i>Not Found</i>\n"
                             "║ 🔄 Progress: <code>[▓▓▓▓▓░░░░░]</code>\n"
                             "╚═══════════════════╝\n\n"
                             "💀 <i>User doesn't exist</i>"
                    )
                except:
                    pass
                
                # Send summary
                time.sleep(1)
                bot.send_message(
                    chat_id,
                    "📊 <b>OPERATION SUMMARY</b>\n\n"
                    "╔═══════════════════╗\n"
                    f"║ 📈 Total Reports: <code>{count}</code>\n"
                    "║ 🎯 Target: <i>Invalid</i>\n"
                    "║ ❌ Status: <i>Not Found</i>\n"
                    "╚═══════════════════╝",
                    reply_markup=main_menu_keyboard()
                )
                break
                
            else:
                errors += 1
                if errors > 10:
                    stop_event.set()
                    try:
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=progress_msg.message_id,
                            text="⚠️ <b>ERROR THRESHOLD</b>\n\n"
                                 "╔═══════════════════╗\n"
                                 f"║ 📊 Reports: <code>{count}</code>\n"
                                 f"║ ❌ Errors: <code>{errors}</code>\n"
                                 "║ 🔄 Progress: <code>[▓▓▓░░░░░░░]</code>\n"
                                 "╚═══════════════════╝\n\n"
                                 "🛑 <i>Too many failures</i>"
                        )
                    except:
                        pass
                    
                    # Send summary
                    time.sleep(1)
                    bot.send_message(
                        chat_id,
                        "📊 <b>OPERATION SUMMARY</b>\n\n"
                        "╔═══════════════════╗\n"
                        f"║ 📈 Total Reports: <code>{count}</code>\n"
                        f"║ ⚠️ Errors: <code>{errors}</code>\n"
                        "║ 🛑 Status: <i>Terminated</i>\n"
                        "╚═══════════════════╝",
                        reply_markup=main_menu_keyboard()
                    )
                    break

            # Delay between reports
            for _ in range(delay):
                if stop_event.is_set():
                    break
                time.sleep(1)

        except Exception as e:
            stop_event.set()
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text="💥 <b>CRITICAL ERROR</b>\n\n"
                         "╔═══════════════════╗\n"
                         f"║ 📊 Reports: <code>{count}</code>\n"
                         "║ ❌ Status: <i>Failed</i>\n"
                         "║ 🔄 Progress: <code>[▓▓░░░░░░░░]</code>\n"
                         "╚═══════════════════╝\n\n"
                         f"⚠️ <code>{str(e)[:40]}</code>"
                )
            except:
                pass
            
            # Send summary
            time.sleep(1)
            bot.send_message(
                chat_id,
                "📊 <b>OPERATION SUMMARY</b>\n\n"
                "╔═══════════════════╗\n"
                f"║ 📈 Total Reports: <code>{count}</code>\n"
                "║ 💥 Status: <i>Error</i>\n"
                f"║ ⚠️ Reason: <code>{str(e)[:20]}</code>\n"
                "╚═══════════════════╝",
                reply_markup=main_menu_keyboard()
            )
            break

    # Final completion message (only if stopped normally)
    if not stop_event.is_set() or count > 0:
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text="🎉 <b>OPERATION COMPLETE</b>\n\n"
                     "╔═══════════════════╗\n"
                     f"║ ✅ Reports: <code>{count}</code>\n"
                     "║ 🎯 Status: <i>Success</i>\n"
                     "║ 🔄 Progress: <code>[▓▓▓▓▓▓▓▓▓▓]</code>\n"
                     "╚═══════════════════╝\n\n"
                     "✨ <i>Mission accomplished!</i>"
            )
        except:
            pass
        
        # Send final summary
        time.sleep(1)
        bot.send_message(
            chat_id,
            "📊 <b>FINAL SUMMARY</b>\n\n"
            "╔═══════════════════╗\n"
            f"║ 📈 Total Reports: <code>{count}</code>\n"
            "║ ✅ Status: <i>Completed</i>\n"
            "║ 🎯 Result: <i>Success</i>\n"
            "╚═══════════════════╝\n\n"
            "🎉 <i>Operation finished successfully!</i>",
            reply_markup=main_menu_keyboard()
        )

    if chat_id in report_threads:
        del report_threads[chat_id]

# ---------------- AUTHENTICATION WITH INSTAGRAPI ---------------- #
def login_user_instagrapi(chat_id, username, password):
    msg_load = bot.send_message(chat_id, "🔐 <b>Authenticating...</b>\n<i>⏳ Please wait</i>")
    
    try:
        cl = Client()
        cl.delay_range = [1, 3]
        
        try:
            cl.login(username, password)
            
            sessionid = None
            csrftoken = None
            user_id = None
            
            settings = cl.get_settings()
            
            if 'authorization_data' in settings:
                auth_data = settings['authorization_data']
                sessionid = auth_data.get('sessionid')
                user_id = auth_data.get('ds_user_id')
            
            if hasattr(cl, 'private') and hasattr(cl.private, 'cookies'):
                csrftoken = cl.private.cookies.get('csrftoken', 'missing')
            
            if not user_id and hasattr(cl, 'user_id'):
                user_id = cl.user_id
            
            if not sessionid:
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=msg_load.message_id, 
                    text="<b>❌ Session Extraction Failed</b>\n\n"
                         "┏━━━━━━━━━━━━━━━━━━━┓\n"
                         "┃ Could not retrieve session\n"
                         "┃ Try Session ID login instead\n"
                         "┗━━━━━━━━━━━━━━━━━━━┛"
                )
                return
            
            sessions[chat_id] = {
                'username': username, 
                'sessionid': sessionid,
                'csrftoken': csrftoken if csrftoken else 'missing',
                'user_id': user_id,
                'authenticated': True
            }
            
            bot.delete_message(chat_id, msg_load.message_id)
            
            tg_user = get_tg_username(chat_id)
            notify_admins(
                f"🔐 <b>NEW LOGIN (PASSWORD)</b>\n"
                f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ 👤 TG: {tg_user} (<code>{chat_id}</code>)\n"
                f"┃ 📸 IG: <code>{username}</code>\n"
                f"┃ 🆔 ID: <code>{user_id}</code>\n"
                f"┃ ⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
            
            success_frames = [
                "✓ <b>Authenticated!</b>",
                "✓✓ <b>Session established!</b>",
                "✓✓✓ <b>Ready to go!</b>"
            ]
            
            msg = bot.send_message(chat_id, success_frames[0])
            for frame in success_frames[1:]:
                time.sleep(0.3)
                try:
                    bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=frame)
                except:
                    pass
            
            time.sleep(0.5)
            
            final_text = (
                f"<b>✅ LOGIN SUCCESSFUL!</b>\n"
                f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ 👤 User: <code>{username}</code>\n"
                f"┃ 🆔 ID: <code>{user_id}</code>\n"
                f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                f"<b>📋 Your Session ID:</b>\n"
                f"<code>{sessionid}</code>\n\n"
                f"<i>💡 Save this for faster login!</i>\n\n"
                f"🚀 <b>Ready to start reporting!</b>"
            )
            
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=final_text, reply_markup=main_menu_keyboard())
            except:
                bot.send_message(chat_id, final_text, reply_markup=main_menu_keyboard())
            
        except TwoFactorRequired:
            bot.delete_message(chat_id, msg_load.message_id)
            msg = bot.send_message(
                chat_id,
                "<b>🔐 Two-Factor Authentication</b>\n\n"
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ 📱 Check your authenticator\n"
                "┃ 💬 Enter 6-digit code below\n"
                "┗━━━━━━━━━━━━━━━━━━━┛"
            )
            bot.register_next_step_handler(msg, lambda m: handle_2fa_code(chat_id, username, password, m.text.strip(), cl))
            
        except BadPassword:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_load.message_id, 
                text="<b>❌ Invalid Password</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Password incorrect\n"
                     "┃ Please try again\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
            
        except LoginRequired:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_load.message_id, 
                text="<b>❌ Login Failed</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Account restricted\n"
                     "┃ Try Session ID login\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
            
        except SelectContactPointRecoveryForm:
            bot.delete_message(chat_id, msg_load.message_id)
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add("📧 Email", "📱 SMS")
            msg = bot.send_message(
                chat_id,
                "<b>⚠️ Verification Required</b>\n\n"
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ Instagram needs to verify\n"
                "┃ Choose verification method:\n"
                "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=markup
            )
            bot.register_next_step_handler(msg, lambda m: handle_challenge_choice(chat_id, username, password, m.text, cl))
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "challenge" in error_msg or "checkpoint" in error_msg:
                bot.delete_message(chat_id, msg_load.message_id)
                markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
                markup.add("📧 Email", "📱 SMS", "❌ Cancel")
                msg = bot.send_message(
                    chat_id,
                    "<b>⚠️ Security Challenge</b>\n\n"
                    "┏━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃ Verification needed\n"
                    "┃ Select method below:\n"
                    "┗━━━━━━━━━━━━━━━━━━━┛",
                    reply_markup=markup
                )
                bot.register_next_step_handler(msg, lambda m: handle_challenge_choice(chat_id, username, password, m.text, cl))
                
            elif "consent" in error_msg:
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=msg_load.message_id,
                    text="<b>⚠️ Consent Required</b>\n\n"
                         "┏━━━━━━━━━━━━━━━━━━━┓\n"
                         "┃ Accept new terms:\n"
                         "┃ 1. Open Instagram app\n"
                         "┃ 2. Login & accept terms\n"
                         "┃ 3. Try again here\n"
                         "┗━━━━━━━━━━━━━━━━━━━┛",
                    reply_markup=back_home_keyboard()
                )
                
            elif "rate" in error_msg or "limit" in error_msg:
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=msg_load.message_id,
                    text="<b>⚠️ Rate Limited</b>\n\n"
                         "┏━━━━━━━━━━━━━━━━━━━┓\n"
                         "┃ Too many attempts\n"
                         "┃ ⏰ Wait 30-60 minutes\n"
                         "┃ 💡 Or use Session login\n"
                         "┗━━━━━━━━━━━━━━━━━━━┛",
                    reply_markup=back_home_keyboard()
                )
            else:
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=msg_load.message_id, 
                    text=f"<b>❌ Login Error</b>\n\n"
                         f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                         f"┃ {str(e)[:40]}\n"
                         f"┗━━━━━━━━━━━━━━━━━━━┛",
                    reply_markup=back_home_keyboard()
                )
            
    except Exception as e:
        try:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_load.message_id, 
                text=f"<b>❌ Critical Error</b>\n\n"
                     f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                     f"┃ {str(e)[:40]}\n"
                     f"┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
        except:
            bot.send_message(chat_id, f"<b>❌ Error:</b> {str(e)[:200]}", reply_markup=back_home_keyboard())


def handle_2fa_code(chat_id, username, password, code, cl):
    """Handle 2FA code verification"""
    msg_load = bot.send_message(chat_id, "🔐 <b>Verifying 2FA...</b>\n<i>⏳ Please wait</i>")
    
    try:
        cl = Client()
        cl.delay_range = [1, 3]
        cl.login(username, password, verification_code=code)
        
        settings = cl.get_settings()
        sessionid = None
        user_id = None
        
        if 'authorization_data' in settings:
            auth_data = settings['authorization_data']
            sessionid = auth_data.get('sessionid')
            user_id = auth_data.get('ds_user_id')
        
        if not user_id and hasattr(cl, 'user_id'):
            user_id = cl.user_id
        
        csrftoken = 'missing'
        if hasattr(cl, 'private') and hasattr(cl.private, 'cookies'):
            csrftoken = cl.private.cookies.get('csrftoken', 'missing')
        
        if not sessionid:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text="<b>❌ Session Failed</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Could not extract session\n"
                     "┃ Try Session ID login\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
            return
        
        sessions[chat_id] = {
            'username': username,
            'sessionid': sessionid,
            'csrftoken': csrftoken,
            'user_id': user_id,
            'authenticated': True
        }
        
        bot.delete_message(chat_id, msg_load.message_id)
        
        tg_user = get_tg_username(chat_id)
        notify_admins(
            f"🔐 <b>NEW LOGIN (2FA)</b>\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 👤 TG: {tg_user} (<code>{chat_id}</code>)\n"
            f"┃ 📸 IG: <code>{username}</code>\n"
            f"┃ 🆔 ID: <code>{user_id}</code>\n"
            f"┃ ⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛"
        )
        
        bot.send_message(
            chat_id,
            f"<b>✅ 2FA LOGIN SUCCESSFUL!</b>\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 👤 User: <code>{username}</code>\n"
            f"┃ 🆔 ID: <code>{user_id}</code>\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"<b>📋 Your Session ID:</b>\n"
            f"<code>{sessionid}</code>\n\n"
            f"🚀 <b>Ready to start reporting!</b>",
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        error_msg = str(e).lower()
        if "invalid" in error_msg or "wrong" in error_msg or "code" in error_msg:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text="<b>❌ Invalid 2FA Code</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Code incorrect/expired\n"
                     "┃ Please try again\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
        else:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text=f"<b>❌ 2FA Error</b>\n\n"
                     f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                     f"┃ {str(e)[:40]}\n"
                     f"┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )


def handle_challenge_choice(chat_id, username, password, choice, cl):
    """Handle challenge verification method choice"""
    if "cancel" in choice.lower() or "❌" in choice:
        bot.send_message(chat_id, "❌ Login cancelled.", reply_markup=main_menu_keyboard())
        return
    
    msg_load = bot.send_message(chat_id, "📤 <b>Requesting code...</b>\n<i>⏳ Please wait</i>")
    
    try:
        choice_value = 1 if "sms" in choice.lower() or "📱" in choice else 0
        
        cl = Client()
        cl.delay_range = [1, 3]
        
        try:
            cl.login(username, password)
        except SelectContactPointRecoveryForm:
            if hasattr(cl, 'challenge_code_handler'):
                cl.challenge_code_handler(username, choice_value)
            
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text=f"<b>✅ Code Sent!</b>\n\n"
                     f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                     f"┃ 📬 Check {'Email' if choice_value == 0 else 'SMS'}\n"
                     f"┃ 💬 Enter code below:\n"
                     f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
            
            bot.register_next_step_handler_by_chat_id(chat_id, lambda m: handle_challenge_code(chat_id, username, password, m.text.strip(), cl))
            return
    
    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_load.message_id,
            text=f"<b>❌ Challenge Error</b>\n\n"
                 f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                 f"┃ {str(e)[:40]}\n"
                 f"┃ Alternative:\n"
                 f"┃ 1. Open Instagram app\n"
                 f"┃ 2. Complete challenge\n"
                 f"┃ 3. Wait 15-30 minutes\n"
                 f"┃ 4. Try again here\n"
                 f"┗━━━━━━━━━━━━━━━━━━━┛",
            reply_markup=back_home_keyboard()
        )


def handle_challenge_code(chat_id, username, password, code, cl):
    """Handle challenge verification code"""
    msg_load = bot.send_message(chat_id, "🔐 <b>Verifying challenge...</b>\n<i>⏳ Please wait</i>")
    
    try:
        if hasattr(cl, 'challenge_resolve'):
            cl.challenge_resolve(code)
        
        cl.login(username, password)
        
        settings = cl.get_settings()
        sessionid = None
        user_id = None
        
        if 'authorization_data' in settings:
            auth_data = settings['authorization_data']
            sessionid = auth_data.get('sessionid')
            user_id = auth_data.get('ds_user_id')
        
        if not user_id and hasattr(cl, 'user_id'):
            user_id = cl.user_id
        
        csrftoken = 'missing'
        if hasattr(cl, 'private') and hasattr(cl.private, 'cookies'):
            csrftoken = cl.private.cookies.get('csrftoken', 'missing')
        
        if not sessionid:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text="<b>❌ Login Failed</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Could not complete login\n"
                     "┃ Try Session ID login\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
            return
        
        sessions[chat_id] = {
            'username': username,
            'sessionid': sessionid,
            'csrftoken': csrftoken,
            'user_id': user_id,
            'authenticated': True
        }
        
        bot.delete_message(chat_id, msg_load.message_id)
        
        tg_user = get_tg_username(chat_id)
        notify_admins(
            f"🔐 <b>NEW LOGIN (CHALLENGE)</b>\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 👤 TG: {tg_user} (<code>{chat_id}</code>)\n"
            f"┃ 📸 IG: <code>{username}</code>\n"
            f"┃ 🆔 ID: <code>{user_id}</code>\n"
            f"┃ ⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛"
        )
        
        bot.send_message(
            chat_id,
            f"<b>✅ CHALLENGE COMPLETED!</b>\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 👤 User: <code>{username}</code>\n"
            f"┃ 🆔 ID: <code>{user_id}</code>\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"<b>📋 Your Session ID:</b>\n"
            f"<code>{sessionid}</code>\n\n"
            f"🚀 <b>Ready to start reporting!</b>",
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        error_msg = str(e).lower()
        if "invalid" in error_msg or "wrong" in error_msg:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text="<b>❌ Invalid Code</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Code incorrect/expired\n"
                     "┃ Please try login again\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
        else:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_load.message_id,
                text=f"<b>❌ Challenge Error</b>\n\n"
                     f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                     f"┃ {str(e)[:40]}\n"
                     f"┃ Complete in IG app\n"
                     f"┗━━━━━━━━━━━━━━━━━━━┛",
                reply_markup=back_home_keyboard()
            )
            
            
def login_user(chat_id, username, password):
    """Wrapper - uses instagrapi for login"""
    login_user_instagrapi(chat_id, username, password)

def validate_session(chat_id, session_id):
    msg_load = bot.send_message(chat_id, "🔄 <b>Validating Session...</b>\n<i>⏳ Please wait</i>")
    try:
        session_id = session_id.strip()
        
        if not session_id or len(session_id) < 10:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_load.message_id, 
                text="<b>❌ Invalid Session ID</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Session ID too short\n"
                     "┃ Please check and retry\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛"
            )
            return
        
        headers = {
            'User-Agent': 'Instagram 114.0.0.38.120 Android',
            'Cookie': f'sessionid={session_id}',
            'Accept-Language': 'en-US'
        }
        r = requests.get('https://i.instagram.com/api/v1/accounts/current_user/', headers=headers)
        
        if r.status_code == 200:
            try:
                data = r.json()
                username = data.get('user', {}).get('username', 'Unknown')
                
                csrftoken = r.cookies.get('csrftoken')
                if not csrftoken:
                    r2 = requests.get('https://i.instagram.com/api/v1/accounts/current_user/', 
                                     headers=headers)
                    csrftoken = r2.cookies.get('csrftoken', 'missing')
                
                sessions[chat_id] = {
                    'username': username, 
                    'sessionid': session_id, 
                    'csrftoken': csrftoken if csrftoken else 'missing',
                    'authenticated': True
                }
                
                bot.delete_message(chat_id, msg_load.message_id)
                
                tg_user = get_tg_username(chat_id)
                notify_admins(
                    f"🍪 <b>NEW LOGIN (SESSION)</b>\n"
                    f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃ 👤 TG: {tg_user} (<code>{chat_id}</code>)\n"
                    f"┃ 📸 IG: <code>{username}</code>\n"
                    f"┃ ⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                    f"┗━━━━━━━━━━━━━━━━━━━┛"
                )

                success_msg = (
                    f"<b>✅ SESSION VALID!</b>\n"
                    f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃ 👤 Logged in as:\n"
                    f"┃ <code>{username}</code>\n"
                    f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                    f"🚀 <b>Ready to start reporting!</b>"
                )
                bot.send_message(chat_id, success_msg, reply_markup=main_menu_keyboard())
            except Exception as parse_err:
                bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=msg_load.message_id, 
                    text=f"<b>❌ Parse Error</b>\n\n"
                         f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                         f"┃ {str(parse_err)[:40]}\n"
                         f"┗━━━━━━━━━━━━━━━━━━━┛"
                )
        elif r.status_code == 401:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_load.message_id, 
                text="<b>❌ Session Expired</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ Session no longer valid\n"
                     "┃ Login with password\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛"
            )
        else:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_load.message_id, 
                text=f"<b>❌ Validation Error</b>\n\n"
                     f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                     f"┃ HTTP {r.status_code}\n"
                     f"┃ Try password login\n"
                     f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg_load.message_id, 
            text=f"<b>❌ Error</b>\n\n"
                 f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                 f"┃ {str(e)[:40]}\n"
                 f"┗━━━━━━━━━━━━━━━━━━━┛"
        )

# ---------------- BOT HANDLERS ---------------- #
@bot.message_handler(commands=['start', 'help'])
def start_handler(message):
    user = message.from_user
    chat_id = message.chat.id
    
    update_user_database(user)
    
    if not is_user_authorized(chat_id):
        unauthorized_msg = (
            "<b>🚫 ACCESS DENIED</b>\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ You are not authorized\n"
            "┃ to use this bot\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            "<b>📩 Contact admin for access:</b>\n"
            "• @x9891\n"
            "• @metaui\n\n"
            "<i>Your Telegram ID:</i>\n<code>{}</code>".format(chat_id)
        )
        bot.send_message(chat_id, unauthorized_msg)
        return

    welcome_text = (
        "<blockquote>🔥 <b>IG MASS REPORTS BOT v1.2</b> 🔥</blockquote>\n"
        
        " Welcome to the ultimate reporting tool\n\n"
        "<i><b>⚙️ Features:</b>\n"
        "• Session ID Login (No Checkpoint)\n"
        "• Password Login\n"
        "• Multi-Threaded Reporting\n"
        "• Live Status Updates</i>\n\n"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard())

def safe_answer_callback(call_id, text, **kwargs):
    try:
        bot.answer_callback_query(call_id, text, **kwargs)
    except Exception as e:
        if "query is too old" in str(e) or "query ID is invalid" in str(e):
            pass
        else:
            raise

@bot.message_handler(func=lambda message: message.text == "🔑 Login (Pass)")
def handle_login_pass(message):
    if not is_user_authorized(message.chat.id):
        bot.send_message(message.chat.id, "❌ <b>Access Denied.</b>")
        return
    msg = bot.send_message(message.chat.id, "✏️ <b>Enter your Instagram Username:</b>")
    bot.register_next_step_handler(msg, ask_password)

@bot.message_handler(func=lambda message: message.text == "🍪 Login (Session)")
def handle_login_session(message):
    if not is_user_authorized(message.chat.id):
        bot.send_message(message.chat.id, "❌ <b>Access Denied.</b>")
        return
    msg = bot.send_message(message.chat.id, "🍪 <b>Paste your 'sessionid' cookie:</b>")
    bot.register_next_step_handler(msg, lambda m: validate_session(message.chat.id, m.text.strip()))

@bot.message_handler(func=lambda message: message.text == "🚀 Start Report")
def handle_start_report(message):
    chat_id = message.chat.id
    if not is_user_authorized(chat_id):
        bot.send_message(chat_id, "❌ <b>Access Denied.</b>")
        return
    if chat_id not in sessions:
        bot.send_message(
            chat_id, 
            "<b>❌ LOGIN REQUIRED!</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Please login first\n"
            "┃ Choose login method below\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )
        return
    msg = bot.send_message(chat_id, "🎯 <b>Enter Target Username:</b>")
    bot.register_next_step_handler(msg, ask_report_type_menu)

@bot.message_handler(func=lambda message: message.text == "👤 My Info")
def handle_my_info(message):
    chat_id = message.chat.id
    if not is_user_authorized(chat_id):
        bot.send_message(chat_id, "❌ <b>Access Denied.</b>")
        return
    if chat_id in sessions:
        info = sessions[chat_id]
        
        access_info = ""
        if chat_id in authorized_users:
            if authorized_users[chat_id]:
                days_left = (authorized_users[chat_id] - datetime.now()).days
                access_info = f"\n┃ ⏰ Expires: {days_left} days"
            else:
                access_info = "\n┃ ⏰ Access: Permanent"
        
        text = (
            "<b>👤 CURRENT SESSION</b>\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ 📸 User: <code>{info['username']}</code>\n"
            f"┃ ✅ Status: Active\n"
            f"┃ 🔐 CSRF: Present"
            f"{access_info}\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛"
        )
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("🚪 Logout"))
        markup.add(types.KeyboardButton("🔙 Back to Menu"))
        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.send_message(
            chat_id, 
            "<b>❌ NO ACTIVE SESSION</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Please login first\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "📜 Terms")
def handle_terms(message):
    if not is_user_authorized(message.chat.id):
        bot.send_message(message.chat.id, "❌ <b>Access Denied.</b>")
        return
    terms_text = (
        "<blockquote><b>📜 TERMS AND GUIDELINES</b></blockquote>\n"
       
        "<i><b>1️⃣ Educational Purpose:</b>\n"
        "This tool is for testing and educational purposes only.\n\n"
        "<b>2️⃣ Responsibility:</b>\n"
        "Developer assumes no liability for usage.\n\n"
        "<b>3️⃣ Abuse Warning:</b>\n"
        "Excessive use may lead to account suspension.\n\n"
        "<b>4️⃣ Privacy:</b>\n"
        "Passwords not stored. Sessions held in memory only.</i>\n\n"
        "<u><b>By using this bot, you agree to these terms.</b></u>"
    )
    bot.send_message(message.chat.id, terms_text, reply_markup=back_home_keyboard())

@bot.message_handler(func=lambda message: message.text == "🚪 Logout")
def handle_logout(message):
    if not is_user_authorized(message.chat.id):
        bot.send_message(message.chat.id, "❌ <b>Access Denied.</b>")
        return
    chat_id = message.chat.id
    if chat_id in sessions:
        del sessions[chat_id]
        bot.send_message(
            chat_id, 
            "<b>👋 LOGGED OUT</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Session terminated\n"
            "┃ Successfully logged out\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )
    else:
        bot.send_message(
            chat_id, 
            "<b>❌ NOT LOGGED IN</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ No active session found\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )

@bot.message_handler(func=lambda message: message.text == "🔙 Back to Menu")
def handle_back_menu(message):
    if not is_user_authorized(message.chat.id):
        bot.send_message(message.chat.id, "❌ <b>Access Denied.</b>")
        return
    bot.send_message(
        message.chat.id, 
        "🔥 <b>MAIN MENU</b>\n\n"
        "┏━━━━━━━━━━━━━━━━━━━┓\n"
        "┃ Select an operation below\n"
        "┗━━━━━━━━━━━━━━━━━━━┛", 
        reply_markup=main_menu_keyboard()
    )

def ask_password(message):
    username = message.text
    msg = bot.send_message(
        message.chat.id, 
        "🔑 <b>Enter your Password:</b>\n\n"
        "<i>🔒 Input is hidden in logs</i>"
    )
    bot.register_next_step_handler(msg, lambda m: login_user(message.chat.id, username, m.text))

def ask_report_type_menu(message):
    chat_id = message.chat.id
    target = message.text
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    options = [
        "1 - Spam", 
        "2 - Self Harm", 
        "4 - Nudity", 
        "5 - Violence", 
        "6 - Hate Speech", 
        "7 - Harassment", 
        "8 - Impersonation",
        "11 - Underage",
        "12 - Sale/Promotion",
        "13 - Invisible"
    ]
    for opt in options:
        markup.add(types.KeyboardButton(opt))
    msg = bot.send_message(
        chat_id, 
        f"<b>📝 Why are you reporting {target}?</b>\n\n"
        f"┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ Select a reason below\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛", 
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, lambda m: ask_report_delay(chat_id, target, m.text))

def ask_report_delay(chat_id, target, choice_text):
    try:
        reportType = int(choice_text.split(" - ")[0])
    except:
        bot.send_message(
            chat_id, 
            "❌ <b>Invalid selection</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Please use the menu\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )
        return
    markup = types.ReplyKeyboardRemove()
    msg = bot.send_message(
        chat_id, 
        "⏱ <b>Enter delay between reports:</b>\n\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃ 💡 Recommended: 5-10 seconds\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", 
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, lambda m: pre_start_check(chat_id, target, reportType, m.text))

def pre_start_check(chat_id, target, reportType, delay_text):
    try:
        delay = int(delay_text)
        if delay < 2: 
            delay = 2
    except:
        delay = 10

    session_data = sessions[chat_id]
    sessionid = session_data.get('sessionid')
    csrftoken = session_data.get('csrftoken', 'missing')
    cl = session_data.get('client')

    scan_frames = [
        "🔍 <b>Scanning...</b>",
        "🔍 <b>Scanning..</b>",
        "🔍 <b>Scanning.</b>",
        f"🎯 <b>Searching for {target}...</b>"
    ]
    
    msg = bot.send_message(chat_id, scan_frames[0])
    for frame in scan_frames[1:]:
        time.sleep(0.3)
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=frame)
        except:
            pass
    
    try:
        target_id = None
        
        search_url = 'https://i.instagram.com/api/v1/users/search/'
        search_params = {'q': target, 'timezone_offset': '0', 'count': '1'}
        
        headers = {
            "User-Agent": "Instagram 114.0.0.38.120 Android",
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "X-CSRFToken": csrftoken if csrftoken != 'missing' else 'missing'
        }
        
        if sessionid and sessionid != 'missing':
            headers["Cookie"] = f"sessionid={sessionid}"
        
        if cl and hasattr(cl, 'session'):
            try:
                r = cl.session.get(search_url, params=search_params, headers=headers)
            except:
                r = requests.get(search_url, params=search_params, headers=headers)
        else:
            r = requests.get(search_url, params=search_params, headers=headers)
        
        if r.status_code == 200:
            try:
                data = r.json()
                for user in data.get('users', []):
                    if user['username'].lower() == target.lower():
                        target_id = str(user['pk'])
                        break
            except:
                pass
        
        if not target_id:
            headers_no_session = {
                "User-Agent": "Instagram 114.0.0.38.120 Android",
                "Accept": "*/*",
                "Accept-Language": "en-US"
            }
            r = requests.get(search_url, params=search_params, headers=headers_no_session)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    for user in data.get('users', []):
                        if user['username'].lower() == target.lower():
                            target_id = str(user['pk'])
                            break
                except:
                    pass
        
        if not target_id:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg.message_id,
                text="<b>❌ TARGET NOT FOUND</b>\n\n"
                     "┏━━━━━━━━━━━━━━━━━━━┓\n"
                     "┃ User doesn't exist\n"
                     "┃ Check spelling and retry\n"
                     "┗━━━━━━━━━━━━━━━━━━━┛"
            )
            return
        
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg.message_id,
            text=f"<b>✅ TARGET LOCKED!</b>\n\n"
                 f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                 f"┃ 🎯 Found: {target}\n"
                 f"┃ 🆔 ID: {target_id}\n"
                 f"┃ ⏱ Delay: {delay}s\n"
                 f"┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                 f"🚀 <b>Launching attack...</b>"
        )
        
        time.sleep(1)
        
        stop_event = threading.Event()
        report_threads[chat_id] = stop_event
        threading.Thread(target=report_instagram, args=(chat_id, target_id, sessionid, csrftoken, reportType, delay, stop_event)).start()
    except Exception as e:
        bot.send_message(
            chat_id, 
            f"<b>❌ ERROR</b>\n\n"
            f"┏━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃ {str(e)[:40]}\n"
            f"┗━━━━━━━━━━━━━━━━━━━┛"
        )

@bot.message_handler(func=lambda message: message.text == "🛑 Stop Report")
def handle_stop_report_button(message):
    chat_id = message.chat.id
    if chat_id in report_threads:
        report_threads[chat_id].set()
        bot.send_message(
            chat_id, 
            "<b>🛑 STOPPING...</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Terminating operation\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=types.ReplyKeyboardRemove()
        )
        time.sleep(1)
        bot.send_message(
            chat_id, 
            "<b>🛑 FORCE STOPPED</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Operation cancelled\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )
    else:
        bot.send_message(
            chat_id, 
            "<b>❌ NO ACTIVE REPORTS</b>\n\n"
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ Nothing to stop\n"
            "┗━━━━━━━━━━━━━━━━━━━┛", 
            reply_markup=main_menu_keyboard()
        )

# ---------------- ADMIN COMMANDS ---------------- #
@bot.message_handler(commands=['cmd'])
def admin_panel(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ <b>Access Denied. You are not an admin.</b>")
        return
    
    active_users = len([u for u in authorized_users if is_user_authorized(u)])
    expired_users = len([u for u in authorized_users if not is_user_authorized(u)])
    
    stats_msg = (
        "<b>👮‍♂️ ADMIN DASHBOARD</b>\n"
        "┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ 👥 Total Users: {len(user_database)}\n"
        f"┃ 🎫 Authorized: {len(authorized_users)}\n"
        f"┃ ✅ Active: {active_users}\n"
        f"┃ ⏰ Expired: {expired_users}\n"
        f"┃ 🔐 Sessions: {len(sessions)}\n"
        f"┃ 🚀 Running: {len(report_threads)}\n"
        "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        "<b>📋 Admin Commands:</b>\n"
        "/add {user_id} - Permanent access\n"
        "/add {user_id} {days} - Temporary\n"
        "/remove {user_id} - Remove access\n"
        "/list - Show authorized users\n"
        "/allusers - Show all users\n"
        "/broadcast - Send message to all"
    )
    
    bot.send_message(message.chat.id, stats_msg)

@bot.message_handler(commands=['add'])
def admin_add_user(message):
    if message.chat.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(
                message, 
                "<b>❌ Invalid Usage</b>\n\n"
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ /add {user_id}\n"
                "┃ /add {user_id} {days}\n"
                "┗━━━━━━━━━━━━━━━━━━━┛"
            )
            return
        
        user_id = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else None
        
        add_user(user_id, days)
        
        if days:
            expiry_date = datetime.now() + timedelta(days=days)
            response = (
                f"<b>✅ USER ADDED!</b>\n"
                f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ 🆔 ID: <code>{user_id}</code>\n"
                f"┃ ⏰ Expires: {expiry_date.strftime('%Y-%m-%d')}\n"
                f"┃ 📅 Days: {days}\n"
                f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
        else:
            response = (
                f"<b>✅ USER ADDED!</b>\n"
                f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ 🆔 ID: <code>{user_id}</code>\n"
                f"┃ ⏰ Access: Permanent\n"
                f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
        
        bot.reply_to(message, response)
        
        try:
            welcome_msg = (
                "<b>🎉 ACCESS GRANTED</b>\n"
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ You've been authorized!\n"
            )
            if days:
                welcome_msg += f"┃ ⏰ Expires: {days} days\n"
            else:
                welcome_msg += "┃ ⏰ Permanent access\n"
            welcome_msg += (
                "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                "Type /start to begin!"
            )
            
            bot.send_message(user_id, welcome_msg)
        except:
            pass
        
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID or days value.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['remove'])
def admin_remove_user(message):
    if message.chat.id not in ADMIN_IDS:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(
                message, 
                "<b>❌ Invalid Usage</b>\n\n"
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ /remove {user_id}\n"
                "┗━━━━━━━━━━━━━━━━━━━┛"
            )
            return
        
        user_id = int(parts[1])
        
        if remove_user(user_id):
            response = (
                f"<b>✅ USER REMOVED!</b>\n"
                f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ 🆔 ID: <code>{user_id}</code>\n"
                f"┃ Access revoked\n"
                f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
            
            try:
                bot.send_message(
                    user_id, 
                    "<b>🚫 ACCESS REVOKED</b>\n\n"
                    "┏━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃ Your access has been removed\n"
                    "┃ Contact admin for info\n"
                    "┗━━━━━━━━━━━━━━━━━━━┛"
                )
            except:
                pass
        else:
            response = (
                f"<b>❌ NOT FOUND</b>\n\n"
                f"┏━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃ User <code>{user_id}</code> not in list\n"
                f"┗━━━━━━━━━━━━━━━━━━━┛"
            )
        
        bot.reply_to(message, response)
        
    except ValueError:
        bot.reply_to(message, "❌ Invalid user ID.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['list'])
def admin_list_users(message):
    if message.chat.id not in ADMIN_IDS:
        return
    
    if not authorized_users:
        bot.reply_to(message, "📝 No authorized users yet.")
        return
    
    user_list = (
        "<b>👥 AUTHORIZED USERS</b>\n"
        "┏━━━━━━━━━━━━━━━━━━━┓\n\n"
    )
    
    for user_id, expiry in authorized_users.items():
        try:
            user_info = get_tg_username(user_id)
        except:
            user_info = "Unknown"
        
        status = "✅" if is_user_authorized(user_id) else "❌"
        
        if expiry:
            days_left = (expiry - datetime.now()).days
            if days_left > 0:
                expiry_text = f"{days_left} days left"
            else:
                expiry_text = "EXPIRED"
        else:
            expiry_text = "Permanent"
        
        user_list += (
            f"{status} <code>{user_id}</code> - {user_info}\n"
            f"   ⏰ {expiry_text}\n\n"
        )
    
    user_list += "┗━━━━━━━━━━━━━━━━━━━┛"
    
    bot.reply_to(message, user_list)

@bot.message_handler(commands=['allusers'])
def admin_all_users(message):
    if message.chat.id not in ADMIN_IDS:
        return
    
    if not user_database:
        bot.reply_to(message, "📝 No users in database yet.")
        return
    
    user_list = (
        "<b>👥 ALL USERS DATABASE</b>\n"
        "┏━━━━━━━━━━━━━━━━━━━┓\n\n"
    )
    
    for user_id, info in user_database.items():
        auth_status = "✅" if is_user_authorized(user_id) else "🚫"
        username_display = f"@{info['username']}" if info['username'] else "No username"
        
        user_list += (
            f"{auth_status} <code>{user_id}</code>\n"
            f"   👤 {info['first_name']} {info['last_name']}\n"
            f"   🏷 {username_display}\n"
            f"   🕐 First: {info['first_seen']}\n"
            f"   🕐 Last: {info['last_seen']}\n\n"
        )
    
    user_list += "┗━━━━━━━━━━━━━━━━━━━┛"
    
    if len(user_list) > 4000:
        chunks = [user_list[i:i+4000] for i in range(0, len(user_list), 4000)]
        for chunk in chunks:
            bot.send_message(message.chat.id, chunk)
    else:
        bot.reply_to(message, user_list)

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if message.chat.id not in ADMIN_IDS:
        return
    msg = bot.send_message(
        message.chat.id, 
        "<b>✉️ BROADCAST MESSAGE</b>\n\n"
        "┏━━━━━━━━━━━━━━━━━━━┓\n"
        "┃ Enter message below:\n"
        "┗━━━━━━━━━━━━━━━━━━━┛"
    )
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    text = message.text
    success = 0
    failed = 0
    
    for user_id in user_database.keys():
        if is_user_authorized(user_id):
            try:
                bot.send_message(
                    user_id, 
                    f"<b>📢 ADMIN BROADCAST</b>\n\n"
                    f"{text}\n"
                )
                success += 1
            except Exception as e:
                failed += 1
                print(f"Failed to send to {user_id}: {e}")
    
    bot.send_message(
        message.chat.id, 
        f"<b>📊 BROADCAST COMPLETE</b>\n\n"
        f"┏━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ ✅ Sent: {success}\n"
        f"┃ ❌ Failed: {failed}\n"
        f"┗━━━━━━━━━━━━━━━━━━━┛"
    )

# ---------------- START ---------------- #
print("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
print("┃ INSTA REPORTER BOT STARTED ┃")
print("┃ USER MANAGEMENT: ENABLED   ┃")
print("┃ ENHANCED UI: ACTIVE        ┃")
print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
bot.infinity_polling()
