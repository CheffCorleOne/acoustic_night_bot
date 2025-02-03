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
3. 🎵 Like profiles to connect
4. 🎶 My Matches - View mutual connections

*Profile Requirements:*
- At least 1 instrument selected
- Specify what you're seeking
- Short bio (120 characters max)

*How Connections Work:*
1. Like profiles you're interested in
2. If they like you back, you'll get a match notification
3. Contact your matches via their Telegram @username

*Tips:*
- Keep your Telegram username updated in profile settings
- Be specific in your bio about your musical style/needs
- Check back regularly for new collaborators

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
        
        await update.message.reply_text(
            f"🎵 Welcome, {user.first_name}!\n"
            "Let's find your perfect music collaborators!"
        )
        return await self.main_menu(update)

    async def main_menu(self, update: Update):
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile")],
            [InlineKeyboardButton("🔍 Find Collaborators", callback_data="browse_mode")],
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
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
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

    # Keep other methods same as previous version

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
                CallbackQueryHandler(bot.show_matches, pattern="^my_matches$"),
                CallbackQueryHandler(bot.help, pattern="^help$")
            ],
            # ... rest of the states remain same as previous version
        },
        fallbacks=[CommandHandler("start", bot.start)],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
