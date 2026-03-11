"""Type-level endpoints: Tier B, instances, reconstruction, deltas, layers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from decoct.api.models import (
    DeltaResponse,
    EntityDeltaResponse,
    EntitySummary,
    InstanceListResponse,
    LayerAttribution,
    LayeredEntityResponse,
    ReconstructedEntityResponse,
)
from decoct.api.reconstruct import build_layered_view, reconstruct_entity_json

router = APIRouter(prefix="/types/{type_id}")


def _require_type(request: Request, type_id: str) -> None:
    store = request.app.state.store
    if not store.has_type(type_id):
        raise HTTPException(status_code=404, detail=f"Type '{type_id}' not found")


def _require_entity(request: Request, type_id: str, entity_id: str) -> None:
    _require_type(request, type_id)
    store = request.app.state.store
    if not store.has_entity(type_id, entity_id):
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found in type '{type_id}'")


@router.get("")
def get_type_detail(request: Request, type_id: str) -> dict[str, Any]:
    """Return Tier B data for a type (classes, templates, base)."""
    _require_type(request, type_id)
    store = request.app.state.store
    return store.classes_raw[type_id]


@router.get("/classes")
def get_classes(request: Request, type_id: str) -> dict[str, Any]:
    """Return class hierarchy only."""
    _require_type(request, type_id)
    store = request.app.state.store
    raw = store.classes_raw[type_id]
    return {
        "base_class": raw.get("base_class", {}),
        "classes": raw.get("classes", {}),
        "subclasses": raw.get("subclasses", {}),
    }


@router.get("/templates")
def get_templates(request: Request, type_id: str) -> dict[str, Any]:
    """Return composite templates only."""
    _require_type(request, type_id)
    raw = request.app.state.store.classes_raw[type_id]
    return {"composite_templates": raw.get("composite_templates", {})}


@router.get("/instances", response_model=InstanceListResponse)
def list_instances(request: Request, type_id: str) -> InstanceListResponse:
    """List entities of this type with class assignments."""
    _require_type(request, type_id)
    store = request.app.state.store
    entity_index = store.entity_indexes.get(type_id, {})
    entities = []
    for eid in sorted(entity_index.keys()):
        class_name, subclass_name = entity_index[eid]
        entities.append(EntitySummary(
            entity_id=eid,
            class_name=class_name,
            subclass_name=subclass_name,
        ))
    return InstanceListResponse(
        type_id=type_id,
        entity_count=len(entities),
        entities=entities,
    )


@router.get("/instances/{entity_id}", response_model=ReconstructedEntityResponse)
def get_reconstructed_entity(request: Request, type_id: str, entity_id: str) -> ReconstructedEntityResponse:
    """Return fully reconstructed entity config."""
    _require_entity(request, type_id, entity_id)
    store = request.app.state.store
    result = reconstruct_entity_json(
        type_id, entity_id,
        store.hierarchies[type_id],
        store.tier_c_data[type_id],
        store.template_indexes[type_id],
    )
    return ReconstructedEntityResponse(**result)


@router.get("/instances/{entity_id}/delta", response_model=EntityDeltaResponse)
def get_entity_delta(request: Request, type_id: str, entity_id: str) -> EntityDeltaResponse:
    """Return raw per-entity delta (overrides, instance_attrs, phone_book row, composite deltas)."""
    _require_entity(request, type_id, entity_id)
    store = request.app.state.store
    entity_index = store.entity_indexes[type_id]
    tier_c = store.tier_c_data[type_id]

    class_name, subclass_name = entity_index[entity_id]

    # Override data
    overrides = tier_c.overrides.get(entity_id)

    # Instance attrs
    instance_attrs = tier_c.instance_attrs.get(entity_id)

    # Phone book row
    phone_book_row: dict[str, Any] | None = None
    if entity_id in tier_c.instance_data.records:
        record = tier_c.instance_data.records[entity_id]
        phone_book_row = dict(zip(tier_c.instance_data.schema, record))

    # Composite deltas
    b_composite_deltas = tier_c.b_composite_deltas.get(entity_id)

    return EntityDeltaResponse(
        entity_id=entity_id,
        type_id=type_id,
        class_name=class_name,
        subclass_name=subclass_name,
        overrides=overrides,
        instance_attrs=instance_attrs,
        phone_book_row=phone_book_row,
        b_composite_deltas=b_composite_deltas,
    )


@router.get("/instances/{entity_id}/layers", response_model=LayeredEntityResponse)
def get_entity_layers(request: Request, type_id: str, entity_id: str) -> LayeredEntityResponse:
    """Return per-entity layered view showing attribute source."""
    _require_entity(request, type_id, entity_id)
    store = request.app.state.store

    raw_layers = build_layered_view(
        type_id, entity_id,
        store.hierarchies[type_id],
        store.tier_c_data[type_id],
        store.template_indexes[type_id],
    )

    layers = {
        path: LayerAttribution(**attrs)
        for path, attrs in raw_layers.items()
    }

    return LayeredEntityResponse(
        entity_id=entity_id,
        entity_type=type_id,
        layers=layers,
    )


@router.get("/deltas", response_model=DeltaResponse)
def get_type_deltas(request: Request, type_id: str) -> DeltaResponse:
    """Return raw Tier C data for a type."""
    _require_type(request, type_id)
    store = request.app.state.store
    raw = store.instances_raw[type_id]
    return DeltaResponse(
        type_id=type_id,
        class_assignments=raw.get("class_assignments", {}),
        subclass_assignments=raw.get("subclass_assignments", {}),
        instance_data=raw.get("instance_data", {}),
        instance_attrs=raw.get("instance_attrs", {}),
        overrides=raw.get("overrides", {}),
        b_composite_deltas=raw.get("b_composite_deltas", {}),
        foreign_keys=raw.get("foreign_keys", {}),
    )
