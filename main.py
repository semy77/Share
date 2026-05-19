import json
import os
import requests
import telebot
import pytz
import time
import base64

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread

# ================= CONFIG =================

TOKEN = "8685204975:AAFHRmp9VbIWQXzYnzo0pMh4NMiaGgyPakw"

GITHUB_TOKEN = "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"

REPO_NAME = "semy77/Likkkkkkkk"

FILE_NAME = "token_ind.json"

INPUT_FILE = "ind.json"

API_URL = "https://papajwt.vercel.app/kirito?uid={uid}&password={password}"

IST = pytz.timezone("Asia/Kolkata")

# ==========================================

bot = telebot.TeleBot(TOKEN)

# ================= TOKEN GENERATOR =================

def get_token(acc):
    uid = acc.get("uid")
    password = acc.get("password")

    try:
        url = API_URL.format(uid=uid, password=password)

        r = requests.get(url, timeout=20)

        data = r.json()

        if data.get("success"):

            return {
                "token": data.get("jwt")
            }

    except Exception as e:
        print(f"ERROR {uid}: {e}")

    return None

# ================= GITHUB UPLOAD =================

def upload_to_github(tokens):

    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_NAME}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    sha = None

    # Existing file SHA
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        sha = r.json()["sha"]

    content = json.dumps(tokens, indent=2).encode("utf-8")

    data = {
        "message": f"Auto Update {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}",
        "content": base64.b64encode(content).decode("utf-8"),
        "branch": "main"
    }

    if sha:
        data["sha"] = sha

    upload = requests.put(url, headers=headers, json=data)

    if upload.status_code in [200, 201]:
        return True

    return upload.text

# ================= MAIN PROCESS =================

def process_and_upload():

    if not os.path.exists(INPUT_FILE):
        return "❌ ind.json file not found"

    try:

        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)

    except Exception as e:
        return f"❌ JSON ERROR:\n{e}"

    tokens = []

    # Fast processing
    with ThreadPoolExecutor(max_workers=10) as executor:

        futures = [
            executor.submit(get_token, acc)
            for acc in accounts
        ]

        for future in as_completed(futures):

            try:
                res = future.result()

                if res:
                    tokens.append(res)

            except:
                pass

    if not tokens:
        return "❌ No tokens generated"

    # Upload to GitHub
    result = upload_to_github(tokens)

    if result is True:

        return (
            f"✅ SUCCESS\n\n"
            f"🔥 Total Tokens: {len(tokens)}\n"
            f"📂 Uploaded To GitHub"
        )

    return f"❌ GitHub Upload Failed\n\n{result}"

# ================= SCHEDULER =================

def scheduler():

    already_run = False

    while True:

        now = datetime.now(IST)

        # 04:05 AM IST
        if now.hour == 4 and now.minute == 5:

            if not already_run:

                result = process_and_upload()

                print(result)

                already_run = True

        else:
            already_run = False

        time.sleep(30)

# ================= BOT COMMANDS =================

@bot.message_handler(commands=['start'])
def start(message):

    chat_id = message.chat.id

    markup = telebot.types.InlineKeyboardMarkup()

    btn = telebot.types.InlineKeyboardButton(
        "🚀 Generate Tokens",
        callback_data="generate"
    )

    markup.add(btn)

    bot.reply_to(
        message,
        f"""
🔥 TOKEN AUTOMATION BOT

🆔 Chat ID: {chat_id}

⏰ Schedule:
04:05 AM IST

✅ Python 3.13 Supported
✅ GitHub Upload
✅ Auto Scheduler
""",
        reply_markup=markup
    )

# ================= BUTTON =================

@bot.callback_query_handler(func=lambda call: call.data == "generate")
def generate(call):

    bot.edit_message_text(
        "⏳ Processing...\nPlease wait...",
        call.message.chat.id,
        call.message.message_id
    )

    result = process_and_upload()

    bot.send_message(
        call.message.chat.id,
        result
    )

# ================= THREAD START =================

Thread(
    target=scheduler,
    daemon=True
).start()

print("🤖 Bot Running Successfully...")

# ================= START BOT =================

bot.infinity_polling(skip_pending=True)