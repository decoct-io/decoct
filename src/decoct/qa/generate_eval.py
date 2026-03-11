"""LLM-based evaluation question generation and validation.

Generates rich, multi-class evaluation questions via LLM, validates them
against raw configs, and produces pruned question banks for weighted evaluation.

LLM provider: OpenAI SDK with configurable ``--base-url`` (defaults to
OpenRouter). Works with any OpenAI-compatible endpoint.

Requires the [llm] extra: pip install decoct[llm]
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.llm_utils import extract_yaml_block
from decoct.qa.eval_models import (
    Difficulty,
    EvalQuestion,
    EvalQuestionBank,
    EvalQuestionClass,
)
from decoct.qa.evaluate import build_raw_context

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

# --- System prompts per question class ---

_CLASS_DEFINITIONS: dict[EvalQuestionClass, str] = {
    EvalQuestionClass.FACTUAL_RETRIEVAL: """\
FACTUAL_RETRIEVAL questions test direct lookup of a single fact from the configs.
Examples:
- "What is the MTU configured on interface GigabitEthernet0/0/0/0 of router access-pe-01?"
- "Which Docker image does the 'web' service use in docker-compose-prod.yaml?"
- "What is the listen_addresses setting in postgresql-db01.conf?"
Answers should be a single value extractable from one config file.
Max score: 1 point (correct or incorrect).""",

    EvalQuestionClass.CROSS_REFERENCE: """\
CROSS_REFERENCE questions require correlating facts across 2+ config files.
Examples:
- "Which routers share the same OSPF area ID as access-pe-03?"
- "Do all PostgreSQL instances use the same max_connections value? If not, which differ?"
- "Which Ansible playbooks reference hosts that appear in the inventory file?"
Answers require comparing or joining data from multiple files.
Max score: 2 points (2=all facts correct + relationship accurate, 1=correct facts but incomplete, 0=wrong).""",

    EvalQuestionClass.OPERATIONAL_INFERENCE: """\
OPERATIONAL_INFERENCE questions require reasoning about operational impact.
Examples:
- "If router p-core-01 goes down, which access routers would lose their primary MPLS path?"
- "What would happen if the MariaDB max_connections were halved on db-prod-02?"
- "Which services would be affected if the Traefik entrypoint port 443 were blocked?"
Answers require causal reasoning about infrastructure behaviour.
Max score: 3 points (3=correct + accurate + actionable, 2=mostly correct, 1=some correct, 0=wrong).""",

    EvalQuestionClass.DESIGN_COMPLIANCE: """\
DESIGN_COMPLIANCE questions ask whether configs follow a standard or best practice.
Examples:
- "Do all access-PE routers have consistent QoS policy-map names?"
- "Are all PostgreSQL instances configured with SSL enabled?"
- "Do all Docker Compose services define health checks?"
Answers should cite specific evidence for compliance or deviation.
Max score: 2 points (2=correct assessment + specific evidence, 1=correct but vague, 0=wrong).""",

    EvalQuestionClass.NEGATIVE_ABSENCE: """\
NEGATIVE_ABSENCE questions ask about things that are NOT present or configured.
Examples:
- "Which routers do NOT have an NTP server configured?"
- "Are there any Docker Compose services without resource limits?"
- "Which sshd configs are missing the PermitRootLogin directive?"
Answers should enumerate what is absent and where.
Max score: 2 points (2=correct identification + evidence, 1=correct but incomplete, 0=wrong).""",
}

_SYSTEM_PROMPT_TEMPLATE = """\
You are an infrastructure configuration expert generating evaluation questions.

## Your task
Generate exactly {count} questions of class **{class_name}** for a fleet of \
infrastructure configuration files.

## Class definition
{class_definition}

## Difficulty distribution
- {easy_count} questions: easy (single file, surface-level)
- {medium_count} questions: medium (2-3 files, moderate reasoning)
- {hard_count} questions: hard (fleet-wide, deep reasoning)

## Output format
Return YAML — a list of question objects:
```yaml
- id: "{class_prefix}-001"
  difficulty: easy
  question: "..."
  reference_answer: "..."
  evidence_locations:
    - "filename.ext → section/key"
  reasoning_required: "Direct lookup"
```

