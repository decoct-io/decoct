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
HYBRID_INFRA_CONFIGS = FIXTURES / "hybrid-infra" / "configs"


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


class TestOrderingQuestions:
    def _make_hybrid_bank(
        self, *, max_questions: int = 500, categories: list[QuestionCategory] | None = None,
    ) -> QuestionBank:
        from decoct.adapters.hybrid_infra import HybridInfraAdapter
        return generate_question_bank(
            HYBRID_INFRA_CONFIGS,
            max_questions=max_questions,
            categories=categories,
            adapter=HybridInfraAdapter(),
        )

    def test_ordering_category_exists(self) -> None:
        assert QuestionCategory.ORDERING.value == "ORDERING"

    def test_ordering_questions_generated_hybrid_infra(self) -> None:
        bank = self._make_hybrid_bank(categories=[QuestionCategory.ORDERING])
        assert len(bank.pairs) > 0
        assert all(q.category == QuestionCategory.ORDERING for q in bank.pairs)

    def test_ordering_position_answer_correct(self) -> None:
        """The 1st scrape config in prometheus-prod should be 'prometheus'."""
        bank = self._make_hybrid_bank(categories=[QuestionCategory.ORDERING])
        position_qs = [
            q for q in bank.pairs
            if "1st" in q.question and "prometheus-prod" in q.question and "scrape_configs" in q.question
        ]
        assert len(position_qs) == 1
        assert position_qs[0].ground_truth.answer == "prometheus"

    def test_ordering_before_after_answer_correct(self) -> None:
        """The scrape config after 'prometheus' in prometheus-prod should be 'core-api'."""
        bank = self._make_hybrid_bank(categories=[QuestionCategory.ORDERING])
        after_qs = [
            q for q in bank.pairs
            if "immediately after prometheus" in q.question and "prometheus-prod" in q.question
        ]
        assert len(after_qs) == 1
        assert after_qs[0].ground_truth.answer == "core-api"

    def test_ordering_first_last_answer_correct(self) -> None:
        """First/last scrape configs in prometheus-prod."""
        bank = self._make_hybrid_bank(categories=[QuestionCategory.ORDERING])
        first_qs = [
            q for q in bank.pairs
            if "first" in q.question and "prometheus-prod" in q.question and "scrape_configs" in q.question
        ]
        last_qs = [
            q for q in bank.pairs
            if "last" in q.question and "prometheus-prod" in q.question and "scrape_configs" in q.question
        ]
        assert len(first_qs) == 1
        assert first_qs[0].ground_truth.answer == "prometheus"
        assert len(last_qs) == 1
        assert last_qs[0].ground_truth.answer == "node-exporter"

    def test_ordering_requires_min_two_items(self) -> None:
        """Lists with < 2 items with a name field should produce no ORDERING questions."""
        from decoct.adapters.hybrid_infra import HybridInfraAdapter
        from decoct.core.composite_value import CompositeValue
        from decoct.core.entity_graph import EntityGraph
        from decoct.core.types import Attribute, Entity

        # Create a minimal entity with a 1-item list
        graph = EntityGraph()
        entity = Entity(id="single-item")
        entity.attributes["tasks"] = Attribute(
            path="tasks",
            value=CompositeValue(data=[{"name": "only-task"}], kind="list"),
            type="list",
        )
        graph.add_entity(entity)

        # Generate ORDERING questions — should get none from this entity
        bank = generate_question_bank(
            HYBRID_INFRA_CONFIGS,
            categories=[QuestionCategory.ORDERING],
            adapter=HybridInfraAdapter(),
        )
        single_item_qs = [q for q in bank.pairs if "single-item" in q.question]
        assert len(single_item_qs) == 0

    def test_ordering_needs_name_field(self) -> None:
        """Lists of dicts without a discoverable name field produce no ORDERING questions."""
        from decoct.qa.questions import _find_name_field
        items = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
        assert _find_name_field(items) is None

    def test_adapter_parameter_backward_compat(self) -> None:
        """generate_question_bank without adapter still works (IOS-XR default)."""
        bank = generate_question_bank(IOSXR_CONFIGS, max_questions=10)
        assert len(bank.pairs) > 0

    def test_adapter_parameter_hybrid_infra(self) -> None:
        """Passing HybridInfraAdapter gets entities from hybrid-infra fixtures."""
        bank = self._make_hybrid_bank(max_questions=10)
        assert bank.entity_count > 0

    def test_serialisation_roundtrip_ordering(self, tmp_path: Path) -> None:
        """ORDERING questions survive save/load."""
        bank = self._make_hybrid_bank(categories=[QuestionCategory.ORDERING], max_questions=50)
        out = tmp_path / "ordering.json"
        save_question_bank(bank, out)
        loaded = load_question_bank(out)
        assert len(loaded.pairs) == len(bank.pairs)
        for orig, reloaded in zip(bank.pairs, loaded.pairs):
            assert orig.category == reloaded.category == QuestionCategory.ORDERING
            assert orig.ground_truth.answer == reloaded.ground_truth.answer

    def test_cli_adapter_option(self, tmp_path: Path) -> None:
        """CLI --adapter hybrid-infra invocation works."""
        out = tmp_path / "questions.json"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "generate-questions",
            "-c", str(HYBRID_INFRA_CONFIGS),
            "-o", str(out),
            "--adapter", "hybrid-infra",
            "--max-questions", "50",
        ])
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        categories = {p["category"] for p in data["pairs"]}
        assert "ORDERING" in categories
