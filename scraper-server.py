"""Long-running scraper: scrapes on startup, then once a day."""

import logging
import time
from datetime import datetime

import schedule

import config
from scraper import TrendScraper

logger = logging.getLogger(__name__)


def run_scraper(scraper):
    try:
        logger.info("Starting scraper run at %s", datetime.now())
        scraper.run()
        logger.info("Completed scraper run at %s", datetime.now())
    except Exception as e:
        logger.error("Error in scraper run: %s", e)


if __name__ == '__main__':
    try:
        scraper = TrendScraper()
    except config.ConfigError as e:
        config.fail(e)

    run_scraper(scraper)

    # Schedule the scraper to run daily
    schedule.every().day.do(run_scraper, scraper)

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