## Rules
1. Every question must be answerable from the provided configs alone
2. Reference answers must be specific and verifiable
3. Evidence locations must point to real files and paths in the configs
4. Questions should cover diverse aspects of the infrastructure
5. Avoid yes/no questions for non-NEGATIVE_ABSENCE classes
6. IDs must be sequential: {class_prefix}-001, {class_prefix}-002, etc.
"""

_VALIDATION_SYSTEM_PROMPT = """\
You are a quality reviewer for infrastructure evaluation questions.

For each question, verify:
1. The question is answerable from the provided raw configs
2. The reference answer is correct and specific
3. The evidence locations point to real data in the configs
4. The question class and difficulty are appropriate

For each question, respond with one of:
- PASS: Question is correct as-is
- REVISE: Question needs minor fixes (provide corrected fields)
- REJECT: Question is unanswerable or fundamentally flawed

## Output format
Return YAML — a list of verdict objects:
```yaml
- id: "FR-001"
  verdict: PASS
- id: "FR-002"
  verdict: REVISE
  revised_question: "..."
  revised_reference_answer: "..."
  revised_evidence_locations:
    - "..."
- id: "FR-003"
  verdict: REJECT
  reason: "..."
```
"""


def _get_class_prefix(qclass: EvalQuestionClass) -> str:
    """Short prefix for question IDs."""
    return {
        EvalQuestionClass.FACTUAL_RETRIEVAL: "FR",
        EvalQuestionClass.CROSS_REFERENCE: "CR",
        EvalQuestionClass.OPERATIONAL_INFERENCE: "OI",
        EvalQuestionClass.DESIGN_COMPLIANCE: "DC",
        EvalQuestionClass.NEGATIVE_ABSENCE: "NA",
    }[qclass]


def _build_generation_prompt(
    qclass: EvalQuestionClass,
    count: int,
    source: str,
    raw_context: str,
    narrative: str | None = None,
) -> tuple[str, str]:
    """Build system + user prompts for question generation."""
    easy_count = int(count * 0.4)
    hard_count = int(count * 0.2)
    medium_count = count - easy_count - hard_count

    system = _SYSTEM_PROMPT_TEMPLATE.format(
        count=count,
        class_name=qclass.value,
        class_definition=_CLASS_DEFINITIONS[qclass],
        easy_count=easy_count,
        medium_count=medium_count,
        hard_count=hard_count,
        class_prefix=_get_class_prefix(qclass),
    )

    parts = [f"Source: {source}"]
    if narrative:
        parts.append(f"\n## Infrastructure Narrative\n{narrative}")
    parts.append(f"\n## Raw Configuration Files\n{raw_context}")

    return system, "\n".join(parts)


def _parse_questions_yaml(
    yaml_str: str,
    qclass: EvalQuestionClass,
) -> list[EvalQuestion]:
    """Parse YAML response into EvalQuestion objects."""
    yaml = YAML(typ="safe")
    data = yaml.load(yaml_str)

    if not isinstance(data, list):
        return []

    questions: list[EvalQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            difficulty_str = str(item.get("difficulty", "medium")).lower()
            try:
                difficulty = Difficulty(difficulty_str)
            except ValueError:
                difficulty = Difficulty.MEDIUM

            evidence = item.get("evidence_locations", [])
            if isinstance(evidence, str):
                evidence = [evidence]

            questions.append(EvalQuestion(
                id=str(item["id"]),
                question_class=qclass,
                difficulty=difficulty,
                question=str(item["question"]),
                reference_answer=str(item["reference_answer"]),
                evidence_locations=[str(e) for e in evidence] if evidence else [],
                reasoning_required=str(item.get("reasoning_required", "")),
            ))
        except (KeyError, TypeError):
            continue

    return questions


def generate_eval_questions(
    config_dir: Path,
    source: str,
    *,
    questions_per_class: int = 120,
    model: str = "google/gemini-2.5-flash",
    base_url: str = _DEFAULT_BASE_URL,
    api_key_env: str = _DEFAULT_API_KEY_ENV,
    on_progress: Callable[[str], None] | None = None,
) -> EvalQuestionBank:
    """Generate evaluation questions via LLM for each question class.

    Makes one API call per question class (5 calls total).

    Args:
        config_dir: Directory of raw config files.
        source: Source label (e.g. "iosxr", "hybrid-infra").
        questions_per_class: Number of candidates per class.
        model: LLM model name.
        base_url: OpenAI-compatible API base URL.
        api_key_env: Environment variable holding the API key.
        on_progress: Optional progress callback.

    Returns:
        EvalQuestionBank with generated candidates.
    """
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    _progress("Building raw config context...")
    raw_context = build_raw_context(config_dir)

    # Load narrative for hybrid-infra
    narrative: str | None = None
    narrative_path = config_dir / "NARRATIVE.md"
    if not narrative_path.exists():
        narrative_path = config_dir.parent / "NARRATIVE.md"
    if narrative_path.exists():
        narrative = narrative_path.read_text(encoding="utf-8")
        _progress("Loaded infrastructure narrative.")

    all_questions: list[EvalQuestion] = []

    for qclass in EvalQuestionClass:
        prefix = _get_class_prefix(qclass)
        _progress(f"Generating {questions_per_class} {qclass.value} questions ({prefix}-*)...")

        system, user = _build_generation_prompt(
            qclass, questions_per_class, source, raw_context, narrative,
        )

        try:
            response_text = _call_llm(
                system, user, model=model, base_url=base_url, api_key_env=api_key_env,
            )
            yaml_str = extract_yaml_block(response_text)
            questions = _parse_questions_yaml(yaml_str, qclass)
            _progress(f"  Parsed {len(questions)} questions for {qclass.value}")
            all_questions.extend(questions)
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"Generation failed for {qclass.value}: {exc}",
                stacklevel=2,
            )
            _progress(f"  WARN: Failed for {qclass.value}: {exc}")

    bank = EvalQuestionBank(
        questions=all_questions,
        source=source,
        model_generate=model,
    )
    _progress(f"Generated {len(all_questions)} total questions: {bank.class_counts}")
    return bank


def validate_eval_questions(
    bank: EvalQuestionBank,
    config_dir: Path,
    *,
    model: str = "google/gemini-2.5-flash",
    base_url: str = _DEFAULT_BASE_URL,
    api_key_env: str = _DEFAULT_API_KEY_ENV,
    target_per_class: int = 100,
    on_progress: Callable[[str], None] | None = None,
) -> EvalQuestionBank:
    """Validate and prune a candidate question bank via LLM.

    Makes one API call per question class (5 calls total).

    Args:
        bank: Candidate question bank to validate.
        config_dir: Directory of raw config files.
        model: LLM model name.
        base_url: OpenAI-compatible API base URL.
        api_key_env: Environment variable holding the API key.
        target_per_class: Maximum questions to keep per class.
        on_progress: Optional progress callback.

    Returns:
        Validated EvalQuestionBank with pruned questions.
    """
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    _progress("Building raw config context for validation...")
    raw_context = build_raw_context(config_dir)

    validated: list[EvalQuestion] = []
    by_class = bank.by_class

    for qclass in EvalQuestionClass:
        candidates = by_class.get(qclass, [])
        if not candidates:
            _progress(f"  No candidates for {qclass.value}, skipping.")
            continue

        _progress(f"Validating {len(candidates)} {qclass.value} questions...")

        # Serialize candidates for the validation prompt
        yaml_obj = YAML(typ="rt")
        yaml_obj.default_flow_style = False
        candidate_dicts = [
            {
                "id": q.id,
                "question": q.question,
                "reference_answer": q.reference_answer,
                "evidence_locations": q.evidence_locations,
            }
            for q in candidates
        ]
        stream = StringIO()
        yaml_obj.dump(candidate_dicts, stream)
        candidates_yaml = stream.getvalue()

        user_prompt = (
            f"## Candidate Questions ({qclass.value})\n{candidates_yaml}\n\n"
            f"## Raw Configuration Files\n{raw_context}"
        )

        try:
            response_text = _call_llm(
                _VALIDATION_SYSTEM_PROMPT,
                user_prompt,
                model=model,
                base_url=base_url,
                api_key_env=api_key_env,
            )
            yaml_str = extract_yaml_block(response_text)
            verdicts = _parse_validation_response(yaml_str)

            # Build lookup for candidates
            candidate_map = {q.id: q for q in candidates}
            class_validated: list[EvalQuestion] = []

            for v in verdicts:
                qid = v.get("id", "")
                verdict = v.get("verdict", "").upper()
                orig = candidate_map.get(qid)
                if not orig:
                    continue

                if verdict == "PASS":
                    class_validated.append(orig)
                elif verdict == "REVISE":
                    revised = EvalQuestion(
                        id=orig.id,
                        question_class=orig.question_class,
                        difficulty=orig.difficulty,
                        question=str(v.get("revised_question", orig.question)),
                        reference_answer=str(v.get("revised_reference_answer", orig.reference_answer)),
                        evidence_locations=[
                            str(e) for e in v.get("revised_evidence_locations", orig.evidence_locations)
                        ],
                        reasoning_required=orig.reasoning_required,
                    )
                    class_validated.append(revised)
                # REJECT: skip

            # Prune to target
            class_validated = class_validated[:target_per_class]
            _progress(f"  {qclass.value}: {len(class_validated)} passed/revised (target {target_per_class})")
            validated.extend(class_validated)

        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"Validation failed for {qclass.value}: {exc}",
                stacklevel=2,
            )
            _progress(f"  WARN: Validation failed for {qclass.value}: {exc}")
            # Keep originals up to target on failure
            validated.extend(candidates[:target_per_class])

    result = EvalQuestionBank(
        questions=validated,
        source=bank.source,
        model_generate=bank.model_generate,
        model_validate=model,
    )
    _progress(f"Validated bank: {len(validated)} questions: {result.class_counts}")
    return result


def _parse_validation_response(yaml_str: str) -> list[dict[str, Any]]:
    """Parse validation YAML response into list of verdict dicts."""
    yaml = YAML(typ="safe")
    data = yaml.load(yaml_str)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    base_url: str,
    api_key_env: str,
    max_tokens: int = 16384,
) -> str:
    """Call LLM via OpenAI-compatible API. Lazy-imports openai."""
    try:
        from openai import OpenAI
    except ImportError:
        msg = "The openai SDK is required for eval question generation. Install with: pip install decoct[llm]"
        raise ImportError(msg)  # noqa: B904

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get(api_key_env)
    if not api_key:
        msg = f"Environment variable {api_key_env} is not set"
        raise ValueError(msg)

    client = OpenAI(base_url=base_url, api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


def save_eval_bank(bank: EvalQuestionBank, path: Path) -> None:
    """Save an EvalQuestionBank to YAML."""
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False

    doc: dict[str, Any] = {
        "version": bank.version,
        "source": bank.source,
        "generated_by": bank.generated_by,
        "model_generate": bank.model_generate,
        "model_validate": bank.model_validate,
        "question_count": len(bank.questions),
        "class_counts": bank.class_counts,
        "questions": [
            {
                "id": q.id,
                "question_class": q.question_class.value,
                "difficulty": q.difficulty.value,
                "question": q.question,
                "reference_answer": q.reference_answer,
                "evidence_locations": q.evidence_locations,
                "reasoning_required": q.reasoning_required,
            }
            for q in bank.questions
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    stream = StringIO()
    yaml.dump(doc, stream)
    path.write_text(stream.getvalue(), encoding="utf-8")


def load_eval_bank(path: Path) -> EvalQuestionBank:
    """Load an EvalQuestionBank from YAML."""
    yaml = YAML(typ="safe")
    data = yaml.load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        msg = f"Expected YAML dict, got {type(data).__name__}"
        raise ValueError(msg)

    questions: list[EvalQuestion] = []
    for item in data.get("questions", []):
        try:
            questions.append(EvalQuestion(
                id=str(item["id"]),
                question_class=EvalQuestionClass(item["question_class"]),
                difficulty=Difficulty(item["difficulty"]),
                question=str(item["question"]),
                reference_answer=str(item["reference_answer"]),
                evidence_locations=[str(e) for e in item.get("evidence_locations", [])],
                reasoning_required=str(item.get("reasoning_required", "")),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    return EvalQuestionBank(
        questions=questions,
        version=data.get("version", 1),
        source=data.get("source", ""),
        generated_by=data.get("generated_by", ""),
        model_generate=data.get("model_generate", ""),
        model_validate=data.get("model_validate", ""),
    )
