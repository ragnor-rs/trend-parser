"""Cloud Run entry point for the bot.

Cloud Run requires a process that listens on $PORT, but the bot itself talks to
Telegram by long polling and never serves HTTP. So the health endpoint runs on a
background thread and the bot owns the main thread.
"""

import os
import threading

from flask import Flask, jsonify

import config
from bot import runBot

app = Flask(__name__)


@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200


def serve_health_check():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    threading.Thread(target=serve_health_check, daemon=True).start()

    try:
        runBot()
    except config.ConfigError as e:
        config.fail(e)
