from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, \
    ConversationHandler, filters
from datetime import datetime, timedelta
import logging
import json
import os
import sys
import asyncio
import pandas as pd

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States for ConversationHandler
(
    CHOOSING_ROLE,
    ARTIST_TYPE,
    COLLAB_TYPE,
    INTRODUCTION,
    LOOKING_FOR,
    PROJECT_DESCRIPTION,
    DEADLINE_CHOICE,
    DEADLINE_DATE,
    HANDLE_SUGGESTION,
    CONTINUE_SEARCHING
) = range(10)

def load_user_data():
    try:
        with open('user_data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_data(data):
    with open('user_data.json', 'w') as f:
        json.dump(data, f, indent=4)

def get_bot_token():
    if len(sys.argv) > 1:
        return sys.argv[1]

    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if token:
        return token

    while True:
        token = input("Please enter your Telegram Bot Token from BotFather: ").strip()
        if token and len(token) > 20:
            return token
        print("Invalid token format. Please enter a valid token.")

class CollaborationBot:
    def __init__(self):
        self.user_data = load_user_data()
        self.artist_types = [
            "singer", "guitarist", "drummer", "cajon player",
            "sound engineer", "pianist", "bassist", "violinist",
            "other instrument", "other (non-instrumental)"
        ]
        self.collab_types = [
            "performing at an Acoustic Night concert",
            "making a music cover",
            "I am open for anything"
        ]

    def find_matches(self, user_id: str) -> list:
        matches = []
        user = self.user_data.get(str(user_id), {})
        if 'role' not in user:
            user['role'] = 'suggest' if 'project_description' in user and 'looking_for' in user else 'join'
            self.user_data[str(user_id)] = user

        for potential_match_id, potential_match in self.user_data.items():
            if potential_match_id == str(user_id):
                continue

            if user.get('role') == 'suggest':
                if (potential_match.get('role') == 'join' and
                        any(artist_type in potential_match['artist_types'] for artist_type in
                            user.get('looking_for', []))):
                    matches.append({
                        'user_id': potential_match_id,
                        'artist_types': potential_match.get('artist_types'),
                        'introduction': potential_match.get('introduction'),
                        'match_user_id': user_id,
                        'match_role': 'suggest'
                    })
            elif user.get('role') == 'join':
                if (potential_match.get('role') == 'suggest' and
                        any(artist_type in user['artist_types'] for artist_type in
                            potential_match.get('looking_for', []))):
                    matches.append({
                        'user_id': potential_match_id,
                        'project_description': potential_match.get('project_description'),
                        'deadline': potential_match.get('deadline'),
                        'match_user_id': user_id,
                        'match_role': 'join'
                    })
        return matches

    async def notify_matches(self, context: ContextTypes.DEFAULT_TYPE, user_id: str):
        matches = self.find_matches(user_id)
        if not matches:
            return

        user = self.user_data.get(str(user_id), {})
        match_text = "🎵 We found some potential collaborators for you!\n\n"
        has_valid_matches = False

        for match in matches:
            match_id = match['user_id']
            if match_id == str(user_id):
                continue

            try:
                chat = await context.bot.get_chat(match_id)
                username = chat.username if chat.username else None
            except Exception as e:
                logger.error(f"Error getting chat info for {match_id}: {e}")
                continue

            if username is None:
                continue

            if user.get('role') == 'join':
                match_text += (
                    f"🎭 Project Description: {match['project_description']}\n"
                    f"📅 Deadline: {match['deadline'] or 'No deadline'}\n"
                    f"📩 Contact: @{username}\n\n"
                )
            else:
                match_text += (
                    f"🎭 Artist Types: {', '.join(match['artist_types'])}\n"
                    f"📝 Introduction: {match['introduction']}\n"
                    f"📩 Contact: @{username}\n\n"
                )
            has_valid_matches = True

        if has_valid_matches:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=match_text
                )
            except Exception as e:
                logger.error(f"Failed to send notification to {user_id}: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [
                InlineKeyboardButton("Join collaboration", callback_data="join"),
                InlineKeyboardButton("Suggest collaboration", callback_data="suggest")
            ],
            [
                InlineKeyboardButton("Delete data", callback_data="delete"),
                InlineKeyboardButton("Help", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.effective_message.reply_text(
            "Welcome to Acoustic Night Collaborations! Choose an option:",
            reply_markup=reply_markup
        )
        return CHOOSING_ROLE

    async def handle_utility_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)

        if query.data == "delete":
            if user_id in self.user_data:
                del self.user_data[user_id]
                save_user_data(self.user_data)
            await query.edit_message_text("All data deleted.")
            return ConversationHandler.END
        elif query.data == "help":
            await query.edit_message_text("Contact support @...")
            return ConversationHandler.END

    async def artist_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        keyboard = [[InlineKeyboardButton(artist_type, callback_data=f"artist_{artist_type}")] 
                   for artist_type in self.artist_types]
        keyboard.append([InlineKeyboardButton("Done", callback_data="done_artist_selection")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Select your artist type(s):",
            reply_markup=reply_markup
        )
        context.user_data['selected_artist_types'] = []
        return ARTIST_TYPE

    async def handle_artist_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "done_artist_selection":
            return await self.collab_type_selection(update, context)
        
        artist_type = query.data.replace('artist_', '')
        if artist_type not in context.user_data['selected_artist_types']:
            context.user_data['selected_artist_types'].append(artist_type)
        return ARTIST_TYPE

    async def collab_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        keyboard = [[InlineKeyboardButton(collab_type, callback_data=f"collab_{collab_type}")] 
                   for collab_type in self.collab_types]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Select collaboration type:",
            reply_markup=reply_markup
        )
        return COLLAB_TYPE

    def main(self):
        token = get_bot_token()
        try:
            application = Application.builder().token(token).build()
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler('start', self.start)],
                states={
                    CHOOSING_ROLE: [CallbackQueryHandler(self.artist_type_selection)],
                    ARTIST_TYPE: [CallbackQueryHandler(self.handle_artist_selection)],
                    COLLAB_TYPE: [CallbackQueryHandler(self.collab_type_selection)],
                },
                fallbacks=[CommandHandler('cancel', lambda update, context: ConversationHandler.END)]
            )
            application.add_handler(conv_handler)
            application.add_handler(CallbackQueryHandler(self.handle_utility_commands))
            application.run_polling()
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

if __name__ == '__main__':
    bot = CollaborationBot()
    bot.main()
