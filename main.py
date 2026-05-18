import os
import json
import random
import string
from collections import defaultdict
import telebot
from telebot import types

# --- CONFIGURATION ---
BOT_TOKEN = "8943507427:AAHlkMj7g-wX6LfGTyj7UZ9qUvbqLVsjrBc"          # Apna Bot Token yahan dalein
BOT_USERNAME = "SHARE_MYFILE_BOT"    # Bina @ ke bot ka username dalein
OWNER_ID = 7898402627                       # Bot Owner ki Telegram ID
OFFICIAL_CHANNEL_ID = -1003849265448      # Permanent Official Channel ID (e.g., -100...)
OFFICIAL_CHANNEL_LINK = "https://t.me/SEMY_FF"

# 🔴 BACKUP DATABASE CHANNEL ID: Saari files ko permanently store karne ke liye
# Bot is channel me Admin hona chahiye message send karne ke liye.
DB_CHANNEL_ID = -1003839220077            

bot = telebot.TeleBot(BOT_TOKEN)

# --- DATA STORAGE ---
DATA_FILE = "bots.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                if "users" not in data: data["users"] = {}
                if "files" not in data: data["files"] = {}
                return data
        except:
            return {"users": {}, "files": {}}
    return {"users": {}, "files": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Global data structure
db = load_data()

# Temporary User Sessions (State Management)
user_sessions = defaultdict(lambda: {
    "state": None, 
    "required_count": 0, 
    "selected_channels": [], 
    "temp_link": None, 
    "temp_id": None
})

# --- HELPER FUNCTIONS ---
def generate_slug(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def init_user(user_id):
    user_id = str(user_id)
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "channels": [],       
            "projects": [],       
            "stats": 0            
        }
        save_data(db)
    else:
        # 🟢 CRASH FIX: Agar naye updates ki wajah se koi key missing ho toh auto-add karein
        if "projects" not in db["users"][user_id]:
            db["users"][user_id]["projects"] = []
        if "stats" not in db["users"][user_id]:
            db["users"][user_id]["stats"] = 0
        if "channels" not in db["users"][user_id]:
            db["users"][user_id]["channels"] = []
        save_data(db)

def check_join(user_id, channel_id):
    try:
        member = bot.get_chat_member(channel_id, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"Error checking channel {channel_id}: {e}")
        return False

# --- KEYBOARDS (MAIN MENU) ---
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_create = types.KeyboardButton("🔗 CREATE NEW")
    btn_project = types.KeyboardButton("🤖 MY PROJECT")
    btn_stats = types.KeyboardButton("🧾 MY STATISTICS")
    markup.row(btn_create, btn_project)
    markup.row(btn_stats)
    return markup

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    init_user(user_id)
    
    # State reset on /start to avoid overlapping buttons
    user_sessions[user_id] = {"state": None, "required_count": 0, "selected_channels": [], "temp_link": None, "temp_id": None}
    
    text_args = message.text.split()
    
    if len(text_args) > 1:
        slug = text_args[1]
        if slug in db.get("files", {}):
            file_data = db["files"][slug]
            
            # Force Join Checking System
            must_join = []
            if not check_join(user_id, OFFICIAL_CHANNEL_ID):
                must_join.append(("📢 Official Channel", OFFICIAL_CHANNEL_LINK))
                
            for ch in file_data.get("channels", []):
                if not check_join(user_id, ch["id"]):
                    must_join.append((f"🔒 Join Channel", ch["link"]))
            
            if must_join:
                # row_width=1 se saare buttons alag alag clean line me aayenge
                markup = types.InlineKeyboardMarkup(row_width=1)
                for name, link in must_join:
                    markup.add(types.InlineKeyboardButton(text=name, url=link))
                markup.add(types.InlineKeyboardButton(text="Verify ✅", callback_data=f"verify_{slug}"))
                
                bot.send_message(
                    message.chat.id, 
                    "⚠️ **Access Denied!**\n\nFile download karne ke liye aapko hamare saare channels join karne honge. Niche diye gaye buttons par click karke join karein aur 'Verify ✅' dabayein.", 
                    reply_markup=markup, 
                    parse_mode="Markdown"
                )
                return
            else:
                deliver_file(message.chat.id, file_data, slug)
                return
        else:
            bot.send_message(message.chat.id, "❌ Link invalid hai ya file delete ho chuki hai.")
            return

    bot.send_message(
        message.chat.id, 
        "👋 **Welcome to Advanced File Sharing Bot!**\n\nYahan aap apni files ko secure force-join ke sath share kar sakte hain.", 
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

def deliver_file(chat_id, file_data, slug):
    creator_id = str(file_data["creator"])
    if creator_id in db["users"]:
        db["users"][creator_id]["stats"] += 1
        save_data(db)
        
    bot.send_message(chat_id, "🎉 **Verification Successful!** Aapki file niche bheji ja rahi hai 👇", parse_mode="Markdown")
    
    try:
        # File direct database backup channel se safely copy hogi
        bot.copy_message(chat_id, DB_CHANNEL_ID, file_data["db_message_id"])
    except Exception as e:
        bot.send_message(chat_id, "❌ File send karne me koi problem aayi. Ensure karein ki bot backup channel me admin hai.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('verify_'))
def handle_verification(call):
    user_id = call.from_user.id
    slug = call.data.split('_')[1]
    
    if slug not in db.get("files", {}):
        bot.answer_callback_query(call.id, "❌ File data nahi mila.")
        return
        
    file_data = db["files"][slug]
    must_join = []
    
    if not check_join(user_id, OFFICIAL_CHANNEL_ID):
        must_join.append(("📢 Official Channel", OFFICIAL_CHANNEL_LINK))
        
    for ch in file_data.get("channels", []):
        if not check_join(user_id, ch["id"]):
            must_join.append((f"🔒 Join Partner Channel", ch["link"]))
            
    if must_join:
        bot.answer_callback_query(call.id, "❌ Aapne abhi tak saare channels join nahi kiye hain!", show_alert=True)
        
        # Keyboard refresh taaki joined channel ka button hat jaye
        markup = types.InlineKeyboardMarkup(row_width=1)
        for name, link in must_join:
            markup.add(types.InlineKeyboardButton(text=name, url=link))
        markup.add(types.InlineKeyboardButton(text="Verify ✅", callback_data=f"verify_{slug}"))
        
        try:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "✅ Verified successfully!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        deliver_file(call.message.chat.id, file_data, slug)

# --- REPLY MENU ACTIONS ---
@bot.message_handler(func=lambda msg: msg.text in ["🔗 CREATE NEW", "🤖 MY PROJECT", "🧾 MY STATISTICS"])
def handle_menu_clicks(message):
    user_id = message.from_user.id
    init_user(user_id)
    
    # Reset sessions on tab switch to avoid hanging states
    user_sessions[user_id] = {"state": None, "required_count": 0, "selected_channels": [], "temp_link": None, "temp_id": None}
    
    if message.text == "🔗 CREATE NEW":
        markup = types.InlineKeyboardMarkup(row_width=4)
        buttons = [types.InlineKeyboardButton(text=f"{i} Channel", callback_data=f"setch_{i}") for i in range(1, 9)]
        markup.add(*buttons)
        
        bot.send_message(
            message.chat.id, 
            "🔢 **How many channels do you want to add for this file project?**\nMaximum 8 channels select kar sakte hain.", 
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    elif message.text == "🤖 MY PROJECT":
        user_data = db["users"][str(user_id)]
        projects = user_data.get("projects", [])
        
        if not projects:
            bot.send_message(message.chat.id, "📂 Aapne abhi tak koi project nahi banaya hai.")
            return
            
        markup = types.InlineKeyboardMarkup(row_width=1)
        for slug in projects:
            if slug in db["files"]:
                markup.add(types.InlineKeyboardButton(text=f"📁 Project: {slug}", callback_data=f"viewproj_{slug}"))
                
        bot.send_message(message.chat.id, "🤖 **Aapke banaye gaye Projects:**", reply_markup=markup, parse_mode="Markdown")
        
    elif message.text == "🧾 MY STATISTICS":
        user_data = db["users"][str(user_id)]
        total_clicks = user_data.get("stats", 0)
        total_proj = len(user_data.get("projects", []))
        
        stats_text = (
            "🧾 **YOUR BOT STATISTICS**\n\n"
            f"👤 **Total Users Directed:** {total_clicks}\n"
            f"📁 **Total Projects Created:** {total_proj}\n\n"
            "Data is updated in real-time ⚡"
        )
        bot.send_message(message.chat.id, stats_text, parse_mode="Markdown")

def generate_channel_selector(user_id):
    session = user_sessions[user_id]
    user_data = db["users"][str(user_id)]
    user_channels = user_data.get("channels", [])
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch in user_channels:
        ch_id = ch["id"]
        status_emoji = "🟢" if ch_id in session["selected_channels"] else "🔴"
        btn_text = f"{status_emoji} {ch['link']}"
        markup.add(types.InlineKeyboardButton(text=btn_text, callback_data=f"togglech_{ch_id}"))
        
    markup.add(types.InlineKeyboardButton(text="Done ✅", callback_data="channels_done"))
    markup.add(types.InlineKeyboardButton(text="➕ Add New Channel", callback_data="add_new_channel"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith(('setch_', 'togglech_', 'channels_done', 'add_new_channel', 'viewproj_')))
def handle_creation_callbacks(call):
    user_id = call.from_user.id
    action = call.data
    
    if action.startswith("setch_"):
        count = int(action.split("_")[1])
        user_sessions[user_id]["required_count"] = count
        user_sessions[user_id]["state"] = "selecting_channels"
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⚙️ **Select exactly {count} channels** from below list or add new ones:",
            reply_markup=generate_channel_selector(user_id),
            parse_mode="Markdown"
        )
        
    elif action.startswith("togglech_"):
        ch_id = int(action.split("_")[1])
        session = user_sessions[user_id]
        
        if ch_id in session["selected_channels"]:
            session["selected_channels"].remove(ch_id)
        else:
            if len(session["selected_channels"]) >= session["required_count"]:
                bot.answer_callback_query(call.id, f"❌ Aap sirf {session['required_count']} channels hi select kar sakte hain!", show_alert=True)
                return
            session["selected_channels"].append(ch_id)
            
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=generate_channel_selector(user_id))
        bot.answer_callback_query(call.id, "Updated!")

    elif action == "add_new_channel":
        user_sessions[user_id]["state"] = "wait_ch_link"
        bot.send_message(call.message.chat.id, "⚠️ **Important:** Pehle bot ko us channel me **Admin** banayein.\n\n👉 Ab channel ka **Public Link** bhejein (e.g., https://t.me/example):")
        bot.answer_callback_query(call.id)

    elif action == "channels_done":
        session = user_sessions[user_id]
        if len(session["selected_channels"]) != session["required_count"]:
            bot.answer_callback_query(call.id, f"❌ Please select exactly {session['required_count']} channels before pressing Done!", show_alert=True)
            return
            
        session["state"] = "wait_for_file"
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📥 **Channels Saved!**\n\nAb mujhe wo **File, Video, Image ya Text Message** bhejiye jiska aap link banana chahte hain."
        )
        bot.answer_callback_query(call.id)
        
    elif action.startswith("viewproj_"):
        slug = action.split("_")[1]
        if slug in db.get("files", {}):
            f_data = db["files"][slug]
            if f_data["creator"] == user_id:
                link = f"https://t.me/{BOT_USERNAME}?start={slug}"
                bot.send_message(call.message.chat.id, f"🔗 **Your Project Link:**\n`{link}`", parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "❌ Permission Denied.")
        else:
            bot.answer_callback_query(call.id, "Project not found.")

# --- TEXT & FILE INPUT HANDLING ---
@bot.message_handler(content_types=['text', 'document', 'video', 'photo', 'audio', 'voice'])
def handle_inputs(message):
    user_id = message.from_user.id
    session = user_sessions[user_id]
    state = session["state"]
    
    if not state:
        return 
        
    if state == "wait_ch_link":
        if message.text and ("t.me/" in message.text or "@" in message.text):
            session["temp_link"] = message.text
            session["state"] = "wait_ch_id"
            bot.send_message(message.chat.id, "🆔 Ab mujhe us channel ki **ID** bhejiye (e.g., `-100123456789`):")
        else:
            bot.send_message(message.chat.id, "❌ Invalid link. Please enter correct telegram channel link.")
            
    elif state == "wait_ch_id":
        try:
            ch_id = int(message.text)
            user_data = db["users"][str(user_id)]
            
            if any(ch["id"] == ch_id for ch in user_data.get("channels", [])):
                bot.send_message(message.chat.id, "⚠️ Yeh channel pehle se added hai!")
            else:
                user_data["channels"].append({"id": ch_id, "link": session["temp_link"]})
                save_data(db)
                bot.send_message(message.chat.id, "🟢 **Channel Added Successfully!**")
            
            session["state"] = "selecting_channels"
            bot.send_message(message.chat.id, f"⚙️ **Select channels ({session['required_count']} required):**", reply_markup=generate_channel_selector(user_id))
        except ValueError:
            bot.send_message(message.chat.id, "❌ Invalid ID format. Channel ID hamesha number me hoti hai (jaise -100...)")

    elif state == "wait_for_file":
        try:
            # File ko Main Database Channel par copy karke permanent save kiya ja raha hai
            forwarded_msg = bot.copy_message(chat_id=DB_CHANNEL_ID, from_chat_id=message.chat.id, message_id=message.message_id)
            db_message_id = forwarded_msg.message_id
            
            slug = generate_slug()
            user_channels = db["users"][str(user_id)].get("channels", [])
            final_channels = [ch for ch in user_channels if ch["id"] in session["selected_channels"]]
            
            db["files"][slug] = {
                "creator": user_id,
                "db_message_id": db_message_id, 
                "channels": final_channels
            }
            
            db["users"][str(user_id)]["projects"].append(slug)
            save_data(db)
            
            # Session Reset completely
            user_sessions[user_id] = {"state": None, "required_count": 0, "selected_channels": [], "temp_link": None, "temp_id": None}
            
            share_link = f"https://t.me/{BOT_USERNAME}?start={slug}"
            success_text = (
                "🚀 **Project Created Successfully!**\n\n"
                f"🔗 **Your Shareable Link:** `{share_link}`"
            )
            bot.send_message(message.chat.id, success_text, reply_markup=get_main_menu(), parse_mode="Markdown")
            
        except Exception as e:
            print(f"Backup failed: {e}")
            bot.send_message(message.chat.id, "❌ **Error:** Bot aapki file ko database channel me save nahi kar paya. Ensure karein ki bot Backup channel me admin hai.")

# --- POLLING ---
if __name__ == "__main__":
    print("🤖 Bot runs cleanly now...")
    bot.infinity_polling(skip_pending=True)
