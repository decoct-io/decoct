"""Deterministic Q&A pair generation from entity-graph configs."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class QuestionCategory(Enum):
    """Categories of comprehension questions."""

    SINGLE_VALUE = "SINGLE_VALUE"
    MULTI_ENTITY = "MULTI_ENTITY"
    EXISTENCE = "EXISTENCE"
    COMPARISON = "COMPARISON"
    COUNT = "COUNT"
    ORDERING = "ORDERING"


@dataclass
class GroundTruth:
    """Ground-truth answer with evidence."""

    answer: str
    evidence_paths: list[str] = field(default_factory=list)


@dataclass
class QAPair:
    """A single question-answer pair."""

    id: str
    category: QuestionCategory
    question: str
    ground_truth: GroundTruth
    entity_ids: list[str] = field(default_factory=list)


@dataclass
class QuestionBank:
    """A collection of Q&A pairs with metadata."""

    pairs: list[QAPair] = field(default_factory=list)
    source_dir: str = ""
    entity_count: int = 0
    type_count: int = 0


# Attribute paths that produce interesting SINGLE_VALUE questions.
_INTERESTING_ATTRS = [
    ("hostname", "hostname"),
    ("interface.Loopback0.ipv4", "Loopback0 IPv4 address"),
    ("interface.MgmtEth0/RP0/CPU0/0.ipv4", "management interface IPv4 address"),
    ("interface.TenGigE0/0/0/0.ipv4", "TenGigE0/0/0/0 IPv4 address"),
    ("interface.TenGigE0/0/0/0.mtu", "TenGigE0/0/0/0 MTU"),
    ("interface.TenGigE0/0/0/0.description", "TenGigE0/0/0/0 description"),
    ("interface.TenGigE0/0/0/1.ipv4", "TenGigE0/0/0/1 IPv4 address"),
    ("ntp.server", "NTP server"),
    ("ntp.source", "NTP source interface"),
    ("ssh.timeout", "SSH timeout"),
    ("router.isis.CORE.net", "IS-IS NET"),
    ("router.isis.CORE.interface.Loopback0.address-family.ipv4-unicast.prefix-sid", "IS-IS prefix-SID"),
    ("mpls.router-id", "MPLS router-ID"),
    ("interface.Loopback0.description", "Loopback0 description"),
    ("interface.MgmtEth0/RP0/CPU0/0.description", "management interface description"),
    ("clock", "clock timezone"),
    ("line.exec-timeout", "exec timeout"),
]

# Attributes for EXISTENCE checks (present/absent).
_EXISTENCE_ATTRS = [
    ("evpn.!", "EVPN"),
    ("l2vpn.!", "L2VPN"),
    ("mpls.!", "MPLS"),
    ("router.isis.CORE.!", "IS-IS"),
    ("interface.TenGigE0/0/0/2.shutdown", "TenGigE0/0/0/2 interface"),
    ("interface.TenGigE0/0/0/3.shutdown", "TenGigE0/0/0/3 interface"),
    ("interface.BVI100.shutdown", "BVI100 interface"),
]

# Attributes for COMPARISON questions.
_COMPARISON_ATTRS = [
    ("interface.TenGigE0/0/0/0.mtu", "TenGigE0/0/0/0 MTU"),
    ("clock", "clock timezone"),
    ("ntp.source", "NTP source interface"),
    ("line.exec-timeout", "exec timeout"),
    ("ssh.timeout", "SSH timeout"),
]

# Path patterns for COUNT questions (count interfaces matching pattern).
_COUNT_PATTERNS = [
    ("interface.TenGigE", "TenGigE interfaces"),
    ("interface.Bundle-Ether", "Bundle-Ether interfaces"),
    ("interface.BVI", "BVI interfaces"),
    ("interface.Loopback", "Loopback interfaces"),
]


def _get_attr_value(entity_attrs: dict[str, Any], path: str) -> str | None:
    """Get string value of an attribute, or None if absent."""
    attr = entity_attrs.get(path)
    if attr is None:
        return None
    return str(attr.value)


def _count_matching_paths(entity_attrs: dict[str, Any], prefix: str) -> int:
    """Count top-level interface instances matching a prefix.

    For 'interface.TenGigE' counts distinct interface names like
    TenGigE0/0/0/0, TenGigE0/0/0/1, etc.
    """
    seen: set[str] = set()
    for path in entity_attrs:
        if path.startswith(prefix):
            parts = path.split(".")
            if len(parts) >= 2:
                # interface.TenGigE0/0/0/0.* -> "TenGigE0/0/0/0" is parts[1]
                seen.add(parts[1])
    return len(seen)


_NAME_CANDIDATES = ["name", "job_name", "title", "id", "label"]

_STANDARD_EXTENSIONS = {"*.yaml", "*.yml", "*.json", "*.conf", "*.cnf", "*.xml"}
_HYBRID_INFRA_EXTENSIONS = _STANDARD_EXTENSIONS


def _find_name_field(items: list[dict[str, Any]]) -> str | None:
    """Find a field that uniquely identifies items in a list composite."""
    for candidate in _NAME_CANDIDATES:
        values = [item.get(candidate) for item in items if isinstance(item, dict) and candidate in item]
        if len(values) >= 2 and len(values) == len(set(values)):
            return candidate
    return None


def _ordinal(n: int) -> str:
    """Return ordinal string: 1 -> '1st', 2 -> '2nd', etc."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{['th', 'st', 'nd', 'rd'][n % 10 if n % 10 < 4 else 0]}"


