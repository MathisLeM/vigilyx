"""
STRIPE CLIENT — Phase 2 ingestion
===================================
Thin wrapper around the Stripe balance_transactions list API.

Responsibilities:
- Paginate through all balance_transactions using cursor-based pagination
  (starting_after parameter, Stripe's standard approach).
- Respect the INGESTION_LOOKBACK_DAYS setting for first-time pulls.
- Validate each raw dict against StripeBalanceTransaction before returning.
- Handle common Stripe errors (AuthenticationError, RateLimitError, APIError).

Does NOT write to the database — that is the ingester's job.

Stripe API reference:
  https://stripe.com/docs/api/balance_transactions/list
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import stripe
from stripe import StripeError, AuthenticationError, RateLimitError

from app.config import settings
from data_contracts.stripe_schemas import StripeBalanceTransaction

logger = logging.getLogger(__name__)

# Max objects per Stripe API page (Stripe hard limit: 100)
PAGE_LIMIT = 100

# Seconds to wait before retrying after a rate-limit response
RATE_LIMIT_SLEEP = 5


class StripeClientError(Exception):
    """Raised when the Stripe API returns an unrecoverable error."""


class StripeAuthError(StripeClientError):
    """Raised when the API key is invalid or has insufficient permissions."""


def _unix(dt: datetime) -> int:
    """Convert a datetime to a Unix timestamp integer."""
    return int(dt.timestamp())


def stream_balance_transactions(
    api_key: str,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> Iterator[StripeBalanceTransaction]:
    """
    Yield validated StripeBalanceTransaction objects from the Stripe API.

    Uses cursor-based pagination (starting_after) to fetch all pages.
    Yields one validated object at a time — the caller controls batching.

    Args:
        api_key:        Stripe secret key (sk_live_xxx or sk_test_xxx).
        created_after:  Fetch transactions created after this datetime (UTC).
                        Defaults to INGESTION_LOOKBACK_DAYS ago.
        created_before: Fetch transactions created before this datetime (UTC).
                        Defaults to now.

    Raises:
        StripeAuthError:   Invalid or expired API key.
        StripeClientError: Unrecoverable Stripe API error.
    """
    now = datetime.now(timezone.utc)

    if created_before is None:
        created_before = now
    if created_after is None:
        created_after = now - timedelta(days=settings.INGESTION_LOOKBACK_DAYS)

    params: dict = {
        "limit": PAGE_LIMIT,
        "created": {
            "gte": _unix(created_after),
            "lte": _unix(created_before),
        },
    }

    logger.info(
        "Stripe stream: %s -> %s",
        created_after.strftime("%Y-%m-%d"),
        created_before.strftime("%Y-%m-%d"),
    )

    total_fetched = 0
    total_validation_errors = 0
    starting_after: str | None = None

    while True:
        if starting_after:
            params["starting_after"] = starting_after

        try:
            response = stripe.BalanceTransaction.list(api_key=api_key, **params)
        except AuthenticationError as exc:
            raise StripeAuthError(f"Invalid Stripe API key: {exc}") from exc
        except RateLimitError:
            logger.warning("Stripe rate limit hit — sleeping %ds", RATE_LIMIT_SLEEP)
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        except StripeError as exc:
            raise StripeClientError(f"Stripe API error: {exc}") from exc

        objects = response.get("data", [])
        if not objects:
            break

        for raw in objects:
            raw_dict = dict(raw)
            try:
                txn = StripeBalanceTransaction.model_validate(raw_dict)
                yield txn
                total_fetched += 1
            except Exception as exc:
                total_validation_errors += 1
                logger.warning(
                    "Validation error for txn %s: %s",
                    raw_dict.get("id", "?"),
                    exc,
                )

        if not response.get("has_more"):
            break

        # Cursor: last ID on this page
        starting_after = objects[-1]["id"]

    logger.info(
        "Stripe stream done: %d fetched, %d validation errors",
        total_fetched,
        total_validation_errors,
    )
