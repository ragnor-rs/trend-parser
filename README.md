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
- Vector storage of trend data using Pinecone, with publication date metadata per article
- Natural language querying of trends by topic, month, and year, filtered by date in the
  vector query itself
- Retrieval Augmented Generation (RAG), with sources cited in the answer
- Month names accepted in any language (translated to English before parsing)
- Deployed on Google Cloud Run

## Prerequisites

- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key
- Pinecone API Key. You do not need to create the index yourself — it is created on first
  run, sized for whichever embedding model is configured.
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

Only the four variables under `# --- Required ---` need values. The optional ones have
working defaults; override `ANSWER_MODEL` / `TRANSLATION_MODEL` / `EMBEDDING_MODEL` if your
OpenAI account does not have access to the defaults.

## Local Development

1. Populate the index first — the bot has nothing to answer from until the scraper has run
   at least once. For a single pass:
```bash
python scraper.py
```

Or as a long-running service that scrapes on startup and then daily:
```bash
python scraper-server.py
```

2. Run the bot:
```bash
python bot.py
```

Then message the bot on Telegram. Because the scraper reads TrendHunter's RSS feed, a fresh
index only holds the ~30 most recent articles, so query the current month.

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
  query with `text-embedding-3-large`, retrieves from Pinecone filtered to the requested
  month, and answers with `gpt-4o`. A `gpt-4o-mini` call translates non-English month
  names.
- **Scraper Service** (`scraper.py`, `scraper-server.py`): discovers articles from
  TrendHunter's RSS feed, reads content, themes, and publication date from each article
  page, and upserts embeddings plus metadata into Pinecone. Runs on startup and then daily.
- **Vector Database**: Pinecone, storing trend embeddings alongside `date`, `year`,
  `month`, `content`, `themes`, and `url` metadata. `year` and `month` are stored as
  numbers so the date filter can be applied inside the query.
- **Shared Config** (`config.py`): credential validation, model selection, and index
  creation, used by both services.

## Known Limitations

- **Coverage is limited to the RSS feed.** The feed carries roughly the 30 most recent
  articles, so the index only accumulates history for as long as the scraper keeps running
  daily; anything published between runs and pushed off the feed is never indexed. There is
  no backfill. TrendHunter was the first of roughly ten candidate trend sources; the rest
  were never implemented.
- **Queries must end in `month year`.** There's no general date parsing — "last spring" or
  a bare topic won't work.
- **The month filter is exact.** A query for a month with nothing indexed returns "no
  relevant trends" rather than widening to nearby months.
- **Both Cloud Run services deploy with `--allow-unauthenticated`.** Only a health-check
  endpoint is exposed, but tighten this if you adapt the config.
- **The scraper depends on TrendHunter's page structure.** Content and themes come from CSS
  selectors against the article pages, which break whenever the site is redesigned — as
  happened when the homepage became a client-side app and the original homepage scraping
  stopped returning anything at all.

## Possible Improvements

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
