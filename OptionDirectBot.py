import logging
import os
import asyncio
from io import BytesIO
import colorlog
from dotenv import load_dotenv
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    Application,
    CallbackQueryHandler
)

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

# Define callback data for menu options
CREATE_CALLBACK = "create"
MODIFY_CALLBACK = "modify"
OPTIMIZE_CALLBACK = "optimize"
CHECK_CALLBACK = "check"
LIKE_CALLBACK = "like"
DISLIKE_CALLBACK = "dislike"

# Store feedback counts
feedback_counts = {
    'likes': 0,
    'dislikes': 0
}

def get_user_info(user: User) -> str:
    """Get formatted user information for logging."""
    return f"User(id={user.id}, username='{user.username or 'None'}', first_name='{user.first_name}')"

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in .env file")

def is_private_chat(update: Update) -> bool:
    """Check if the message is from a private chat."""
    return update.effective_chat.type == "private"

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Help command received from {user_info}")

    help_message = (
        "🤖 Available Commands:\n\n"
        "/start - Start the bot and show main menu\n"
        "/help - Show this help message\n"
        "/clear - Clear chat history\n\n"
        "📋 Menu Options:\n"
        "- Create: Generate new content\n"
        "- Modify: Edit existing images\n"
        "- Optimize: Enhance content\n"
        "- Check: Analyze content\n\n"
        "Need assistance? Just use /help! 😊"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_message
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Start command received from {user_info}")

    # Create menu keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Create 🎨", callback_data=CREATE_CALLBACK)],
        [InlineKeyboardButton("Modify ✏️", callback_data=MODIFY_CALLBACK)],
        [InlineKeyboardButton("Optimize 🔄", callback_data=OPTIMIZE_CALLBACK)],
        [InlineKeyboardButton("Check 🔍", callback_data=CHECK_CALLBACK)]
    ])

    welcome_message = (
        "👋 Welcome to OptionDirectBot!\n\n"
        "I'm here to help you with various tasks.\n"
        "Please select an option from the menu below:"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_message,
        reply_markup=keyboard
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear chat history."""
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Clear command received from {user_info}")

    try:
        current_message_id = update.message.message_id
        
        for message_id in range(current_message_id, 0, -1):
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=message_id
                )
            except Exception:
                continue
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🧹 Chat history has been cleared!"
        )
    except Exception as e:
        logger.error(f"Error clearing chat: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, I couldn't clear the chat history completely. Some messages might be too old to delete."
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle menu selection callbacks."""
    query = update.callback_query
    await query.answer()
    
    user_info = get_user_info(query.from_user)
    logger.info(f"Menu selection from {user_info}: {query.data}")
    
    try:
        if query.data == LIKE_CALLBACK:
            feedback_counts['likes'] += 1
            await query.edit_message_reply_markup(None)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="👍 Thank you for your feedback!"
            )
            return
            
        elif query.data == DISLIKE_CALLBACK:
            feedback_counts['dislikes'] += 1
            await query.edit_message_reply_markup(None)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="👎 Thank you for your feedback. We'll try to improve!"
            )
            return
            
        if query.data == CREATE_CALLBACK:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Please provide a prompt for what you'd like to create:"
            )
            context.user_data['state'] = 'awaiting_create_prompt'
            
        elif query.data == MODIFY_CALLBACK:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Please send the image you'd like to modify:"
            )
            context.user_data['state'] = 'awaiting_modify_image'
            
        elif query.data == OPTIMIZE_CALLBACK:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Optimize option selected (functionality to be implemented)"
            )
            
        elif query.data == CHECK_CALLBACK:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Check option selected (functionality to be implemented)"
            )
            
    except Exception as e:
        logger.error(f"Error handling callback query: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Sorry, there was an error processing your request. Please try again."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages and images based on current state."""
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    current_state = context.user_data.get('state', None)
    
    if current_state == 'awaiting_create_prompt':
        prompt = update.message.text
        logger.info(f"Received create prompt from {user_info}: {prompt}")
        feedback_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍 Like it", callback_data=LIKE_CALLBACK),
                InlineKeyboardButton("👎 Dislike", callback_data=DISLIKE_CALLBACK)
            ]
        ])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Creating content with prompt: {prompt}\n(Functionality to be implemented)",
            reply_markup=feedback_keyboard
        )
        context.user_data['state'] = None
        
    elif current_state == 'awaiting_modify_image':
        if update.message.photo:
            logger.info(f"Received image for modification from {user_info}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Please provide a prompt describing how you'd like to modify the image:"
            )
            context.user_data['state'] = 'awaiting_modify_prompt'
            context.user_data['image_file_id'] = update.message.photo[-1].file_id
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Please send an image to modify."
            )
            
    elif current_state == 'awaiting_modify_prompt':
        prompt = update.message.text
        image_file_id = context.user_data.get('image_file_id')
        logger.info(f"Received modify prompt from {user_info}: {prompt}")
        feedback_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍 Like it", callback_data=LIKE_CALLBACK),
                InlineKeyboardButton("👎 Dislike", callback_data=DISLIKE_CALLBACK)
            ]
        ])
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Modifying image with prompt: {prompt}\n(Functionality to be implemented)",
            reply_markup=feedback_keyboard
        )
        context.user_data['state'] = None
        context.user_data['image_file_id'] = None
        
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please use /start to see available options."
        )

def main():
    """Initialize and start the bot"""
    logger.info("Starting OptionDirectBot...")
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(CommandHandler('clear', clear))
    
    # Add callback query handler for menu selections
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Add message handler for text and photos
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO,
        handle_message
    ))
    
    logger.info("Bot is ready and listening for messages")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
