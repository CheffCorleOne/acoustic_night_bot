import os
import logging
import json
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

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    MAIN_MENU,
    EDIT_PROFILE,
    SELECT_INSTRUMENTS,
    SELECT_SEEKING,
    WRITE_BIO,
    BROWSE_MODE,
    BROWSE_PROFILES
) = range(7)

USER_DATA_FILE = "users.json"
INSTRUMENTS = [
    "vocalist", "guitarist", "drummer", "cajon player",
    "sound engineer", "pianist", "bassist", "violinist",
    "other instrument", "other (non-instrumental)"
]

HELP_TEXT = """
🎵 *Acoustic Night Collaboration Bot Help* 🎵

*Main Features:*
1. ✏️ Edit Profile - Set up your instruments and preferences
2. 🔍 Find Collaborators - Two search modes:
   - 🎯 Smart Matches: Based on mutual preferences
   - 🔀 Browse All: Discover all musicians
3. 👤 My Profile - View your current profile details
4. 🎶 My Matches - View mutual connections
5. ❓ Help - Show this information

*Profile Requirements:*
- At least 1 instrument selected
- Specify what you're seeking
- Short bio (120 characters max)

Need help? Contact @your_support_username
"""

class AcousticMatchBot:
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
        
        if user_id in self.users:
            self.users[user_id].update({
                "name": user.full_name,
                "username": user.username
            })
        else:
            self.users[user_id] = {
                "name": user.full_name,
                "username": user.username,
                "instruments": [],
                "seeking": [],
                "bio": "",
                "likes": [],
                "matches": [],
                "viewed": [],
                "created_at": datetime.now().isoformat()
            }
        
        self.save_users()
        return await self.main_menu(update)

    async def main_menu(self, update: Update):
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile")],
            [InlineKeyboardButton("🔍 Find Collaborators", callback_data="browse_mode")],
            [InlineKeyboardButton("👤 My Profile", callback_data="my_profile")],
            [InlineKeyboardButton("🎶 My Matches", callback_data="my_matches")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        
        if update.message:
            await update.message.reply_text(
                "Main Menu:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            query = update.callback_query
            await query.edit_message_text(
                "Main Menu:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return MAIN_MENU

    async def show_my_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        user = self.users[user_id]
        
        profile_text = (
            "👤 *Your Profile*\n\n"
            f"🎻 Instruments: {', '.join(user['instruments']) if user['instruments'] else '−'}\n"
            f"🔍 Seeking: {', '.join(user['seeking']) if user['seeking'] else '−'}\n"
            f"📝 Bio: {user['bio'] if user['bio'] else '−'}"
        )
        
        await query.edit_message_text(
            profile_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
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
        return EDIT_PROFILE

    async def select_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        
        current_selection = self.users[user_id][category]
        keyboard = []
        
        for instr in INSTRUMENTS:
            status = "✅" if instr in current_selection else "◻️"
            keyboard.append([InlineKeyboardButton(
                f"{status} {instr.title()}",
                callback_data=f"toggle_{category}_{instr}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        
        await query.edit_message_text(
            f"Select your {category.replace('_', ' ')}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_INSTRUMENTS if category == "instruments" else SELECT_SEEKING

    async def handle_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        _, category, instrument = query.data.split("_", 2)
        
        if instrument in self.users[user_id][category]:
            self.users[user_id][category].remove(instrument)
        else:
            self.users[user_id][category].append(instrument)
        
        self.save_users()
        return await self.select_category(update, context, category)

    async def request_bio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "📝 Please write a short bio (max 120 characters):\n\n"
            "Example:\n"
            "\"Guitarist looking for vocalist to create acoustic covers. "
            "Available weekends. Love rock and pop!\""
        )
        return WRITE_BIO

    async def save_bio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        bio = update.message.text
        
        if len(bio) > 120:
            await update.message.reply_text("❌ Bio is too long! Maximum 120 characters.")
            return WRITE_BIO
            
        self.users[user_id]["bio"] = bio
        self.save_users()
        await update.message.reply_text("✅ Bio saved successfully!")
        return await self.main_menu(update)

    async def browse_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if len(self.users) <= 1:
            await query.edit_message_text("😢 No other profiles available yet!")
            return await self.main_menu(update)
        
        keyboard = [
            [InlineKeyboardButton("🎯 Smart Matches", callback_data="smart")],
            [InlineKeyboardButton("🔀 Browse All", callback_data="all")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        
        await query.edit_message_text(
            "🔍 Choose browsing mode:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return BROWSE_MODE

    async def prepare_browsing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = str(query.from_user.id)
        mode = query.data
        
        candidates = []
        for uid, user in self.users.items():
            if uid == user_id or uid in self.users[user_id]["viewed"]:
                continue
                
            if mode == "smart":
                instrument_match = any(instr in user["instruments"] for instr in self.users[user_id]["seeking"])
                seeking_match = any(instr in self.users[user_id]["instruments"] for instr in user["seeking"])
                if instrument_match and seeking_match:
                    candidates.append(user)
            else:
                candidates.append(user)
        
        if not candidates:
            await query.edit_message_text("😢 No matching profiles found!")
            return await self.main_menu(update)
        
        context.user_data["candidates"] = candidates
        context.user_data["current_index"] = 0
        return await self.show_profile(update, context)

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        candidates = context.user_data["candidates"]
        index = context.user_data["current_index"]
        
        if index >= len(candidates):
            await update.callback_query.edit_message_text("🏁 You've viewed all profiles!")
            return await self.main_menu(update)
        
        profile = candidates[index]
        contact = f"@{profile['username']}" if profile.get("username") else "⚠️ No username set"

        keyboard = [
            [InlineKeyboardButton("🎵 Like", callback_data="like"),
             InlineKeyboardButton("➡️ Next", callback_data="next")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ]
        
        text = (
            f"🎸 Profile {index+1}/{len(candidates)}\n\n"
            f"👤 Name: {profile['name']}\n"
            f"📞 Contact: {contact}\n"
            f"🎻 Instruments: {', '.join(profile['instruments'])}\n"
            f"🔍 Seeking: {', '.join(profile['seeking'])}\n"
            f"📝 Bio: {profile['bio']}"
        )
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return BROWSE_PROFILES

    async def handle_like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        current_user = self.users[user_id]
        profile = context.user_data["candidates"][context.user_data["current_index"]]
        
        current_user["viewed"].append(profile["user_id"])
        
        if user_id in self.users.get(profile["user_id"], {}).get("likes", []):
            current_user["matches"].append(profile["user_id"])
            self.users[profile["user_id"]]["matches"].append(user_id)
            
            match_user = self.users[profile["user_id"]]
            contact = f"@{match_user['username']}" if match_user.get("username") else "⚠️ No username set"
            
            await query.answer("🎉 Match! Check 'My Matches'")
            await query.message.reply_text(
                f"🎉 You've matched with {match_user['name']}!\n"
                f"📞 Contact them at: {contact}"
            )
        else:
            current_user["likes"].append(profile["user_id"])
            await query.answer("🎵 Like sent!")
        
        self.save_users()
        context.user_data["current_index"] += 1
        return await self.show_profile(update, context)

    async def show_matches(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        
        if not self.users[user_id]["matches"]:
            await query.answer("You have no matches yet 😢")
            return MAIN_MENU
        
        matches_text = "🎶 Your Matches:\n\n"
        for match_id in self.users[user_id]["matches"]:
            match = self.users.get(match_id, {})
            contact = f"@{match['username']}" if match.get("username") else "⚠️ No username set"
            matches_text += (
                f"👤 {match.get('name', 'Anonymous')}\n"
                f"🎻 Instruments: {', '.join(match.get('instruments', []))}\n"
                f"📞 Contact: {contact}\n\n"
            )
        
        await query.message.reply_text(matches_text)
        return MAIN_MENU

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.message.reply_text(
            HELP_TEXT,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return await self.main_menu(update)

def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(bot_token).build()
    bot = AcousticMatchBot()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(bot.edit_profile, pattern="^edit_profile$"),
                CallbackQueryHandler(bot.browse_mode, pattern="^browse_mode$"),
                CallbackQueryHandler(bot.show_my_profile, pattern="^my_profile$"),
                CallbackQueryHandler(bot.show_matches, pattern="^my_matches$"),
                CallbackQueryHandler(bot.help, pattern="^help$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ],
            EDIT_PROFILE: [
                CallbackQueryHandler(lambda u,c: bot.select_category(u, c, "instruments"), pattern="^edit_instruments$"),
                CallbackQueryHandler(lambda u,c: bot.select_category(u, c, "seeking"), pattern="^edit_seeking$"),
                CallbackQueryHandler(bot.request_bio, pattern="^edit_bio$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ],
            SELECT_INSTRUMENTS: [
                CallbackQueryHandler(bot.handle_toggle, pattern=r"^toggle_instruments_"),
                CallbackQueryHandler(bot.edit_profile, pattern="^back$")
            ],
            SELECT_SEEKING: [
                CallbackQueryHandler(bot.handle_toggle, pattern=r"^toggle_seeking_"),
                CallbackQueryHandler(bot.edit_profile, pattern="^back$")
            ],
            WRITE_BIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_bio)
            ],
            BROWSE_MODE: [
                CallbackQueryHandler(bot.prepare_browsing),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ],
            BROWSE_PROFILES: [
                CallbackQueryHandler(bot.handle_like, pattern="^like$"),
                CallbackQueryHandler(bot.show_profile, pattern="^next$"),
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
