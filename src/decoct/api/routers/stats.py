"""Stats endpoint: GET /stats (output-side only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from decoct.api.models import StatsResponse

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
def get_stats(request: Request) -> StatsResponse:
    """Return output-side compression statistics."""
    store = request.app.state.store
    output_dir = store.output_dir

    # Compute output-side stats without requiring input_dir
    from decoct.tokens import count_tokens

    def _file_stats(path: Any) -> tuple[int, int, int]:
        text = path.read_text(encoding="utf-8")
        return len(text.encode("utf-8")), text.count("\n"), count_tokens(text)

    tier_a_stats: dict[str, Any] = {"file_count": 0, "total_bytes": 0, "total_lines": 0, "total_tokens": 0}
    tier_b_stats: dict[str, Any] = {"file_count": 0, "total_bytes": 0, "total_lines": 0, "total_tokens": 0}
    tier_c_stats: dict[str, Any] = {"file_count": 0, "total_bytes": 0, "total_lines": 0, "total_tokens": 0}
    type_stats_list: list[dict[str, Any]] = []

    # Tier A
    tier_a_path = output_dir / "tier_a.yaml"
    if tier_a_path.exists():
        byt, lin, tok = _file_stats(tier_a_path)
        tier_a_stats = {"file_count": 1, "total_bytes": byt, "total_lines": lin, "total_tokens": tok}

    types_section = store.tier_a.get("types", {})
    assertions_section = store.tier_a.get("assertions", {})

    for type_id in store.type_ids:
        type_info = types_section.get(type_id, {})
        type_assertions = assertions_section.get(type_id, {}) if isinstance(assertions_section, dict) else {}

        ts: dict[str, Any] = {
            "type_id": type_id,
            "entity_count": type_info.get("count", 0),
            "class_count": type_info.get("classes", 0),
            "subclass_count": type_info.get("subclasses", 0),
            "base_only_ratio": (
                type_assertions.get("base_only_ratio", 0.0) if isinstance(type_assertions, dict) else 0.0
            ),
            "tier_b_bytes": 0,
            "tier_b_tokens": 0,
            "tier_c_bytes": 0,
            "tier_c_tokens": 0,
        }

        classes_path = output_dir / type_info.get("tier_b_ref", f"{type_id}_classes.yaml")
        if classes_path.exists():
            byt, lin, tok = _file_stats(classes_path)
            ts["tier_b_bytes"] = byt
            ts["tier_b_tokens"] = tok
            tier_b_stats["file_count"] += 1
            tier_b_stats["total_bytes"] += byt
            tier_b_stats["total_lines"] += lin
            tier_b_stats["total_tokens"] += tok

        instances_path = output_dir / type_info.get("tier_c_ref", f"{type_id}_instances.yaml")
        if instances_path.exists():
            byt, lin, tok = _file_stats(instances_path)
            ts["tier_c_bytes"] = byt
            ts["tier_c_tokens"] = tok
            tier_c_stats["file_count"] += 1
            tier_c_stats["total_bytes"] += byt
            tier_c_stats["total_lines"] += lin
            tier_c_stats["total_tokens"] += tok

        type_stats_list.append(ts)

    total_bytes = tier_a_stats["total_bytes"] + tier_b_stats["total_bytes"] + tier_c_stats["total_bytes"]
    total_tokens = tier_a_stats["total_tokens"] + tier_b_stats["total_tokens"] + tier_c_stats["total_tokens"]
    total_files = tier_a_stats["file_count"] + tier_b_stats["file_count"] + tier_c_stats["file_count"]

    return StatsResponse(
        tier_a=tier_a_stats,
        tier_b=tier_b_stats,
        tier_c=tier_c_stats,
        output_total_bytes=total_bytes,
        output_total_tokens=total_tokens,
        output_total_files=total_files,
        type_stats=type_stats_list,
    )
