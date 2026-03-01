"""Shared utilities for Lifeguard modules."""

from __future__ import annotations


def drop_none(d: dict) -> dict:
    """Remove None values from a dictionary.

    Useful for Firestore serialization where None values
    should be excluded rather than stored.
    """
    return {k: v for k, v in d.items() if v is not None}
