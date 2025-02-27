# Channel and Group Management Bot
# Features:
# * Token read from .env file 
# * Join/Leave handling on channels and groups where the bot is admin
# * Link checking every 30 minutes for 403 errors
# * Chat monitoring for allowed domains (blndev.com)
# * User warning and kicking system

import logging
import os
import asyncio
import re
from datetime import datetime, timedelta, timezone
import colorlog
from dotenv import load_dotenv
from telegram import Update, User, Chat
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackContext,
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
CHECK_LINKS_INTERVAL = 60  # 30 minutes in seconds
SCAN_MESSAGE_DAYS = 7  # Number of days of messages to scan
USER_WARNINGS = {}  # Store user warnings: {user_id: warning_count}
MONITORED_CHATS = set()  # Store channels and groups where bot is admin

# Store active links for summary
ACTIVE_LINKS = {}  # {chat_id: {url: title}}

import pickle
# In-memory storage for messages
chat_messages = {}
# File path for storing chat messages
CHAT_MESSAGES_FILE = 'chat_messages.pkl'

async def message_store_handler(update: Update, context: CallbackContext):
    logger.debug(f"received update {update.to_json()} with context {context}")
    # Store the message in the chat_messages dictionary
    chat_id = None
    message_id = None
    user_id = None
    message_text = None
    timestamp = None

    if update.channel_post:
        print(f"Channel chat_id: {chat_id}")
        chat_id = update.channel_post.chat_id
        message_id = update.channel_post.message_id
        user_id = None
        message_text = update.channel_post.text
        timestamp = update.channel_post.date

    elif update.message:
        chat_type = update.message.chat.type 
        if chat_type == "private":
            logger.warning(f"Private chat received from chat: {update.message.chat}, msg: {update.message.text}")
            return
        
        chat_id = update.message.chat_id
        message_id = update.message.message_id
        user_id = update.message.from_user.id
        message_text = update.message.text
        timestamp = update.message.date
        
        chat_messages[chat_id].append({
            'message_id': message_id,
            'user_id': user_id,
            'message_text': message_text,
            'timestamp': timestamp
        })
    else:
        logger.warning("no channel post or message. exit analyze function")

    if chat_id not in chat_messages:
        chat_messages[chat_id] = []

    # Optionally, clean up old messages
    clean_up_old_messages(chat_id)
    dump_chat_messages_to_disk()
    #TODO: now add scan logic from other handler

def clean_up_old_messages(chat_id):
    # Remove messages older than 7 days
    #tz = datetime.now().astimezone().tzinfo
    seven_days_ago = datetime.now().astimezone() - timedelta(days=7)
    chat_messages[chat_id] = [
        message for message in chat_messages[chat_id] if message['timestamp'] >= seven_days_ago
    ]

def get_all_chat_ids():
    # Return a list of all chat IDs
    return list(chat_messages.keys())

def get_messages_last_7_days(chat_id):
    # Return messages from the last 7 days for the specified chat
    return chat_messages.get(chat_id, [])

def dump_chat_messages_to_disk():
    with open(CHAT_MESSAGES_FILE, 'wb') as f:
        pickle.dump(chat_messages, f)
    print("Chat messages dumped to disk.")

def load_chat_messages_from_disk():
    global chat_messages
    if os.path.exists(CHAT_MESSAGES_FILE):
        with open(CHAT_MESSAGES_FILE, 'rb') as f:
            chat_messages = pickle.load(f)
        print("Chat messages loaded from disk.")

def get_user_info(user: User) -> str:
    """Get formatted user information for logging."""
    return f"User(id={user.id}, username='{user.username or 'None'}', first_name='{user.first_name}')"

def get_chat_info(chat: Chat) -> str:
    """Get formatted chat information for logging."""
    return f"Chat(id={chat.id}, type='{chat.type}', title='{chat.title or 'None'}')"

async def is_admin(chat_id: int, context: ContextTypes.DEFAULT_TYPE=None, bot=None) -> bool:
    """Check if user is an admin in the chat."""
    try:
        if context and not bot:
            bot = context.bot
        chat_member = await context.bot.get_chat_member(chat_id, user_id=bot.id)
        status = chat_member.status in ['administrator', 'creator']
        logger.debug(f"Bot is Admin in chat {chat_id}: {status}")
        return status
    except TelegramError:
        return False

def extract_urls(text: str) -> list:
    """Extract URLs from text."""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)

