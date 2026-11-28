from __future__ import annotations

from decimal import Decimal

import pytest

from evagix.scanning import coverage_thresholds as parser


def workflow(
    command: str, *, style: str | None = None, identity: str = "id: coverage", shell: str | None = None
) -> str:
    lines = [
        "name: Checks",
        "on: [push, pull_request]",
        "jobs:",
        "  tests:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        f"      - {identity}",
    ]
    if style is None:
        lines.append(f"        run: {command}")
    else:
        lines.append(f"        run: {style}")
        lines.extend(f"          {line}" for line in command.split("\n"))
    if shell is not None:
        lines.append(f"        shell: {shell}")
    return "\n".join(lines) + "\n"


def assert_unsupported(source: str) -> None:
    result = parser.extract_coverage_thresholds(source)
    assert result.thresholds == {}
    assert result.limitations


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("80", "80"),
        ("80.000", "80"),
        ("00080.5000", "80.5"),
        ("0", "0"),
        ("000.0000", "0"),
        ("100", "100"),
        ("100.000", "100"),
        ("0.00000000000000000000000000001", "0.00000000000000000000000000001"),
        ("80.00000000000000000000000000001", "80.00000000000000000000000000001"),
    ],
)
def test_literal_values_are_exact_and_canonical(literal: str, expected: str) -> None:
    result = parser.extract_coverage_thresholds(workflow(f"pytest --cov=evagix --cov-fail-under={literal}"))
    assert not result.limitations
    assert list(result.thresholds) == [("tests", "id", "coverage")]
    record = result.thresholds[("tests", "id", "coverage")]
    assert record.value == expected
    assert (record.job, record.step_kind, record.step) == ("tests", "id", "coverage")


@pytest.mark.parametrize("style", [None, "|", "|-", "|+"])
@pytest.mark.parametrize(
    "invocation", ["pytest", "python -m pytest", "python3 -m pytest", "python3.11 -m pytest", "python.exe -m pytest"]
)
def test_direct_invocations_keep_exact_source_locations(style: str | None, invocation: str) -> None:
    command = f"{invocation} -q --cov=evagix --cov-fail-under 80"
    if style:
        command = "# Test comment\n\n" + command + "\n"
    source = workflow(command, style=style)
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    record = result.thresholds[("tests", "id", "coverage")]
    expected_line, raw = next(
        (number, line) for number, line in enumerate(source.splitlines(), 1) if "--cov-fail-under" in line
    )
    assert (record.line, record.column) == (expected_line, raw.index("--cov-fail-under") + 1)
    assert raw[record.column - 1 :].startswith("--cov-fail-under 80")


def test_crlf_and_unicode_step_name_do_not_shift_locations() -> None:
    source = workflow("pytest --cov-fail-under=80", identity="name: Coverage Ω").replace("\n", "\r\n")
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    record = result.thresholds[("tests", "name", "Coverage Ω")]
    assert record.line == 8
    assert record.column == source.splitlines()[7].index("--cov-fail-under") + 1


def test_lower_equal_and_precise_values_have_the_same_command_signature() -> None:
    values = ["80", "80.000", "70", "80.00000000000000000000000000001"]
    records = [
        parser.extract_coverage_thresholds(workflow(f"pytest tests --cov-fail-under={value}")).thresholds[
            ("tests", "id", "coverage")
        ]
        for value in values
    ]
    assert len({record.signature for record in records}) == 1
    assert records[0].value == records[1].value
    assert Decimal(records[2].value) < Decimal(records[0].value) < Decimal(records[3].value)


def test_attached_and_separate_threshold_values_are_equivalent() -> None:
    results = [
        parser.extract_coverage_thresholds(workflow(f"pytest --cov=evagix --cov-fail-under{separator}80")).thresholds[
            ("tests", "id", "coverage")
        ]
        for separator in ["=", " "]
    ]
    assert results[0].signature == results[1].signature
    assert results[0].value == results[1].value == "80"


def test_step_reordering_and_label_changes_preserve_identities() -> None:
    prefix = "jobs:\n  tests:\n    steps:\n"
    first = "      - id: unit\n        name: Unit coverage\n        run: pytest tests/unit --cov-fail-under=80\n"
    second = "      - name: Integration coverage\n        run: pytest tests/integration --cov-fail-under=90\n"
    before = parser.extract_coverage_thresholds(prefix + first + second)
    after = parser.extract_coverage_thresholds(prefix + second + first.replace("Unit coverage", "Unit checks"))
    assert not before.limitations and not after.limitations
    assert (
        set(before.thresholds)
        == set(after.thresholds)
        == {("tests", "id", "unit"), ("tests", "name", "Integration coverage")}
    )
    for key in before.thresholds:
        assert before.thresholds[key].value == after.thresholds[key].value
        assert before.thresholds[key].signature == after.thresholds[key].signature
        assert before.thresholds[key].line != after.thresholds[key].line


