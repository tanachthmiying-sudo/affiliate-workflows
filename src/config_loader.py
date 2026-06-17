"""Config loader — reads config.yaml from project root."""
import os
import yaml
from typing import Any, Dict


def load_config(path: str = None) -> Dict[str, Any]:
    """Load config.yaml from project root. Returns empty dict if not found."""
    if not path:
        # Walk up to find config.yaml
        current = os.path.dirname(os.path.abspath(__file__))
        for _ in range(3):
            candidate = os.path.join(current, "config.yaml")
            if os.path.exists(candidate):
                path = candidate
                break
            current = os.path.dirname(current)

    if not path or not os.path.exists(path):
        return {}

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
