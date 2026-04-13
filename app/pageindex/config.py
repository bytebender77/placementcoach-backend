"""
PageIndex — Settings
=====================
PageIndex-specific config values, read from the same .env file
as the rest of PlacementCoach (via app.core.config.Settings).
This module just imports `settings` and exposes a typed alias
so PageIndex services don't need to depend on the top-level config.
"""
from app.core.config import settings  # noqa: F401 — re-export

__all__ = ["settings"]
