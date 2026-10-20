"""Collect TrendHunter articles and store their embeddings in Pinecone.

Articles are discovered through TrendHunter's RSS feed. The homepage used to be
server-rendered and was scraped directly, but it is now a client-side app whose HTML
contains no article links at all; the feed is both the only reliable source of recent
article URLs and the one robots.txt permits. Individual article pages are still
server-rendered, so their content is read from the page itself.
"""

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# One log line per article is useful; one per HTTP request underneath it is not.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("pinecone").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# A descriptive User-Agent is both polite and necessary: the default
# python-requests agent is widely rejected.
USER_AGENT = (
    "trend-parser/1.0 (+https://github.com/ragnor-rs/trend-parser) "
    "python-requests"
)
REQUEST_TIMEOUT = 30


class TrendScraper:
    def __init__(self):
        self.base_url = "https://www.trendhunter.com"
        self.feed_url = f"{self.base_url}/rss"
        self.openai_client = config.openai_client()
        self.index = config.pinecone_index()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get_articles(self):
        """Return [{'url', 'feed_date'}] for the articles currently in the feed.

        The feed's own publication date is kept as a fallback for the few articles
        whose page omits the date metadata.
        """
        response = self.session.get(self.feed_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        channel = ET.fromstring(response.content)
        articles = []
        for item in channel.findall("./channel/item"):
            link = item.findtext("link")
            if not link:
                continue
            # The feed still emits http:// links; the site serves https.
            url = link.strip().replace("http://", "https://", 1)
            articles.append({"url": url, "feed_date": _parse_rss_date(item.findtext("pubDate"))})
        return articles

    def extract_article_data(self, url, feed_date=None):
        full_url = url if url.startswith("http") else f"{self.base_url}{url}"
        response = self.session.get(full_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        date = self._extract_date(soup, feed_date, full_url)

        content_div = soup.select_one("div.tha__articleText")
        content = content_div.text.strip() if content_div else ""

        themes_div = soup.select(".tpt__aSecCont .tpt__aItemText")
        themes = [theme.text.strip() for theme in themes_div]

        return {
            "date": date,
            "content": content,
            "themes": themes,
            "url": full_url,
        }

    def _extract_date(self, soup, feed_date, url):
        """Read the publication date from the article's Open Graph metadata.

        The byline/date text block this used to parse is gone from the current
        markup. Falling back to "now" silently was the worst failure here: every
        article landed in the index stamped with the scrape date, so querying any
        earlier month returned nothing.
        """
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            try:
                return _to_naive_utc(datetime.fromisoformat(meta["content"].replace("Z", "+00:00")))
            except ValueError:
                logger.warning("Unparseable article:published_time on %s: %r", url, meta["content"])

        if feed_date:
            return feed_date

        logger.warning("No publication date found for %s; skipping it", url)
        return None

    def generate_embedding(self, text):
        response = self.openai_client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding

    def process_article(self, article_data):
        content = article_data["content"]

        # Remove the last line if it starts with "Image Credit: "
        content_lines = content.split("\n")
        if content_lines and content_lines[-1].strip().startswith("Image Credit: "):
            content = "\n".join(content_lines[:-1])

        # Clean themes by removing numbering using regex
        cleaned_themes = []
        for theme in article_data["themes"]:
            # Remove numbering like "1.", "1a.", "2b.", etc.
            cleaned_theme = re.sub(r"^[0-9a-zA-Z]+\.\s*", "", theme.strip())
            cleaned_themes.append(cleaned_theme)

        combined_text = f"{content} {' '.join(cleaned_themes)}"
        embedding = self.generate_embedding(combined_text)

        date = article_data["date"]
        metadata = {
            "date": date.isoformat(),
            # year and month are stored separately so the bot can filter by date
            # inside the Pinecone query. Filtering the ISO string is not possible,
            # and filtering after retrieval throws away relevant matches.
            "year": date.year,
            "month": date.month,
            "content": content,
            "themes": cleaned_themes,
            "url": article_data["url"],
        }

        self.index.upsert(
            vectors=[{
                # A stable id, so re-scraping an article updates its vector instead
                # of inserting a duplicate. Python's hash() is salted per process,
                # so it produced a different id on every run.
                "id": hashlib.sha1(article_data["url"].encode("utf-8")).hexdigest(),
                "values": embedding,
                "metadata": metadata,
            }]
        )

    def run(self):
        logger.info("Starting trend scraping...")
        try:
            articles = self.get_articles()
        except (requests.RequestException, ET.ParseError) as e:
            logger.error("Could not read the article feed at %s: %s", self.feed_url, e)
            return 0

        logger.info("Found %d articles in the feed", len(articles))

        stored = 0
        for article in articles:
            url = article["url"]
            try:
                article_data = self.extract_article_data(url, article["feed_date"])
                if not article_data["content"]:
                    logger.warning("No article text found at %s; skipping it", url)
                    continue
                if not article_data["date"]:
                    continue
                self.process_article(article_data)
                stored += 1
                logger.info("Processed article: %s", url)
            except Exception as e:
                logger.error("Error processing article %s: %s", url, e)

        logger.info("Trend scraping completed: stored %d of %d articles", stored, len(articles))
        return stored


def _parse_rss_date(value):
    if not value:
        return None
    try:
        return _to_naive_utc(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def _to_naive_utc(value):
    """Normalise to a naive UTC datetime.

    Dates are compared and stored as plain ISO strings, so mixing offset-aware and
    naive values would make them inconsistent.
    """
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


if __name__ == "__main__":
    try:
        scraper = TrendScraper()
    except config.ConfigError as e:
        config.fail(e)
    scraper.run()
