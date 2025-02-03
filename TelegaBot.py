import os
import logging
import json
from datetime import datetime
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from fastapi import FastAPI
from uvicorn import Server, Config

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
(
    MAIN_MENU,
    SELECT_INSTRUMENTS,
    SELECT_SEEKING,
    WRITE_BIO,
    BROWSE_PROFILES
) = range(5)

# Файл для хранения данных
USER_DATA_FILE = "users.json"

class AcousticNightBot:
    def __init__(self):
        self.instruments = [
            "Vocals", "Guitar", "Piano", "Bass",
            "Drums", "Violin", "Saxophone", "Cajon",
            "Sound Engineering", "Other"
        ]
        self.users = self.load_users()

    def load_users(self):
        try:
            with open(USER_DATA_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_users(self):
        with open(USER_DATA_FILE, "w") as f:
            json.dump(self.users, f, indent=2)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = str(user.id)
        
        if user_id not in self.users:
            self.users[user_id] = {
                "name": user.full_name,
                "instruments": [],
                "seeking": [],
                "bio": "",
                "matches": [],
                "created_at": datetime.now().isoformat()
            }
            self.save_users()
        
        keyboard = [
            [InlineKeyboardButton("🎵 Find Collaborators", callback_data="find")],
            [InlineKeyboardButton("📝 Edit Profile", callback_data="edit")],
            [InlineKeyboardButton("💌 My Matches", callback_data="matches")]
        ]
        
        await update.message.reply_text(
            f"🎸 Welcome to Acoustic Night Club, {user.first_name}!\n\n"
            "Choose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU

    async def edit_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("🎻 My Instruments", callback_data="edit_instruments")],
            [InlineKeyboardButton("🔍 Seeking", callback_data="edit_seeking")],
            [InlineKeyboardButton("📝 Bio", callback_data="edit_bio")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        
        await query.edit_message_text(
            "✏️ Edit Profile:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU

    async def select_instruments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        current_instruments = self.users[user_id]["instruments"]
        
        keyboard = []
        for instrument in self.instruments:
            status = "✅" if instrument in current_instruments else "◻️"
            keyboard.append([InlineKeyboardButton(
                f"{status} {instrument}", 
                callback_data=f"toggle_{instrument}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        
        await query.edit_message_text(
            "🎻 Select your instruments:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_INSTRUMENTS

    async def handle_instruments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        data = query.data
        
        if data.startswith("toggle_"):
            instrument = data.split("_", 1)[1]
            if instrument in self.users[user_id]["instruments"]:
                self.users[user_id]["instruments"].remove(instrument)
            else:
                self.users[user_id]["instruments"].append(instrument)
            self.save_users()
            
            return await self.select_instruments(update, context)
        
        return await self.edit_profile(update, context)

    async def browse_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = str(query.from_user.id)
        other_users = [u for u in self.users.values() if u != self.users[user_id]]
        
        if not other_users:
            await query.edit_message_text("😢 No available profiles yet!")
            return MAIN_MENU
        
        context.user_data["browse_index"] = 0
        return await self.show_profile(update, context, other_users)

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, users: list):
        query = update.callback_query
        await query.answer()
        
        index = context.user_data["browse_index"]
        if index >= len(users):
            await query.edit_message_text("🏁 End of list!")
            return MAIN_MENU
        
        profile = users[index]
        keyboard = [
            [InlineKeyboardButton("❤️ Like", callback_data="like")],
            [InlineKeyboardButton("➡️ Next", callback_data="next")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        
        text = (
            f"🎸 Profile {index+1}/{len(users)}\n\n"
            f"👤 Name: {profile['name']}\n"
            f"🎻 Instruments: {', '.join(profile['instruments'])}\n"
            f"🔍 Seeking: {', '.join(profile['seeking'])}\n"
            f"📝 Bio: {profile['bio']}"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return BROWSE_PROFILES

# Keep Alive Server для Render
app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "active", "timestamp": datetime.now().isoformat()}

def run_server():
    Server(Config(app=app, host="0.0.0.0", port=8000)).run()

if __name__ == "__main__":
    # Запуск сервера в отдельном потоке
    Thread(target=run_server).start()
    
    # Инициализация бота
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(bot_token).build()
    bot = AcousticNightBot()

    # Обработчики команд
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(bot.browse_profiles, pattern="^find$"),
                CallbackQueryHandler(bot.edit_profile, pattern="^edit$"),
                CallbackQueryHandler(bot.edit_profile, pattern="^back$")
            ],
            SELECT_INSTRUMENTS: [
                CallbackQueryHandler(bot.handle_instruments)
            ],
            BROWSE_PROFILES: [
                CallbackQueryHandler(lambda u,c: bot.show_profile(u,c,bot.users.values()), pattern="^next$"),
                CallbackQueryHandler(bot.edit_profile, pattern="^back$")
            ]
        },
        fallbacks=[CommandHandler("start", bot.start)]
    )

    application.add_handler(conv_handler)
    application.run_polling()
