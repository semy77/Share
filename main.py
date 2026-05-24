import asyncio
import os
import sys
import logging
import subprocess
import shutil
import zipfile
import sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Apne credentials .env file mein rakhein ya yahan direct dalein
TOKEN = "8624297353:AAFs7rcku6gaULup0M-It5YP7dCMVVo2czA"
ADMIN_ID = 7898402627

BASE_DIR = Path(__file__).parent.absolute()
SERVERS_DIR = BASE_DIR / 'vps_hosted_bots'
DATABASE_PATH = BASE_DIR / 'vps_manager.db'

SERVERS_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Active processes ko track karne ke liye memory dict
# { server_id: subprocess.Popen }
active_processes = {}

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vps_bots
                 (server_id TEXT PRIMARY KEY, name TEXT, path TEXT, main_file TEXT, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- SECURITY CHECK DECORATOR ---
def is_admin(user_id: int):
    return user_id == ADMIN_ID

# --- KEYBOARDS ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Host New Bot (.py / .zip)", callback_data="host_new")],
        [InlineKeyboardButton(text="🖥️ Manage Hosted Bots", callback_data="manage_bots")],
        [InlineKeyboardButton(text="📊 VPS System Status", callback_data="vps_status")]
    ])

# --- COMMANDS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Unauthorized! Aap is VPS ke master nahi hain.")
        return
    
    welcome_text = """
🖥️ <b>WELCOME TO MASTER VPS CONTROLLER</b> 🖥️
-----------------------------------------
Aap apne is Telegram Bot se poore VPS par chalne wale baki bots ko asani se manage kar sakte hain.

• Har bot ka data alag folder mein safe rahega.
• Live logs aur errors check kar sakte hain.
• Kisi bhi bot ko kabhi bhi Start/Stop/Delete kar sakte hain.
"""
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