def test_same_step_identity_in_different_jobs_is_unambiguous() -> None:
    source = "jobs:\n"
    for job, value in [("unit", 80), ("integration", 90)]:
        source += f"  {job}:\n    steps:\n      - id: coverage\n        run: pytest --cov-fail-under={value}\n"
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    assert {key: record.value for key, record in result.thresholds.items()} == {
        ("unit", "id", "coverage"): "80",
        ("integration", "id", "coverage"): "90",
    }


@pytest.mark.parametrize("identity", ["name: Coverage", "name: 'Coverage'", 'name: "Coverage"'])
def test_literal_names_can_identify_a_step(identity: str) -> None:
    result = parser.extract_coverage_thresholds(workflow("pytest --cov-fail-under=80", identity=identity))
    assert not result.limitations
    assert list(result.thresholds) == [("tests", "name", "Coverage")]


@pytest.mark.parametrize("identity", ["name: 'Coverage # tests'", 'name: "Coverage # tests"'])
def test_yaml_quoted_identity_preserves_an_embedded_hash(identity: str) -> None:
    result = parser.extract_coverage_thresholds(workflow("pytest --cov-fail-under=80", identity=identity))
    assert not result.limitations
    assert list(result.thresholds) == [("tests", "name", "Coverage # tests")]


def test_apostrophe_inside_plain_identity_does_not_hide_a_yaml_comment() -> None:
    source = workflow("pytest --cov-fail-under=80", identity="name: Team's coverage # documentation")
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    assert list(result.thresholds) == [("tests", "name", "Team's coverage")]


@pytest.mark.parametrize(
    "source",
    [
        "jobs:\n  tests:\n    steps:\n      - id: coverage\n        run: pytest --cov-fail-under=80\n  tests:\n    steps: []\n",
        workflow("pytest --cov-fail-under=80") + "jobs: {}\n",
        workflow("pytest --cov-fail-under=80").replace("        run:", "        id: replacement\n        run:"),
        workflow("pytest --cov-fail-under=80") + "        run: pytest --cov-fail-under=70\n",
        workflow("pytest --cov-fail-under=80") + "      - id: coverage\n        run: echo unrelated\n",
        workflow("pytest --cov-fail-under=80", identity="name: Coverage")
        + "      - name: Coverage\n        run: echo unrelated\n",
    ],
)
def test_duplicate_keys_and_identities_never_choose_a_declaration(source: str) -> None:
    assert_unsupported(source)


def test_name_fallback_must_be_unique_even_when_another_step_has_an_id() -> None:
    source = workflow("pytest --cov-fail-under=80", identity="name: Coverage")
    source += "      - id: other\n        name: Coverage\n        run: echo unrelated\n"
    assert_unsupported(source)


@pytest.mark.parametrize(
    "identity",
    [
        "name: ${{ matrix.target }}",
        "name: '${{ matrix.target }}'",
        'name: "${{ matrix.target }}"',
        "id: '${{ matrix.target }}'",
        "name: |\n          Coverage",
    ],
)
def test_dynamic_or_multiline_identities_are_not_comparison_keys(identity: str) -> None:
    assert_unsupported(workflow("pytest --cov-fail-under=80", identity=identity))


@pytest.mark.parametrize(
    "literal",
    ["-1", "+80", ".5", "80.", "1e2", "NaN", "Infinity", "101", "100.00000000000000000000000000001", "0" * 65, ""],
)
def test_threshold_values_outside_literal_percentage_subset_are_incomplete(literal: str) -> None:
    assert_unsupported(workflow(f"pytest --cov-fail-under={literal}"))


