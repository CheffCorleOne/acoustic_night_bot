import os
import logging
import json
import psycopg2
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

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        self.create_tables()

    def create_tables(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)
            self.conn.commit()

    def get_user(self, user_id):
        with self.conn.cursor() as cur:
            cur.execute("SELECT data FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            return json.loads(result[0]) if result else None

    def save_user(self, user_id, data):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, data)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data
            """, (user_id, json.dumps(data, default=str)))
            self.conn.commit()

    def get_all_users(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT data FROM users")
            return [json.loads(row[0]) for row in cur.fetchall()]

class AcousticMatchBot:
    def __init__(self):
        self.db = Database()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = str(user.id)
        
        user_data = self.db.get_user(user_id) or {
            "user_id": user_id,
            "name": user.full_name,
            "username": user.username,
            "instruments": [],
            "seeking": [],
            "bio": "",
            "likes": [],
            "matches": [],
            "pending": [],
            "viewed": [],
            "created_at": datetime.now().isoformat()
        }
        
        user_data.update({
            "name": user.full_name,
            "username": user.username
        })
        
        self.db.save_user(user_id, user_data)
        return await self.main_menu(update, context)

    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Profile", callback_data="edit_profile")],
            [InlineKeyboardButton("🔍 Find Collaborators", callback_data="browse_mode")],
            [InlineKeyboardButton("👤 My Profile", callback_data="my_profile")],
            [InlineKeyboardButton("🎶 My Matches", callback_data="my_matches")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text("Main Menu:", reply_markup=reply_markup)
        else:
            await update.callback_query.edit_message_text("Main Menu:", reply_markup=reply_markup)
        return MAIN_MENU

    async def show_my_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        user_data = self.db.get_user(user_id)
        
        profile_text = (
            "👤 *Your Profile*\n\n"
            f"🎻 Instruments: {', '.join(user_data['instruments']) or '-'}\n"
            f"🔍 Seeking: {', '.join(user_data['seeking']) or '-'}\n"
            f"📝 Bio: {user_data['bio'] or '-'}"
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
        user_data = self.db.get_user(user_id)
        
        current_selection = user_data[category]
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
        
        user_data = self.db.get_user(user_id)
        if instrument in user_data[category]:
            user_data[category].remove(instrument)
        else:
            user_data[category].append(instrument)
        
        self.db.save_user(user_id, user_data)
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
            
        user_data = self.db.get_user(user_id)
        user_data["bio"] = bio
        self.db.save_user(user_id, user_data)
        await update.message.reply_text("✅ Bio saved successfully!")
        return await self.main_menu(update, context)

    async def browse_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        all_users = self.db.get_all_users()
        if len(all_users) <= 1:
            await query.edit_message_text("😢 No other profiles available yet!")
            return await self.main_menu(update, context)
        
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
        current_user = self.db.get_user(user_id)
        all_users = self.db.get_all_users()
        
        candidates = []
        for user in all_users:
            if user["user_id"] == user_id:
                continue
                
            if mode == "smart":
                instrument_match = any(instr in user["instruments"] for instr in current_user["seeking"])
                seeking_match = any(instr in current_user["instruments"] for instr in user["seeking"])
                if instrument_match and seeking_match:
                    candidates.append(user)
            else:
                if user["user_id"] not in current_user["pending"]:
                    candidates.append(user)
        
        if not candidates:
            await query.edit_message_text("😢 No matching profiles found!")
            return await self.main_menu(update, context)
        
        context.user_data["candidates"] = candidates
        context.user_data["current_index"] = 0
        return await self.show_profile(update, context)

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        candidates = context.user_data["candidates"]
        index = context.user_data["current_index"]
        current_user = self.db.get_user(user_id)
        
        if index >= len(candidates):
            await update.callback_query.edit_message_text("🏁 You've viewed all profiles!")
            return await self.main_menu(update, context)
        
        profile = candidates[index]
        is_match = profile["user_id"] in current_user["matches"]
        contact = f"@{profile['username']}" if (is_match and profile.get("username")) else "🔒 Contact hidden until mutual match"

        keyboard = []
        if index > 0:
            keyboard.append([InlineKeyboardButton("⬅️ Previous", callback_data="previous")])
        
        if not is_match:
            keyboard.append([
                InlineKeyboardButton("🎵 Let's Collab", callback_data="like"),
                InlineKeyboardButton("➡️ Next", callback_data="next")
            ])
        else:
            keyboard.append([InlineKeyboardButton("➡️ Next", callback_data="next")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back")])
        
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

    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        action = query.data
        
        if action == "previous":
            context.user_data["current_index"] -= 1
        elif action == "next":
            context.user_data["current_index"] += 1
        
        return await self.show_profile(update, context)

    async def handle_like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        current_user = self.db.get_user(user_id)
        profile = context.user_data["candidates"][context.user_data["current_index"]]
        target_id = profile["user_id"]
        
        if target_id in current_user["pending"]:
            await query.answer("Request already pending!")
            return BROWSE_PROFILES
            
        current_user["pending"].append(target_id)
        self.db.save_user(user_id, current_user)
        
        # Send request to target user
        keyboard = [
            [InlineKeyboardButton("✅ Accept", callback_data=f"accept_{user_id}"),
             InlineKeyboardButton("❌ Decline", callback_data=f"decline_{user_id}")]
        ]
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎵 New collaboration request from {current_user['name']}!\n\n"
                 f"View their profile and respond:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await query.answer("Request sent!")
        context.user_data["current_index"] += 1
        return await self.show_profile(update, context)

    async def handle_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        action, sender_id = query.data.split("_")
        
        current_user = self.db.get_user(user_id)
        sender_data = self.db.get_user(sender_id)
        
        if sender_id in current_user["pending"]:
            current_user["pending"].remove(sender_id)
        
        if action == "accept":
            current_user["matches"].append(sender_id)
            sender_data["matches"].append(user_id)
            
            # Show updated profile
            contact = f"@{sender_data['username']}" if sender_data.get("username") else "⚠️ No username set"
            text = (
                f"🎉 New Collaboration Partner!\n\n"
                f"👤 Name: {sender_data['name']}\n"
                f"📞 Contact: {contact}\n"
                f"🎻 Instruments: {', '.join(sender_data['instruments'])}\n"
                f"🔍 Seeking: {', '.join(sender_data['seeking'])}\n"
                f"📝 Bio: {sender_data['bio']}"
            )
            await query.edit_message_text(text)
            await query.answer("Match accepted!")
        else:
            await query.answer("Request declined")
            await query.message.delete()
        
        self.db.save_user(user_id, current_user)
        self.db.save_user(sender_id, sender_data)
        return MAIN_MENU

    async def show_matches(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)
        current_user = self.db.get_user(user_id)
        all_users = self.db.get_all_users()
        
        matches = current_user["matches"]
        smart_matches = [
            u["user_id"] for u in all_users
            if u["user_id"] != user_id and
            any(instr in u["instruments"] for instr in current_user["seeking"]) and
            any(instr in current_user["instruments"] for instr in u["seeking"])
        ]
        
        all_matches = list(set(matches + smart_matches))
        
        if not all_matches:
            await query.answer("You have no matches yet 😢")
            return MAIN_MENU
        
        matches_text = "🎶 Your Matches:\n\n"
        for match_id in all_matches:
            match = self.db.get_user(match_id)
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
        return await self.main_menu(update, context)

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
                CallbackQueryHandler(bot.handle_navigation, pattern="^(previous|next)$"),
                CallbackQueryHandler(bot.handle_like, pattern="^like$"),
                CallbackQueryHandler(bot.main_menu, pattern="^back$")
            ]
        },
        fallbacks=[CommandHandler("start", bot.start)],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(bot.handle_response, pattern=r"^(accept|decline)_"))
    
    application.run_polling()

if __name__ == "__main__":
    main()
