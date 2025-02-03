# main.py
import os
import logging
from datetime import datetime, timedelta
from threading import Thread
from typing import Dict, List

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
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import psutil

# ======================
# Configuration
# ======================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///acoustic_night.db"
ENGINE = create_engine(DATABASE_URL)
Base = declarative_base()

# ======================
# Database Models
# ======================
class User(Base):
    __tablename__ = "users"

    user_id = Column(String(50), primary_key=True)
    instruments = Column(JSON)
    seeking = Column(JSON)
    purpose = Column(String(20))  # club/personal/both
    bio = Column(String(200))
    matches = Column(JSON, default=[])
    likes = Column(JSON, default=[])
    last_active = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)

Base.metadata.create_all(ENGINE)

# ======================
# FastAPI Keep-Alive
# ======================
app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "OK", "timestamp": datetime.now().isoformat()}

@app.get("/status")
def memory_status():
    process = psutil.Process()
    return {
        "memory_mb": process.memory_info().rss / 1024**2,
        "users_count": Session(ENGINE).query(User).count()
    }

def run_keep_alive():
    server = Server(Config(app=app, host="0.0.0.0", port=8000))
    server.run()

# ======================
# Bot Core
# ======================
class AcousticNightBot:
    def __init__(self):
        self.instruments = [
            "Vocals", "Guitar", "Piano", "Bass",
            "Drums", "Violin", "Saxophone", "Cajon",
            "Sound Engineering", "Other"
        ]
        self.scheduler = AsyncIOScheduler()
        self.setup_scheduler()

    # ======================
    # Scheduler Jobs
    # ======================
    def setup_scheduler(self):
        self.scheduler.add_job(
            self.cleanup_inactive_users,
            'cron',
            hour=3,
            timezone="UTC"
        )
        self.scheduler.add_job(
            self.check_matches,
            'interval',
            minutes=15
        )
        self.scheduler.start()

    async def cleanup_inactive_users(self):
        with Session(ENGINE) as session:
            month_ago = datetime.now() - timedelta(days=30)
            inactive_users = session.query(User).filter(
                User.last_active < month_ago
            ).delete()
            session.commit()
            logger.info(f"Cleaned up {inactive_users} inactive users")

    async def check_matches(self):
        with Session(ENGINE) as session:
            users = session.query(User).all()
            for user in users:
                matches = self.find_matches(user.user_id, session)
                new_matches = [m for m in matches if m not in user.matches]
                if new_matches:
                    user.matches = user.matches + new_matches
                    session.commit()
                    # Here should be notification logic

    # ======================
    # Core Functionality
    # ======================
    def get_user(self, user_id: str, session: Session) -> User:
        return session.query(User).filter_by(user_id=user_id).first()

    def find_matches(self, user_id: str, session: Session) -> List[str]:
        current_user = self.get_user(user_id, session)
        if not current_user:
            return []

        query = session.query(User).filter(
            User.user_id != user_id,
            User.purpose.in_(self.get_compatible_purposes(current_user.purpose)),
            User.instruments.op("&&")(current_user.seeking),
            User.seeking.op("&&")(current_user.instruments)
        ).limit(50)

        return [user.user_id for user in query.all()]

    def get_compatible_purposes(self, purpose: str) -> List[str]:
        mapping = {
            "club": ["club", "both"],
            "personal": ["personal", "both"],
            "both": ["club", "personal", "both"]
        }
        return mapping.get(purpose, [])

    # ======================
    # Telegram Handlers
    # ======================
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        with Session(ENGINE) as session:
            if self.get_user(str(user.id), session):
                return await self.main_menu(update, context)

        keyboard = [[InlineKeyboardButton("Create Profile", callback_data="create_profile")]]
        await update.message.reply_text(
            f"🎵 Welcome to Acoustic Night Collaborations!\n\n"
            "Let's create your musician profile to find collaborators "
            "for club events or personal projects.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU

    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("Browse Profiles", callback_data="browse")],
            [InlineKeyboardButton("My Profile", callback_data="view_profile")],
            [InlineKeyboardButton("My Matches", callback_data="matches")]
        ]
        
        await query.edit_message_text(
            "Main Menu:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MAIN_MENU

    async def create_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        context.user_data["instruments"] = []
        keyboard = self._generate_instrument_keyboard([])
        await query.edit_message_text(
            "Select your instruments (multiple selection):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_INSTRUMENTS

    def _generate_instrument_keyboard(self, selected: List[str]):
        keyboard = []
        for instr in self.instruments:
            status = "✅" if instr in selected else "◻️"
            keyboard.append([InlineKeyboardButton(
                f"{status} {instr}", 
                callback_data=f"toggle_{instr}"
            )])
        keyboard.append([InlineKeyboardButton("Next ➡️", callback_data="done_instruments")])
        return keyboard

    async def handle_instruments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if data.startswith("toggle_"):
            instrument = data.split("_", 1)[1]
            if instrument in context.user_data["instruments"]:
                context.user_data["instruments"].remove(instrument)
            else:
                context.user_data["instruments"].append(instrument)
            
            keyboard = self._generate_instrument_keyboard(context.user_data["instruments"])
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
            return SELECT_INSTRUMENTS
        
        # Transition to seeking selection
        context.user_data["seeking"] = []
        keyboard = self._generate_instrument_keyboard([])
        await query.edit_message_text(
            "What instruments are you looking for?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_SEEKING

    async def save_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        with Session(ENGINE) as session:
            db_user = User(
                user_id=str(user.id),
                instruments=context.user_data["instruments"],
                seeking=context.user_data["seeking"],
                purpose=context.user_data["purpose"],
                bio=update.message.text
            )
            session.add(db_user)
            session.commit()
        
        await update.message.reply_text(
            "Profile created! Start browsing collaborators."
        )
        return await self.main_menu(update, context)

# ======================
# Conversation States
# ======================
(
    MAIN_MENU,
    SELECT_INSTRUMENTS,
    SELECT_SEEKING,
    SET_PURPOSE,
    WRITE_BIO,
    BROWSE_PROFILES
) = range(6)

# ======================
# Initialization
# ======================
def run_bot():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(bot_token).build()
    bot = AcousticNightBot()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(bot.create_profile, pattern="^create_profile$"),
                CallbackQueryHandler(bot.main_menu, pattern="^browse$")
            ],
            SELECT_INSTRUMENTS: [
                CallbackQueryHandler(bot.handle_instruments)
            ],
            SELECT_SEEKING: [
                CallbackQueryHandler(bot.handle_instruments)
            ],
            SET_PURPOSE: [
                # Add purpose handling
            ],
            WRITE_BIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_profile)
            ]
        },
        fallbacks=[CommandHandler("start", bot.start)]
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    Thread(target=run_keep_alive).start()
    run_bot()
