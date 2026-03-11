"""Shared LLM utilities for entity-graph learn modules."""

from __future__ import annotations

import re


def extract_yaml_block(response_text: str) -> str:
    """Extract YAML from a markdown code block or raw response."""
    match = re.search(r"```ya?ml\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return response_text.strip()
