"""Shared configuration, credential checks, and client construction.

Both the bot and the scraper need the same three credentials and the same Pinecone
index, so the setup lives here rather than being duplicated in each entry point.
Missing credentials are reported as a single readable message instead of a traceback
from somewhere deep inside a client library.
"""

import logging
import os
import sys

import openai
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

logger = logging.getLogger(__name__)

# Model choices are environment-overridable so a clone can run against whatever
# models its OpenAI account actually has access to.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "gpt-4o")
TRANSLATION_MODEL = os.getenv("TRANSLATION_MODEL", "gpt-4o-mini")

# text-embedding-3-large emits 3072 dimensions. If EMBEDDING_MODEL is changed to
# text-embedding-3-small, set EMBEDDING_DIMENSIONS=1536 to match.
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))

# How many articles to pull from the index as context for one answer.
TOP_K = int(os.getenv("TOP_K", "5"))

# Where to put the index if it has to be created.
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")

_SETUP_HINT = (
    "Copy .env.example to .env and fill in your credentials "
    "(see the Setup section of README.md)."
)


class ConfigError(Exception):
    """Raised when the environment is not usable, with a message meant for humans."""


def require_env(*names):
    """Return the named environment variables, or raise listing everything missing."""
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ".\n"
            + _SETUP_HINT
        )
    return [os.getenv(name) for name in names]


def openai_client():
    """Build an OpenAI client, failing early if the key is absent."""
    (api_key,) = require_env("OPENAI_API_KEY")
    return openai.OpenAI(api_key=api_key)


def pinecone_index():
    """Return the Pinecone index, creating it if it does not exist yet.

    Creating it here means a fresh clone does not have to hand-configure an index
    with the right dimension count before the scraper can store anything.
    """
    api_key, index_name = require_env("PINECONE_API_KEY", "PINECONE_INDEX_NAME")
    pc = Pinecone(api_key=api_key)

    if not pc.has_index(index_name):
        logger.info(
            "Pinecone index %r not found; creating it (%d dimensions, cosine, %s/%s)",
            index_name,
            EMBEDDING_DIMENSIONS,
            PINECONE_CLOUD,
            PINECONE_REGION,
        )
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )

    existing = pc.describe_index(index_name).dimension
    if existing is not None and existing != EMBEDDING_DIMENSIONS:
        raise ConfigError(
            f"Pinecone index {index_name!r} has {existing} dimensions but "
            f"{EMBEDDING_MODEL} produces {EMBEDDING_DIMENSIONS}. Point "
            "PINECONE_INDEX_NAME at an index with the right dimension count, or set "
            "EMBEDDING_DIMENSIONS to match your embedding model."
        )

    return pc.Index(index_name)


def fail(error):
    """Print a configuration error without a traceback and exit non-zero."""
    print(f"Configuration error: {error}", file=sys.stderr)
    sys.exit(1)
