# * gives a short introduction on start
# * receive images, post images (use make sepia)
# * scan for NSFW (dummy instead onnx) and remove with a message

import logging
import os
import asyncio
from io import BytesIO
import random
import colorlog
from PIL import Image
from dotenv import load_dotenv
from telegram import Update, User, Message
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    Application
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

def get_user_info(user: User) -> str:
    """Get formatted user information for logging."""
    return f"User(id={user.id}, username='{user.username or 'None'}', first_name='{user.first_name}')"

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in .env file")

def make_sepia(image: Image.Image) -> Image.Image:
    """
    Apply sepia filter to an image.
    Args:
        image (Image.Image): Original PIL Image
    Returns:
        Image.Image: Sepia-filtered image
    """
    width, height = image.size
    pixels = image.load()  # Load pixel data
    
    for x in range(width):
        for y in range(height):
            r, g, b = pixels[x, y][:3]
            # Sepia formula
            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
            # Ensure values are within valid range
            pixels[x, y] = (
                min(tr, 255),
                min(tg, 255),
                min(tb, 255)
            )
    
    return image

def dummy_nsfw_check(image: Image.Image) -> bool:
    """
    Dummy NSFW detection (random for demonstration).
    In a real implementation, this would use a proper NSFW detection model.
    Args:
        image (Image.Image): Image to check
    Returns:
        bool: True if image is considered inappropriate
    """
    return random.random() < 0.1  # 10% chance of being flagged

def is_private_chat(update: Update) -> bool:
    """
    Check if the message is from a private chat.
    Args:
        update (Update): Telegram update object
    Returns:
        bool: True if private chat, False otherwise
    """
    return update.effective_chat.type == "private"

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /help command.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    # Only respond to help in private chats
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Help command received from {user_info}")

    help_message = (
        "🔍 Available Commands:\n\n"
        "/start - Start the bot and see welcome message\n"
        "/help - Show this help message\n"
        "/clear - Clear chat history and images\n\n"
        "📸 Image Processing:\n"
        "- Send any image to apply sepia filter\n"
        "- Images are automatically checked for inappropriate content\n"
        "- Processing usually takes a few seconds\n"
        "- React with 👍 or ❤️ if you like the result\n"
        "- Use 👎 if you want to give feedback for improvement\n\n"
        "Need more help? Just ask! 😊"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_message
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text messages.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    # Only respond to text messages in private chats
    if not is_private_chat(update):
        return

    # Skip if this is a reaction to a photo
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        return

    text = update.message.text.lower()
    user_info = get_user_info(update.effective_user)
    logger.info(f"Received message from {user_info}: {text}")
    
    if 'bye' in text or 'goodbye' in text:
        logger.info(f"Sending goodbye message to {user_info}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="👋 Goodbye! Feel free to come back anytime. Your images will be waiting!"
        )
    elif 'help' in text:
        await help(update, context)
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Send me an image to process it, or type 'help' to see what I can do! 📸"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /start command.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    # Only respond to /start in private chats
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Start command received from {user_info}")

    welcome_message = (
        "👋 Welcome to the Image Processing Bot!\n\n"
        "I can help you with images in the following ways:\n"
        "1. 🎨 Apply a sepia filter to your images\n"
        "2. 🛡️ Check images for inappropriate content\n"
        "3. 🧹 Clear chat history with /clear\n\n"
        "Just send me any image and I'll process it!\n"
        "Type 'help' anytime to see available commands."
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_message
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Clear chat history and images.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    # Only allow clearing in private chats
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Clear command received from {user_info}")

    try:
        # Get the message ID of the /clear command
        current_message_id = update.message.message_id
        
        # Delete all messages up to the current one
        for message_id in range(current_message_id, 0, -1):
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=message_id
                )
            except Exception:
                # Skip if message can't be deleted (already deleted or too old)
                continue
        
        # Send confirmation (which will be the only message in chat)
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

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming images with processing feedback.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    # Skip processing for non-private chats
    if not is_private_chat(update):
        return

    user_info = get_user_info(update.effective_user)
    logger.info(f"Processing image from {user_info}")

    # Send immediate feedback
    processing_msg = None
    try:
        processing_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔄 Processing your image... Please wait about 5 seconds."
        )
        
        # Get the largest available photo
        photo = max(update.message.photo, key=lambda x: x.file_size)
        
        # Download the image
        image_file = await context.bot.get_file(photo.file_id)
        image_bytes = await image_file.download_as_bytearray()
        
        # Open image with PIL
        image = Image.open(BytesIO(image_bytes))
        
        # Check for NSFW content
        logger.info(f"Checking image content for {user_info}")
        if dummy_nsfw_check(image):
            logger.warning(f"NSFW content detected in image from {user_info} - removing message")
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                if processing_msg:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=processing_msg.message_id
                    )
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ This image has been removed as it may contain inappropriate content."
                )
                logger.info(f"Successfully removed NSFW image from {user_info}")
            except Exception as e:
                logger.error(f"Failed to remove NSFW image from {user_info}: {e}")
            return
        logger.info(f"Content check passed for {user_info}")
        
        # Apply sepia filter
        logger.info(f"Applying sepia filter for {user_info}")
        sepia_image = make_sepia(image)
        
        # Simulate processing time
        await asyncio.sleep(5)
        logger.info(f"Image processing completed for {user_info}")
        
        # Save processed image to bytes
        output = BytesIO()
        sepia_image.save(output, format='JPEG')
        output.seek(0)
        
        # Delete processing message
        if processing_msg:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
        
        # Send processed image with enhanced caption
        logger.info(f"Sending processed image back to {user_info}")
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=output,
            caption="🎨 Here's your image with a sepia filter!\n\n"
                    "Like the result? React with 👍 or ❤️\n"
                    "Want to give feedback? React with 👎\n\n"
                    "Want to process another image? Just send it to me! 📸"
        )
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        # Delete processing message if it exists
        if processing_msg:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=processing_msg.message_id
                )
            except:
                pass
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Sorry, I couldn't process that image. Please try again with another image."
        )

