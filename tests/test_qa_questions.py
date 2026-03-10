"""Tests for QA question generation (no LLM needed)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from decoct.cli import cli
from decoct.qa.questions import (
    QuestionBank,
    QuestionCategory,
    generate_question_bank,
    load_question_bank,
    save_question_bank,
)

FIXTURES = Path(__file__).parent / "fixtures"
IOSXR_CONFIGS = FIXTURES / "iosxr" / "configs"


class TestGenerateQuestionBank:
    def test_non_empty_bank(self) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=50)
        assert len(bank.pairs) > 0

    def test_all_categories_represented(self) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=200)
        categories = {q.category for q in bank.pairs}
        assert QuestionCategory.SINGLE_VALUE in categories
        assert QuestionCategory.MULTI_ENTITY in categories
        assert QuestionCategory.EXISTENCE in categories
        assert QuestionCategory.COMPARISON in categories
        assert QuestionCategory.COUNT in categories

    def test_ground_truth_non_empty(self) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=50)
        for q in bank.pairs:
            assert q.ground_truth.answer != "", f"Empty answer for {q.id}"

    def test_entity_ids_populated(self) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=50)
        for q in bank.pairs:
            assert len(q.entity_ids) > 0, f"No entity_ids for {q.id}"

    def test_deterministic_with_same_seed(self) -> None:
        bank1 = generate_question_bank(IOSXR_CONFIGS, max_questions=50, seed=42)
        bank2 = generate_question_bank(IOSXR_CONFIGS, max_questions=50, seed=42)
        assert len(bank1.pairs) == len(bank2.pairs)
        for q1, q2 in zip(bank1.pairs, bank2.pairs):
            assert q1.id == q2.id
            assert q1.question == q2.question
            assert q1.ground_truth.answer == q2.ground_truth.answer

    def test_different_seed_different_result(self) -> None:
        bank1 = generate_question_bank(IOSXR_CONFIGS, max_questions=50, seed=42)
        bank2 = generate_question_bank(IOSXR_CONFIGS, max_questions=50, seed=99)
        # At least some questions should differ (different sampling)
        ids1 = {q.id for q in bank1.pairs}
        ids2 = {q.id for q in bank2.pairs}
        assert ids1 != ids2

    def test_max_questions_respected(self) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=10)
        assert len(bank.pairs) <= 10

    def test_entity_and_type_count(self) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=10)
        assert bank.entity_count == 86
        assert bank.type_count == 5

    def test_category_filter(self) -> None:
        bank = generate_question_bank(
            IOSXR_CONFIGS,
            max_questions=50,
            categories=[QuestionCategory.SINGLE_VALUE],
        )
        categories = {q.category for q in bank.pairs}
        assert categories == {QuestionCategory.SINGLE_VALUE}


class TestSerialisationRoundTrip:
    def test_save_and_load(self, tmp_path: Path) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=20)
        out = tmp_path / "questions.json"
        save_question_bank(bank, out)

        loaded = load_question_bank(out)
        assert len(loaded.pairs) == len(bank.pairs)
        assert loaded.entity_count == bank.entity_count
        assert loaded.type_count == bank.type_count

        for orig, reloaded in zip(bank.pairs, loaded.pairs):
            assert orig.id == reloaded.id
            assert orig.category == reloaded.category
            assert orig.question == reloaded.question
            assert orig.ground_truth.answer == reloaded.ground_truth.answer
            assert orig.entity_ids == reloaded.entity_ids

    def test_save_produces_valid_json(self, tmp_path: Path) -> None:
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=10)
        out = tmp_path / "questions.json"
        save_question_bank(bank, out)
        data = json.loads(out.read_text())
        assert "pairs" in data
        assert len(data["pairs"]) == len(bank.pairs)


class TestCompareAnswers:
    def test_exact_match(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert _compare_answers("hello", "hello")

    def test_case_insensitive(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert _compare_answers("Hello", "hello")
        assert _compare_answers("YES", "yes")

    def test_whitespace_normalisation(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert _compare_answers("  hello  world  ", "hello world")

    def test_boolean_equivalence(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert _compare_answers("yes", "true")
        assert _compare_answers("no", "false")
        assert _compare_answers("yes", "1")
        assert not _compare_answers("yes", "no")

    def test_numeric_equivalence(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert _compare_answers("9216", "9216.0")
        assert _compare_answers("3", "3.0")

    def test_substring_match(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert _compare_answers("9216", "The MTU is 9216")
        assert not _compare_answers("9216", "9217")

    def test_no_match(self) -> None:
        from decoct.qa.evaluate import _compare_answers

        assert not _compare_answers("hello", "world")


class TestGenerateQuestionsCLI:
    def test_basic_invocation(self, tmp_path: Path) -> None:
        out = tmp_path / "questions.json"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "generate-questions",
            "-c", str(IOSXR_CONFIGS),
            "-o", str(out),
            "--max-questions", "20",
        ])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data["pairs"]) <= 20

    def test_seed_parameter(self, tmp_path: Path) -> None:
        out1 = tmp_path / "q1.json"
        out2 = tmp_path / "q2.json"
        runner = CliRunner()
        runner.invoke(cli, [
            "entity-graph", "generate-questions",
            "-c", str(IOSXR_CONFIGS), "-o", str(out1), "--seed", "42",
        ])
        runner.invoke(cli, [
            "entity-graph", "generate-questions",
            "-c", str(IOSXR_CONFIGS), "-o", str(out2), "--seed", "42",
        ])
        assert out1.read_text() == out2.read_text()
