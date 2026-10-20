"""Cloud Run entry point for the scraper: scrapes on startup, then daily."""

import logging
import os
import threading
import time
from datetime import datetime

import schedule
from flask import Flask, jsonify

import config
from scraper import TrendScraper

logger = logging.getLogger(__name__)

app = Flask(__name__)

try:
    scraper = TrendScraper()
except config.ConfigError as e:
    config.fail(e)


def run_scraper():
    try:
        logger.info("Starting scraper run at %s", datetime.now())
        scraper.run()
        logger.info("Completed scraper run at %s", datetime.now())
    except Exception as e:
        logger.error("Error in scraper run: %s", e)


def scheduler_thread():
    run_scraper()

    # Schedule the scraper to run daily
    schedule.every().day.do(run_scraper)

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    # Start the scheduler in a background thread
    threading.Thread(target=scheduler_thread, daemon=True).start()

    # Run the Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
