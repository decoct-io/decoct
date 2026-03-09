"""Tests for INI/key-value input support."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml.comments import CommentedMap

from decoct.formats import detect_format, ini_to_commented_map, load_input

FIXTURES = Path(__file__).parent / "fixtures"
INI_FIXTURES = FIXTURES / "ini"


class TestIniToCommentedMap:
    def test_sectioned_ini_produces_nested_commented_map(self) -> None:
        text = "[server]\nhost = 0.0.0.0\nport = 8080\n"
        result = ini_to_commented_map(text)
        assert isinstance(result, CommentedMap)
        assert isinstance(result["server"], CommentedMap)
        assert result["server"]["host"] == "0.0.0.0"
        assert result["server"]["port"] == 8080

    def test_flat_keyvalue_produces_flat_commented_map(self) -> None:
        text = "host = localhost\nport = 5432\nssl = off\n"
        result = ini_to_commented_map(text)
        assert isinstance(result, CommentedMap)
        assert result["host"] == "localhost"
        assert result["port"] == 5432
        assert result["ssl"] is False

    def test_flat_skips_comments_and_blanks(self) -> None:
        text = "# comment\n\nkey = value\n; another comment\nother = data\n"
        result = ini_to_commented_map(text)
        assert len(result) == 2
        assert result["key"] == "value"
        assert result["other"] == "data"

    def test_multiple_sections(self) -> None:
        text = "[a]\nx = 1\n[b]\ny = 2\n"
        result = ini_to_commented_map(text)
        assert list(result.keys()) == ["a", "b"]
        assert result["a"]["x"] == 1
        assert result["b"]["y"] == 2

    def test_equals_in_value_preserved(self) -> None:
        text = "connection_string = host=db port=5432\n"
        result = ini_to_commented_map(text)
        assert result["connection_string"] == "host=db port=5432"


class TestTypeInference:
    def test_boolean_true_variants(self) -> None:
        for val in ("true", "True", "TRUE", "yes", "Yes", "on", "ON"):
            text = f"key = {val}\n"
            result = ini_to_commented_map(text)
            assert result["key"] is True, f"Failed for {val}"

    def test_boolean_false_variants(self) -> None:
        for val in ("false", "False", "FALSE", "no", "No", "off", "OFF"):
            text = f"key = {val}\n"
            result = ini_to_commented_map(text)
            assert result["key"] is False, f"Failed for {val}"

    def test_integer_detection(self) -> None:
        text = "port = 5432\ncount = 0\nnegative = -1\n"
        result = ini_to_commented_map(text)
        assert result["port"] == 5432
        assert isinstance(result["port"], int)
        assert result["count"] == 0
        assert result["negative"] == -1

    def test_float_detection(self) -> None:
        text = "ratio = 3.14\ntimeout = 0.5\n"
        result = ini_to_commented_map(text)
        assert result["ratio"] == 3.14
        assert isinstance(result["ratio"], float)
        assert result["timeout"] == 0.5

    def test_string_preserved(self) -> None:
        text = "name = myapp\npath = /var/log\nsize = 128MB\n"
        result = ini_to_commented_map(text)
        assert result["name"] == "myapp"
        assert isinstance(result["name"], str)
        assert result["size"] == "128MB"


class TestDetectFormat:
    def test_ini_extension(self) -> None:
        assert detect_format(Path("config.ini")) == "ini"

    def test_conf_extension(self) -> None:
        assert detect_format(Path("postgresql.conf")) == "ini"

    def test_cfg_extension(self) -> None:
        assert detect_format(Path("app.cfg")) == "ini"

    def test_cnf_extension(self) -> None:
        assert detect_format(Path("my.cnf")) == "ini"

    def test_properties_extension(self) -> None:
        assert detect_format(Path("app.properties")) == "ini"

    def test_yaml_still_detected(self) -> None:
        assert detect_format(Path("config.yaml")) == "yaml"

    def test_json_still_detected(self) -> None:
        assert detect_format(Path("config.json")) == "json"


class TestLoadInput:
    def test_loads_sectioned_ini(self) -> None:
        doc, raw = load_input(INI_FIXTURES / "simple-config.ini")
        assert isinstance(doc, CommentedMap)
        assert "server" in doc
        assert "database" in doc
        assert doc["server"]["port"] == 8080
        assert doc["server"]["debug"] is True
        assert doc["database"]["ssl"] is False

    def test_loads_flat_config(self) -> None:
        doc, raw = load_input(INI_FIXTURES / "flat-config.conf")
        assert isinstance(doc, CommentedMap)
        assert doc["port"] == 5432
        assert doc["max_connections"] == 100
        assert doc["logging_collector"] is True
        assert doc["ssl"] is False
        assert doc["shared_buffers"] == "128MB"

    def test_loads_mysql_cnf(self) -> None:
        doc, raw = load_input(INI_FIXTURES / "mysql-config.cnf")
        assert isinstance(doc, CommentedMap)
        assert "mysqld" in doc
        assert "client" in doc
        assert doc["mysqld"]["port"] == 3306
        assert doc["mysqld"]["slow_query_log"] is True

    def test_ini_through_strip_secrets_pipeline(self) -> None:
        """Verify that strip-secrets works on an INI-loaded document."""
        from decoct.passes.strip_secrets import StripSecretsPass

        doc, _raw = load_input(INI_FIXTURES / "with-secrets.ini")
        p = StripSecretsPass()
        result = p.run(doc)
        assert doc["database"]["password"] == "[REDACTED]"
        assert doc["api"]["api_key"] == "[REDACTED]"
        assert doc["database"]["host"] == "db.example.com"
        assert result.items_removed > 0

    def test_raw_text_returned(self) -> None:
        doc, raw = load_input(INI_FIXTURES / "simple-config.ini")
        assert "[server]" in raw
        assert "port" in raw
