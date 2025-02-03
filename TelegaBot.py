import os
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler
)

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
MAIN_MENU, EDIT_PROFILE, SELECT_INSTRUMENTS = range(3)

USER_DATA_FILE = "users.json"
INSTRUMENTS = [
    "vocalist", "guitarist", "drummer", "cajon player",
    "sound engineer", "pianist", "bassist", "violinist",
    "other instrument", "other (non-instrumental)"
]

class AcousticBot:
    def __init__(self):
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
                "bio": "",
                "matches": [],
                "created": datetime.now().isoformat()
            }
            self.save_users()
        
        return await self.main_menu(update)

    async def main_menu(self, update: Update):
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile")],
            [InlineKeyboardButton("🔍 Find Collaborators", callback_data="find")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        
        if update.message:
            await update.message.reply_text(
                "🎸 Acoustic Night Collaborations",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            query = update.callback_query
            await query.edit_message_text(
                "🎸 Acoustic Night Collaborations",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return MAIN_MENU

    async def edit_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        return await self.select_instruments(update)

    async def select_instruments(self, update: Update):
        query = update.callback_query
        user_id = str(query.from_user.id)
        
        keyboard = []
        for instr in INSTRUMENTS:
            selected = "✅" if instr in self.users[user_id]["instruments"] else "◻️"
            keyboard.append([InlineKeyboardButton(
                f"{selected} {instr.title()}", 
                callback_data=f"toggle_{instr}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        
        await query.edit_message_text(
            "Select your instruments/roles:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_INSTRUMENTS

    async def toggle_instrument(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        instrument = query.data.split("_", 1)[1]
        
        if instrument in self.users[user_id]["instruments"]:
            self.users[user_id]["instruments"].remove(instrument)
        else:
            self.users[user_id]["instruments"].append(instrument)
        
        self.save_users()
        return await self.select_instruments(update)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        help_text = (
            "🎵 *How to use:*\n\n"
            "1. Edit Profile - Select your instruments\n"
            "2. Find Collaborators - Search for musicians\n"
            "3. My Matches - View your connections\n\n"
            "Support: @your_username"
        )
        await query.message.reply_text(help_text)
        return await self.main_menu(update)

def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(bot_token).build()
    bot = AcousticBot()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(bot.edit_profile, pattern="^edit_profile$"),
                CallbackQueryHandler(bot.help, pattern="^help$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ],
            SELECT_INSTRUMENTS: [
                CallbackQueryHandler(bot.toggle_instrument, pattern="^toggle_"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ]
        },
        fallbacks=[CommandHandler("start", bot.start)],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
