"""Fleet-level endpoints: GET / and GET /types."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from decoct.api.models import TypeListResponse, TypeSummary

router = APIRouter()


@router.get("/")
def get_fleet_overview(request: Request) -> dict[str, Any]:
    """Return Tier A fleet overview."""
    store = request.app.state.store
    return dict(store.tier_a)


@router.get("/types", response_model=TypeListResponse)
def list_types(request: Request) -> TypeListResponse:
    """List all entity types with counts."""
    store = request.app.state.store
    types_section = store.tier_a.get("types", {})
    summaries = []
    for type_id in store.type_ids:
        info = types_section[type_id]
        summaries.append(TypeSummary(
            type_id=type_id,
            count=info.get("count", 0),
            classes=info.get("classes", 0),
            subclasses=info.get("subclasses", 0),
            tier_b_ref=info.get("tier_b_ref", ""),
            tier_c_ref=info.get("tier_c_ref", ""),
            summary=info.get("summary"),
            key_differentiators=info.get("key_differentiators"),
        ))
    return TypeListResponse(types=summaries)
