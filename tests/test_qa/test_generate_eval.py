"""Tests for generate_eval.py — LLM question generation and validation."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from decoct.qa.eval_models import (
    Difficulty,
    EvalQuestion,
    EvalQuestionBank,
    EvalQuestionClass,
)
from decoct.qa.generate_eval import (
    _build_generation_prompt,
    _get_class_prefix,
    _parse_questions_yaml,
    load_eval_bank,
    save_eval_bank,
)


class TestGetClassPrefix:
    def test_all_classes(self) -> None:
        assert _get_class_prefix(EvalQuestionClass.FACTUAL_RETRIEVAL) == "FR"
        assert _get_class_prefix(EvalQuestionClass.CROSS_REFERENCE) == "CR"
        assert _get_class_prefix(EvalQuestionClass.OPERATIONAL_INFERENCE) == "OI"
        assert _get_class_prefix(EvalQuestionClass.DESIGN_COMPLIANCE) == "DC"
        assert _get_class_prefix(EvalQuestionClass.NEGATIVE_ABSENCE) == "NA"


class TestBuildGenerationPrompt:
    def test_returns_system_and_user(self) -> None:
        system, user = _build_generation_prompt(
            EvalQuestionClass.FACTUAL_RETRIEVAL,
            count=10,
            source="iosxr",
            raw_context="some config data",
        )
        assert "FACTUAL_RETRIEVAL" in system
        assert "10" in system
        assert "FR-" in system
        assert "iosxr" in user
        assert "some config data" in user

    def test_narrative_included_when_provided(self) -> None:
        _, user = _build_generation_prompt(
            EvalQuestionClass.CROSS_REFERENCE,
            count=5,
            source="hybrid-infra",
            raw_context="configs",
            narrative="Ridgeline Data narrative",
        )
        assert "Ridgeline Data narrative" in user

    def test_difficulty_distribution(self) -> None:
        system, _ = _build_generation_prompt(
            EvalQuestionClass.FACTUAL_RETRIEVAL,
            count=120,
            source="test",
            raw_context="",
        )
        assert "48 questions: easy" in system
        assert "48 questions: medium" in system
        assert "24 questions: hard" in system


class TestParseQuestionsYaml:
    def test_valid_yaml(self) -> None:
        yaml_str = textwrap.dedent("""\
        - id: "FR-001"
          difficulty: easy
          question: "What is the MTU?"
          reference_answer: "9000"
          evidence_locations:
            - "router-01.cfg"
          reasoning_required: "Direct lookup"
        - id: "FR-002"
          difficulty: hard
          question: "What is the hostname?"
          reference_answer: "access-pe-01"
          evidence_locations:
            - "router-01.cfg"
          reasoning_required: "Direct lookup"
        """)
        questions = _parse_questions_yaml(yaml_str, EvalQuestionClass.FACTUAL_RETRIEVAL)
        assert len(questions) == 2
        assert questions[0].id == "FR-001"
        assert questions[0].difficulty == Difficulty.EASY
        assert questions[0].question_class == EvalQuestionClass.FACTUAL_RETRIEVAL
        assert questions[1].difficulty == Difficulty.HARD

    def test_invalid_difficulty_defaults_to_medium(self) -> None:
        yaml_str = textwrap.dedent("""\
        - id: "FR-001"
          difficulty: ultra
          question: "Q?"
          reference_answer: "A"
        """)
        questions = _parse_questions_yaml(yaml_str, EvalQuestionClass.FACTUAL_RETRIEVAL)
        assert len(questions) == 1
        assert questions[0].difficulty == Difficulty.MEDIUM

    def test_malformed_entries_skipped(self) -> None:
        yaml_str = textwrap.dedent("""\
        - id: "FR-001"
          question: "Q?"
          reference_answer: "A"
        - not_a_dict
        - missing_required: true
        """)
        questions = _parse_questions_yaml(yaml_str, EvalQuestionClass.FACTUAL_RETRIEVAL)
        assert len(questions) == 1  # Only first one has required fields

    def test_non_list_returns_empty(self) -> None:
        questions = _parse_questions_yaml("key: value", EvalQuestionClass.FACTUAL_RETRIEVAL)
        assert questions == []

    def test_string_evidence_converted_to_list(self) -> None:
        yaml_str = textwrap.dedent("""\
        - id: "FR-001"
          question: "Q?"
          reference_answer: "A"
          evidence_locations: "single-file.cfg"
        """)
        questions = _parse_questions_yaml(yaml_str, EvalQuestionClass.FACTUAL_RETRIEVAL)
        assert questions[0].evidence_locations == ["single-file.cfg"]


class TestSaveLoadEvalBank:
    def test_round_trip(self, tmp_path: Path) -> None:
        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    difficulty=Difficulty.EASY,
                    question="What is the MTU?",
                    reference_answer="9000",
                    evidence_locations=["router-01.cfg"],
                    reasoning_required="Direct lookup",
                ),
                EvalQuestion(
                    id="CR-001",
                    question_class=EvalQuestionClass.CROSS_REFERENCE,
                    difficulty=Difficulty.MEDIUM,
                    question="Which routers share OSPF area?",
                    reference_answer="access-pe-01, access-pe-02",
                    evidence_locations=["router-01.cfg", "router-02.cfg"],
                    reasoning_required="Cross-file comparison",
                ),
            ],
            source="iosxr",
            model_generate="test-model",
            model_validate="val-model",
        )

        path = tmp_path / "bank.yaml"
        save_eval_bank(bank, path)

        loaded = load_eval_bank(path)
        assert len(loaded.questions) == 2
        assert loaded.source == "iosxr"
        assert loaded.model_generate == "test-model"
        assert loaded.model_validate == "val-model"

        q = loaded.questions[0]
        assert q.id == "FR-001"
        assert q.question_class == EvalQuestionClass.FACTUAL_RETRIEVAL
        assert q.difficulty == Difficulty.EASY
        assert q.reference_answer == "9000"

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("just a string")
        with pytest.raises(ValueError, match="Expected YAML dict"):
            load_eval_bank(path)

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "bank.yaml"
        bank = EvalQuestionBank(source="test")
        save_eval_bank(bank, path)
        assert path.exists()


class TestGenerateEvalQuestions:
    @patch("decoct.qa.generate_eval._call_llm")
    def test_calls_llm_per_class(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        """Generation makes one LLM call per question class."""
        # Create a minimal config dir
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router")

        mock_llm.return_value = textwrap.dedent("""\
        ```yaml
        - id: "XX-001"
          difficulty: easy
          question: "What is the hostname?"
          reference_answer: "test-router"
          evidence_locations:
            - "test.cfg"
          reasoning_required: "Direct lookup"
        ```
        """)

        from decoct.qa.generate_eval import generate_eval_questions

        bank = generate_eval_questions(
            cfg_dir, "test",
            questions_per_class=5,
            model="test-model",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        assert mock_llm.call_count == 5  # One per class
        assert len(bank.questions) == 5  # 1 question per class
        assert bank.source == "test"
        assert bank.model_generate == "test-model"


class TestValidateEvalQuestions:
    @patch("decoct.qa.generate_eval._call_llm")
    def test_pass_keeps_question(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router")

        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    difficulty=Difficulty.EASY,
                    question="What is the hostname?",
                    reference_answer="test-router",
                ),
            ],
            source="test",
        )

        mock_llm.return_value = textwrap.dedent("""\
        ```yaml
        - id: "FR-001"
          verdict: PASS
        ```
        """)

        from decoct.qa.generate_eval import validate_eval_questions

        validated = validate_eval_questions(
            bank, cfg_dir,
            model="test-model",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        assert len(validated.questions) == 1
        assert validated.questions[0].id == "FR-001"

    @patch("decoct.qa.generate_eval._call_llm")
    def test_reject_removes_question(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router")

        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    difficulty=Difficulty.EASY,
                    question="Bad question?",
                    reference_answer="wrong",
                ),
            ],
            source="test",
        )

        mock_llm.return_value = textwrap.dedent("""\
        ```yaml
        - id: "FR-001"
          verdict: REJECT
          reason: "Not answerable"
        ```
        """)

        from decoct.qa.generate_eval import validate_eval_questions

        validated = validate_eval_questions(
            bank, cfg_dir,
            model="test-model",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        assert len(validated.questions) == 0

    @patch("decoct.qa.generate_eval._call_llm")
    def test_revise_updates_question(self, mock_llm: MagicMock, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        (cfg_dir / "test.cfg").write_text("hostname test-router")

        bank = EvalQuestionBank(
            questions=[
                EvalQuestion(
                    id="FR-001",
                    question_class=EvalQuestionClass.FACTUAL_RETRIEVAL,
                    difficulty=Difficulty.EASY,
                    question="Old question?",
                    reference_answer="old answer",
                ),
            ],
            source="test",
        )

        mock_llm.return_value = textwrap.dedent("""\
        ```yaml
        - id: "FR-001"
          verdict: REVISE
          revised_question: "New question?"
          revised_reference_answer: "new answer"
        ```
        """)

        from decoct.qa.generate_eval import validate_eval_questions

        validated = validate_eval_questions(
            bank, cfg_dir,
            model="test-model",
            base_url="http://fake",
            api_key_env="FAKE_KEY",
        )

        assert len(validated.questions) == 1
        assert validated.questions[0].question == "New question?"
        assert validated.questions[0].reference_answer == "new answer"
