"""Base interface for emotion sample sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class EmotionSource(ABC):
    """Async source of emotion samples for the base station."""

    @abstractmethod
    async def samples(self) -> AsyncIterator[dict]:
        """Yield emotion sample dictionaries."""
        raise NotImplementedError
