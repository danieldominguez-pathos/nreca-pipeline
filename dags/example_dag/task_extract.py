"""Extract task helper functions.

This module contains helper functions used by the extract task.
Keeping logic in separate files improves testability and maintainability.

IMPORTANT: These functions are called from within @task.virtualenv tasks,
where all imports must happen inside the function body.
"""

from __future__ import annotations


def generate_items(count: int = 5) -> list[dict]:
    """Generate mock items for extraction.

    Args:
        count: Number of items to generate.

    Returns:
        List of item dictionaries with name and value.
    """
    from datetime import datetime

    return [
        {
            "name": f"item_{i}",
            "value": i * 10,
            "extracted_at": datetime.utcnow().isoformat(),
        }
        for i in range(count)
    ]
