"""Compression: class extraction, delta compression, normalisation."""

from decoct.compression.archetypal import archetypal_compress
from decoct.compression.engine import CompressionEngine, get_engine, registry
from decoct.compression.greedy_bundle import GreedyBundleEngine  # triggers registration

__all__ = [
    "CompressionEngine",
    "GreedyBundleEngine",
    "archetypal_compress",
    "get_engine",
    "registry",
]
