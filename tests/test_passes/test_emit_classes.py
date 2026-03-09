"""Tests for the emit-classes pass."""

from __future__ import annotations

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from decoct.passes.emit_classes import EmitClassesPass, _classify_defaults, _derive_class_name, emit_classes
from decoct.schemas.models import Schema


def _make_schema(defaults: dict) -> Schema:
    return Schema(
        platform="test-platform",
        source="test",
        confidence="authoritative",
        defaults=defaults,
        drop_patterns=[],
        system_managed=[],
    )


class TestClassifyDefaults:
    def test_groups_by_prefix(self) -> None:
        defaults = {
            "services.*.restart": "no",
            "services.*.privileged": False,
            "networks.*.driver": "bridge",
        }
        classes = _classify_defaults(defaults)
        assert "service-restart-defaults" in classes or "service-defaults" in classes
        # Should have at least 2 classes (services vs networks)
        assert len(classes) >= 2

    def test_single_class_for_flat_defaults(self) -> None:
        defaults = {
            "Port": 22,
            "LogLevel": "INFO",
        }
        classes = _classify_defaults(defaults)
        assert len(classes) >= 1


class TestDeriveClassName:
    def test_service_level(self) -> None:
        name = _derive_class_name(["services", "*", "restart"])
        assert "service" in name
        assert "defaults" in name

    def test_deep_nesting(self) -> None:
        name = _derive_class_name(["services", "*", "healthcheck", "interval"])
        assert "service" in name
        assert "healthcheck" in name

    def test_top_level(self) -> None:
        name = _derive_class_name(["Port"])
        assert "defaults" in name

    def test_wildcards_only(self) -> None:
        name = _derive_class_name(["*", "**"])
        assert name == "defaults"


class TestEmitClasses:
    def test_adds_comment_to_doc(self) -> None:
        doc = CommentedMap({"services": {"web": {"image": "nginx"}}})
        schema = _make_schema({"services.*.restart": "no", "services.*.privileged": False})
        count = emit_classes(doc, schema)
        assert count >= 1
        # The doc should now have a start comment
        yaml = YAML(typ="rt")
        from io import StringIO
        stream = StringIO()
        yaml.dump(doc, stream)
        output = stream.getvalue()
        assert "@class" in output
        assert "test-platform" in output

    def test_no_op_without_defaults(self) -> None:
        doc = CommentedMap({"foo": "bar"})
        schema = _make_schema({})
        count = emit_classes(doc, schema)
        assert count == 0

    def test_no_op_for_non_map(self) -> None:
        from ruamel.yaml.comments import CommentedSeq
        doc = CommentedSeq([1, 2, 3])
        schema = _make_schema({"foo": "bar"})
        count = emit_classes(doc, schema)
        assert count == 0


class TestEmitClassesPass:
    def test_pass_with_schema(self) -> None:
        doc = CommentedMap({"services": {"web": {"image": "nginx"}}})
        schema = _make_schema({"services.*.restart": "no"})
        p = EmitClassesPass(schema=schema)
        result = p.run(doc)
        assert "classes emitted" in result.details[0]

    def test_pass_without_schema(self) -> None:
        doc = CommentedMap({"foo": "bar"})
        p = EmitClassesPass()
        result = p.run(doc)
        assert result.items_removed == 0

    def test_ordering(self) -> None:
        p = EmitClassesPass()
        assert "strip-defaults" in p.run_after
        assert "prune-empty" in p.run_after


class TestEmitClassesE2E:
    def test_compress_with_classes(self) -> None:
        from pathlib import Path

        from click.testing import CliRunner

        from decoct.cli import cli

        fixtures = Path(__file__).parent.parent / "fixtures"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "compress",
            str(fixtures / "yaml" / "cloud-init-config.yaml"),
            "--schema", "cloud-init",
        ])
        assert result.exit_code == 0
        assert "@class" in result.output
        assert "cloud-init" in result.output
