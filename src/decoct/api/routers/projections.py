"""Projection endpoints: GET /types/{type_id}/projections."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from decoct.api.models import ProjectionListResponse

router = APIRouter(prefix="/types/{type_id}/projections")


@router.get("", response_model=ProjectionListResponse)
def list_projections(request: Request, type_id: str) -> ProjectionListResponse:
    """List available projections for a type."""
    store = request.app.state.store
    if not store.has_type(type_id):
        raise HTTPException(status_code=404, detail=f"Type '{type_id}' not found")
    subjects = store.projection_index.get(type_id, [])
    return ProjectionListResponse(type_id=type_id, subjects=subjects)


@router.get("/{subject}")
def get_projection(request: Request, type_id: str, subject: str) -> dict[str, Any]:
    """Return projection data for a subject."""
    store = request.app.state.store
    if not store.has_type(type_id):
        raise HTTPException(status_code=404, detail=f"Type '{type_id}' not found")

    subjects = store.projection_index.get(type_id, [])
    if subject not in subjects:
        raise HTTPException(
            status_code=404,
            detail=f"Projection '{subject}' not found for type '{type_id}'",
        )

    data = store.load_projection(type_id, subject)
    if data is None:
        raise HTTPException(status_code=404, detail="Projection file not found")
    return dict(data)
