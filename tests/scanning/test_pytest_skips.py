from __future__ import annotations

import pytest

from evagix.scanning import pytest_skips
from evagix.scanning.pytest_skips import SkipDeclaration, extract_test_declarations
from evagix.scanning.pytest_skips import TestDeclaration as Declaration


@pytest.mark.parametrize(
    "marker",
    [
        "pytest.mark.skip",
        "pytest.mark.skip()",
        'pytest.mark.skip("pending")',
        'pytest.mark.skip(reason="pending")',
    ],
)
def test_literal_decorator_records_its_location_without_running_source(marker: str) -> None:
    source = f"import pytest\nraise AssertionError('must not execute')\n@{marker}\ndef test_example():\n    pass\n"
    assert extract_test_declarations(source) == {"test_example": Declaration(4, SkipDeclaration(3, 2, "test"))}


@pytest.mark.parametrize("assignment", ["pytestmark =", "pytestmark: object ="])
@pytest.mark.parametrize(
    "value",
    [
        "pytest.mark.skip",
        '[pytest.mark.skip(reason="pending")]',
        '(pytest.mark.skipif(False, reason="conditional"), pytest.mark.skip)',
    ],
)
def test_module_marker_applies_to_existing_candidate_declarations(assignment: str, value: str) -> None:
    source = (
        f"import pytest\n{assignment} {value}\n"
        "def test_first():\n    pass\n"
        "class TestGroup:\n    async def test_second(self):\n        pass\n"
    )
    declarations = extract_test_declarations(source)
    assert set(declarations) == {"test_first", "TestGroup.test_second"}
    assert declarations["test_first"].skip is not None
    assert declarations["test_first"].skip == declarations["TestGroup.test_second"].skip
    assert declarations["test_first"].skip.scope == "module"
    assert declarations["test_first"].skip.line == 2


@pytest.mark.parametrize(
    ("source", "position"),
    [
        (
            "import pytest\n@pytest.mark.skip\nclass TestGroup:\n    def test_example(self):\n        pass\n",
            SkipDeclaration(2, 2, "class"),
        ),
        (
            "import pytest\nclass TestGroup:\n    pytestmark = pytest.mark.skip\n"
            "    def test_example(self):\n        pass\n",
            SkipDeclaration(3, 18, "class"),
        ),
        (
            "import pytest\nclass TestGroup:\n    @pytest.mark.skip\n    def test_example(self):\n        pass\n",
            SkipDeclaration(3, 6, "test"),
        ),
    ],
)
def test_class_and_method_markers_have_distinct_scopes(source: str, position: SkipDeclaration) -> None:
    declarations = extract_test_declarations(source)
    assert list(declarations) == ["TestGroup.test_example"]
    assert declarations["TestGroup.test_example"].skip == position


def test_inherited_marker_is_reported_once_per_candidate() -> None:
    source = (
        "import pytest\npytestmark = pytest.mark.skip\n"
        "@pytest.mark.skip\nclass TestGroup:\n    pytestmark = pytest.mark.skip\n"
        "    @pytest.mark.skip\n    def test_example(self):\n        pass\n"
    )
    assert extract_test_declarations(source) == {
        "TestGroup.test_example": Declaration(7, SkipDeclaration(2, 14, "module"))
    }


@pytest.mark.parametrize(
    "marker",
    [
        'pytest.mark.skipif(True, reason="conditional")',
        'pytest.mark.skipif(False, reason="conditional")',
        'pytest.mark.skipif(sys.platform == "win32", reason="conditional")',
        'unittest.skip("pending")',
    ],
)
def test_conditional_and_other_decorators_do_not_become_unconditional_markers(marker: str) -> None:
    source = f"import pytest\n@{marker}\ndef test_example():\n    pass\n"
    assert extract_test_declarations(source) == {"test_example": Declaration(3, None)}


@pytest.mark.parametrize(
    "marker",
    [
        "pytest.mark.skip(reason=get_reason())",
        "pytest.mark.skip(reason=reason)",
        'pytest.mark.skip(reason=f"pending {issue}")',
        "pytest.mark.skip(*args)",
        "pytest.mark.skip(**kwargs)",
        'pytest.mark.skip("one", "two")',
        'pytest.mark.skip("one", reason="two")',
        "pytest.mark.skip(condition=True)",
        "pytest.mark.skip(reason=None)",
    ],
)
def test_unsupported_direct_skip_arguments_are_unknown_rather_than_absent(marker: str) -> None:
    source = f"import pytest\n@{marker}\ndef test_example():\n    pass\n"
    with pytest.raises(ValueError, match="outside the supported literal syntax"):
        extract_test_declarations(source)


