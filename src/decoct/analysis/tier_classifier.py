"""Final role and bootstrap signal classification (§3.4, §3.5, §7.3)."""

from __future__ import annotations

import math

from decoct.core.canonical import IS_SCALAR_LIKE
from decoct.core.types import (
    AttributeProfile,
    BootstrapSignal,
    FinalRole,
    TierCStorage,
)


def classify_final_role(
    H_norm: float,
    cardinality: int,
    n_entities: int,
    coverage: float,
    len_mean: float,
    attribute_type: str,
    small_group_floor: int = 8,
) -> tuple[FinalRole, float]:
    """Classify an attribute's final emission role (§3.4).

    Returns (role, confidence).
    """
    # True universal constants only
    if coverage == 1.0 and cardinality == 1:
        return (FinalRole.A_BASE, 1.0)

    # High-entropy or very wide attributes
    if n_entities >= small_group_floor:
        if cardinality > 0.5 * n_entities or H_norm > 0.8:
            return (FinalRole.C, min(1.0, H_norm))
    else:
        # Below the floor, only classify as C if cardinality is genuinely high
        if cardinality >= n_entities or H_norm > 0.9:
            return (FinalRole.C, min(1.0, H_norm))

    # Long low-cardinality values are still too expensive inline
    if len_mean > 200 and cardinality < math.sqrt(n_entities):
        return (FinalRole.C, 0.6)

    # Everything else is class-compressible in v1
    return (FinalRole.B, max(0.5, 1.0 - H_norm))


def classify_bootstrap_role(profile: AttributeProfile) -> BootstrapSignal:
    """Classify an attribute's bootstrap signal (§3.5)."""
    # True constants can help define type
    if profile.final_role == FinalRole.A_BASE:
        return BootstrapSignal.VALUE_SIGNAL

    # Sparse presence often discriminates type even if not constant
    if profile.coverage < 0.2:
        return BootstrapSignal.PRESENCE_SIGNAL

    # Low-cardinality, low-entropy attributes can discriminate by value
    if profile.cardinality <= 3 and profile.coverage > 0.95 and profile.entropy_norm < 0.3:
        return BootstrapSignal.VALUE_SIGNAL

    return BootstrapSignal.NONE


def select_tier_c_storage(profile: AttributeProfile) -> TierCStorage:
    """Determine Tier C storage for a C-role attribute (§7.3)."""
    if profile.final_role != FinalRole.C:
        return TierCStorage.NONE

    if IS_SCALAR_LIKE(profile.attribute_type) and profile.coverage == 1.0:
        return TierCStorage.PHONE_BOOK

    return TierCStorage.INSTANCE_ATTRS
