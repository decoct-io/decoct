"""Tests for the two-agent progressive disclosure QA harness."""

from __future__ import annotations

from pathlib import Path

from decoct.agent_qa.bridge import (
    format_answerer_prompt,
    format_router_prompt,
    load_files,
    parse_router_response,
    validate_routed_files,
)


# --- parse_router_response ---


def test_parse_router_response_raw_json() -> None:
    raw = '{"files": ["sshd_classes.yaml", "sshd_instances.yaml"], "reasoning": "Need sshd data"}'
    result = parse_router_response(raw)
    assert result["files"] == ["sshd_classes.yaml", "sshd_instances.yaml"]
    assert result["reasoning"] == "Need sshd data"


def test_parse_router_response_markdown_block() -> None:
    text = (
        "Here is my routing decision:\n\n"
        "```json\n"
        '{"files": ["ansible-playbook_classes.yaml"], "reasoning": "Playbook question"}\n'
        "```\n\n"
        "Let me know if you need more."
    )
    result = parse_router_response(text)
    assert result["files"] == ["ansible-playbook_classes.yaml"]
    assert result["reasoning"] == "Playbook question"


def test_parse_router_response_embedded() -> None:
    text = (
        'Based on my analysis, the answer is: {"files": ["docker-compose_classes.yaml"], '
        '"reasoning": "Docker question"} and that should be enough.'
    )
    result = parse_router_response(text)
    assert result["files"] == ["docker-compose_classes.yaml"]
    assert result["reasoning"] == "Docker question"


def test_parse_router_response_invalid() -> None:
    result = parse_router_response("I don't know what to do, sorry!")
    assert result["files"] == []
    assert result["reasoning"] == ""


# --- load_files ---


def test_load_files(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("key: value\n")
    (tmp_path / "b.yaml").write_text("other: data\n")
    content = load_files(tmp_path, ["a.yaml", "b.yaml"])
    assert "--- a.yaml ---" in content
    assert "key: value" in content
    assert "--- b.yaml ---" in content
    assert "other: data" in content


def test_load_files_missing(tmp_path: Path) -> None:
    (tmp_path / "exists.yaml").write_text("hello: world\n")
    content = load_files(tmp_path, ["exists.yaml", "gone.yaml"])
    assert "--- exists.yaml ---" in content
    assert "hello: world" in content
    assert "--- gone.yaml ---" in content
    assert "[file not found]" in content


# --- validate_routed_files ---


def test_validate_routed_files(tmp_path: Path) -> None:
    (tmp_path / "real.yaml").write_text("data: yes\n")
    (tmp_path / "also_real.yaml").write_text("data: yes\n")
    valid, missing = validate_routed_files(
        tmp_path, ["real.yaml", "ghost.yaml", "also_real.yaml", "nope.yaml"],
    )
    assert valid == ["real.yaml", "also_real.yaml"]
    assert missing == ["ghost.yaml", "nope.yaml"]


def test_validate_routed_files_all_valid(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("ok\n")
    (tmp_path / "b.yaml").write_text("ok\n")
    valid, missing = validate_routed_files(tmp_path, ["a.yaml", "b.yaml"])
    assert valid == ["a.yaml", "b.yaml"]
    assert missing == []


def test_validate_routed_files_all_missing(tmp_path: Path) -> None:
    valid, missing = validate_routed_files(tmp_path, ["x.yaml", "y.yaml"])
    assert valid == []
    assert missing == ["x.yaml", "y.yaml"]


def test_validate_routed_files_empty() -> None:
    valid, missing = validate_routed_files(Path("/tmp"), [])
    assert valid == []
    assert missing == []


# --- format_router_prompt ---


def test_format_router_prompt() -> None:
    prompt = format_router_prompt("types:\n  sshd:\n    count: 5", "What do sshd configs share?")
    assert "types:\n  sshd:\n    count: 5" in prompt
    assert "What do sshd configs share?" in prompt
    assert "File selection strategy" in prompt
    assert "Projection validation" in prompt
    assert "Token budget" in prompt


# --- format_answerer_prompt ---


def test_format_answerer_prompt() -> None:
    prompt = format_answerer_prompt("What port does sshd use?", "--- sshd_classes.yaml ---\nPort: 22\n")
    assert "What port does sshd use?" in prompt
    assert "--- sshd_classes.yaml ---" in prompt
    assert "Port: 22" in prompt
    assert "Reconstruction Rule" in prompt
    assert "Do not fabricate config values" in prompt
    assert "absence is itself the answer" in prompt


def test_format_answerer_prompt_with_category() -> None:
    prompt = format_answerer_prompt(
        "What is the ARP timeout impact?",
        "--- classes.yaml ---\narp_timeout: 300\n",
        category="OI",
    )
    assert "operational inference" in prompt
    assert "reason about what these settings mean" in prompt


def test_format_answerer_prompt_with_fr_category() -> None:
    prompt = format_answerer_prompt(
        "What version runs on router-1?",
        "--- classes.yaml ---\nversion: 7.9.2\n",
        category="FR",
    )
    assert "factual retrieval" in prompt
    assert "look up the specific value" in prompt


def test_format_answerer_prompt_with_na_category() -> None:
    prompt = format_answerer_prompt(
        "Is SNMP configured?",
        "--- classes.yaml ---\nhostname: router-1\n",
        category="NA",
    )
    assert "negative/absence" in prompt
    assert "missing or not configured" in prompt


def test_format_answerer_prompt_with_tier_a_excerpt() -> None:
    prompt = format_answerer_prompt(
        "How many routers?",
        "--- classes.yaml ---\ndata: yes\n",
        tier_a_excerpt="types:\n  router:\n    count: 10\n",
    )
    assert "tier_a.yaml (fleet context)" in prompt
    assert "types:\n  router:\n    count: 10" in prompt
    assert "--- classes.yaml ---" in prompt


def test_format_answerer_prompt_no_category() -> None:
    prompt = format_answerer_prompt("Some question?", "data: here\n")
    # No hint block when no category
    assert "**Hint:**" not in prompt


def test_format_answerer_prompt_unknown_category() -> None:
    prompt = format_answerer_prompt("Some question?", "data: here\n", category="ZZ")
    # Unknown category produces no hint
    assert "**Hint:**" not in prompt
