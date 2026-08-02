"""Typed FMC error taxonomy shared by clients and collectors."""

from __future__ import annotations

from enum import StrEnum


class FmcErrorCategory(StrEnum):
    AUTH_ERROR = "AUTH_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    TEMPORARY_FMC_ERROR = "TEMPORARY_FMC_ERROR"
    UNSUPPORTED_ENDPOINT = "UNSUPPORTED_ENDPOINT"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    STALE_DEVICE = "STALE_DEVICE"
    PARTIAL_RESULT = "PARTIAL_RESULT"


class FmcRequestError(RuntimeError):
    """An FMC failure with a stable machine-readable category."""

    def __init__(
        self,
        category: FmcErrorCategory,
        message: str,
        *,
        path: str,
        status_code: int | None = None,
        response_bytes: int = 0,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.path = path
        self.status_code = status_code
        self.response_bytes = response_bytes


def category_for_status(status_code: int) -> FmcErrorCategory:
    if status_code == 401:
        return FmcErrorCategory.AUTH_ERROR
    if status_code == 403:
        return FmcErrorCategory.PERMISSION_ERROR
    if status_code == 404:
        return FmcErrorCategory.STALE_DEVICE
    if status_code == 429:
        return FmcErrorCategory.RATE_LIMIT
    if status_code in {500, 502, 503, 504}:
        return FmcErrorCategory.TEMPORARY_FMC_ERROR
    if status_code == 400:
        return FmcErrorCategory.INVALID_REQUEST
    return FmcErrorCategory.INVALID_RESPONSE