async def check_url(url: str) -> tuple[bool, str]:
    """Check if URL returns 403 or 301 error.
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=False, timeout=10) as response:
                if response.status == 403:
                    return False, "403 Forbidden"
                elif response.status == 301:
                    location = response.headers.get('Location', 'unknown')
                    return False, f"301 Moved Permanently to {location}"
                return True, ""
    except Exception as e:
        logger.warning(f"Failed to check URL: {url} - {str(e)}")
        return True, ""  # Assume URL is valid if check fails

async def is_allowed_domain(url: str) -> bool:
    """Check if URL domain is in allowed list."""
    try:
        domain = re.findall(r'https?://(?:www\.)?([^/]+)', url)[0]
        return any(allowed in domain for allowed in ALLOWED_DOMAINS)
    except:
        return False

async def handle_chat_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added to a channel or group."""
    if update.my_chat_member and update.my_chat_member.new_chat_member.user.id == context.bot.id:
        chat_info = get_chat_info(update.effective_chat)
        if update.my_chat_member.new_chat_member.status in ['administrator', 'member']:
            logger.info(f"Bot added to {update.effective_chat.type}: {chat_info}")
            MONITORED_CHATS.add(update.effective_chat.id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="👋 Hello! I'm now monitoring this chat for link safety and domain compliance."
            )
        elif update.my_chat_member.new_chat_member.status == 'left':
            logger.info(f"Bot removed from {update.effective_chat.type}: {chat_info}")
            MONITORED_CHATS.discard(update.effective_chat.id)

# async def update_monitored_chats(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
#     """Update MONITORED_CHATS based on bot's status in the chat."""
#     logger.debug(f"Entering update_monitored_chats for chat_id: {chat_id}")
#     try:
#         # Get current monitoring status
#         was_monitored = chat_id in MONITORED_CHATS
#         # Check bot's status
        
#         if is_admin(chat_id=chat_id, context=context):
#             MONITORED_CHATS.add(chat_id)
#             if not was_monitored:
#                 logger.info(f"Started monitoring chat {chat_id}")
#             else:
#                 logger.debug(f"Continuing to monitor chat {chat_id}")
#         else:
#             if was_monitored:
#                 logger.info(f"Stopped monitoring chat {chat_id}")
#             MONITORED_CHATS.discard(chat_id)
#             logger.debug(f"Chat {chat_id} not monitored")
#     except TelegramError as e:
#         if chat_id in MONITORED_CHATS:
#             logger.info(f"Stopped monitoring chat {chat_id} due to error")
#         logger.warning(f"Could not verify status in chat {chat_id}: {e}")
#         MONITORED_CHATS.discard(chat_id)
#     logger.debug(f"Exiting update_monitored_chats. Total monitored chats: {len(MONITORED_CHATS)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in channels and groups."""
    chat_info = get_chat_info(update.effective_chat)
    logger.debug(f"Entering handle_message for {chat_info}")
    
    # Get the message object based on whether it's a channel post or regular message
    message = update.channel_post if update.channel_post else update.message
    if not message:
        logger.debug("No message found in update, exiting handle_message")
        return

    # Update MONITORED_CHATS on every message
    logger.debug(f"Updating monitored chats status for {chat_info}")
    # await update_monitored_chats(update.effective_chat.id, context)
    urls = await extract_urls(message.text or message.caption or "")

    if urls:
        logger.info(f"Checking URLs in message from {update.effective_chat.type}: {chat_info}")
        for url in urls:
            # Check domain compliance
            if not await is_allowed_domain(url):
                logger.warning(f"Unauthorized domain detected in URL: {url}")
                try:
                    await message.delete()
                    warning_msg = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ Message removed: Contains link to unauthorized domain. Only blndev.com domains are allowed."
                    )
                    # If it's a group message, warn the user
                    if message.from_user:
                        await warn_user(message.from_user.id, update.effective_chat.id, context)
                        # Delete warning message after 30 seconds in groups
                        await asyncio.sleep(30)
                        await warning_msg.delete()
                except TelegramError as e:
                    logger.error(f"Failed to delete message with unauthorized domain: {e}")
                break

