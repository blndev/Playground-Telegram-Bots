# * gives a short introduction on start
# * receive images, post images (use make sepia)
# * scan for NSFW (dummy instead onnx) and remove with a message

import logging
import os
from io import BytesIO
import random
from PIL import Image
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    Application
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Suppress httpx logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

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

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /help command.
    Args:
        update (Update): Telegram update object
        context (ContextTypes.DEFAULT_TYPE): Context object
    """
    help_message = (
        "🔍 Available Commands:\n\n"
        "/start - Start the bot and see welcome message\n"
        "/help - Show this help message\n"
        "/clear - Clear chat history and images\n\n"
        "📸 Image Processing:\n"
        "- Send any image to apply sepia filter\n"
        "- Images are automatically checked for inappropriate content\n"
        "- Processing usually takes a few seconds\n\n"
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
    text = update.message.text.lower()
    
    if 'bye' in text or 'goodbye' in text:
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
    # Send immediate feedback
    processing_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔄 Processing your image... This usually takes a few seconds."
    )
    
    try:
        # Get the largest available photo
        photo = max(update.message.photo, key=lambda x: x.file_size)
        
        # Download the image
        image_file = await context.bot.get_file(photo.file_id)
        image_bytes = await image_file.download_as_bytearray()
        
        # Open image with PIL
        image = Image.open(BytesIO(image_bytes))
        
        # Check for NSFW content
        if dummy_nsfw_check(image):
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
            # Delete processing message
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ This image has been removed as it may contain inappropriate content."
            )
            return
        
        # Apply sepia filter
        sepia_image = make_sepia(image)
        
        # Save processed image to bytes
        output = BytesIO()
        sepia_image.save(output, format='JPEG')
        output.seek(0)
        
        # Delete processing message
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=processing_msg.message_id
        )
        
        # Send processed image with enhanced caption
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=output,
            caption="🎨 Here's your image with a sepia filter!\nWant to process another image? Just send it to me! 📸"
        )
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        # Delete processing message
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

def main():
    """Initialize and start the bot"""
    # Create application
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(CommandHandler('clear', clear))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
