from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse, Response
from fastapi.routing import APIRoute


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field_errors: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors


def error_response(error: ApiError) -> ORJSONResponse:
    return ORJSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
            "field_errors": error.field_errors,
        },
    )


class ContractRoute(APIRoute):
    """Apply the frozen v1 error envelope only to routers that opt in."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def contract_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except ApiError as error:
                return error_response(error)
            except RequestValidationError as error:
                field_errors = [
                    {
                        "field": ".".join(str(part) for part in item["loc"] if part != "body"),
                        "message": item["msg"],
                    }
                    for item in error.errors()
                ]
                return error_response(ApiError(400, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.", field_errors))

        return contract_handler