async def check_all_links(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task to check all links in channels and groups."""
    logger.info("Starting periodic link check")
    bot = context.bot
    global ACTIVE_LINKS
    for chat_id, messages in chat_messages.items():
        logger.info(f"Checking messages in chat {chat_id}")
        for message in messages:
            #TODO: forbidden word list
            if "nsfw" in message['message_text']:
                try:
                    context.bot.delete_message(chat_id=chat_id, message_id=message['message_id'])
                    print(f"Deleted message {message['message_id']} from chat {chat_id}")
                except Exception as e:
                    print(f"Failed to delete message {message['message_id']} from chat {chat_id}: {e}")
            elif False: #message.new_chat_members or message.left_chat_member:
                #TODO: delete message also 
                # try:
                #     await message.delete()
                #     logger.info(f"Removed join/leave message in chat {chat_id}")
                # except TelegramError as e:
                #     logger.error(f"Failed to delete join/leave message: {e}")
                # continue
                pass
            
            urls = extract_urls(message["message_text"])
            for url in urls:
                # First check domain compliance
                if not await is_allowed_domain(url):
                    logger.warning(f"Found unauthorized domain in URL: {url}")
                    try:
                        context.bot.delete_message(chat_id=chat_id, message_id=message['message_id'])
                        if message.user_id!="":
                            await warn_user(message.user_id, chat_id, context)
                    except TelegramError as e:
                        logger.error(f"Failed to delete message with unauthorized domain: {e}")
                    continue
                else:
                    #allowed urls
                    # Then check for errors
                    is_valid, error_message = await check_url(url)
                    if not is_valid:
                        logger.warning(f"Found error for URL: {url} - {error_message}")
                        try:
                            await message.delete()
                            await bot.send_message(
                                chat_id=chat_id,
                                text=f"🔍 Removed message with broken link ({error_message}): {url}"
                            )
                        except TelegramError as e:
                            logger.error(f"Failed to delete message with broken link: {e}")
                    else:
                        logger.info(f"Found error URL: {url} - add to active links")
                        # Store active link for summary
                        if chat_id not in ACTIVE_LINKS:
                            ACTIVE_LINKS[chat_id] = {}
                        ACTIVE_LINKS[chat_id][url] = message.text or message.caption or url                

    try:
        # Create summary posts for each chat
        for chat_id, links in ACTIVE_LINKS.items():
            if links:
                summary = "📊 Active Links Summary:\n\n"
                for url, title in links.items():
                    summary += f"🔗 {title}\n{url}\n\n"
                try:
                    await bot.send_message(chat_id=chat_id, text=summary)
                except TelegramError as e:
                    logger.error(f"Failed to send summary for chat {chat_id}: {e}")
        
        # Clear active links for next check
        ACTIVE_LINKS.clear()
        logger.info(f"Link check and summary completed for {len(MONITORED_CHATS)} chats")
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
            warning_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Warning {USER_WARNINGS[user_id]}/{WARNING_THRESHOLD}"
            )
            # Delete warning message after 30 seconds in groups
            await asyncio.sleep(30)
            await warning_msg.delete()
        except TelegramError as e:
            logger.error(f"Failed to send warning to user {user_id}: {e}")

async def initialize_monitored_chats(application: Application):
    """Initialize MONITORED_CHATS with all channels and groups where bot is member/admin."""
    # try:
    # Get bot information
    bot = application.bot
    bot_info = await bot.get_me()
    logger.info(f"Initializing monitored chats for bot")

    #     # Get all updates to find initial chats
    #     updates = await bot.get_updates(offset=-1, timeout=1)
    #     initial_chats = set()
    #     for update in updates:
    #         if update.effective_chat:
    #             initial_chats.add(update.effective_chat.id)

    #     # Check bot's status in each chat
    #     for chat_id in initial_chats:
    #         try:
    #             chat = await bot.get_chat(chat_id)
    #             if is_admin(chat_id=chat_id, context=None, bot=bot):
    #                 MONITORED_CHATS.add(chat_id)
    #                 logger.info(f"Added existing chat to monitoring: {get_chat_info(chat)}")
    #         except TelegramError as e:
    #             logger.warning(f"Could not verify status in chat {chat_id}: {e}")

    #     logger.info(f"Initialized monitoring for {len(MONITORED_CHATS)} chats")
    # except Exception as e:
    #     logger.error(f"Error initializing monitored chats: {e}")

def main():
    """Start the bot with proper async handling"""
    logger.info("Starting Chat Management Bot...")
    
    # Load messages from disk
    load_chat_messages_from_disk()

    # Create application
    application = ApplicationBuilder().token(TOKEN).concurrent_updates(True).build()
    
    # create local message store
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_store_handler))

    # Add handlers for both channels and groups
    application.add_handler(MessageHandler(
        (filters.ChatType.CHANNEL | filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & 
        (filters.TEXT | filters.CAPTION), 
        handle_message
    ))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
        handle_chat_join
    ))
    
    # Schedule periodic link checking
    application.job_queue.run_repeating(check_all_links, interval=CHECK_LINKS_INTERVAL, first=10)
    
    # Set up pre-run callback for initialization
    application.post_init = initialize_monitored_chats
    
    # Run the bot
    logger.info("Bot is ready and listening for updates")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