def _item_label(path: str) -> str:
    """Derive a human-readable item label from a composite path.

    'tasks' -> 'task', 'scrape_configs' -> 'scrape config', etc.
    """
    segment = path.rsplit(".", 1)[-1]
    # Depluralize naive: strip trailing 's'
    if segment.endswith("s") and len(segment) > 2:
        segment = segment[:-1]
    return segment.replace("_", " ")


def generate_question_bank(
    config_dir: Path,
    *,
    max_questions: int = 200,
    seed: int = 42,
    categories: list[QuestionCategory] | None = None,
    adapter: Any | None = None,
) -> QuestionBank:
    """Generate ground-truth Q&A pairs from raw configs.

    Args:
        config_dir: Directory containing config files.
        max_questions: Maximum number of questions to generate.
        seed: Random seed for reproducibility.
        categories: Categories to include (all if None).
        adapter: Adapter instance to use. Defaults to IosxrAdapter.

    Returns:
        QuestionBank with deterministic Q&A pairs.
    """
    from decoct.adapters.base import BaseAdapter
    from decoct.core.entity_graph import EntityGraph

    if adapter is None:
        from decoct.adapters.iosxr import IosxrAdapter
        adapter = IosxrAdapter()

    graph = EntityGraph()

    # Discover files based on adapter type
    source_type = adapter.source_type()
    if source_type in ("standard", "hybrid-infra"):
        all_files: list[Path] = []
        for pattern in sorted(_STANDARD_EXTENSIONS):
            all_files.extend(config_dir.glob(pattern))
        source_files = sorted(set(all_files))
    else:
        source_files = sorted(config_dir.glob("*.cfg"))

    assert isinstance(adapter, BaseAdapter)
    for src in source_files:
        parsed = adapter.parse(str(src))
        adapter.extract_entities(parsed, graph)

    if not graph.entities:
        return QuestionBank(source_dir=str(config_dir))

    # Group entities by type hint
    type_groups: dict[str, list[str]] = {}
    for entity in graph.entities:
        type_hint = entity.schema_type_hint or "unknown"
        type_groups.setdefault(type_hint, []).append(entity.id)

    allowed = set(categories) if categories else set(QuestionCategory)
    candidates: list[QAPair] = []
    qid = 0

    # --- SINGLE_VALUE ---
    if QuestionCategory.SINGLE_VALUE in allowed:
        for entity in graph.entities:
            for attr_path, attr_label in _INTERESTING_ATTRS:
                val = _get_attr_value(entity.attributes, attr_path)
                if val is not None:
                    qid += 1
                    candidates.append(QAPair(
                        id=f"sv-{qid:04d}",
                        category=QuestionCategory.SINGLE_VALUE,
                        question=f"What is the {attr_label} for {entity.id}?",
                        ground_truth=GroundTruth(
                            answer=val,
                            evidence_paths=[f"{entity.id}.{attr_path}"],
                        ),
                        entity_ids=[entity.id],
                    ))

    # --- MULTI_ENTITY ---
    if QuestionCategory.MULTI_ENTITY in allowed:
        # Find attributes shared by a subset of entities within a type
        for type_id, entity_ids in type_groups.items():
            if len(entity_ids) < 2:
                continue
            entities = [graph.get_entity(eid) for eid in entity_ids]
            for attr_path, attr_label in _INTERESTING_ATTRS:
                # Group entities by their value for this attribute
                value_groups: dict[str, list[str]] = {}
                for ent in entities:
                    val = _get_attr_value(ent.attributes, attr_path)
                    if val is not None:
                        value_groups.setdefault(val, []).append(ent.id)

                # Generate questions for values shared by 2+ but not all entities
                for val, eids in value_groups.items():
                    if 2 <= len(eids) < len(entity_ids):
                        qid += 1
                        answer_str = ", ".join(sorted(eids))
                        candidates.append(QAPair(
                            id=f"me-{qid:04d}",
                            category=QuestionCategory.MULTI_ENTITY,
                            question=f"Which {type_id} devices have {attr_label} set to {val}?",
                            ground_truth=GroundTruth(
                                answer=answer_str,
                                evidence_paths=[f"{eid}.{attr_path}" for eid in sorted(eids)],
                            ),
                            entity_ids=sorted(eids),
                        ))

    # --- EXISTENCE ---
    if QuestionCategory.EXISTENCE in allowed:
        for entity in graph.entities:
            for attr_path, feature_label in _EXISTENCE_ATTRS:
                has_feature = attr_path in entity.attributes
                qid += 1
                candidates.append(QAPair(
                    id=f"ex-{qid:04d}",
                    category=QuestionCategory.EXISTENCE,
                    question=f"Does {entity.id} have {feature_label} configured?",
                    ground_truth=GroundTruth(
                        answer="yes" if has_feature else "no",
                        evidence_paths=[f"{entity.id}.{attr_path}"] if has_feature else [],
                    ),
                    entity_ids=[entity.id],
                ))

    # --- COMPARISON ---
    if QuestionCategory.COMPARISON in allowed:
        for type_id, entity_ids in type_groups.items():
            if len(entity_ids) < 2:
                continue
            entities = [graph.get_entity(eid) for eid in entity_ids]
            for attr_path, attr_label in _COMPARISON_ATTRS:
                values: set[str] = set()
                present_count = 0
                for ent in entities:
                    val = _get_attr_value(ent.attributes, attr_path)
                    if val is not None:
                        values.add(val)
                        present_count += 1
                # Only ask if most entities have this attribute
                if present_count >= len(entity_ids) * 0.5:
                    all_same = len(values) == 1
                    qid += 1
                    candidates.append(QAPair(
                        id=f"cmp-{qid:04d}",
                        category=QuestionCategory.COMPARISON,
                        question=f"Do all {type_id} devices share the same {attr_label}?",
                        ground_truth=GroundTruth(
                            answer="yes" if all_same else "no",
                            evidence_paths=[f"{eid}.{attr_path}" for eid in entity_ids],
                        ),
                        entity_ids=entity_ids,
                    ))

    # --- COUNT ---
    if QuestionCategory.COUNT in allowed:
        for entity in graph.entities:
            for prefix, label in _COUNT_PATTERNS:
                count = _count_matching_paths(entity.attributes, prefix)
                if count > 0:
                    qid += 1
                    candidates.append(QAPair(
                        id=f"cnt-{qid:04d}",
                        category=QuestionCategory.COUNT,
                        question=f"How many {label} does {entity.id} have?",
                        ground_truth=GroundTruth(
                            answer=str(count),
                            evidence_paths=[f"{entity.id}.{prefix}*"],
                        ),
                        entity_ids=[entity.id],
                    ))

    # --- ORDERING ---
    if QuestionCategory.ORDERING in allowed:
        from decoct.core.composite_value import CompositeValue

        for entity in graph.entities:
            for attr_path, attr in entity.attributes.items():
                if not isinstance(attr.value, CompositeValue) or attr.value.kind != "list":
                    continue
                items = attr.value.data
                if not isinstance(items, list) or len(items) < 2:
                    continue
                # Only lists of dicts with a discoverable name field
                dict_items = [it for it in items if isinstance(it, dict)]
                if len(dict_items) < 2:
                    continue
                name_field = _find_name_field(dict_items)
                if name_field is None:
                    continue

                label = _item_label(attr_path)

                # Position questions
                for idx, item in enumerate(dict_items):
                    name_val = item.get(name_field)
                    if name_val is None:
                        continue
                    qid += 1
                    candidates.append(QAPair(
                        id=f"ord-{qid:04d}",
                        category=QuestionCategory.ORDERING,
                        question=f"What is the {_ordinal(idx + 1)} {label} in {entity.id}'s {attr_path}?",
                        ground_truth=GroundTruth(
                            answer=str(name_val),
                            evidence_paths=[f"{entity.id}.{attr_path}[{idx}].{name_field}"],
                        ),
                        entity_ids=[entity.id],
                    ))

                # Before/After questions
                for idx in range(len(dict_items) - 1):
                    cur_name = dict_items[idx].get(name_field)
                    next_name = dict_items[idx + 1].get(name_field)
                    if cur_name is None or next_name is None:
                        continue
                    qid += 1
                    candidates.append(QAPair(
                        id=f"ord-{qid:04d}",
                        category=QuestionCategory.ORDERING,
                        question=f"What {label} comes immediately after {cur_name} in {entity.id}'s {attr_path}?",
                        ground_truth=GroundTruth(
                            answer=str(next_name),
                            evidence_paths=[f"{entity.id}.{attr_path}[{idx + 1}].{name_field}"],
                        ),
                        entity_ids=[entity.id],
                    ))

                # First/Last questions
                first_name = dict_items[0].get(name_field)
                last_name = dict_items[-1].get(name_field)
                if first_name is not None:
                    qid += 1
                    candidates.append(QAPair(
                        id=f"ord-{qid:04d}",
                        category=QuestionCategory.ORDERING,
                        question=f"What is the first {label} in {entity.id}'s {attr_path}?",
                        ground_truth=GroundTruth(
                            answer=str(first_name),
                            evidence_paths=[f"{entity.id}.{attr_path}[0].{name_field}"],
                        ),
                        entity_ids=[entity.id],
                    ))
                if last_name is not None:
                    qid += 1
                    candidates.append(QAPair(
                        id=f"ord-{qid:04d}",
                        category=QuestionCategory.ORDERING,
                        question=f"What is the last {label} in {entity.id}'s {attr_path}?",
                        ground_truth=GroundTruth(
                            answer=str(last_name),
                            evidence_paths=[f"{entity.id}.{attr_path}[{len(dict_items) - 1}].{name_field}"],
                        ),
                        entity_ids=[entity.id],
                    ))

    # Sample to max_questions with seeded RNG
    rng = random.Random(seed)
    if len(candidates) > max_questions:
        # Ensure all categories are represented
        by_cat: dict[QuestionCategory, list[QAPair]] = {}
        for q in candidates:
            by_cat.setdefault(q.category, []).append(q)

        selected: list[QAPair] = []
        # Reserve at least 1 per category
        cats = sorted(by_cat.keys(), key=lambda c: c.value)
        per_cat = max(1, max_questions // len(cats))
        for cat in cats:
            pool = by_cat[cat]
            rng.shuffle(pool)
            selected.extend(pool[:per_cat])

        # Fill remaining slots
        remaining = [q for q in candidates if q not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[: max_questions - len(selected)])

        candidates = selected[:max_questions]

    return QuestionBank(
        pairs=candidates,
        source_dir=str(config_dir),
        entity_count=len(graph.entities),
        type_count=len(type_groups),
    )


def save_question_bank(bank: QuestionBank, path: Path) -> None:
    """Serialize a QuestionBank to JSON."""
    data = {
        "source_dir": bank.source_dir,
        "entity_count": bank.entity_count,
        "type_count": bank.type_count,
        "pairs": [
            {
                "id": q.id,
                "category": q.category.value,
                "question": q.question,
                "ground_truth": {
                    "answer": q.ground_truth.answer,
                    "evidence_paths": q.ground_truth.evidence_paths,
                },
                "entity_ids": q.entity_ids,
            }
            for q in bank.pairs
        ],
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


def load_question_bank(path: Path) -> QuestionBank:
    """Deserialize a QuestionBank from JSON."""
    data = json.loads(path.read_text())
    pairs: list[QAPair] = []
    for item in data["pairs"]:
        pairs.append(QAPair(
            id=item["id"],
            category=QuestionCategory(item["category"]),
            question=item["question"],
            ground_truth=GroundTruth(
                answer=item["ground_truth"]["answer"],
                evidence_paths=item["ground_truth"]["evidence_paths"],
            ),
            entity_ids=item["entity_ids"],
        ))
    return QuestionBank(
        pairs=pairs,
        source_dir=data.get("source_dir", ""),
        entity_count=data.get("entity_count", 0),
        type_count=data.get("type_count", 0),
    )