async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle reactions to bot-generated images.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    user_info = get_user_info(update.effective_user)
    logger.debug(f"Reaction handler triggered by {user_info}")

    # Only handle reactions in private chats
    if not is_private_chat(update):
        logger.debug(f"Skipping reaction: not a private chat (type: {update.effective_chat.type})")
        return

    # Check if this is a reply to a message
    if not update.message:
        logger.debug("Skipping reaction: no message object")
        return
    
    if not update.message.reply_to_message:
        logger.debug("Skipping reaction: not a reply to any message")
        return

    # Check if the reaction is to a bot-generated image
    replied_msg = update.message.reply_to_message
    if not replied_msg.from_user:
        logger.debug("Skipping reaction: replied message has no user")
        return
    
    if replied_msg.from_user.id != context.bot.id:
        logger.debug(f"Skipping reaction: replied message not from bot (from user {replied_msg.from_user.id})")
        return
    
    # Only handle reactions to photos
    if not replied_msg.photo:
        logger.debug("Skipping reaction: replied message is not a photo")
        return

    reaction = update.message.text
    logger.debug(f"Processing reaction '{reaction}' from {user_info}")

    try:
        if '👍' in reaction or '❤️' in reaction:
            logger.info(f"Received positive reaction from {user_info}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Thank you! I'm glad you liked the result! 😊"
            )
            logger.debug("Sent positive reaction response")
        elif '👎' in reaction:
            logger.warning(f"Received negative reaction from {user_info}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="I'm sorry you didn't like it. Could you tell me what you didn't like? "
                "This helps me understand how to improve! 🤔"
            )
            logger.debug("Sent negative reaction response")
        else:
            logger.debug(f"Unhandled reaction type: {reaction}")
    except Exception as e:
        logger.error(f"Error handling reaction: {e}")

def main():
    """Initialize and start the bot"""
    logger.info("Starting Image Processing Bot...")
    
    # Create application
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Add handlers in specific order
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(CommandHandler('clear', clear))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    
    # Handle reactions before general text messages
    # reaction_handler = MessageHandler(
    #     filters.TEXT & filters.REPLY & filters.Regex('(👍|👎|❤️)'),
    #     handle_reaction,
    #     block=True  # Ensure reaction handling completes before other handlers
    # )
    reaction_handler = MessageHandler(
        filters.TEXT & filters.REPLY,
        handle_reaction,
        block=True  # Ensure reaction handling completes before other handlers
    )
    application.add_handler(reaction_handler)
    
    # Handle all other text messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text
    ))
    
    # Start the bot
    logger.info("Bot is ready and listening for messages")
    application.run_polling()

if __name__ == '__main__':
    main()
