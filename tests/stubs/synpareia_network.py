"""Starlette stub for the synpareia network reputation endpoint.

Mirrors the subset we query from providers.query_synpareia_network:
`GET /api/v1/agents/{identifier}/reputation`.

This is the highest-confidence signal source in the multi-provider model
— it represents verified interaction history on our own platform — so
scenario tests need to show it dominating results when all providers
agree or conflict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from starlette.requests import Request

DEFAULT_FIXTURES: dict[str, dict[str, Any]] = {
    "alice": {
        "interaction_count": 54,
        "average_quality": 0.78,
        "pot_pass_rate": 0.96,
        "reputation_score": 0.82,
    },
    "bob": {
        "interaction_count": 9,
        "average_quality": 0.61,
        "pot_pass_rate": 0.88,
        "reputation_score": 0.55,
    },
    "newcomer": {
        "interaction_count": 0,
        "average_quality": None,
        "pot_pass_rate": None,
    },
}


def make_synpareia_network_app(
    fixtures: dict[str, dict[str, Any]] | None = None,
    *,
    fail_mode: str | None = None,
) -> Starlette:
    data = fixtures if fixtures is not None else DEFAULT_FIXTURES

    async def get_reputation(request: Request) -> JSONResponse:
        if fail_mode == "500":
            return JSONResponse({"error": "server_error"}, status_code=500)
        identifier = request.path_params["identifier"]
        if identifier not in data:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(data[identifier])

    return Starlette(
        routes=[
            Route(
                "/api/v1/agents/{identifier}/reputation",
                get_reputation,
                methods=["GET"],
            ),
        ]
    )
