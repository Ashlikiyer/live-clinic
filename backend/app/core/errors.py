from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    # Call errors (WebSocket `error` events), from the spec.
    STT_FAILED = "STT_FAILED"
    LLM_FAILED = "LLM_FAILED"
    TOOL_FAILED = "TOOL_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    CALL_LIMIT_REACHED = "CALL_LIMIT_REACHED"
    # Generic HTTP errors.
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """An error returned to the client as `{"error": {"code", "message"}}`."""

    def __init__(self, code: ErrorCode, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_body(code: ErrorCode, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code.value, "message": message}}


_STATUS_CODES = {
    401: ErrorCode.UNAUTHORIZED,
    404: ErrorCode.NOT_FOUND,
    429: ErrorCode.RATE_LIMITED,
}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(error_body(ErrorCode.VALIDATION_ERROR, "Invalid request."), status_code=422)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
