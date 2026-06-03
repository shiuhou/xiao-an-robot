"""Base interface for camera frame sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class FrameSource(ABC):
    """Async source of camera-like frame dictionaries."""

    @abstractmethod
    async def frames(self) -> AsyncIterator[dict]:
        """Yield frame dictionaries."""
        raise NotImplementedError
