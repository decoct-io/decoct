# Progressive Disclosure API

decoct includes a FastAPI-based API that serves pre-computed entity-graph output with progressive disclosure. Start with the fleet overview, then drill into types, classes, entities, and subject projections.

## Quick Start

```bash
# Generate output (if not already present)
python scripts/run_hybrid_infra.py

# Start the server
decoct serve -o output/hybrid-infra

# Or with custom host/port
decoct serve -o output/hybrid-infra --host 0.0.0.0 --port 9000

# Development mode with auto-reload
decoct serve -o output/hybrid-infra --reload
```

The server reads pre-computed output at startup and serves it as JSON via REST endpoints.

## Progressive Disclosure Flow

The API is designed around a progressive disclosure pattern — start broad, drill down as needed:

1. **Tier A** (`GET /`) — fleet-level overview, type counts, topology
2. **Type list** (`GET /types`) — structured list of all entity types
3. **Tier B** (`GET /types/{type_id}`) — shared config: base class, classes, subclasses, templates
4. **Instances** (`GET /types/{type_id}/instances`) — entity list with class assignments
5. **Entity delta** (`GET /types/{type_id}/instances/{entity_id}/delta`) — just the per-entity differences from its class
6. **Entity layers** (`GET /types/{type_id}/instances/{entity_id}/layers`) — each attribute tagged with its source layer
7. **Reconstructed** (`GET /types/{type_id}/instances/{entity_id}`) — fully merged entity config

## Endpoints

### Fleet Level

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Tier A fleet overview (types, assertions, topology) |
| GET | `/types` | List all entity types with counts |
| GET | `/stats` | Output-side compression statistics |

### Type Level

| Method | Path | Description |
|--------|------|-------------|
| GET | `/types/{type_id}` | Full Tier B data (base class, classes, subclasses, composite templates) |
| GET | `/types/{type_id}/classes` | Class hierarchy only (base, classes, subclasses) |
| GET | `/types/{type_id}/templates` | Composite templates only |
| GET | `/types/{type_id}/instances` | Entity list with class and subclass assignments |
| GET | `/types/{type_id}/deltas` | Raw Tier C data (class assignments, overrides, phone book, instance attrs, composite deltas) |

### Entity Level

| Method | Path | Description |
|--------|------|-------------|
| GET | `/types/{type_id}/instances/{entity_id}` | Fully reconstructed entity config (all layers merged) |
| GET | `/types/{type_id}/instances/{entity_id}/delta` | Raw per-entity delta (overrides, instance attrs, phone book row, composite deltas) |
| GET | `/types/{type_id}/instances/{entity_id}/layers` | Layered view showing the source of each attribute |

### Projections

| Method | Path | Description |
|--------|------|-------------|
| GET | `/types/{type_id}/projections` | List available subject projections for a type |
| GET | `/types/{type_id}/projections/{subject}` | Subject projection data |

## Example Walkthrough

```bash
# 1. Fleet overview — what types exist?
curl localhost:8000/
# Returns: types with counts, assertions, topology

# 2. Structured type list
curl localhost:8000/types
# Returns: [{type_id, count, classes, subclasses, summary, ...}, ...]

# 3. Tier B for docker-compose — what's shared?
curl localhost:8000/types/docker-compose
# Returns: base_class, classes, subclasses, composite_templates

# 4. Which entities exist?
curl localhost:8000/types/docker-compose/instances
# Returns: [{entity_id, class_name, subclass_name}, ...]

# 5. What's different about a specific entity?
curl localhost:8000/types/docker-compose/instances/compose-app-prod-01/delta
# Returns: overrides, instance_attrs, phone_book_row, b_composite_deltas

# 6. Where does each attribute come from?
curl localhost:8000/types/docker-compose/instances/compose-app-prod-01/layers
# Returns: {path: {value, source, class_name?}, ...}

# 7. Give me the full reconstructed config
curl localhost:8000/types/docker-compose/instances/compose-app-prod-01
# Returns: {entity_id, entity_type, attributes, relationships}

# 8. Raw Tier C deltas for all entities of a type
curl localhost:8000/types/docker-compose/deltas

# 9. Available projections
curl localhost:8000/types/docker-compose/projections

# 10. Compression stats
curl localhost:8000/stats
```

## Layered View

The `/layers` endpoint tags each attribute with its source in the 7-layer precedence chain:

| Source | Description |
|--------|-------------|
| `base_class` | Attribute from the type's base class (shared by all entities) |
| `class` | Attribute from the entity's primary class `own_attrs` |
| `subclass` | Attribute from the entity's subclass `own_attrs` |
| `override` | Per-entity B-layer override (delta from class) |
| `composite_template` | Expanded composite template value |
| `instance_attr` | C-layer instance-specific attribute (sparse) |
| `phone_book` | C-layer dense scalar from the phone book |

Example response:

```json
{
  "entity_id": "compose-app-prod-01",
  "entity_type": "docker-compose",
  "layers": {
    "networks": {
      "value": {"attachable": "false", "driver": "bridge"},
      "source": "base_class"
    },
    "volumes": {
      "value": {"external": "false"},
      "source": "class",
      "class_name": "volumes_docker_compose_volumes_T0"
    },
    "services.redis.image": {
      "value": "redis:7-alpine",
      "source": "composite_template",
      "class_name": "docker-compose.services.T0"
    }
  }
}
```

## Error Handling

- **404** — returned for unknown `type_id`, `entity_id`, or projection `subject`
- **200** with empty data — returned for valid types that have no composite templates, projections, etc.
- Startup fails if `tier_a.yaml` is missing from the output directory

## Module Structure

```
src/decoct/api/
    __init__.py          # exports create_app
    app.py               # FastAPI app factory + lifespan
    loader.py            # OutputStore: reads YAML, caches, builds entity index
    models.py            # Pydantic response models
    reconstruct.py       # Hydrate from YAML dicts, call reconstitute_entity()
    routers/
        __init__.py
        fleet.py         # GET /, GET /types
        types.py         # GET /types/{type_id}, instances, deltas, layers
        projections.py   # GET /types/{type_id}/projections
        stats.py         # GET /stats
```

## CLI Reference

```
decoct serve [OPTIONS]

Options:
  -o, --output-dir PATH  Entity-graph output directory to serve. [required]
  --host TEXT             Bind host. [default: 127.0.0.1]
  --port INTEGER          Bind port. [default: 8000]
  --reload                Enable auto-reload for development.
  --help                  Show this message and exit.
```

## Dependencies

The API requires `fastapi` and `uvicorn`, which are included as core dependencies:

```toml
dependencies = [
    "ruamel.yaml>=0.18",
    "tiktoken>=0.7",
    "click>=8.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]
```

## Testing

```bash
pytest tests/test_api/ -v
```

The test suite uses the `output/hybrid-infra/` sample output as a fixture and covers all endpoints including the full progressive disclosure flow.
