"""Projection spec loader and dumper (R3 — subject projections)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.projections.models import (
    ProjectionSpec,
    RelatedPath,
    SubjectSpec,
)


def load_projection_spec(path: str | Path) -> ProjectionSpec:
    """Load and validate a projection spec from YAML.

    Raises:
        FileNotFoundError: if the spec file does not exist
        ValueError: if the spec is invalid
    """
    path = Path(path)
    yaml = YAML(typ="safe")
    raw: dict[str, Any] = yaml.load(path.read_text())

    if not isinstance(raw, dict):
        msg = f"Projection spec must be a YAML mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    # Validate version
    version = raw.get("version")
    if version != 1:
        msg = f"Unsupported projection spec version: {version!r} (expected 1)"
        raise ValueError(msg)

    source_type = raw.get("source_type")
    if not source_type or not isinstance(source_type, str):
        msg = "Projection spec must have a non-empty 'source_type' string"
        raise ValueError(msg)

    generated_by = raw.get("generated_by", "claude-code")

    subjects: list[SubjectSpec] = []
    for i, subj_raw in enumerate(raw.get("subjects", [])):
        if not isinstance(subj_raw, dict):
            msg = f"Subject {i} must be a mapping"
            raise ValueError(msg)

        name = subj_raw.get("name")
        if not name or not isinstance(name, str):
            msg = f"Subject {i} must have a non-empty 'name' string"
            raise ValueError(msg)

        include_paths = subj_raw.get("include_paths", [])
        if not include_paths:
            msg = f"Subject {i} ('{name}') must have at least one include_path"
            raise ValueError(msg)

        related_paths: list[RelatedPath] = []
        for j, rp_raw in enumerate(subj_raw.get("related_paths", [])):
            if not isinstance(rp_raw, dict):
                msg = f"Subject {i}, related_paths[{j}] must be a mapping"
                raise ValueError(msg)
            rp_path = rp_raw.get("path")
            if not rp_path or not isinstance(rp_path, str):
                msg = f"Subject {i}, related_paths[{j}] must have a non-empty 'path' string"
                raise ValueError(msg)
            related_paths.append(RelatedPath(
                path=rp_path,
                reason=rp_raw.get("reason", ""),
            ))

        subjects.append(SubjectSpec(
            name=name,
            description=subj_raw.get("description", ""),
            include_paths=list(include_paths),
            related_paths=related_paths,
            example_questions=list(subj_raw.get("example_questions", [])),
        ))

    return ProjectionSpec(
        version=version,
        source_type=source_type,
        generated_by=generated_by,
        subjects=subjects,
    )


def dump_projection_spec(spec: ProjectionSpec) -> str:
    """Serialize ProjectionSpec to YAML string using ruamel.yaml round-trip."""
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False

    doc: dict[str, Any] = {
        "version": spec.version,
        "source_type": spec.source_type,
        "generated_by": spec.generated_by,
        "subjects": [],
    }
    for subject in spec.subjects:
        subj_dict: dict[str, Any] = {
            "name": subject.name,
            "description": subject.description,
            "include_paths": subject.include_paths,
        }
        if subject.related_paths:
            subj_dict["related_paths"] = [
                {"path": rp.path, "reason": rp.reason}
                for rp in subject.related_paths
            ]
        if subject.example_questions:
            subj_dict["example_questions"] = subject.example_questions
        doc["subjects"].append(subj_dict)

    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()
