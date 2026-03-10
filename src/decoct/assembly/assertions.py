"""Structural invariant checks (§10.2).

Re-exports from reconstruction.validator for convenience.
"""

from decoct.reconstruction.validator import (
    ReconstructionError,
    StructuralInvariantError,
    validate_reconstruction,
    validate_structural_invariants,
)

__all__ = [
    "ReconstructionError",
    "StructuralInvariantError",
    "validate_reconstruction",
    "validate_structural_invariants",
]
