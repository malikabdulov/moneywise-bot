"""Utilities for parsing expense input messages."""

from __future__ import annotations

import re
from typing import Optional

AMOUNT_PATTERN = re.compile(r"(?<!\S)(?P<amount>[\d\s.,]+)(?!\S)")


def parse_expense_text(text: str) -> dict[str, Optional[int | str]]:
    """Parse free form expense text into structured components.

    Parameters
    ----------
    text:
        Raw message received from the user.

    Returns
    -------
    dict
        Mapping with ``amount`` (int), ``category`` (str) and ``description`` (str)
        keys. Values are set to ``None`` when not recognized. A description is
        detected only when an amount is present and corresponds to the text after
        the numeric value. Category corresponds to the text before the amount or
        the whole message if no amount was found.
    """

    cleaned = (text or "").strip()
    if not cleaned:
        return {"amount": None, "category": None, "description": None}

    match = AMOUNT_PATTERN.search(cleaned)
    if match is None:
        if any(char.isdigit() for char in cleaned):
            return {"amount": None, "category": None, "description": None}
        return {"amount": None, "category": cleaned, "description": None}

    raw_amount = match.group("amount")
    normalized_amount = re.sub(r"[^\d]", "", raw_amount)
    if not normalized_amount:
        return {"amount": None, "category": None, "description": None}

    amount = int(normalized_amount)
    if amount <= 0:
        return {"amount": None, "category": None, "description": None}

    before = cleaned[: match.start()].strip()
    after = cleaned[match.end() :].strip()

    category = before or None
    description = after or None

    return {
        "amount": amount,
        "category": category,
        "description": description,
    }
