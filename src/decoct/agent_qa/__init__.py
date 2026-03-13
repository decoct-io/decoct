"""Two-agent progressive disclosure QA harness for decoct compressed output."""

from decoct.agent_qa.bridge import (
    format_answerer_prompt,
    format_router_prompt,
    get_data_manual_excerpt,
    load_files,
    parse_router_response,
    validate_routed_files,
)

__all__ = [
    "format_answerer_prompt",
    "format_router_prompt",
    "get_data_manual_excerpt",
    "load_files",
    "parse_router_response",
    "validate_routed_files",
]
