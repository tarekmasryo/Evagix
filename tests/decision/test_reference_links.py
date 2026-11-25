from __future__ import annotations

import pytest

from evagix.reference_links import LocalLink, extract_local_links


def test_explicit_links_preserve_source_positions_and_order() -> None:
    text = '# Project\nSee [script](./scripts/test.sh#usage) and ![diagram](docs/map.png "Map").\n'
    assert extract_local_links(text) == [
        LocalLink("scripts/test.sh", 2, 14),
        LocalLink("docs/map.png", 2, 54),
    ]


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        ("docs/a.md", "docs/a.md"),
        ("./docs/../run.py", "run.py"),
        ("<docs/my file.md>", "docs/my file.md"),
        ("docs/my%20file.md", "docs/my file.md"),
        ("docs/%D9%85%D9%84%D9%81.md", "docs/ملف.md"),
        ("docs/ملف.md#عنوان", "docs/ملف.md"),
        ("docs/a%23b.md", "docs/a#b.md"),
        ("docs/a%2520b.md", "docs/a%20b.md"),
        ('docs/a.md "Documentation"', "docs/a.md"),
        ("docs/a.md 'Documentation'", "docs/a.md"),
    ],
)
def test_supported_local_destinations(destination: str, expected: str) -> None:
    links = extract_local_links(f"[reference]({destination})")
    assert len(links) == 1
    assert links[0].target == expected


@pytest.mark.parametrize(
    "destination",
    [
        "https://example.org/file.md",
        "mailto:person@example.org",
        "#heading",
        "",
        "/absolute.md",
        "//example.org/file.md",
        "../outside.md",
        "docs/../../outside.md",
        "%2fetc/passwd",
        "~/secret",
        "C:/file.md",
        "docs\\file.md",
        "docs/*.md",
        "docs/{name}.md",
        "docs/$NAME.md",
        "file.md?raw=1",
        "file.md%3fquery",
        "docs/%00secret",
        "docs/%ff.md",
        "docs/%xy.md",
        "docs/%2.md",
        "docs/",
        "docs/.",
        "docs/sub/..",
        "< file.md>",
        "docs/\u202efile.md",
        "docs/[name].md",
        "<docs/<name>.md>",
    ],
)
def test_nonlocal_ambiguous_or_invalid_destinations_are_not_claims(destination: str) -> None:
    assert extract_local_links(f"[reference]({destination})") == []


@pytest.mark.parametrize(
    "text",
    [
        "```md\n[example](missing.md)\n```\n",
        "~~~md\n[example](missing.md)\n~~~~\n",
        "````md\n```\n[example](missing.md)\n````\n",
        "```md\n[example](missing.md)\n",
        "    [example](missing.md)\n",
        "\t[example](missing.md)\n",
        "> [quoted](missing.md)\n",
        "<!-- [hidden](missing.md) -->",
        "<!-- multi\n[hidden](missing.md)\n-->",
        "<!-- never closed\n[hidden](missing.md)",
        '<pre class="example">\n[example](missing.md)\n</pre>',
        "<code>[example](missing.md)</code>",
        "<SCRIPT>\n[example](missing.md)\n</SCRIPT>",
        "`[example](missing.md)`",
        "``a ` [example](missing.md)``",
        "`multi\n[example](missing.md)\nline`",
        r"\[escaped](missing.md)",
        "`missing.md` and missing.md",
        "[reference][target]\n[target]: missing.md",
    ],
)
def test_examples_comments_quotes_and_unsupported_forms_are_excluded(text: str) -> None:
    assert extract_local_links(text) == []


def test_masking_preserves_line_and_column_after_hidden_sections() -> None:
    text = "<!-- [hidden](old.py) --> [live](new.py)\r\n```\r\n[x](old.py)\r\n```\r\n[live](last.py)"
    assert extract_local_links(text) == [LocalLink("new.py", 1, 34), LocalLink("last.py", 5, 8)]


def test_nonmatching_fence_markers_do_not_end_code_block() -> None:
    assert extract_local_links("```md\n~~~\n[x](old.py)\n``` trailing\n[x](old.py)\n```\n[x](live.py)") == [
        LocalLink("live.py", 7, 5)
    ]


def test_unclosed_inline_backticks_do_not_hide_live_markdown_links() -> None:
    assert extract_local_links("unclosed ` followed by [x](live.py)")[0].target == "live.py"


def test_oversized_destination_is_ignored() -> None:
    assert extract_local_links("[x](" + "a" * 2049 + ")") == []


@pytest.mark.parametrize("separator", ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_non_markdown_separators_inside_masked_comments_do_not_change_line_count(separator: str) -> None:
    assert extract_local_links(f"<!-- hidden{separator}comment -->\n[live](old.py)\n") == [LocalLink("old.py", 2, 8)]


@pytest.mark.parametrize("separator", ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"])
def test_non_markdown_separators_preserve_original_line_and_column(separator: str) -> None:
    assert extract_local_links(f"alpha{separator}[live](old.py)\n") == [LocalLink("old.py", 1, 14)]


@pytest.mark.parametrize("newline", ["\r", "\n", "\r\n"])
def test_markdown_line_endings_are_counted_once(newline: str) -> None:
    assert extract_local_links(f"first{newline}[live](old.py){newline}") == [LocalLink("old.py", 2, 8)]


def test_lazy_quote_continuations_are_excluded_until_blank_line() -> None:
    text = "> example:\n[quoted](old.py)\nmore [quoted](old.py)\n\n[live](live.py)\n"
    assert extract_local_links(text) == [LocalLink("live.py", 5, 8)]


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "%E2%80%A8", "%E2%80%A9"])
def test_path_line_separators_are_not_safe_display_paths(separator: str) -> None:
    assert extract_local_links(f"[reference](<docs/a{separator}b.md>)") == []


@pytest.mark.parametrize(
    "text",
    [
        "<div>\n[example](old.py)\n</div>\n",
        "<table>\n<tr><td>[example](old.py)</td></tr>\n</table>\n",
        "<DIV>\n[example](old.py)\n</DIV>\n",
        "<custom-widget>\n[example](old.py)\n</custom-widget>\n",
    ],
)
def test_raw_html_blocks_are_excluded_until_blank_line(text: str) -> None:
    assert extract_local_links(text + "\n[live](live.py)\n") == [LocalLink("live.py", text.count("\n") + 2, 8)]


def test_inline_html_does_not_hide_markdown_links() -> None:
    text = "<span>Text</span> [live](live.py)\n"
    assert extract_local_links(text) == [LocalLink("live.py", 1, 26)]


def test_large_malformed_markup_preserves_following_link() -> None:
    text = "[" * 500_000 + "\n<span" + " " * 500_000 + "\n[live](live.py)\n"
    assert extract_local_links(text) == [LocalLink("live.py", 3, 8)]
