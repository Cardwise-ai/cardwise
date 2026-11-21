"""Vercel entrypoint (see [tool.vercel] in pyproject.toml and vercel.json)."""

from cardwise_api.main import app

__all__ = ["app"]
