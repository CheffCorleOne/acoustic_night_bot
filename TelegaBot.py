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
from datetime import datetime

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
        """Find matching collaborators based on user preferences."""
        matches = []
        user = self.user_data.get(str(user_id), {})

        # Debug print
        print(f"Finding matches for user_id: {user_id}")
        print(f"User data: {user}")

        # Ensure user has role and relevant data
        if 'role' not in user:
            user['role'] = 'suggest' if 'project_description' in user and 'looking_for' in user else 'join'
            self.user_data[str(user_id)] = user  # Save inferred role back to user data
            print(f"Role inferred for user {user_id}: {user['role']}")

        for potential_match_id, potential_match in self.user_data.items():
            if potential_match_id == str(user_id):
                continue  # Skip self-matching

            # Debug print for each potential match
            print(f"Checking potential match: {potential_match_id} with role {potential_match.get('role')}")

            # If current user is suggesting collaboration
            if user.get('role') == 'suggest':
                print(f"User {user_id} is suggesting collaboration, checking for a match with {potential_match_id}")
                if (potential_match.get('role') == 'join' and
                        any(artist_type in potential_match['artist_types'] for artist_type in
                            user.get('looking_for', []))):
                    match_data = {
                        'user_id': potential_match_id,
                        'artist_types': potential_match.get('artist_types'),
                        'introduction': potential_match.get('introduction'),
                        'match_user_id': user_id,
                        'match_role': 'suggest'
                    }
                    matches.append(match_data)
                    print(f"Match found: {match_data}")

            # If current user is looking to join a collaboration
            elif user.get('role') == 'join':
                print(f"User {user_id} is looking to join, checking for a match with {potential_match_id}")
                if (potential_match.get('role') == 'suggest' and
                        any(artist_type in user['artist_types'] for artist_type in
                            potential_match.get('looking_for', []))):
                    match_data = {
                        'user_id': potential_match_id,
                        'project_description': potential_match.get('project_description'),
                        'deadline': potential_match.get('deadline'),
                        'match_user_id': user_id,
                        'match_role': 'join'
                    }
                    matches.append(match_data)
                    print(f"Match found: {match_data}")

        # Final match list print
        print(f"Matches found for user {user_id}: {matches}")
        return matches

    async def notify_matches(self, context: ContextTypes.DEFAULT_TYPE, user_id: str):
        """Notify users about their matches without duplication and avoid self-notification."""
        print(f"Notifying matches for user_id: {user_id}")

        matches = self.find_matches(user_id)
        print(f"Matches found: {matches}")  # Add this debug line

        if not matches:
            print(f"No matches found for user {user_id}")  # Add this to confirm no matches
            return
        user = self.user_data.get(str(user_id), {})

        match_text = "🎵 We found some potential collaborators for you!\n\n"
        notified_users = set()  # Track users to avoid duplicate notifications
        has_valid_matches = False  # Ensure we send only relevant messages

        for match in matches:
            match_id = match['user_id']

            # Skip if the match is the requesting user (to avoid self-notification)
            if match_id == str(user_id):
                print(f"Skipping self-notification for {user_id}")
                continue  # Skip notifying the requesting user about themselves

            try:
                chat = await context.bot.get_chat(match_id)
                username = chat.username if chat.username else None
            except Exception as e:
                logger.error(f"Error getting chat info for {match_id}: {e}")
                continue

            if username is None:
                logger.warning(f"Skipping user {match_id} due to missing username")
                continue  # Avoid sending messages with @None

            # Format message for the requesting user
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

            has_valid_matches = True  # At least one valid match was found

            # Notify the matched user if not already notified
            # if match_id not in notified_users:
            #     notified_users.add(match_id)
            #     match_notification = (
            #         "🎵 We found a potential collaborator for you!\n\n"
            #         f"They are interested in your {'project' if user.get('role') == 'suggest' else 'application'}!\n"
            #         f"📩 Contact: @{username}\n"
            #     )
            #     try:
            #         await context.bot.send_message(
            #             chat_id=match_id,
            #             text=match_notification
            #         )
            #         print(f"Sent notification to {match_id}")
            #     except Exception as e:
            #         logger.error(f"Failed to send notification to {match_id}: {e}")

        # Send the summary message only if there were valid matches
        if has_valid_matches:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=match_text
                )
                print(f"Sent match summary to {user_id}")
            except Exception as e:
                logger.error(f"Failed to send notification to {user_id}: {e}")
        else:
            print(f"No valid matches found for user {user_id}, skipping notification.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [
                InlineKeyboardButton("I am open to joining a collaboration", callback_data="join"),
                InlineKeyboardButton("I want to suggest a collaboration", callback_data="suggest")
            ],
            [
                InlineKeyboardButton("Delete everything", callback_data="delete"),
                InlineKeyboardButton("Start over", callback_data="start_over")
            ],
            [
                InlineKeyboardButton("Add a new application", callback_data="new_app"),
                InlineKeyboardButton("Help", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Hello! Dear user, we welcome you to Acoustic Night Collaborations! "
            "Here, we help you find other artists to collaborate with. "
            "It could be used for any personal projects or to find other artists "
            "to perform at Acoustic Night concerts. Let's start!",
            reply_markup=reply_markup
        )
        return CHOOSING_ROLE

    async def notify_all_users(self, context: ContextTypes.DEFAULT_TYPE):
        """Notify all users about their matches."""
        print("Scheduling user notifications...")
        for user_id in self.user_data.keys():
            print(f"Sending notifications for user_id: {user_id}")
            try:
                await self.notify_matches(context, user_id)
            except Exception as e:
                print(f"Error notifying user {user_id}: {e}")

    async def artist_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        print(f"Received callback data: {query.data}")  # Log the callback data

        if query.data in ["delete", "start_over", "new_app", "help"]:
            return await self.handle_utility_commands(update, context)

        keyboard = [[InlineKeyboardButton(artist_type, callback_data=f"artist_{artist_type}")]
                    for artist_type in self.artist_types]
        keyboard.append([InlineKeyboardButton("Done", callback_data="done_artist_selection")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "What kind of artist are you? (You can select multiple)",
            reply_markup=reply_markup
        )

        context.user_data['selected_artist_types'] = []
        context.user_data['role'] = query.data  # 'join' or 'suggest'

        return ARTIST_TYPE

    async def handle_utility_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = str(query.from_user.id)

        if query.data == "delete":
            if user_id in self.user_data:
                del self.user_data[user_id]
                save_user_data(self.user_data)
            await query.edit_message_text("All your applications have been deleted.")
            return ConversationHandler.END

        elif query.data == "start_over":
            await query.edit_message_text("Let's start over!")
            return await self.start(update, context)

        elif query.data == "new_app":
            await query.edit_message_text("Let's create a new application!")
            return await self.start(update, context)

        elif query.data == "help":
            await query.edit_message_text(
                "If you need assistance, please describe your issue here. "
                "The creators will get back to you as soon as possible."
            )
            return ConversationHandler.END

    async def handle_artist_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "done_artist_selection":
            if context.user_data['role'] == 'join':
                return await self.collab_type_selection(update, context)
            elif context.user_data['role'] == 'suggest':
                return await self.looking_for_selection(update, context)

        artist_type = query.data.replace('artist_', '')
        if artist_type not in context.user_data['selected_artist_types']:
            context.user_data['selected_artist_types'].append(artist_type)

        await query.answer(f"Selected: {artist_type}")
        return ARTIST_TYPE

    async def collab_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        keyboard = [[InlineKeyboardButton(collab_type, callback_data=f"collab_{collab_type}")]
                    for collab_type in self.collab_types]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "What kind of collaboration are you looking for?",
            reply_markup=reply_markup
        )
        return COLLAB_TYPE

    async def handle_collab_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        collab_type = query.data.replace('collab_', '')
        context.user_data['collab_type'] = collab_type

        await query.edit_message_text(
            "You can introduce yourself here (people who are suggesting "
            "collaborations will see this):"
        )
        return INTRODUCTION

    async def looking_for_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        keyboard = [[InlineKeyboardButton(artist_type, callback_data=f"looking_{artist_type}")]
                    for artist_type in self.artist_types]
        keyboard.append([InlineKeyboardButton("Done", callback_data="done_looking_selection")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Whom are you looking for? (You can select multiple)",
            reply_markup=reply_markup
        )
        return LOOKING_FOR

    async def handle_looking_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "done_looking_selection":
            await query.edit_message_text(
                "Please write a description of your project, the artists you are "
                "looking for will see your message and will decide whether or "
                "not they want to join you:"
            )
            return PROJECT_DESCRIPTION

        artist_type = query.data.replace('looking_', '')
        if 'looking_for' not in context.user_data:
            context.user_data['looking_for'] = []

        if artist_type not in context.user_data['looking_for']:
            context.user_data['looking_for'].append(artist_type)

        await query.answer(f"Selected: {artist_type}")
        return LOOKING_FOR

    async def handle_project_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_message = update.message.text
        context.user_data['project_description'] = user_message

        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="yes_deadline"),
                InlineKeyboardButton("No", callback_data="no_deadline")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Does your application have a deadline?",
            reply_markup=reply_markup
        )
        return DEADLINE_CHOICE

    async def handle_deadline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Check if the update contains a callback query
        if update.callback_query:
            query = update.callback_query
            user_id = query.from_user.id  # Extracting user_id from the callback query
            print(f"handle_deadline triggered for user_id: {user_id}")

            await query.answer()  # Acknowledge the callback query

            if query.data == "yes_deadline":
                await query.edit_message_text("Please enter the deadline date (YYYY-MM-DD format):")
                return DEADLINE_DATE
            else:
                self.user_data[str(user_id)] = {
                    'artist_types': context.user_data.get('selected_artist_types', []),
                    'looking_for': context.user_data.get('looking_for', []),
                    'project_description': context.user_data.get('project_description'),
                    'deadline': None
                }
                save_user_data(self.user_data)

                print(f"Calling notify_matches for user_id: {user_id}")
                await self.notify_matches(context, user_id)

                await query.edit_message_text(
                    "Thank you for your application! You will be notified if other "
                    "artists decide to join your collaboration!"
                )
                return ConversationHandler.END
        else:
            # If the update does not contain a callback query, log an error or handle accordingly
            print("Received update without a callback query!")

    async def handle_deadline_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            deadline_date = datetime.strptime(update.message.text, '%Y-%m-%d')
            context.user_data['deadline'] = deadline_date.strftime('%Y-%m-%d')

            user_id = update.effective_user.id
            self.user_data[str(user_id)] = {
                'artist_types': context.user_data.get('selected_artist_types', []),
                'looking_for': context.user_data.get('looking_for', []),
                'project_description': context.user_data.get('project_description'),
                'deadline': context.user_data['deadline'],
                'role': context.user_data['role']
            }
            save_user_data(self.user_data)

            await update.message.reply_text(
                "Thank you for your application! You will be notified if other "
                "artists decide to join your collaboration!"
            )
            return ConversationHandler.END

        except ValueError:
            await update.message.reply_text(
                "Invalid date format. Please use YYYY-MM-DD format (e.g., 2025-12-31):"
            )
            return DEADLINE_DATE

    async def handle_introduction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_message = update.message.text
        user_id = update.effective_user.id

        self.user_data[str(user_id)] = {
            'artist_types': context.user_data.get('selected_artist_types', []),
            'collab_type': context.user_data.get('collab_type'),
            'introduction': user_message,
            'role': context.user_data.get('role')
        }
        save_user_data(self.user_data)

        await update.message.reply_text(
            "Thank you for your application! You will be notified about the "
            "upcoming collaboration suggestions and will have the opportunity "
            "to decide if you would want to join it."
        )
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END

    def init_jobs(self, application: Application):
        """Initialize jobs after the bot is ready."""
        print("Scheduling user notifications...")
        application.job_queue.run_once(self.notify_all_users, 0)

    def main(self):
        token = get_bot_token()

        try:
            print("Starting bot...")
            application = Application.builder().token(token).build()

            conv_handler = ConversationHandler(
                entry_points=[CommandHandler('start', self.start)],
                states={
                    CHOOSING_ROLE: [CallbackQueryHandler(self.artist_type_selection)],
                    ARTIST_TYPE: [CallbackQueryHandler(self.handle_artist_selection)],
                    COLLAB_TYPE: [CallbackQueryHandler(self.handle_collab_selection)],
                    INTRODUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_introduction)],
                    LOOKING_FOR: [CallbackQueryHandler(self.handle_looking_selection)],
                    PROJECT_DESCRIPTION: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_project_description)],
                    DEADLINE_CHOICE: [CallbackQueryHandler(self.handle_deadline)],
                    DEADLINE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_deadline_date)]
                },
                fallbacks=[CommandHandler('cancel', self.cancel)]
            )

            application.add_handler(conv_handler)
            print("Bot is running! Press Ctrl+C to stop.")

            # Notify users before the bot starts polling
            print("Scheduling user notifications...")
            application.job_queue.run_once(self.notify_all_users, 0)

            application.run_polling()

        except Exception as e:
            print(f"Error starting bot: {e}")
            print("Please check if your token is correct and try again.")
            sys.exit(1)


if __name__ == '__main__':
    bot = CollaborationBot()
    bot.main()


