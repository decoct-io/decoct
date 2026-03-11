"""FastAPI app factory with lifespan for OutputStore loading."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from decoct.api.loader import OutputStore
from decoct.api.routers import fleet, projections, stats, types


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load output store at startup."""
    app.state.store.load()
    yield


def create_app(output_dir: str | Path) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        output_dir: Path to pre-computed entity-graph output directory.

    Returns:
        Configured FastAPI app with OutputStore loaded via lifespan.
    """
    app = FastAPI(
        title="decoct Progressive Disclosure API",
        description="Serve pre-computed entity-graph output with progressive disclosure.",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.state.store = OutputStore(Path(output_dir))

    app.include_router(fleet.router)
    app.include_router(types.router)
    app.include_router(projections.router)
    app.include_router(stats.router)

    return app
