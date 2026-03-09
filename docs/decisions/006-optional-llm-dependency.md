# ADR-006: LLM Features as Optional Dependency

## Status
Accepted

## Context
decoct has two modes: deterministic pipeline (schemas + assertions → tree transformations) and LLM-assisted features (schema learning, assertion learning). The Anthropic SDK is required for LLM features.

## Decision
The Anthropic SDK is an optional dependency in the `[llm]` extra. `pip install decoct` gives the full deterministic pipeline. `pip install decoct[llm]` adds LLM features.

## Rationale
1. **Zero-dependency core** — The deterministic pipeline works with just ruamel.yaml, tiktoken, and click. No API keys, no network access, no vendor lock-in.
2. **Offline-first** — Infrastructure environments often have restricted network access. The core pipeline must work offline.
3. **Deferred import** — The `learn.py` module imports `anthropic` at function call time, not at module import time. This means `import decoct` never fails due to missing anthropic SDK.
4. **Clear boundary** — Users know exactly when they need the LLM extra: `decoct schema learn` and `decoct assertion learn` commands.

## Consequences
- `learn.py` uses deferred imports for `anthropic`.
- CLI commands that require the SDK catch `ImportError` and display a helpful message.
- Tests for learn functionality mock the Anthropic client.
- The `[llm]` extra specifies `anthropic>=0.40`.
