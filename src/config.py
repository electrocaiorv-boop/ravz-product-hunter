"""Centralized environment configuration loading.

Loads variables from a local `.env` file (if present) via python-dotenv,
so the rest of the application can read configuration through
`os.environ.get(...)` without caring whether a value came from the real
shell environment or from `.env`. A real environment variable always
takes precedence over `.env` (python-dotenv's default: override=False).

This module never prints or logs the value of any secret -- only whether
one is configured. `.env` is for local development only and is excluded
from version control by `.gitignore`; only `.env.example` (with empty
values) is committed.
"""

import os

from dotenv import load_dotenv

load_dotenv()

APIFY_API_TOKEN_ENV_VAR = "APIFY_API_TOKEN"


def get_apify_token() -> str | None:
    """Return the configured Apify API token, or None if not set."""
    return os.environ.get(APIFY_API_TOKEN_ENV_VAR) or None


def apify_token_configured() -> bool:
    """Return True if an Apify API token is configured, without exposing it."""
    return get_apify_token() is not None


def describe_apify_token_status() -> str:
    """Human-readable status message. Never includes the token's value."""
    if apify_token_configured():
        return "APIFY_API_TOKEN: configured."
    return (
        "APIFY_API_TOKEN is not configured. Set it in your local .env file "
        "(see .env.example) to enable Apify-based features."
    )
