# Design Trends Telegram Bot

A Telegram bot that provides insights about design trends by analyzing data from TrendHunter.com. The bot uses OpenAI's GPT-4 for generating responses and Pinecone for vector storage.

## Features

- Daily scraping of design trends from TrendHunter.com
- Vector storage of trend data using Pinecone
- Natural language querying of trends by topic, month, and year
- Retrieval Augmented Generation (RAG) for accurate responses
- Deployed on Google Cloud Run

## Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key
- Pinecone API Key and Environment
- Google Cloud Project

## Setup

1. Clone the repository:
```bash
git clone https://github.com/ragnor-rs/trend-parser.git
cd trend-parser
```

2. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a `.env` file with your credentials:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

## Local Development

1. Run the bot:
```bash
python bot.py
```

2. Run the scraper (in a separate terminal). For a single pass:
```bash
python scraper.py
```

Or as a long-running service that scrapes on startup and then daily:
```bash
python scraper-server.py
```

## Deployment to Google Cloud

1. Install and initialize the Google Cloud SDK:
```bash
# Install Google Cloud SDK
gcloud init
```

2. Enable required APIs:
```bash
gcloud services enable cloudbuild.googleapis.com run.googleapis.com
```

3. Deploy using Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml
```

## Usage

1. Start a chat with your bot on Telegram
2. Send a message in the format: `topic month year`
   Example: `sustainable design March 2024`
3. The bot will respond with insights about design trends for your query

## Architecture

- **Bot Service**: Handles Telegram interactions and generates responses using RAG
- **Scraper Service**: Collects and processes trend data daily
- **Vector Database**: Stores trend embeddings and metadata
- **OpenAI Integration**: Generates embeddings and responses

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Disclaimer

This project scrapes publicly available articles from TrendHunter.com and is intended
for personal and educational use. It is not affiliated with or endorsed by TrendHunter.

If you run it, you are responsible for complying with TrendHunter's Terms of Service and
`robots.txt`, and for keeping your request volume reasonable. The scraped articles remain
the property of their respective owners — the MIT license below covers this project's
source code only, not any content it retrieves.

## License

Released under the [MIT License](LICENSE).
