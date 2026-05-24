import asyncio
import os
import sys
import logging
import subprocess
import psutil
import sqlite3
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8624297353:AAFjqxZ7F-MnMSeicX4bHRQ2i3PkzD-k3E0"
OWNER_ID = 7898402627
YOUR_USERNAME = "SEMY0HERE"
UPDATE_CHANNEL = "https://t.me/YourChannel"

BASE_DIR = Path(__file__).parent.absolute()
SERVERS_DIR = BASE_DIR / 'hosted_servers'  # जहाँ हर सर्वर का अलग venv होगा
DATABASE_PATH = BASE_DIR / 'bot_data.db'

SERVERS_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# एक्टिव रनिंग सर्वर्स को ट्रैक करने के लिए डिक्शनरी
# { user_id: { server_id: { "process": subprocess, "path": Path, "file": name } } }
running_servers = {}

# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS servers
                 (server_id TEXT PRIMARY KEY, user_id INTEGER, name TEXT, path TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HELPER KEYBOARDS ---
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Updates", url=UPDATE_CHANNEL)],
        [InlineKeyboardButton(text="📤 Host File", callback_data="host_file"),
         InlineKeyboardButton(text="📥 Download Files", callback_data="download_files")],
        [InlineKeyboardButton(text="⚡ Bot Speed", callback_data="bot_speed"),
         InlineKeyboardButton(text="🤖 Running Bots", callback_data="running_bots")],
        [InlineKeyboardButton(text="💬 Contact Owner", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")]
    ])
    return keyboard

# --- COMMAND HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = f"""
╔═══════════════════════╗
    🚀 <b>MINI VPS HOSTING BOT</b> 🚀
╚═══════════════════════╝

👋 <b>Hi, {message.from_user.full_name}!</b>
यहाँ आप अपनी Python या ZIP फ़ाइलें अपलोड करके उन्हें एक अलग आइसोलेटेड सर्वर (Mini VPS) पर होस्ट कर सकते हैं।

• <b>Auto-pip:</b> <code>requirements.txt</code> डिटेक्ट होने पर लाइब्रेरी खुद इंस्टॉल होंगी।
• <b>Server Isolation:</b> हर होस्ट का अपना अलग सर्वर होगा।
"""
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# --- CALLBACK HANDLERS ---
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 <b>Main Menu</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "host_file")
async def host_file_info(callback: types.CallbackQuery):
    text = """
📤 <b>HOST NEW FILE / SERVER</b>

<b>स्टेप्स:</b>
1. बोट को सीधे एक <code>.py</code> फ़ाइल या <code>.zip</code> फ़ाइल भेजें।
2. अगर ज़िप फ़ाइल है, तो सुनिश्चित करें कि मुख्य फ़ाइल का नाम <code>bot.py</code> या <code>main.py</code> हो।
3. डिपेंडेंसी के लिए ज़िप में <code>requirements.txt</code> जरूर डालें।
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🏠 Back", callback_data="back_to_main")]]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

# --- FILE UPLOAD & VPS CREATION LOGIC ---
@dp.message(F.document)
async def handle_docs(message: types.Message):
    user_id = message.from_user.id
    document = message.document
    file_name = document.file_name
    
    if not (file_name.endswith('.py') or file_name.endswith('.zip')):
        await message.answer("❌ सिर्फ .py और .zip फ़ाइलें ही होस्ट की जा सकती हैं!")
        return
        
    status_msg = await message.answer("📥 फ़ाइल डाउनलोड की जा रही है और सर्वर क्रिएट हो रहा है...")
    
    # सर्वर के लिए यूनिक आईडी और पाथ बनाना
    server_id = f"srv_{user_id}_{int(datetime.now().timestamp())}"
    server_path = SERVERS_DIR / server_id
    server_path.mkdir(parents=True, exist_ok=True)
    
    file_path = server_path / file_name
    await bot.download(document, destination=file_path)
    
    await status_msg.edit_text("⚙️ <b>Mini VPS सेटअप हो रहा है... Virtual Environment बनाया जा रहा है...</b>", parse_mode="HTML")
    
    # 1. Virtual Environment (venv) बनाना ताकि हर सर्वर अलग रहे
    venv_path = server_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    
    # OS के हिसाब से pip और python का पाथ सेट करना
    pip_exe = venv_path / "bin" / "pip" if os.name != 'nt' else venv_path / "Scripts" / "pip.exe"
    python_exe = venv_path / "bin" / "python" if os.name != 'nt' else venv_path / "Scripts" / "python.exe"
    
    # 2. अगर ZIP है तो उसे अनज़िप करना
    main_script = file_path
    if file_name.endswith('.zip'):
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(server_path)
        
        # मुख्य फ़ाइल खोजना
        if (server_path / "main.py").exists():
            main_script = server_path / "main.py"
        elif (server_path / "bot.py").exists():
            main_script = server_path / "bot.py"
        else:
            # अगर कोई मुख्य फ़ाइल न मिले तो पहली उपलब्ध .py फ़ाइल चुनना
            py_files = list(server_path.glob("*.py"))
            if py_files: main_script = py_files[0]
            
        # 3. requirements.txt चेक करके लाइब्रेरी इंस्टॉल करना
        req_path = server_path / "requirements.txt"
        if req_path.exists():
            await status_msg.edit_text("📦 <code>requirements.txt</code> मिल गया! लाइब्रेरीज़ इन्सटॉल हो रही हैं, कृपया प्रतीक्षा करें...", parse_mode="HTML")
            subprocess.run([str(pip_exe), "install", "-r", str(req_path)], check=True)

    await status_msg.edit_text("🚀 <b>सर्वर लॉन्च हो रहा है...</b>", parse_mode="HTML")
    
    # 4. स्क्रिप्ट को बैकग्राउंड प्रोसेस के रूप में अलग सर्वर पर स्टार्ट करना
    try:
        process = subprocess.Popen([str(python_exe), str(main_script)], cwd=str(server_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # ट्रैक करने के लिए डिक्शनरी में सेव करना
        if user_id not in running_servers:
            running_servers[user_id] = {}
        running_servers[user_id][server_id] = {"process": process, "path": server_path, "file": file_name}
        
        # डेटाबेस में एंट्री
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO servers VALUES (?, ?, ?, ?, 'RUNNING')", (server_id, user_id, file_name, str(server_path)))
        conn.commit()
        conn.close()
        
        await status_msg.edit_text(f"✅ <b>सर्वर सफलतापूर्वक होस्ट हो गया!</b>\n\n🆔 Server ID: <code>{server_id}</code>\n📂 फ़ाइल: {file_name}\n🟢 स्टेटस: Running (Isolated VPS Mode)", parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        await status_msg.edit_text(f"❌ सर्वर स्टार्ट करने में एरर आया: {e}")

# --- RUNNING BOTS (SERVER MANAGER) ---
@dp.callback_query(F.data == "running_bots")
async def show_running_bots(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_servers = running_servers.get(user_id, {})
    
    if not user_servers:
        await callback.message.edit_text("🤖 <b>कोई भी सर्वर अभी रन नहीं कर रहा है।</b>", parse_mode="HTML", reply_markup=get_main_keyboard())
        return
        
    text = "🤖 <b>आपके एक्टिव सर्वर्स (Mini VPS):</b>\n\n"
    buttons = []
    
    for srv_id, srv_data in user_servers.items():
        text += f"🖥️ <b>ID:</b> <code>{srv_id}</code>\n📦 <b>फ़ाइल:</b> {srv_data['file']}\n\n"
        buttons.append([InlineKeyboardButton(text=f"🛑 Stop {srv_data['file'][:15]}", callback_data=f"stop_srv:{srv_id}")])
        
    buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("stop_srv:"))
async def stop_server(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    server_id = callback.data.split(":")[1]
    
    if user_id in running_servers and server_id in running_servers[user_id]:
        # प्रोसेस बंद करना
        process = running_servers[user_id][server_id]["process"]
        process.terminate()
        del running_servers[user_id][server_id]
        
        # डेटाबेस अपडेट
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM servers WHERE server_id = ?", (server_id,))
        conn.commit()
        conn.close()
        
        await callback.answer("🛑 सर्वर बंद कर दिया गया है!", show_alert=True)
        await show_running_bots(callback)
    else:
        await callback.answer("❌ सर्वर नहीं मिला!", show_alert=True)

# --- DOWNLOAD FILES & SERVER EXPLORER ---
@dp.callback_query(F.data == "download_files")
async def download_files_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # डेटाबेस से इस यूजर के सभी सर्वर्स (चाहे रनिंग हों या स्टॉप) निकालना
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT server_id, name FROM servers WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await callback.message.edit_text("📂 <b>कोई भी सर्ver फ़ोल्डर उपलब्ध नहीं है।</b>", parse_mode="HTML", reply_markup=get_main_keyboard())
        return
        
    text = "📥 <b>नीचे दिए गए सर्वर पर क्लिक करके उसकी सभी फ़ाइलें प्राप्त करें:</b>\n"
    buttons = []
    for srv_id, name in rows:
        buttons.append([InlineKeyboardButton(text=f"📂 Explore: {name[:20]}", callback_data=f"explore_srv:{srv_id}")])
        
    buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("explore_srv:"))
async def explore_and_send_files(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    server_id = callback.data.split(":")[1]
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM servers WHERE server_id = ?", (server_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await callback.answer("❌ सर्वर पाथ नहीं मिला!", show_alert=True)
        return
        
    server_path = Path(row[0])
    if not server_path.exists():
        await callback.answer("❌ सर्वर फ़ोल्डर सर्वर से डिलीट हो चुका है!", show_alert=True)
        return
        
    await callback.message.answer(f"📦 <b>सर्वर ({server_id}) की फ़ाइलें निकाली जा रही हैं और भेजी जा रही हैं...</b>", parse_mode="HTML")
    
    # सर्वर फ़ोल्डर के अंदर की सभी मुख्य फ़ाइलें ढूंढना (venv फ़ोल्डर को छोड़कर)
    files_sent = 0
    for item in server_path.rglob("*"):
        if item.is_file() and "venv" not in item.parts:
            try:
                # टेलीग्राम पर फ़ाइल भेजना
                await callback.message.reply_document(document=FSInputFile(str(item)), caption=f"📄 फ़ाइल: <code>{item.name}</code>", parse_mode="HTML")
                files_sent += 1
                await asyncio.sleep(0.5) # फ्लडिंग से बचने के लिए छोटा गैप
            except Exception as e:
                logger.error(f"Error sending file {item.name}: {e}")
                
    if files_sent == 0:
        await callback.message.answer("⚠️ इस सर्वर फ़ोल्डर में कोई फ़ाइल नहीं मिली।")
    await callback.answer()

# --- BOT SPEED ---
@dp.callback_query(F.data == "bot_speed")
async def callback_bot_speed(callback: types.CallbackQuery):
    start_time = datetime.now()
    await callback.answer("⚡ Speed Testing...")
    end_time = datetime.now()
    speed = (end_time - start_time).total_seconds() * 1000
    
    text = f"╔═══════════════════════╗\n    ⚡ <b>SPEED TEST</b> ⚡\n╚═══════════════════════╝\n\n🚀 <b>Response Time:</b> {speed:.2f}ms\n🖥️ <b>CPU Usage:</b> {psutil.cpu_percent()}%\n📊 <b>Memory:</b> {psutil.virtual_memory().percent}%"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

# --- START BOT ---
async def main():
    logger.info("Starting up the Ultra Host Bot...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
