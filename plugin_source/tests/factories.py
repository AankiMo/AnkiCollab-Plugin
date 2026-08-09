"""factory_boy factories for common data structures used by the addon.

each factory produces a realistic *dict* (or lightweight object) that the addon code
would normally receive from the backend API or the Anki collection.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_guid() -> str:
    return uuid.uuid4().hex[:10]


def _random_hash() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Deck / Subscription
# ---------------------------------------------------------------------------

class SubscriptionFactory(factory.Factory):
    """Builds a *dict* matching the shape returned by the backend manifest."""

    class Meta:
        model = dict

    deck_hash = factory.LazyFunction(_random_hash)
    deck_name = factory.Sequence(lambda n: f"Test Deck {n}")
    human_hash = factory.LazyAttribute(lambda o: o.deck_name.replace(" ", "_").lower())
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    optional_tags = factory.LazyFunction(dict)
    protected_fields = factory.LazyFunction(dict)
    protected_tags = factory.LazyFunction(list)


class DeckConfigFactory(factory.Factory):
    """Builds the per-deck config dict stored inside the addon config."""

    class Meta:
        model = dict

    deckId = factory.Sequence(lambda n: n + 1)
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    optional_tags = factory.LazyFunction(dict)
    stats_enabled = False
    share_stats = False
    last_stats_timestamp = 0


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

class NoteInfoFactory(factory.Factory):
    """Produces a dict that looks like what Anki returns from ``col.get_note()``."""

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: 1_000_000 + n)
    guid = factory.LazyFunction(_random_guid)
    mid = 1
    fields = factory.LazyFunction(lambda: ["front text", "back text"])
    tags = factory.LazyFunction(list)
    flags = 0


class NotePayloadFactory(factory.Factory):
    """A backend note payload (as received from the API)."""

    class Meta:
        model = dict

    guid = factory.LazyFunction(_random_guid)
    fields = factory.LazyFunction(lambda: {"Front": "front text", "Back": "back text"})
    tags = factory.LazyFunction(lambda: ["tag1", "tag2"])
    note_model_name = "Basic"
    note_model_uuid = factory.LazyFunction(lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

class MediaEntryFactory(factory.Factory):
    """A single media-file metadata dict used by the media manager."""

    class Meta:
        model = dict

    filename = factory.Sequence(lambda n: f"image_{n}.png")
    file_hash = factory.LazyFunction(_random_hash)
    file_size = factory.LazyAttribute(lambda o: 1024 * (hash(o.filename) % 100 + 1))
    download_url = factory.LazyAttribute(lambda o: f"https://media.example.com/{o.filename}")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginResultFactory(factory.Factory):
    """Backend login / token-refresh response."""

    class Meta:
        model = dict

    token = factory.LazyFunction(lambda: f"tok_{uuid.uuid4().hex[:16]}")
    refresh_token = factory.LazyFunction(lambda: f"ref_{uuid.uuid4().hex[:16]}")
    expiry = factory.LazyFunction(lambda: (datetime.now(timezone.utc).timestamp()) + 3600)


# ---------------------------------------------------------------------------
# Review / Stats
# ---------------------------------------------------------------------------

class ReviewHistoryEntryFactory(factory.Factory):
    """A single row from review-history SQL results."""

    class Meta:
        model = dict

    card_id = factory.Sequence(lambda n: 5_000_000 + n)
    note_id = factory.Sequence(lambda n: 1_000_000 + n)
    ease = 3
    interval = 30
    time_taken = 8000  # ms
    review_date = factory.LazyFunction(lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
