"""Card retrieval. The SearchBackend protocol lives in cardwise_core.search."""

from cardwise_api.retrieval.grep_backend import Executor, GrepSearchBackend

__all__ = ["Executor", "GrepSearchBackend"]