@pytest.mark.parametrize(
    "body",
    [
        "if flag:\n    pytest.skip('conditional')",
        "pytest.skip('runtime call')",
        "def helper():\n    pytest.skip('nested')",
        'note = "@pytest.mark.skip"',
        "# @pytest.mark.skip\npass",
    ],
)
def test_runtime_calls_comments_and_strings_are_not_declarations(body: str) -> None:
    indented = "\n".join("    " + line for line in body.splitlines())
    source = f"import pytest\ndef test_example():\n{indented}\n"
    assert extract_test_declarations(source) == {"test_example": Declaration(2, None)}


def test_conditional_definitions_assignments_and_nested_tests_are_outside_scope() -> None:
    source = (
        "import pytest\n"
        "if condition:\n    pytestmark = pytest.mark.skip\n"
        "    @pytest.mark.skip\n    def test_conditional():\n        pass\n"
        "def helper():\n    @pytest.mark.skip\n    def test_nested():\n        pass\n"
        "class Helper:\n    @pytest.mark.skip\n    def test_method(self):\n        pass\n"
        "class TestGroup:\n    if condition:\n        @pytest.mark.skip\n"
        "        def test_conditional(self):\n            pass\n"
        "    class TestNested:\n        def test_inner(self):\n            pass\n"
        "def test_visible():\n    pass\n"
    )
    declarations = extract_test_declarations(source)
    assert list(declarations) == ["test_visible"]
    assert declarations["test_visible"].skip is None


def test_unchanged_marker_remains_present_after_reason_and_line_changes() -> None:
    before = extract_test_declarations(
        'import pytest\n@pytest.mark.skip(reason="pending")\ndef test_example():\n    pass\n'
    )
    after = extract_test_declarations(
        'import pytest\n\n@pytest.mark.skip(reason="tracked elsewhere")\ndef test_example():\n    pass\n'
    )
    assert before["test_example"].skip == SkipDeclaration(2, 2, "test")
    assert after["test_example"].skip == SkipDeclaration(3, 2, "test")


@pytest.mark.parametrize(
    "binding",
    [
        "",
        "from another_library import pytest\n",
        "import pytest\npytest = replacement\n",
        "import pytest\ndel pytest\n",
        "import pytest\npytest.mark.skip = replacement\n",
        "import pytest\nfrom another_library import *\n",
        "import pytest\nfrom another_library import pytest\n",
        "import pytest\nimport pytest\n",
        "if condition:\n    import pytest\n",
        "import pytest\ndef helper(pytest):\n    pass\n",
        "import pytest\nclass pytest:\n    pass\n",
        "import pytest\ntry:\n    pass\nexcept Exception as pytest:\n    pass\n",
        "import pytest\nmatch value:\n    case pytest:\n        pass\n",
        "import pytest\nmatch value:\n    case {**pytest}:\n        pass\n",
    ],
)
def test_ambiguous_direct_pytest_bindings_fail_conservatively(binding: str) -> None:
    with pytest.raises(ValueError, match="pytest binding"):
        extract_test_declarations(binding + "@pytest.mark.skip\ndef test_example():\n    pass\n")


@pytest.mark.parametrize(
    "source",
    [
        "import pytest as pt\n@pt.mark.skip\ndef test_example():\n    pass\n",
        "from pytest import mark\n@mark.skip\ndef test_example():\n    pass\n",
    ],
)
def test_aliases_are_outside_supported_marker_scope(source: str) -> None:
    assert extract_test_declarations(source) == {"test_example": Declaration(3, None)}


def test_explicit_same_name_import_is_supported() -> None:
    source = "import pytest as pytest\n@pytest.mark.skip\ndef test_example():\n    pass\n"
    assert extract_test_declarations(source)["test_example"].skip == SkipDeclaration(2, 2, "test")


@pytest.mark.parametrize(
    "source",
    [
        "def test_same():\n    pass\ndef test_same():\n    pass\n",
        "class TestGroup:\n    def test_same(self):\n        pass\n    def test_same(self):\n        pass\n",
        "class TestGroup:\n    pass\nclass TestGroup:\n    pass\n",
    ],
)
def test_duplicate_declaration_names_do_not_silently_replace_evidence(source: str) -> None:
    with pytest.raises(ValueError, match="duplicate Python declarations"):
        extract_test_declarations(source)


def test_identical_method_names_in_different_classes_are_unambiguous() -> None:
    source = (
        "class TestFirst:\n    def test_same(self):\n        pass\n"
        "class TestSecond:\n    def test_same(self):\n        pass\n"
    )
    assert set(extract_test_declarations(source)) == {"TestFirst.test_same", "TestSecond.test_same"}


@pytest.mark.parametrize(
    "source",
    [
        "import pytest\npytestmark = pytest.mark.skip\npytestmark = []\ndef test_example():\n    pass\n",
        "import pytest\nclass TestGroup:\n    pytestmark = []\n    pytestmark = pytest.mark.skip\n"
        "    def test_example(self):\n        pass\n",
    ],
)
def test_repeated_scope_marker_assignments_are_ambiguous(source: str) -> None:
    with pytest.raises(ValueError, match="multiple pytestmark assignments"):
        extract_test_declarations(source)


