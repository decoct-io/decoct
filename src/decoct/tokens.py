"""Token counting and statistics."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken


def count_tokens(text: str, encoding: str = "cl100k_base") -> int:
    """Count tokens in a string using the specified tiktoken encoding."""
    enc = tiktoken.get_encoding(encoding)
    return len(enc.encode(text))


@dataclass
class TokenReport:
    """Token usage statistics comparing input and output."""

    input_tokens: int
    output_tokens: int

    @property
    def savings_tokens(self) -> int:
        """Tokens saved by compression."""
        return self.input_tokens - self.output_tokens

    @property
    def savings_pct(self) -> float:
        """Percentage of tokens saved."""
        if self.input_tokens == 0:
            return 0.0
        return (self.savings_tokens / self.input_tokens) * 100


def create_report(input_text: str, output_text: str, encoding: str = "cl100k_base") -> TokenReport:
    """Create a token report comparing input and output text."""
    return TokenReport(
        input_tokens=count_tokens(input_text, encoding),
        output_tokens=count_tokens(output_text, encoding),
    )


def format_report(report: TokenReport) -> str:
    """Format a token report for CLI display."""
    return (
        f"Tokens: {report.input_tokens} → {report.output_tokens} "
        f"(saved {report.savings_tokens}, {report.savings_pct:.1f}%)"
    )
