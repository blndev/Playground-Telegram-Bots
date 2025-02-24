# Playground-Telegram-Bots

A collection of Proof of Concept (POC) Telegram bots for various purposes.

> **Note**: These bots are Proofs of Concept (POCs) - experimental implementations designed to demonstrate specific features and capabilities. They are intended for learning, testing, and demonstration purposes only. POCs are not production-ready and may lack security features, proper error handling, and scalability considerations that would be necessary for a production environment.

## Setup

1. Clone the repository:
```bash
git clone https://github.com/blndev/Playground-Telegram-Bots.git
cd Playground-Telegram-Bots
```

2. Create and configure environment:
```bash
# Make setup script executable (if not already)
chmod +x setup.sh

# Run setup script to create virtual environment and install dependencies
./setup.sh
```

3. Configure bot tokens:
- Copy the example environment file: `cp .env.example .env`
- Edit `.env` and add your bot tokens

## HandleChannelsBot

A powerful channel management bot that helps maintain channel quality and moderate content. This POC demonstrates automated channel moderation capabilities.

> **POC Limitations**: This implementation uses in-memory storage for warnings and link tracking, which means data is lost when the bot restarts. In a production environment, this would require a persistent database and more robust error handling.

### Features

1. **Automated Message Management**
   - Automatically removes join/leave messages
   - Keeps the channel clean from service messages

2. **Link Monitoring**
   - Checks posted links every 3 days for accessibility
   - Reports broken links (403 errors) to the channel
   - Provides summaries of working links
   - Automatically cleans up links older than 3 days

3. **Domain Restriction**
   - Only allows links from blndev.com
   - Automatically removes messages with unauthorized links
   - Warns users who post unauthorized links

4. **User Management**
   - Warning system for rule violations
   - Tracks user warnings
   - Automatically kicks users after 5 warnings
   - Maintains channel quality through consistent enforcement

### Usage

1. Ensure setup is complete and virtual environment is activated
2. Add your Telegram bot token to `.env`
3. Run the bot:
```bash
python HandleChannelsBot.py
```

The bot will start monitoring the channel, managing messages, and checking links automatically.

## HandleImagesBot

An image processing bot that applies filters and moderates content. This POC demonstrates basic image processing and content moderation concepts.

> **POC Limitations**: Uses a dummy NSFW detection (random 10% chance) instead of a real machine learning model. The sepia filter implementation is basic and processes images in memory. A production version would need proper image validation, efficient processing, and a real content detection model.

### Features

1. **Image Processing**
   - Applies sepia filter to uploaded images
   - Processes images of various sizes
   - Returns processed images with filters applied

2. **Content Moderation**
   - Scans images for inappropriate content
   - Automatically removes potentially NSFW images
   - Provides feedback when content is removed

3. **User Interface**
   - Friendly welcome message with usage instructions
   - Interactive help system (type 'help' or use /help)
   - Clear feedback on all operations
   - Simple to use - just send an image
   - /clear command to remove chat history

4. **Chat Management**
   - Clear entire chat history with a single command
   - Removes all messages and images
   - Provides feedback on clearing operation

5. **Interactive Features**
   - Responds to natural language help requests
   - Provides processing status updates
   - Friendly goodbye messages
   - Helpful suggestions for next actions
   - Real-time feedback during image processing

### Usage

1. Ensure setup is complete and virtual environment is activated
2. Add your Telegram bot token to `.env`
3. Run the bot:
```bash
python HandleImagesBot.py
```

Send any image to the bot, and it will process it with a sepia filter while checking for inappropriate content.