@pytest.mark.parametrize(
    "command",
    [
        "pytest --cov-fail-under",
        "pytest --cov-fail-under --cov=evagix",
        "pytest --cov-fail-under=80 --cov-fail-under=80",
        "pytest --cov-fail-under=80 --cov-fail-under 70",
        "pytest -- --cov-fail-under=80",
        "pytest --cov-fail-under=$MINIMUM",
        'pytest --cov-fail-under="$MINIMUM"',
        "pytest --cov-fail-under=${{ matrix.minimum }}",
        "pytest --cov-fail-under=80 --unknown-flag",
        "pytest --cov-fail-under=80 --cov=$PACKAGE",
        'pytest --cov-fail-under=80 --cov="$PACKAGE"',
        'pytest --override-ini="addopts=--cov-fail-under=80"',
        "echo pytest --cov-fail-under=80",
        "bash -c 'pytest --cov-fail-under=80'",
        "uv run pytest --cov-fail-under=80",
        "python -c 'pytest --cov-fail-under=80'",
        "MODE=test pytest --cov-fail-under=80",
        "pytest --cov-fail-under=80 && echo done",
        "pytest --cov-fail-under=80; pytest --cov-fail-under=70",
        "pytest --cov-fail-under=80 | tee output",
        "pytest --cov-fail-under=80 > output",
        'pytest --cov-fail-under="80',
    ],
)
def test_unsupported_commands_do_not_supply_threshold_evidence(command: str) -> None:
    assert_unsupported(workflow(command))


@pytest.mark.parametrize("arguments", ["*", "tests/test_*.py", "tests/test_?.py", "tests/test_[ab].py"])
def test_unquoted_globs_are_not_literal_arguments(arguments: str) -> None:
    assert_unsupported(workflow(f"pytest --cov-fail-under=80 {arguments}"))


@pytest.mark.parametrize("arguments", ['"tests/test_*.py"', "'tests/test_[ab].py'"])
def test_quoted_glob_characters_remain_literal_arguments(arguments: str) -> None:
    result = parser.extract_coverage_thresholds(workflow(f"pytest --cov-fail-under=80 {arguments}"))
    assert not result.limitations and len(result.thresholds) == 1


@pytest.mark.parametrize("option", ["--junitxml", "--junit-xml"])
@pytest.mark.parametrize("separator", ["=", " "])
def test_quoted_junit_environment_value_is_the_bounded_expansion_exception(option: str, separator: str) -> None:
    command = f'python -m pytest --cov-fail-under=80 {option}{separator}"$RUNNER_TEMP/results.xml"'
    result = parser.extract_coverage_thresholds(workflow(command))
    assert not result.limitations
    assert result.thresholds[("tests", "id", "coverage")].value == "80"


@pytest.mark.parametrize(
    "argument",
    [
        "$RUNNER_TEMP/results.xml",
        '"${RUNNER_TEMP}/results.xml"',
        '"$(get_path)/results.xml"',
        '"${{ runner.temp }}/results.xml"',
    ],
)
def test_other_junit_expansion_forms_remain_incomplete(argument: str) -> None:
    assert_unsupported(workflow(f"pytest --cov-fail-under=80 --junitxml={argument}"))


@pytest.mark.parametrize("shell", ["pwsh", "powershell"])
@pytest.mark.parametrize("executable", ['"pytest"', "'pytest'", '"python" -m pytest'])
def test_powershell_quoted_strings_are_not_direct_executable_invocations(shell: str, executable: str) -> None:
    assert_unsupported(workflow(f"{executable} --cov-fail-under=80", shell=shell))


@pytest.mark.parametrize("scope", ["workflow", "job"])
def test_inherited_unsupported_shell_does_not_create_evidence(scope: str) -> None:
    source = workflow("pytest --cov-fail-under=80")
    if scope == "workflow":
        source = "defaults:\n  run:\n    shell: python\n" + source
    else:
        source = source.replace("    steps:", "    defaults:\n      run:\n        shell: python\n    steps:")
    assert_unsupported(source)


def test_explicit_supported_shell_can_override_an_unsupported_default() -> None:
    source = "defaults:\n  run:\n    shell: python\n" + workflow("pytest --cov-fail-under=80", shell="bash")
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations and len(result.thresholds) == 1


@pytest.mark.parametrize(
    "command", ["pytest --cov-fail-under=80 # --cov-fail-under=70", "# not a cmd comment\npytest --cov-fail-under=80"]
)
def test_cmd_hash_tokens_are_not_shell_comments(command: str) -> None:
    assert_unsupported(workflow(command, style="|", shell="cmd"))


@pytest.mark.parametrize(
    "command",
    [
        "pytest --cov-fail-under=80\npytest --cov-fail-under=70",
        "echo setup\npytest --cov-fail-under=80",
        "cat <<'EOF'\npytest --cov-fail-under=80\nEOF",
        "if true; then\npytest --cov-fail-under=80\nfi",
        "pytest \\\n--cov-fail-under=80",
    ],
)
def test_multiline_executable_content_and_heredocs_are_incomplete(command: str) -> None:
    assert_unsupported(workflow(command, style="|"))


