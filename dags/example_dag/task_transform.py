"""Transform task helper functions.

This module contains helper functions used by the transform task.
"""

from __future__ import annotations


def transform_item(item: dict) -> dict:
    """Transform a single item.

    Args:
        item: Raw item dictionary.

    Returns:
        Transformed item with additional computed fields.
    """
    return {
        **item,
        "value_doubled": item["value"] * 2,
        "name_upper": item["name"].upper(),
    }


def filter_items(items: list[dict], min_value: int = 0) -> list[dict]:
    """Filter items by minimum value.

    Args:
        items: List of item dictionaries.
        min_value: Minimum value threshold.

    Returns:
        Filtered list of items.
    """
    return [item for item in items if item.get("value", 0) >= min_value]
