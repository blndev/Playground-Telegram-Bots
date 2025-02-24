# * the must be read from a .env file 
# * Join/Leave handling on channels where the bot is admin (e.g. delete all User has joined and user has left messages)
# * in a regular interval e.g. check the links posted not by the bot in the last 3 days that they not returning 403
#   - if they return 403, create a post that link xyz is no longer working. 
#   - as a sum show a list of still working links 
# * monitor and maintain channel
#  - Check for not allowed links (only blndev.com) is allowed, remove other links
# * warn users (wrong link)
# * kick users (too many warnings (5))
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

if __name__ == '__main__':
    application = ApplicationBuilder().token('TOKEN').build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    application.run_polling()