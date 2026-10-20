import logging
from datetime import datetime

import telegramify_markdown
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import config

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# httpx logs every request URL at INFO, and the Telegram API embeds the bot token in
# the URL path — which would write the token into the logs on every poll.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class TrendBot:
    def __init__(self):
        self.openai_client = config.openai_client()
        self.index = config.pinecone_index()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "👋 Welcome to the Design Trends Bot! 🎨\n\n"
            "I can help you discover design trends for specific topics, months, and years.\n\n"
            "To get started, just send me a message in this format:\n"
            "`topic month year`\n\n"
            "For example:\n"
            "`sustainable design March 2024`\n"
            "`minimalist furniture January 2024`\n\n"
            "I'll analyze the trends and provide you with insights! 🚀"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📚 How to use the Design Trends Bot:\n\n"
            "1. Send a message with your query in this format:\n"
            "`topic month year`\n\n"
            "2. I'll search through our database of design trends and provide you with relevant insights.\n\n"
            "Examples:\n"
            "- `sustainable design March 2024`\n"
            "- `minimalist furniture January 2024`\n"
            "- `color trends February 2024`\n\n"
            "Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding

    def search_trends(self, query, month=None, year=None):
        query_embedding = self.generate_embedding(query)

        # Filter by date inside the query rather than after it. Retrieving the top
        # matches first and then discarding the ones outside the requested month
        # loses articles that are in the index but rank below the cut.
        date_filter = {}
        if year:
            date_filter['year'] = {'$eq': year}
        if month:
            date_filter['month'] = {'$eq': month}

        results = self.index.query(
            vector=query_embedding,
            top_k=config.TOP_K,
            include_metadata=True,
            filter=date_filter or None
        )

        return list(results.matches)

    def generate_response(self, query, results, month_str, year_str):
        if not results:
            return "I couldn't find any relevant trends for your query. Try a different topic or time period."

        # Prepare context from search results
        context = "\n\n".join([
            f"Content: {r.metadata['content']}\n"
            f"Themes: {', '.join(r.metadata['themes'])}\n"
            f"Source: {r.metadata['url']}"
            for r in results
        ])

        # Generate response using OpenAI
        response = self.openai_client.chat.completions.create(
            model=config.ANSWER_MODEL,
            messages=[
                {"role": "system", "content": "You are a design trends analyst. You provide insightful analysis of design trends based on the given date, query and context. You are a helpful assistant. You are straight to the point and concise."},
                {"role": "system", "content": f"Date:\n{month_str} {year_str}"},
                {"role": "system", "content": f"Query:\n{query}"},
                {"role": "system", "content": f"Context:\n\n{context}"},
                {"role": "user", "content": "Please provide a summary of the design trends. Strictly adhere to the query. Do not invent anything. If there's no topic of the query then admit there's no relevant knowledge in the context. Say you don't know if there's no information in the context. Do not explain nor summarize the context if there's no relevant information in it. Mention the month and the year. Use the language of the query. Add the sources of the information in the separate paragraph as a list if and only if there's relevant information in the context."}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        return response.choices[0].message.content

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            # Parse the message
            message_parts = update.message.text.strip().split()
            # The last two words are the month and the year, so a usable query needs
            # at least one more word for the topic itself.
            if len(message_parts) < 3:
                await update.message.reply_text(
                    "Please provide a topic, month, and year in the format: `topic month year`\n"
                    "Example: `sustainable design March 2024`",
                    parse_mode='Markdown'
                )
                return

            # Extract query components
            topic = " ".join(message_parts[:-2])
            month_str = message_parts[-2]
            year_str = message_parts[-1]

            # Convert month name to English using OpenAI if needed
            try:
                # First try direct conversion
                month = datetime.strptime(month_str, "%B").month
            except ValueError:
                await update.message.chat.send_action(action="typing")

                # If direct conversion fails, use OpenAI to translate the month name
                logger.info(f"Attempting to translate month name: {month_str}")
                translation_prompt = f"Translate the following month name to English. Return ONLY the English month name, nothing else: {month_str}"

                translation_response = self.openai_client.chat.completions.create(
                    model=config.TRANSLATION_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a helpful translator. Translate month names to English."},
                        {"role": "user", "content": translation_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=20
                )

                english_month = translation_response.choices[0].message.content.strip()
                logger.info(f"Translated month name: {english_month}")

                try:
                    month = datetime.strptime(english_month, "%B").month
                    month_str = english_month
                except ValueError:
                    await update.message.reply_text(
                        "Invalid month format. Please use a valid month name in any language."
                    )
                    return

            # Convert year to integer
            try:
                year = int(year_str)
            except ValueError:
                await update.message.reply_text(
                    "Invalid year format. Please use a valid year (e.g., 2024)."
                )
                return

            await update.message.chat.send_action(action="typing")

            # Search for trends
            results = self.search_trends(topic, month, year)

            # Generate response
            response = self.generate_response(topic, results, month_str, year_str)

            # Convert response to Telegram MarkdownV2 format
            telegram_markdown = telegramify_markdown.markdownify(
                response,
                max_line_length=None,  # If you want to change the max line length for links, images, set it to the desired value.
                normalize_whitespace=False
            )

            # Send response with markdown formatting
            await update.message.reply_text(telegram_markdown, parse_mode='MarkdownV2')

        except Exception as e:
            logger.exception(f"Error processing message: {str(e)}")
            await update.message.reply_text(
                "Sorry, I encountered an error while processing your request. Please try again later."
            )

def runBot():
    (token,) = config.require_env("TELEGRAM_BOT_TOKEN")

    # Initialize bot
    application = Application.builder().token(token).build()
    trend_bot = TrendBot()

    # Add handlers
    application.add_handler(CommandHandler("start", trend_bot.start))
    application.add_handler(CommandHandler("help", trend_bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, trend_bot.handle_message))

    # Start the bot
    logger.info("Bot started; polling for messages")
    application.run_polling()

if __name__ == "__main__":
    try:
        runBot()
    except config.ConfigError as e:
        config.fail(e)
