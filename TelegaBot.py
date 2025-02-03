# main.py
import os
import json
import logging
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

# Инициализация FastAPI для keep-alive
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "active", "timestamp": datetime.now().isoformat()}

# Настройка логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
(
    CHOOSE_ACTION,
    SELECT_GENRE,
    SELECT_INSTRUMENTS,
    PROJECT_DESCRIPTION,
    SET_DEADLINE,
    CONFIRM_PROJECT
) = range(6)

class CollaborationBot:
    def __init__(self):
        self.user_data_file = "users.json"
        self.users = self.load_users()
        self.genres = ["Rock", "Jazz", "Pop", "Classical", "Electronic"]
        self.instruments = [
            "Vocals", "Guitar", "Piano", "Drums",
            "Bass", "Violin", "Saxophone", "Production"
        ]

    def load_users(self):
        try:
            with open(self.user_data_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_users(self):
        with open(self.user_data_file, "w") as f:
            json.dump(self.users, f, indent=2)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start с интерактивным меню"""
        user = update.effective_user
        keyboard = [
            [
                InlineKeyboardButton("🎵 Найти коллаборацию", callback_data="find_collab"),
                InlineKeyboardButton("💡 Создать проект", callback_data="create_project")
            ],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        
        await update.message.reply_text(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            "Я помогу тебе найти музыкантов для:\n"
            "• Совместных выступлений\n"
            "• Записи каверов\n"
            "• Создания оригинальной музыки\n\n"
            "Выбери действие:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSE_ACTION

    async def handle_project_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Создание нового проекта"""
        query = update.callback_query
        await query.answer()
        
        # Сброс предыдущих данных
        context.user_data.clear()
        
        # Шаг 1: Выбор жанра
        keyboard = [
            [InlineKeyboardButton(genre, callback_data=f"genre_{genre}")]
            for genre in self.genres
        ]
        await query.edit_message_text(
            "🎶 Выбери музыкальный жанр для проекта:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_GENRE

    async def handle_instrument_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор необходимых инструментов"""
        query = update.callback_query
        await query.answer()
        
        # Сохраняем жанр
        genre = query.data.replace("genre_", "")
        context.user_data["genre"] = genre
        
        # Шаг 2: Выбор инструментов
        keyboard = [
            [InlineKeyboardButton(instr, callback_data=f"instr_{instr}")]
            for instr in self.instruments
        ]
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="done_instruments")])
        
        await query.edit_message_text(
            "🎹 Выбери необходимые инструменты (можно несколько):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_INSTRUMENTS

    async def handle_project_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ввод описания проекта"""
        query = update.callback_query
        await query.answer()
        
        # Сохраняем инструменты
        if "instruments" not in context.user_data:
            context.user_data["instruments"] = []
        
        if query.data.startswith("instr_"):
            instrument = query.data.replace("instr_", "")
            context.user_data["instruments"].append(instrument)
            return SELECT_INSTRUMENTS
        
        # Переход к описанию
        await query.edit_message_text(
            "📝 Напиши подробное описание проекта:\n\n"
            "• Цель проекта\n"
            "• Требования к участникам\n"
            "• Предполагаемый график\n"
            "• Любые другие детали"
        )
        return PROJECT_DESCRIPTION

    async def handle_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установка дедлайна"""
        context.user_data["description"] = update.message.text
        
        keyboard = [
            [
                InlineKeyboardButton("⏰ Указать дедлайн", callback_data="set_deadline"),
                InlineKeyboardButton("🚀 Начать сразу", callback_data="no_deadline")
            ]
        ]
        await update.message.reply_text(
            "📅 Хочешь установить крайний срок для подачи заявок?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SET_DEADLINE

    async def save_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение проекта и поиск совпадений"""
        query = update.callback_query
        await query.answer()
        
        # Сохраняем дедлайн
        if query.data == "set_deadline":
            await query.edit_message_text("📅 Введи дату в формате ДД.ММ.ГГГГ (например: 31.12.2024):")
            return SET_DEADLINE
        
        # Финализация проекта
        user_id = str(update.effective_user.id)
        self.users[user_id] = {
            "project": context.user_data,
            "timestamp": datetime.now().isoformat(),
            "matches": []
        }
        self.save_users()
        
        # Поиск совпадений
        matches = self.find_matches(user_id)
        response = "🎉 Проект создан! Мы уже ищем подходящих участников..."
        
        if matches:
            response += "\n\n🔍 Найдены потенциальные кандидаты:\n"
            response += "\n".join([f"• {u['username']} ({', '.join(u['instruments'])})" for u in matches[:3]])
        
        await query.edit_message_text(response)
        return ConversationHandler.END

    def find_matches(self, project_owner_id: str):
        """Поиск совпадений по инструментам и жанру"""
        project = self.users.get(project_owner_id, {}).get("project", {})
        matches = []
        
        for user_id, data in self.users.items():
            if user_id == project_owner_id:
                continue
            
            # Проверка совпадений по инструментам
            common_instruments = set(project.get("instruments", [])) & set(data.get("instruments", []))
            
            # Проверка совпадения жанра
            genre_match = data.get("genre") == project.get("genre")
            
            if common_instruments and genre_match:
                matches.append({
                    "user_id": user_id,
                    "username": data.get("username"),
                    "instruments": list(common_instruments)
                })
        
        return sorted(matches, key=lambda x: len(x["instruments"]), reverse=True)[:5]

# Инициализация и запуск
def run_bot():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = Application.builder().token(bot_token).build()

    collab_bot = CollaborationBot()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", collab_bot.start)],
        states={
            CHOOSE_ACTION: [
                CallbackQueryHandler(collab_bot.handle_project_creation, pattern="^create_project$"),
                # Добавь обработчики для других кнопок
            ],
            SELECT_GENRE: [
                CallbackQueryHandler(collab_bot.handle_instrument_selection, pattern="^genre_")
            ],
            SELECT_INSTRUMENTS: [
                CallbackQueryHandler(collab_bot.handle_project_description, pattern="^done_instruments$"),
                CallbackQueryHandler(collab_bot.handle_instrument_selection, pattern="^instr_")
            ],
            PROJECT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, collab_bot.handle_deadline)
            ],
            SET_DEADLINE: [
                CallbackQueryHandler(collab_bot.save_project, pattern="^no_deadline$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, collab_bot.save_project)
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: ConversationHandler.END)]
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    # Запуск веб-сервера в отдельном потоке
    server = Server(Config(app=app, host="0.0.0.0", port=8000))
    Thread(target=server.run).start()
    
    # Запуск Telegram бота
    run_bot()