@pytest.mark.parametrize(
    "mutation",
    [
        "del pytestmark",
        "if flag:\n    pytestmark = []",
        "pytestmark += []",
        "pytestmark[0] = replacement",
        "del pytestmark[0]",
        "pytestmark[:] = []",
        "pytestmark.clear()",
        "if flag:\n    pytestmark.append(replacement)",
    ],
)
@pytest.mark.parametrize("scope", ["module", "class"])
def test_scope_marker_mutations_do_not_support_an_unconditional_skip(mutation: str, scope: str) -> None:
    body = "pytestmark = [pytest.mark.skip]\n" + mutation + "\ndef test_example():\n    pass\n"
    if scope == "class":
        body = "class TestGroup:\n" + "\n".join("    " + line for line in body.splitlines()) + "\n"
    with pytest.raises(ValueError, match="unsupported rebinding or mutation"):
        extract_test_declarations("import pytest\n" + body)


@pytest.mark.parametrize(
    "binding",
    [
        "from helper import pytestmark",
        "from helper import marker as pytestmark",
        "import helper as pytestmark",
        "def pytestmark():\n    pass",
        "async def pytestmark():\n    pass",
        "class pytestmark:\n    pass",
        "try:\n    pass\nexcept Exception as pytestmark:\n    pass",
        "match value:\n    case pytestmark:\n        pass",
        "match value:\n    case [*pytestmark]:\n        pass",
        "match value:\n    case {**pytestmark}:\n        pass",
    ],
)
@pytest.mark.parametrize("scope", ["module", "class"])
def test_import_definition_and_pattern_bindings_invalidate_scope_marker(binding: str, scope: str) -> None:
    body = "pytestmark = pytest.mark.skip\n" + binding + "\ndef test_example():\n    pass\n"
    if scope == "class":
        body = "class TestGroup:\n" + "\n".join("    " + line for line in body.splitlines()) + "\n"
    with pytest.raises(ValueError, match="unsupported rebinding or mutation"):
        extract_test_declarations("import pytest\n" + body)


@pytest.mark.parametrize(
    "shadow",
    [
        "def helper():\n    pytestmark = []\n    del pytestmark\n",
        "async def helper():\n    pytestmark = []\n    pytestmark.clear()\n",
        "class Helper:\n    pytestmark = []\n    pytestmark.append(replacement)\n",
        "helper = lambda pytestmark: pytestmark.clear()\n",
    ],
)
def test_local_scope_shadowing_does_not_mutate_the_module_marker(shadow: str) -> None:
    source = "import pytest\npytestmark = pytest.mark.skip\n" + shadow + "def test_example():\n    pass\n"
    assert extract_test_declarations(source)["test_example"].skip == SkipDeclaration(2, 14, "module")


def test_method_local_shadowing_does_not_mutate_the_class_marker() -> None:
    source = (
        "import pytest\nclass TestGroup:\n    pytestmark = pytest.mark.skip\n"
        "    def helper(self):\n        pytestmark = []\n        del pytestmark\n"
        "    def test_example(self):\n        pass\n"
    )
    assert extract_test_declarations(source)["TestGroup.test_example"].skip == SkipDeclaration(3, 18, "class")


@pytest.mark.parametrize("annotation_first", [False, True])
def test_annotation_without_value_is_not_a_marker_reassignment(annotation_first: bool) -> None:
    lines = ["pytestmark = pytest.mark.skip", "pytestmark: object"]
    if annotation_first:
        lines.reverse()
    source = "import pytest\n" + "\n".join(lines) + "\ndef test_example():\n    pass\n"
    assert extract_test_declarations(source)["test_example"].skip == SkipDeclaration(
        3 if annotation_first else 2, 14, "module"
    )


@pytest.mark.parametrize("source", ["def test_broken(:\n", "\0", "def test_bad():\npass\n"])
def test_malformed_source_has_a_bounded_error(source: str) -> None:
    with pytest.raises(ValueError, match="cannot be safely parsed"):
        extract_test_declarations(source)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_unicode_positions_count_characters_and_normalize_newlines(newline: str) -> None:
    source = newline.join(
        [
            "import pytest",
            'note = "مثال"; pytestmark = pytest.mark.skip',
            "def test_example():",
            "    pass",
            "",
        ]
    )
    assert extract_test_declarations(source)["test_example"].skip == SkipDeclaration(2, 29, "module")


def test_syntax_node_budget_accepts_exact_limit_and_rejects_excess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pytest_skips, "_NODE_LIMIT", 2)
    assert extract_test_declarations("pass\n") == {}
    with pytest.raises(ValueError, match="inspection limit"):
        extract_test_declarations("pass\npass\n")