# --- CALLBACKS ---
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("🎮 <b>Master Control Panel Menu:</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data == "host_new")
async def host_new_info(callback: types.CallbackQuery):
    text = """
📤 <b>HOW TO HOST A NEW BOT:</b>

1. Is chat mein direct ek <code>.py</code> file ya ek <code>.zip</code> file bhejein.
2. Agar `.zip` file hai, toh uske andar main file ka naam <code>bot.py</code> ya <code>main.py</code> rakhein.
3. Dependencies automatic install karne ke liye zip ke andar <code>requirements.txt</code> zaroor daalein.
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")]]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

# --- FILE UPLOADING & DEPLOYMENT LOGIC ---
@dp.message(F.document)
async def handle_bot_upload(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    doc = message.document
    filename = doc.file_name

    if not (filename.endswith('.py') or filename.endswith('.zip')):
        await message.answer("❌ Error: Sirf `.py` ya `.zip` format ki files hi accepted hain!")
        return

    status_msg = await message.answer("⏳ File received! Isolate space create ho rahi hai...")

    # Unique Server ID generation
    server_id = f"bot_{int(datetime.now().timestamp())}"
    bot_dir = SERVERS_DIR / server_id
    bot_dir.mkdir(parents=True, exist_ok=True)

    # Download File
    destination_path = bot_dir / filename
    await bot.download(doc, destination=destination_path)

    await status_msg.edit_text("⚙️ Creating Virtual Environment (venv)...")
    
    # Virtual Environment Create karna taaki data/libraries mix na hon
    venv_path = bot_dir / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

    pip_exe = venv_path / "bin" / "pip" if os.name != 'nt' else venv_path / "Scripts" / "pip.exe"
    python_exe = venv_path / "bin" / "python" if os.name != 'nt' else venv_path / "Scripts" / "python.exe"

    main_script = destination_path

    # Extract if ZIP
    if filename.endswith('.zip'):
        await status_msg.edit_text("📦 Extracting ZIP files...")
        with zipfile.ZipFile(destination_path, 'r') as zip_ref:
            zip_ref.extractall(bot_dir)
        
        # Main file identification
        if (bot_dir / "main.py").exists():
            main_script = bot_dir / "main.py"
        elif (bot_dir / "bot.py").exists():
            main_script = bot_dir / "bot.py"
        else:
            py_files = list(bot_dir.glob("*.py"))
            if py_files:
                main_script = py_files[0]

        # Requirements installation
        req_file = bot_dir / "requirements.txt"
        if req_file.exists():
            await status_msg.edit_text("⏳ Installing requirements.txt (Isme thoda time lag sakta hai)...")
            subprocess.run([str(pip_exe), "install", "-r", str(req_file)], check=True)

    # Log files paths for Output and Errors
    stdout_log = bot_dir / "output.log"
    stderr_log = bot_dir / "error.log"

    await status_msg.edit_text("🚀 Starting the Bot process...")

    try:
        # Script ko background mein chalana aur unke logs files mein redirect karna
        out_file = open(stdout_log, "w")
        err_file = open(stderr_log, "w")
        
        process = subprocess.Popen(
            [str(python_exe), str(main_script)],
            cwd=str(bot_dir),
            stdout=out_file,
            stderr=err_file
        )

        active_processes[server_id] = process

        # DB Entry
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO vps_bots VALUES (?, ?, ?, ?, 'RUNNING')", 
                  (server_id, filename, str(bot_dir), str(main_script)))
        conn.commit()
        conn.close()

        success_text = f"✅ <b>Bot Successfully Hosted!</b>\n\n🆔 <b>ID:</b> <code>{server_id}</code>\n📂 <b>Folder Name:</b> {filename}\n🟢 <b>Status:</b> Running in Isolated VPS Mode"
        await status_msg.edit_text(success_text, parse_mode="HTML", reply_markup=get_main_keyboard())

    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to launch bot. Error: {str(e)}")

# --- BOT MANAGEMENT PANEL ---
@dp.callback_query(F.data == "manage_bots")
async def manage_bots(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT server_id, name, status FROM vps_bots")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await callback.message.edit_text("🤖 Koi bhi bot hosted nahi hai.", reply_markup=get_main_keyboard())
        return

    text = "🤖 <b>Hosted Bots List:</b>\n\n"
    buttons = []
    for srv_id, name, status in rows:
        # Check if process is actually running in memory
        actual_status = "🟢 RUNNING" if srv_id in active_processes and active_processes[srv_id].poll() is None else "🔴 STOPPED"
        text += f"🔹 <b>ID:</b> <code>{srv_id}</code>\n📦 <b>Name:</b> {name}\n⚡ <b>Status:</b> {actual_status}\n\n"
        buttons.append([InlineKeyboardButton(text=f"⚙️ Manage {name[:15]}", callback_data=f"control:{srv_id}")])

    buttons.append([InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# Single Bot Control Actions
@dp.callback_query(F.data.startswith("control:"))
async def control_bot_menu(callback: types.CallbackQuery):
    server_id = callback.data.split(":")[1]
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT name, status FROM vps_bots WHERE server_id = ?", (server_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        await callback.answer("Bot nahi mila!")
        return

    name, _ = row
    is_running = server_id in active_processes and active_processes[server_id].poll() is None
    status_str = "🟢 Running" if is_running else "🔴 Stopped"

    text = f"🛠️ <b>Bot Settings: {name}</b>\nID: <code>{server_id}</code>\nCurrent State: <b>{status_str}</b>"
    
    buttons = [
        [
            InlineKeyboardButton(text="▶️ Start", callback_data=f"start_b:{server_id}"),
            InlineKeyboardButton(text="🛑 Stop", callback_data=f"stop_b:{server_id}")
        ],
        [
            InlineKeyboardButton(text="📄 View Error Logs", callback_data=f"logs_err:{server_id}"),
            InlineKeyboardButton(text="📥 Download Files", callback_data=f"dl_dir:{server_id}")
        ],
        [InlineKeyboardButton(text="🗑️ Delete Completely", callback_data=f"del_b:{server_id}")],
        [InlineKeyboardButton(text="🔙 Back to List", callback_data="manage_bots")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# STOP ACTION
@dp.callback_query(F.data.startswith("stop_b:"))
async def stop_bot_process(callback: types.CallbackQuery):
    server_id = callback.data.split(":")[1]
    if server_id in active_processes:
        process = active_processes[server_id]
        process.terminate()
        process.wait() # process safely close karein
        del active_processes[server_id]
        await callback.answer("🛑 Bot Process stopped successfully!", show_alert=True)
    else:
        await callback.answer("⚠️ Bot pehle se hi band hai.", show_alert=True)
    await control_bot_menu(callback)

# START ACTION
@dp.callback_query(F.data.startswith("start_b:"))
async def start_bot_process(callback: types.CallbackQuery):
    server_id = callback.data.split(":")[1]
    
    if server_id in active_processes and active_processes[server_id].poll() is None:
        await callback.answer("⚠️ Bot pehle se hi chal raha hai.", show_alert=True)
        return

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path, main_file FROM vps_bots WHERE server_id = ?", (server_id,))
    row = c.fetchone()
    conn.close()

    if row:
        bot_dir, main_script = Path(row[0]), Path(row[1])
        venv_path = bot_dir / "venv"
        python_exe = venv_path / "bin" / "python" if os.name != 'nt' else venv_path / "Scripts" / "python.exe"
        
        stdout_log = bot_dir / "output.log"
        stderr_log = bot_dir / "error.log"

        out_file = open(stdout_log, "a")
        err_file = open(stderr_log, "a")

        process = subprocess.Popen([str(python_exe), str(main_script)], cwd=str(bot_dir), stdout=out_file, stderr=err_file)
        active_processes[server_id] = process
        await callback.answer("🚀 Bot start kar diya gaya hai!", show_alert=True)
    
    await control_bot_menu(callback)

# VIEW LOGS/ERRORS ACTION
@dp.callback_query(F.data.startswith("logs_err:"))
async def view_bot_logs(callback: types.CallbackQuery):
    server_id = callback.data.split(":")[1]
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM vps_bots WHERE server_id = ?", (server_id,))
    row = c.fetchone()
    conn.close()

    if row:
        err_log_path = Path(row[0]) / "error.log"
        if err_log_path.exists():
            with open(err_log_path, "r") as f:
                logs = f.read()[-3000:] # Aakhri ke 3000 chars read karega taaki message limit cross na ho
            
            if not logs.strip():
                logs = "No errors found! Clean logs. 🟢"
            
            text = f"📄 <b>Error Logs (Last few lines):</b>\n\n<code>{logs}</code>"
        else:
            text = "❌ Log file abhi tak create nahi hui hai."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🔙 Back", callback_data=f"control:{server_id}")]]])
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

# DOWNLOAD FILES ACTION
@dp.callback_query(F.data.startswith("dl_dir:"))
async def download_bot_files(callback: types.CallbackQuery):
    server_id = callback.data.split(":")[1]
    
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path, name FROM vps_bots WHERE server_id = ?", (server_id,))
    row = c.fetchone()
    conn.close()

    if row:
        bot_dir = Path(row[0])
        bot_name = row[1]
        await callback.message.answer(f"📦 <code>{bot_name}</code> folder ki saari files nikal kar bheji ja rahi hain...")

        # Venv folder ko chhod kar baaki files user ko bhejna
        for item in bot_dir.rglob("*"):
            if item.is_file() and "venv" not in item.parts and item.name not in ["output.log", "error.log"]:
                try:
                    await callback.message.reply_document(document=FSInputFile(str(item)), caption=f"📄 File: <code>{item.name}</code>", parse_mode="HTML")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Error sending file {item.name}: {e}")
        await callback.answer("Sent!")

# DELETE ACTION
@dp.callback_query(F.data.startswith("del_b:"))
async def delete_bot_completely(callback: types.CallbackQuery):
    server_id = callback.data.split(":")[1]
    
    # Process band karein agar chal raha ho
    if server_id in active_processes:
        active_processes[server_id].terminate()
        active_processes[server_id].wait()
        del active_processes[server_id]

    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()
    c.execute("SELECT path FROM vps_bots WHERE server_id = ?", (server_id,))
    row = c.fetchone()
    
    if row:
        bot_dir = Path(row[0])
        if bot_dir.exists():
            shutil.rmtree(bot_dir) # Poora folder delete

        c.execute("DELETE FROM vps_bots WHERE server_id = ?", (server_id,))
        conn.commit()
    conn.close()

    await callback.answer("🗑️ Bot files aur database entry permanently delete kar di gayi hai!", show_alert=True)
    await manage_bots(callback)

# --- SYSTEM MONITOR ---
@dp.callback_query(F.data == "vps_status")
async def view_vps_status(callback: types.CallbackQuery):
    import psutil
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    status_text = f"📊 <b>VPS LIVE STATUS</b>\n\n🖥️ <b>CPU Usage:</b> {cpu}%\n💾 <b>RAM Usage:</b> {ram}%\n💽 <b>Disk Space:</b> {disk}%"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")]]])
    await callback.message.edit_text(status_text, parse_mode="HTML", reply_markup=keyboard)

# --- MAIN ---
async def main():
    logger.info("Master VPS Bot Started...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
