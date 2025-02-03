import os
import logging
import json
import asyncio  # Добавлен импорт asyncio
from datetime import datetime
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
import uvicorn

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
(
    MAIN_MENU,
    EDIT_PROFILE,
    SELECT_INSTRUMENTS,
    SELECT_SEEKING,
    WRITE_BIO,
    BROWSE_PROFILES
) = range(6)

USER_DATA_FILE = "users.json"

HELP_MESSAGE = """
🎵 *Acoustic Night Collaboration Bot Help* 🎵

_Этот бот помогает музыкантам Nazarbayev University находить друг друга для:_

• 🎸 Совместных выступлений на мероприятиях клуба
• 🎹 Персональных музыкальных проектов
• 🥁 Джем-сессий и неформальных коллабораций

📌 *Основные функции:*
1. _Edit Profile_ - Заполните свой профиль (инструменты, цели)
2. _Find Collaborators_ - Поиск подходящих музыкантов
3. _My Matches_ - Ваши успешные совпадения
4. _Help_ - Эта справочная информация

🎛 *Как использовать:*
1. Сначала заполните профиль через _Edit Profile_
2. Используйте _Find Collaborators_ для поиска
3. Лайкайте понравившиеся профили
4. При взаимном лайке получите контакты

⚙️ *Требования к профилю:*
- Минимум 1 выбранный инструмент
- Указание целей сотрудничества
- Короткое описание (50+ символов)

🛠 По вопросам и предложениям: @ваш_логин
"""

class AcousticNightBot:
    def __init__(self):
        self.instruments = [
            "🎤 Vocals", "🎸 Guitar", "🎹 Piano", "🎻 Violin",
            "🥁 Drums", "🎷 Saxophone", "🎺 Trumpet", "📻 Sound Engineering",
            "🪕 Other"
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

    def is_profile_complete(self, user_id: str) -> bool:
        user = self.users.get(user_id, {})
        return (
            len(user.get("instruments", [])) > 0 and
            len(user.get("seeking", [])) > 0 and
            len(user.get("bio", "")) >= 50
        )

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
        
        return await self.main_menu(update, context)

    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile")],
            [InlineKeyboardButton("🔍 Find Collaborators", callback_data="find_collab")],
            [InlineKeyboardButton("🎵 My Matches", callback_data="my_matches")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        
        if isinstance(update, Update) and update.message:
            await update.message.reply_text(
                "🎸 *Acoustic Night Collaborations*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            query = update.callback_query
            await query.answer()
            await query.edit_message_text(
                "🎸 *Acoustic Night Collaborations*",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        return MAIN_MENU

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.message.reply_text(
            HELP_MESSAGE,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return await self.main_menu(update, context)

    async def edit_profile_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("🎻 My Instruments", callback_data="edit_instruments")],
            [InlineKeyboardButton("🔍 Seeking", callback_data="edit_seeking")],
            [InlineKeyboardButton("📝 Bio", callback_data="edit_bio")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        
        await query.edit_message_text(
            "✏️ *Edit Profile*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return EDIT_PROFILE

    async def select_instruments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        
        keyboard = []
        for instr in self.instruments:
            selected = "✅" if instr in self.users[user_id]["instruments"] else "◻️"
            keyboard.append([InlineKeyboardButton(
                f"{selected} {instr}", 
                callback_data=f"toggle_{instr}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        
        await query.edit_message_text(
            "🎻 *Select Your Instruments*:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SELECT_INSTRUMENTS

    async def handle_instrument_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        instrument = query.data.split("_", 1)[1]
        
        if instrument in self.users[user_id]["instruments"]:
            self.users[user_id]["instruments"].remove(instrument)
        else:
            self.users[user_id]["instruments"].append(instrument)
        
        self.save_users()
        return await self.select_instruments(update, context)

    async def check_profile_complete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        
        if not self.is_profile_complete(user_id):
            await query.message.reply_text(
                "⚠️ Please complete your profile first!\n"
                "You need:\n"
                "- At least 1 instrument\n"
                "- Seeking preferences\n"
                "- Bio (50+ characters)"
            )
            return await self.edit_profile_menu(update, context)
        
        return await self.browse_profiles(update, context)

    async def browse_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        
        # Фильтрация профилей
        candidates = [
            u for uid, u in self.users.items() 
            if uid != user_id 
            and any(instr in u["instruments"] for instr in self.users[user_id]["seeking"])
        ]
        
        if not candidates:
            await query.edit_message_text("😢 No available collaborators yet!")
            return MAIN_MENU
        
        context.user_data["browse_index"] = 0
        context.user_data["candidates"] = candidates
        return await self.show_profile(update, context)

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        index = context.user_data["browse_index"]
        candidates = context.user_data["candidates"]
        
        if index >= len(candidates):
            await query.edit_message_text("🏁 End of collaborators list!")
            return MAIN_MENU
        
        profile = candidates[index]
        keyboard = [
            [InlineKeyboardButton("🎵 Like", callback_data="like")],
            [InlineKeyboardButton("➡️ Next", callback_data="next")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        
        text = (
            f"🎸 *Collaborator Profile* ({index+1}/{len(candidates)})\n\n"
            f"👤 *Name*: {profile['name']}\n"
            f"🎻 *Instruments*: {', '.join(profile['instruments'])}\n"
            f"🔍 *Seeking*: {', '.join(profile['seeking'])}\n"
            f"📝 *Bio*: {profile['bio']}"
        )
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return BROWSE_PROFILES

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "OK"}

async def run_bot():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(bot_token).build()
    bot = AcousticNightBot()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(bot.edit_profile_menu, pattern="^edit_profile$"),
                CallbackQueryHandler(bot.check_profile_complete, pattern="^find_collab$"),
                CallbackQueryHandler(bot.handle_help, pattern="^help$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ],
            EDIT_PROFILE: [
                CallbackQueryHandler(bot.select_instruments, pattern="^edit_instruments$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ],
            SELECT_INSTRUMENTS: [
                CallbackQueryHandler(bot.handle_instrument_toggle, pattern="^toggle_"),
                CallbackQueryHandler(bot.edit_profile_menu, pattern="^back$")
            ],
            BROWSE_PROFILES: [
                CallbackQueryHandler(bot.show_profile, pattern="^next$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ]
        },
        fallbacks=[CommandHandler("start", bot.start)],
        per_message=True
    )

    application.add_handler(conv_handler)
    await application.initialize()
    await application.start()
    logger.info("Bot started successfully")
    while True:
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_bot())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
