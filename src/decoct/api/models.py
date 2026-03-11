"""Pydantic response models for the Progressive Disclosure API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TypeSummary(BaseModel):
    """Summary of a single entity type (from Tier A)."""

    type_id: str
    count: int
    classes: int
    subclasses: int
    tier_b_ref: str
    tier_c_ref: str
    summary: str | None = None
    key_differentiators: list[str] | None = None


class TypeListResponse(BaseModel):
    """Response for GET /types."""

    types: list[TypeSummary]


class EntitySummary(BaseModel):
    """An entity with its class assignment."""

    entity_id: str
    class_name: str | None = None
    subclass_name: str | None = None


class InstanceListResponse(BaseModel):
    """Response for GET /types/{type_id}/instances."""

    type_id: str
    entity_count: int
    entities: list[EntitySummary]


class ReconstructedEntityResponse(BaseModel):
    """Response for GET /types/{type_id}/instances/{entity_id}."""

    entity_id: str
    entity_type: str
    attributes: dict[str, Any]
    relationships: list[list[str]]


class LayerAttribution(BaseModel):
    """A single attribute with its source layer."""

    value: Any
    source: str
    class_name: str | None = None


class LayeredEntityResponse(BaseModel):
    """Response for GET /types/{type_id}/instances/{entity_id}/layers."""

    entity_id: str
    entity_type: str
    layers: dict[str, LayerAttribution]


class DeltaResponse(BaseModel):
    """Response for GET /types/{type_id}/deltas (raw Tier C data)."""

    type_id: str
    class_assignments: dict[str, Any]
    subclass_assignments: dict[str, Any]
    instance_data: dict[str, Any]
    instance_attrs: dict[str, Any]
    overrides: dict[str, Any]
    b_composite_deltas: dict[str, Any]
    foreign_keys: dict[str, Any]


class EntityDeltaResponse(BaseModel):
    """Response for GET /types/{type_id}/instances/{entity_id}/delta."""

    entity_id: str
    type_id: str
    class_name: str | None = None
    subclass_name: str | None = None
    overrides: dict[str, Any] | None = None
    instance_attrs: dict[str, Any] | None = None
    phone_book_row: dict[str, Any] | None = None
    b_composite_deltas: dict[str, Any] | None = None


class ProjectionListResponse(BaseModel):
    """Response for GET /types/{type_id}/projections."""

    type_id: str
    subjects: list[str]


class StatsResponse(BaseModel):
    """Response for GET /stats (output-side only)."""

    tier_a: dict[str, Any]
    tier_b: dict[str, Any]
    tier_c: dict[str, Any]
    output_total_bytes: int
    output_total_tokens: int
    output_total_files: int
    type_stats: list[dict[str, Any]]
