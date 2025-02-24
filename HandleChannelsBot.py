# Channel Management Bot
# Features:
# * Token read from .env file 
# * Join/Leave handling on channels where the bot is admin
# * Link checking every 3 days for 403 errors
# * Channel monitoring for allowed domains (blndev.com)
# * User warning and kicking system

import logging
import os
import asyncio
import datetime
import re
from typing import Dict, List, Set
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in .env file")

# Constants
ALLOWED_DOMAIN = "blndev.com"
MAX_WARNINGS = 5
LINK_CHECK_INTERVAL = 3 * 24 * 60 * 60  # 3 days in seconds
WARNING_MESSAGES = {}  # Dict to store user warnings {user_id: warning_count}
POSTED_LINKS = {}  # Dict to store links with timestamps {link: timestamp}

def extract_links(text: str) -> List[str]:
    """
    Extract links from message text using regex.
    Args:
        text (str): Message text to extract links from
    Returns:
        List[str]: List of extracted links
    """
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

async def check_link(link: str) -> bool:
    """
    Check if a link is accessible.
    Args:
        link (str): URL to check
    Returns:
        bool: True if link is accessible, False if returns 403
    """
    try:
        response = requests.head(link, allow_redirects=True, timeout=10)
        return response.status_code != 403
    except:
        return False

async def periodic_link_check(context: CallbackContext):
    """
    Periodically check stored links for accessibility.
    Remove links older than 3 days and report broken links.
    """
    current_time = datetime.datetime.now()
    broken_links = []
    working_links = []
    
    for link, timestamp in list(POSTED_LINKS.items()):
        # Remove links older than 3 days
        if (current_time - timestamp).days > 3:
            del POSTED_LINKS[link]
            continue
            
        if not await check_link(link):
            broken_links.append(link)
        else:
            working_links.append(link)
    
    # Report broken links
    if broken_links:
        message = "🚫 The following links are no longer working:\n"
        message += "\n".join(f"- {link}" for link in broken_links)
        await context.bot.send_message(chat_id=context.job.chat_id, text=message)
    
    # Report working links summary
    if working_links:
        message = "✅ Working links in the last 3 days:\n"
        message += "\n".join(f"- {link}" for link in working_links)
        await context.bot.send_message(chat_id=context.job.chat_id, text=message)

async def handle_join_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle join/leave messages by deleting them.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
    except TelegramError as e:
        logger.error(f"Error deleting join/leave message: {e}")

async def warn_user(chat_id: int, user_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE):
    """
    Warn a user and track warning count.
    Args:
        chat_id (int): Chat ID where warning occurred
        user_id (int): User ID to warn
        reason (str): Reason for warning
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    if user_id not in WARNING_MESSAGES:
        WARNING_MESSAGES[user_id] = 1
    else:
        WARNING_MESSAGES[user_id] += 1
    
    warning_count = WARNING_MESSAGES[user_id]
    message = f"⚠️ Warning {warning_count}/{MAX_WARNINGS}: {reason}"
    
    if warning_count >= MAX_WARNINGS:
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            message = f"🚫 User has been kicked after {MAX_WARNINGS} warnings."
            del WARNING_MESSAGES[user_id]
        except TelegramError as e:
            logger.error(f"Error kicking user: {e}")
    
    await context.bot.send_message(chat_id=chat_id, text=message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming messages, check for unauthorized links.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    if not update.message or not update.message.text:
        return

    links = extract_links(update.message.text)
    if not links:
        return

    unauthorized_links = []
    for link in links:
        if ALLOWED_DOMAIN not in link:
            unauthorized_links.append(link)
        else:
            # Store allowed links for periodic checking
            POSTED_LINKS[link] = datetime.datetime.now()

    if unauthorized_links:
        # Delete message with unauthorized links
        try:
            await context.bot.delete_message(
                chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
        except TelegramError as e:
            logger.error(f"Error deleting message: {e}")

        # Warn user
        warning_text = f"Only links from {ALLOWED_DOMAIN} are allowed."
        await warn_user(
            update.message.chat_id,
            update.message.from_user.id,
            warning_text,
            context
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /start command.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Channel management bot is active! I'm monitoring messages and managing the channel."
    )

def main():
    """Initialize and start the bot"""
    # Create application
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
        handle_join_leave
    ))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Schedule periodic link checking
    job_queue = application.job_queue
    job_queue.run_repeating(periodic_link_check, interval=LINK_CHECK_INTERVAL, first=10)
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