@pytest.mark.parametrize("style", [">", ">-", ">+", "|2", "|2-", "|-2"])
def test_unsupported_block_scalar_styles_are_explicit(style: str) -> None:
    assert_unsupported(workflow("pytest --cov-fail-under=80", style=style))


@pytest.mark.parametrize("quoted", ["'pytest --cov-fail-under=80'", '"pytest --cov-fail-under=80"'])
def test_quoted_run_scalars_are_explicitly_unsupported(quoted: str) -> None:
    assert_unsupported(workflow(quoted))


@pytest.mark.parametrize("style", [None, "|"])
def test_hash_comments_do_not_supply_extra_threshold_flags(style: str | None) -> None:
    result = parser.extract_coverage_thresholds(
        workflow("pytest --cov-fail-under=80 # --cov-fail-under=70", style=style, shell="bash")
    )
    assert not result.limitations
    assert result.thresholds[("tests", "id", "coverage")].value == "80"


def test_shell_quotes_inside_plain_yaml_do_not_protect_yaml_comments() -> None:
    source = workflow('pytest -k "test # comment" --cov-fail-under=80')
    result = parser.extract_coverage_thresholds(source)
    assert not result.thresholds


def test_yaml_comment_cannot_hide_an_unclosed_shell_quote_after_a_threshold() -> None:
    assert_unsupported(workflow('pytest --cov-fail-under=80 -k "test # comment"'))


def test_literal_run_block_preserves_hash_inside_a_shell_quoted_argument() -> None:
    source = workflow('pytest -k "test # comment" --cov-fail-under=80', style="|")
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    assert result.thresholds[("tests", "id", "coverage")].value == "80"


@pytest.mark.parametrize("command", ["pytest # --cov-fail-under=80", "# pytest --cov-fail-under=80"])
def test_thresholds_mentioned_only_in_comments_are_not_evidence(command: str) -> None:
    result = parser.extract_coverage_thresholds(workflow(command, style="|"))
    assert not result.thresholds


@pytest.mark.parametrize("style", ["|", ">", "|-"])
def test_workflow_like_text_inside_other_scalar_keeps_its_owner(style: str) -> None:
    source = (
        f"description: {style}\n"
        "  jobs:\n"
        "    fake:\n"
        "      steps:\n"
        "        - id: forged\n"
        "          run: pytest --cov-fail-under=1\n" + workflow("pytest --cov-fail-under=80")
    )
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    assert list(result.thresholds) == [("tests", "id", "coverage")]


def test_step_block_scalar_cannot_forge_a_neighboring_run() -> None:
    source = workflow("pytest --cov-fail-under=80")
    source += "      - name: Description\n        description: |\n          run: pytest --cov-fail-under=1\n"
    result = parser.extract_coverage_thresholds(source)
    assert not result.limitations
    assert list(result.thresholds) == [("tests", "id", "coverage")]


@pytest.mark.parametrize(
    "replacement",
    [
        "&coverage pytest --cov-fail-under=80",
        "*coverage",
        "!!str pytest --cov-fail-under=80",
        "[pytest, --cov-fail-under=80]",
    ],
)
def test_structural_indirection_does_not_supply_run_evidence(replacement: str) -> None:
    assert_unsupported(workflow(replacement))


def test_valid_step_survives_an_independent_unsupported_step() -> None:
    source = workflow("pytest --cov-fail-under=80")
    source += "      - id: unsupported\n        run: uv run pytest --cov-fail-under=90\n"
    result = parser.extract_coverage_thresholds(source)
    assert result.limitations
    assert list(result.thresholds) == [("tests", "id", "coverage")]


def test_parser_limits_do_not_leak_partial_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    source = workflow("pytest --cov-fail-under=80")
    monkeypatch.setattr(parser, "_NODE_LIMIT", len(source.splitlines()) - 1)
    assert_unsupported(source)


def test_deep_opaque_structure_exceeds_the_bounded_parser() -> None:
    nested = "extra:\n" + "\n".join("  " * index + "child:" for index in range(1, 36)) + "\n"
    assert_unsupported(nested + workflow("pytest --cov-fail-under=80"))


def test_binary_content_is_incomplete_and_never_echoed() -> None:
    source = workflow("pytest --cov-fail-under=80") + "private-token=synthetic-secret\x00\n"
    result = parser.extract_coverage_thresholds(source)
    assert not result.thresholds and result.limitations
    assert "synthetic-secret" not in " ".join(result.limitations)
