import logging
import os
import asyncio
import re
from datetime import datetime, timedelta
import colorlog
from dotenv import load_dotenv
from telegram import Update, User, Chat
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    Application
)
from telegram.error import TelegramError
import aiohttp

# Configure colored logging
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }
))

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Suppress httpx logging
logging.getLogger("httpx").setLevel(logging.WARNING)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in .env file")

# Constants
ALLOWED_DOMAINS = ['blndev.com']
WARNING_THRESHOLD = 3
CHECK_LINKS_INTERVAL = 3 * 24 * 60 * 60  # 3 days in seconds
USER_WARNINGS = {}  # Store user warnings: {user_id: warning_count}

def get_user_info(user: User) -> str:
    """Get formatted user information for logging."""
    return f"User(id={user.id}, username='{user.username or 'None'}', first_name='{user.first_name}')"

def get_chat_info(chat: Chat) -> str:
    """Get formatted chat information for logging."""
    return f"Chat(id={chat.id}, type='{chat.type}', title='{chat.title or 'None'}')"

async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is an admin in the channel."""
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['administrator', 'creator']
    except TelegramError:
        return False

async def extract_urls(text: str) -> list:
    """Extract URLs from text."""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

async def check_url(url: str) -> bool:
    """Check if URL returns 403 error."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True, timeout=10) as response:
                return response.status != 403
    except:
        logger.warning(f"Failed to check URL: {url}")
        return True  # Assume URL is valid if check fails

async def is_allowed_domain(url: str) -> bool:
    """Check if URL domain is in allowed list."""
    try:
        domain = re.findall(r'https?://(?:www\.)?([^/]+)', url)[0]
        return any(allowed in domain for allowed in ALLOWED_DOMAINS)
    except:
        return False

async def handle_channel_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added to a channel."""
    if update.my_chat_member and update.my_chat_member.new_chat_member.user.id == context.bot.id:
        chat_info = get_chat_info(update.effective_chat)
        if update.my_chat_member.new_chat_member.status in ['administrator', 'member']:
            logger.info(f"Bot added to channel: {chat_info}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="👋 Hello! I'm now monitoring this channel for link safety and domain compliance."
            )
        elif update.my_chat_member.new_chat_member.status == 'left':
            logger.info(f"Bot removed from channel: {chat_info}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in channels."""
    if not update.channel_post:
        return

    chat_info = get_chat_info(update.effective_chat)
    message = update.channel_post
    urls = await extract_urls(message.text or message.caption or "")

    if urls:
        logger.info(f"Checking URLs in message from channel: {chat_info}")
        for url in urls:
            # Check domain compliance
            if not await is_allowed_domain(url):
                logger.warning(f"Unauthorized domain detected in URL: {url}")
                try:
                    await message.delete()
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ Message removed: Contains link to unauthorized domain. Only blndev.com domains are allowed."
                    )
                except TelegramError as e:
                    logger.error(f"Failed to delete message with unauthorized domain: {e}")
                break

async def check_all_links(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task to check all links in channels for 403 errors."""
    logger.info("Starting periodic link check")
    bot = context.bot
    
    async def check_channel_messages(chat_id):
        try:
            # Get chat information
            chat = await bot.get_chat(chat_id)
            if chat.pinned_message:
                # Check pinned message
                message = chat.pinned_message
                if message.text or message.caption:
                    urls = await extract_urls(message.text or message.caption or "")
                    for url in urls:
                        if not await check_url(url):
                            logger.warning(f"Found 403 error for URL: {url}")
                            try:
                                await message.delete()
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=f"🔍 Removed message with broken link (403 error): {url}"
                                )
                            except TelegramError as e:
                                logger.error(f"Failed to delete message with 403 link: {e}")
        except TelegramError as e:
            logger.error(f"Error checking messages in channel {chat_id}: {e}")

    try:
        # Note: In a production environment, you would maintain a database of channels
        # For demonstration, we'll just log that the check was attempted
        logger.info("Link check attempted - In production, this would check all monitored channels")
    except Exception as e:
        logger.error(f"Error during link check: {e}")

async def warn_user(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Warn a user and kick if threshold reached."""
    if user_id not in USER_WARNINGS:
        USER_WARNINGS[user_id] = 1
    else:
        USER_WARNINGS[user_id] += 1

    if USER_WARNINGS[user_id] >= WARNING_THRESHOLD:
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"User has been removed after {WARNING_THRESHOLD} warnings."
            )
            del USER_WARNINGS[user_id]
        except TelegramError as e:
            logger.error(f"Failed to ban user {user_id}: {e}")
    else:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Warning {USER_WARNINGS[user_id]}/{WARNING_THRESHOLD}"
            )
        except TelegramError as e:
            logger.error(f"Failed to send warning to user {user_id}: {e}")

def main():
    """Initialize and start the bot"""
    logger.info("Starting Channel Management Bot...")
    
    # Create application
    application = ApplicationBuilder().token(TOKEN).concurrent_updates(True).build()
    
    # Add handlers
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.UpdateType.CHANNEL_POST, handle_message))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_channel_join))
    
    # Schedule periodic link checking
    #application.job_queue.run_repeating(check_all_links, interval=CHECK_LINKS_INTERVAL, first=10)
    
    # Start the bot
    logger.info("Bot is ready and listening for channel updates")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
