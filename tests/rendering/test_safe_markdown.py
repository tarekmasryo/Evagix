from __future__ import annotations

from html import unescape
from urllib.parse import urlsplit

import pytest

from evagix.reports import safe_markdown


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            "<img src=x> @person [link](https://example.invalid)",
            "` <img src=x> @person [link](https://example.invalid) `",
        ),
        ("`` `", "``` `` ` ```"),
        ("عربي\n\r\t\x1b\u202e\ud800\u2028", "` عربي\\n\\r\\t\\u001b\\u202e\\ud800\\u2028 `"),
        ("", "`  `"),
    ],
)
def test_code_span_keeps_markup_and_controls_literal(value: str, expected: str) -> None:
    assert safe_markdown.markdown_code(value) == expected


def test_redaction_happens_before_markdown_encoding() -> None:
    secret = "ghp_" + "b" * 36
    assert secret not in safe_markdown.markdown_code(secret)
    assert "[REDACTED]" in safe_markdown.markdown_code(secret)
    url = f"https://example.invalid/log?token={secret}"
    output = safe_markdown.markdown_details(url)
    assert secret not in output
    assert "[REDACTED]" in output and not output.startswith("[Details]")


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://example.invalid/log",
        "https://user:password@example.invalid/",
        "https://example.invalid:444/log",
        "https://[broken",
        "https://example.invalid/\n![pixel](https://example.invalid)",
        "https://example.invalid/\u202e",
        "https://example.invalid/" + "x" * 2048,
    ],
)
def test_unsafe_detail_urls_are_not_markdown_links(url: str) -> None:
    assert not safe_markdown.markdown_details(url).startswith("[Details]")


def test_https_link_encodes_markdown_and_html_delimiters() -> None:
    value = 'https://example.invalid/log(foo)"<bar>\\`'
    assert safe_markdown.markdown_details(value) == (
        "[Details](<https://example.invalid/log%28foo%29%22%3Cbar%3E%5C%60>)"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://user&colon;password&commat;example.invalid/",
        "https://example.invalid/log?a=1&copy;=2&b=3",
        "https://example.invalid/log?a=&amp;value",
    ],
)
def test_commonmark_entity_decoding_does_not_change_detail_destination(url: str) -> None:
    output = safe_markdown.markdown_details(url)
    assert output.startswith("[Details](<") and output.endswith(">)")
    destination = unescape(output[len("[Details](<") : -2])
    assert destination == url
    assert urlsplit(destination).username is None


def test_budget_counts_utf8_bytes_without_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safe_markdown, "_MAX_MARKDOWN_BYTES", 4)
    assert safe_markdown.bounded_markdown("أب") == "أب"
    with pytest.raises(ValueError, match="4-byte output limit"):
        safe_markdown.bounded_markdown("أبج")
