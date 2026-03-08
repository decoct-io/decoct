"""Tests for token counting and statistics."""

from decoct.tokens import TokenReport, count_tokens, create_report, format_report


class TestCountTokens:
    def test_count_simple_string(self) -> None:
        count = count_tokens("hello world")
        assert count > 0
        assert isinstance(count, int)

    def test_count_empty_string(self) -> None:
        assert count_tokens("") == 0

    def test_cl100k_base(self) -> None:
        count = count_tokens("hello world", encoding="cl100k_base")
        assert count > 0

    def test_o200k_base(self) -> None:
        count = count_tokens("hello world", encoding="o200k_base")
        assert count > 0

    def test_yaml_content(self) -> None:
        yaml_text = "services:\n  web:\n    image: nginx:1.25\n    restart: always\n"
        count = count_tokens(yaml_text)
        assert count > 0


class TestTokenReport:
    def test_savings(self) -> None:
        r = TokenReport(input_tokens=100, output_tokens=60)
        assert r.savings_tokens == 40
        assert r.savings_pct == 40.0

    def test_no_savings(self) -> None:
        r = TokenReport(input_tokens=100, output_tokens=100)
        assert r.savings_tokens == 0
        assert r.savings_pct == 0.0

    def test_zero_input(self) -> None:
        r = TokenReport(input_tokens=0, output_tokens=0)
        assert r.savings_pct == 0.0

    def test_full_savings(self) -> None:
        r = TokenReport(input_tokens=100, output_tokens=0)
        assert r.savings_pct == 100.0


class TestCreateReport:
    def test_identical_text(self) -> None:
        text = "services:\n  web:\n    image: nginx:1.25\n"
        r = create_report(text, text)
        assert r.input_tokens == r.output_tokens
        assert r.savings_tokens == 0

    def test_compressed_text(self) -> None:
        input_text = "services:\n  web:\n    image: nginx:1.25\n    restart: always\n    privileged: false\n"
        output_text = "services:\n  web:\n    image: nginx:1.25\n"
        r = create_report(input_text, output_text)
        assert r.input_tokens > r.output_tokens
        assert r.savings_tokens > 0
        assert r.savings_pct > 0

    def test_with_o200k_encoding(self) -> None:
        r = create_report("hello world", "hello", encoding="o200k_base")
        assert r.input_tokens >= r.output_tokens


class TestFormatReport:
    def test_format_output(self) -> None:
        r = TokenReport(input_tokens=1000, output_tokens=600)
        formatted = format_report(r)
        assert "1000" in formatted
        assert "600" in formatted
        assert "400" in formatted
        assert "40.0%" in formatted

    def test_format_zero(self) -> None:
        r = TokenReport(input_tokens=0, output_tokens=0)
        formatted = format_report(r)
        assert "0.0%" in formatted
