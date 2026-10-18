# Design Trends Telegram Bot

A Telegram bot that answers natural-language questions about design trends, grounded in
articles scraped daily from TrendHunter.com. Ask it `color trends April 2025` and it
retrieves the relevant articles from a vector index, feeds them to an LLM as context, and
answers with sources — rather than inventing an answer from the model's training data.

## Background

This started in early 2025 as a request from a design studio that wanted to speed up its
trend research: instead of a human reading trend sites every week, a bot that could be
asked "what's new in design for fintech?" and answer from what it had actually read.

The first prototype was built on [n8n](https://n8n.io) — no-code, fast to assemble, and
good enough to prove the idea worked. It was then rewritten in Python because the no-code
version was hard to control in the details that mattered (prompting, chunking, retrieval
filtering) and noticeably slower. The git history here starts at that rewrite.

Two things were learned the expensive way and are worth stating up front, since they shape
the current design:

- **Embedding and generation model quality dominates everything else.** An earlier version
  on `text-embedding-3-small` kept answering "I'm currently unable to provide specific
  information" even when relevant articles *were* in the context. Chunk-size tuning and
  index rebuilds didn't fix it; moving to `text-embedding-3-large` did.
- **Conversation memory made answers worse, not better.** Mixing prior messages into the
  retrieval context mostly injected noise, so each query is now answered independently
  with no chat history.

## Features

- Daily scraping of design trends from TrendHunter.com
- Vector storage of trend data using Pinecone, with `date` metadata per article
- Natural language querying of trends by topic, month, and year
- Retrieval Augmented Generation (RAG), with sources cited in the answer
- Month names accepted in any language (translated to English before parsing)
- Deployed on Google Cloud Run

## Prerequisites

- Python 3.11+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key
- Pinecone API Key and an index sized for `text-embedding-3-large` (3072 dimensions)
- Google Cloud Project (only if deploying)

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

Note that the bot has nothing to answer from until the scraper has populated the index at
least once.

## Usage

Start a chat with your bot on Telegram and send a message ending with a month and year:

```
topic month year
```

The topic can be several words; the last two words are always parsed as month and year.

**Example — `furniture april 2025`:**

> The furniture design trends as of April 2025 highlight a focus on multifunctionality,
> integration of technology, and personalized design reflecting individual lifestyles and
> community. Key trends include:
>
> 1. **Architectural-inspired Furniture**: Furniture designs are increasingly drawing
>    inspiration from architectural elements, transforming ordinary pieces into miniature
>    landscapes that reflect personal and communal identities.
> 2. **Community-centric Design**: There's a growing emphasis on designs that foster a
>    sense of community within living spaces […]

**Example — `color trends april 2025`:**

> In April 2025, design trends are significantly influenced by sustainability, technology,
> personal well-being, and the integration of creativity in everyday experiences […]
>
> Sources:
> - https://www.trendhunter.com/slideshow/april-2025-eco
> - https://www.trendhunter.com/slideshow/april-2025-art-design
> - https://www.trendhunter.com/slideshow/april-2025-lifestyle

**Example — `модные цвета апрель 2025`** (month names in other languages are translated
before parsing, and the answer comes back in the language of the query):

> Основные точки дизайнерских тенденций:
>
> 1. **Пастельные Тоны и Мягкие Цвета**: Введение пастельных тонов в модели кроссовок
>    New Balance указывает на сдвиг к более мягким цветовым палитрам […]

When the index holds nothing relevant, the bot says so instead of guessing — that behaviour
is deliberate and prompted for.

## Architecture

- **Bot Service** (`bot.py`, `bot-server.py`): handles Telegram interactions, embeds the
  query with `text-embedding-3-large`, retrieves from Pinecone, and answers with
  `gpt-4-turbo-preview`. A `gpt-3.5-turbo` call translates non-English month names.
- **Scraper Service** (`scraper.py`, `scraper-server.py`): collects articles linked from
  the TrendHunter homepage, extracts content, themes, and publication date, and upserts
  embeddings plus metadata into Pinecone. Runs on startup and then daily.
- **Vector Database**: Pinecone, storing trend embeddings alongside `date`, `content`,
  `themes`, and `url` metadata.

## Known Limitations

- **Date filtering happens after retrieval, not during it.** The bot asks Pinecone for the
  top 5 semantic matches and *then* discards those outside the requested month. If none of
  the top 5 fall in that month, you get "no relevant trends" even when the index does hold
  matching articles. This is the most common cause of a disappointing answer. Filtering via
  Pinecone metadata query instead would fix it.
- **Coverage is limited to the TrendHunter homepage.** The scraper only follows links
  present on the front page at scrape time, so anything that scrolled off between daily
  runs is never indexed. TrendHunter was the first of roughly ten candidate trend sources;
  the rest were never implemented.
- **Queries must end in `month year`.** There's no general date parsing — "last spring" or
  a bare topic won't work.
- **`bot-server.py` has an unreachable scheduler loop.** `app.run()` blocks before the
  `while True` beneath it, so that loop never executes.
- **`pinecone-client` is deprecated** in favour of the `pinecone` package; the pin here
  still installs but will eventually need updating.
- **Both Cloud Run services deploy with `--allow-unauthenticated`.** Only a health-check
  endpoint is exposed, but tighten this if you adapt the config.

## Possible Improvements

- Filter by date in the Pinecone query rather than after retrieval
- Add the remaining trend sources beyond TrendHunter
- Follow pagination/archives so backfill isn't limited to the homepage
- Consider letting the model read arbitrary sites directly instead of maintaining a
  hand-written scraper per source

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
