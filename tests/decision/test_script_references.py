from __future__ import annotations

import pytest

from evagix.reference_links import LocalLink
from evagix.script_references import extract_script_references


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_script_commands_keep_literal_targets_and_source_locations(newline: str) -> None:
    text = newline.join(
        [
            "# Project",
            'Run `python "scripts/check old.py" --quiet`.',
            "```bash",
            "python3 -I ./scripts/check.py",
            "bash scripts/check.sh",
            "./scripts/check",
            "```",
        ]
    )
    assert extract_script_references(text) == [
        LocalLink("scripts/check old.py", 2, 13),
        LocalLink("scripts/check.py", 4, 12),
        LocalLink("scripts/check.sh", 5, 6),
        LocalLink("scripts/check", 6, 1),
    ]


@pytest.mark.parametrize(
    "body",
    [
        "cd component\npython scripts/check.py",
        "python scripts/check.py\ncd component",
        "source setup.sh\npython scripts/check.py",
        "cat <<EOF\npython scripts/check.py\nEOF",
        "if false; then\npython scripts/check.py\nfi",
        "python -c 'print(1)'\npython scripts/check.py",
        "python scripts/check.py && echo done",
        "python scripts/check.py | tee output",
        "python scripts/check.py \\\n  --quiet",
    ],
)
def test_ambiguous_fence_is_excluded_as_a_whole(body: str) -> None:
    assert extract_script_references(f"```sh\n{body}\n```\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "Do not run `python scripts/check.py`.",
        "For example, run `python scripts/check.py`.",
        "The old command was `python scripts/check.py`.",
        "```python\npython scripts/check.py\n```",
        "```\npython scripts/check.py\n```",
        "```bash\npython scripts/check.py\n",
        "<!--\nRun `python scripts/check.py`.\n-->",
        "> Run `python scripts/check.py`.\nRun `python scripts/check.py`.",
        "<pre>\nRun `python scripts/check.py`.\n</pre>",
        "    Run `python scripts/check.py`.",
        "````markdown\n```sh\npython scripts/check.py\n```\n````",
    ],
)
def test_examples_negations_and_unsupported_markdown_are_excluded(text: str) -> None:
    assert extract_script_references(text) == []


@pytest.mark.parametrize(
    "command",
    [
        "python -m scripts.check",
        "python -c scripts/check.py",
        "python ../scripts/check.py",
        "python link/../scripts/check.py",
        "python /scripts/check.py",
        "python ~/scripts/check.py",
        "python $ROOT/scripts/check.py",
        "python scripts/*.py",
        "python scripts/check.py; echo done",
        'python "scripts/check.py"suffix',
        "python scripts\\check.py",
        "python https://example.invalid/check.py",
        "env python scripts/check.py",
        "sudo python scripts/check.py",
        "./python scripts/check.py",
        "node --eval scripts/check.js",
        "pwsh -Command scripts/check.ps1",
    ],
)
def test_dynamic_or_ambiguous_commands_do_not_become_script_claims(command: str) -> None:
    references = extract_script_references(f"Run `{command}`.")
    # An explicitly local executable is a reference to itself, not its argument.
    assert references == ([LocalLink("python", 1, 6)] if command.startswith("./python ") else [])


def test_percent_encoded_names_are_not_url_decoded() -> None:
    assert extract_script_references("Execute `python scripts/check%20old.py`.") == [
        LocalLink("scripts/check%20old.py", 1, 17)
    ]


@pytest.mark.parametrize(
    "command",
    [
        "python scripts/check.py (Set-Location subdir)",
        '"./scripts/check.ps1"',
        "'python' scripts/check.py",
        'python "scripts/check\told.py"',
        "python scripts/check\u202e.py",
        "python scripts/check\u2028.py",
        "python -",
        "python -- scripts/check.py",
        'python ""',
        "python scripts/../../check.py",
        "python scripts/check.py/.",
        "bash +e scripts/current.sh",
    ],
)
def test_expressions_and_control_characters_are_not_literal_invocations(command: str) -> None:
    assert extract_script_references(f"```powershell\n{command}\n```\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "``example\nRun `python scripts/check.py`.\n``",
        "- ``example\n  Run `python scripts/check.py`.\n  ``",
        "`example\nRun `python scripts/check.py`.\n`",
    ],
)
def test_multiline_inline_code_does_not_create_instructions(text: str) -> None:
    assert extract_script_references(text) == []


@pytest.mark.parametrize(
    ("command", "target"),
    [
        ("python.exe -B -u scripts/check.py", "scripts/check.py"),
        ("python3.11 scripts/check.py --quiet", "scripts/check.py"),
        ("sh -eu ./scripts/check.sh", "scripts/check.sh"),
        ("zsh -n scripts/check.sh", "scripts/check.sh"),
        ("node scripts/check.js", "scripts/check.js"),
        ("node.exe scripts/check.js", "scripts/check.js"),
        ("pwsh -NoProfile -File scripts/check.ps1", "scripts/check.ps1"),
        ("powershell.exe -NonInteractive -file scripts/check.ps1", "scripts/check.ps1"),
        ("python './scripts/check old.py'", "scripts/check old.py"),
        ("python scripts/./check.py", "scripts/check.py"),
    ],
)
def test_supported_interpreters_and_literal_options(command: str, target: str) -> None:
    result = extract_script_references(f"Run `{command}`.")
    assert len(result) == 1 and result[0].target == target


def test_comment_and_tilde_fence_keep_source_positions() -> None:
    text = "<!-- hidden\nRun `python scripts/hidden.py`.\n-->\n~~~sh\n# comment\npython scripts/check.py\n~~~\n"
    assert extract_script_references(text) == [LocalLink("scripts/check.py", 6, 8)]


def test_repeated_paths_keep_distinct_locations() -> None:
    text = "Run `python scripts/check.py`.\nRun `python scripts/check.py`.\n"
    assert extract_script_references(text) == [
        LocalLink("scripts/check.py", 1, 13),
        LocalLink("scripts/check.py", 2, 13),
    ]


def test_large_unsupported_command_does_not_hide_later_instruction() -> None:
    text = "Run `python scripts/" + "x" * 5000 + ".py`.\n\nRun `python scripts/check.py`.\n"
    assert extract_script_references(text) == [LocalLink("scripts/check.py", 3, 13)]


@pytest.mark.parametrize(
    "text",
    [
        "Do not\nRun `python scripts/check.py`.",
        "Run `python scripts/check.py`.\nThis is an example of an obsolete command.",
        "Run `cd subdir`.\nRun `python scripts/check.py`.",
        "- Do not\n  Run `python scripts/check.py`.",
        "For example:\nRun `python scripts/check.py`.",
        "- Prepare the environment.\n- Run `python scripts/check.py`.",
        "1. Run `python scripts/check.py`.\n2. Review the output.",
    ],
)
def test_mixed_paragraphs_do_not_create_inline_instructions(text: str) -> None:
    assert extract_script_references(text) == []
