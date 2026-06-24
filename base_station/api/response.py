"""Stable JSON response envelopes for the local API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict[str, Any]

    def __iter__(self) -> Iterator[Any]:
        yield self.status
        yield self.body


def success(data: Any = None, status: int = 200) -> ApiResponse:
    return ApiResponse(
        status=int(status),
        body={
            "ok": True,
            "data": data,
            "error": None,
        },
    )


def error(
    code: str,
    message: str,
    status: int = 400,
    details: Any = None,
) -> ApiResponse:
    return ApiResponse(
        status=int(status),
        body={
            "ok": False,
            "data": None,
            "error": {
                "code": str(code),
                "message": str(message),
                "details": details,
            },
        },
    )
