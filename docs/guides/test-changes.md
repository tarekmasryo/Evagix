# Review test-file removals and added skip declarations

`changed --tests` is an offline, advisory preview for committed Python test
changes. It compares the unique merge base of the selected refs with the head.
This addition is under development after the prepared `0.2.0a1` preview; it is
not in the published `0.1.2` package.

```bash
evagix changed . --tests --base main --head HEAD
evagix changed . --tests --base main --head HEAD --format json
evagix changed . --tests --base main --head HEAD --format markdown
```

The report identifies:

- `tests.deleted-file`: a regular tracked Python test-file path at the merge
  base is absent at head, without a Git rename candidate. Its location belongs
  to the merge base. Test behavior may have moved elsewhere; this does not
  establish that coverage was lost.
- `tests.unconditional-skip-added`: an existing named test declaration gained a
  supported literal `pytest.mark.skip` marker. The report includes the head
  marker's line and character column and the previous declaration's location.

For example, adding the decorator below to an existing `test_payment` declaration
produces an advisory finding at the decorator:

```python
import pytest

@pytest.mark.skip(reason="Pending fixture repair")
def test_payment():
    assert payment_total() == 100
```

Review whether each change is intentional and whether relevant behavior is still
tested. These findings do not prove test collection, execution, test quality,
task completion, or merge readiness. Skip reasons and source snippets are not
included in output.

## Supported scope

File basenames must match `test_*.py` or `*_test.py`, case-sensitively. They are
candidate test files: custom pytest discovery settings, collection hooks,
plugins, ignored directories and `__test__` flags are not interpreted.

Within changed files, supported tests are direct module functions named `test_*`
and direct `test_*` methods of top-level `Test*` classes, including async
definitions. A test is compared by its qualified name within the same file or
a Git rename candidate. New files, new test names, renamed test functions,
nested classes/functions and conditionally defined tests are outside skip
comparison scope.

The initial extractor recognizes these
[pytest marker forms](https://docs.pytest.org/en/stable/how-to/skipping.html):

- `@pytest.mark.skip`, `@pytest.mark.skip()`, or the same decorator with one
  literal string reason, positional or `reason="..."`.
- Those markers on a supported class.
- A direct module/class `pytestmark` assignment containing one such marker, or
  a literal list/tuple containing it.

A direct, unaliased module-level `import pytest` is required for literal skip
markers. Obvious shadowing/rebinding, duplicate declarations, or mutations of a
supported `pytestmark` make the affected inspection incomplete. Marker
inheritance is compared before/after: an already marked test, a reason-only
change or removal of a marker is not a new finding. A direct skip with unsupported
arguments (including dynamic reasons) makes inspection incomplete instead of
being mistaken for an unmarked test. Multiple applicable markers
produce one finding per existing test, using the outermost supported marker.

`skipif` is excluded even for literal `True` conditions. Runtime `pytest.skip`
calls, `importorskip`, `xfail`, aliases, variable/decorator factories,
conditional marker assignments and arbitrary runtime mutation are not
interpreted. No Python source, pytest collection, project commands, Git filters
or hooks are executed. The analyzer uses the running Python interpreter's
parser; unsupported syntax is reported as incomplete.

## Renames and revisions

The report lists [Git rename candidates](https://git-scm.com/docs/git-diff#Documentation/git-diff.txt---find-renamesltngt)
separately, using an explicit 50% similarity threshold. A recognized test-file
rename does not produce a deletion finding. A rename with edits still undergoes
skip comparison when both names match the supported patterns. A move outside
those patterns is visible with an inspection limitation.

Git similarity is a heuristic, not proof of test identity. Large rewrites,
splits, merges or moves to existing files may appear as unmatched removed paths.
Inspect those changes before concluding that tests were removed. Exhaustive
rename detection is bounded to 200 candidates; exceeding the candidate budget
makes this limitation explicit.

Refs are resolved to immutable commits. Staged, unstaged and untracked changes
do not affect the report. An advanced base branch is compared through the merge
base. Missing history/objects and ambiguous merge bases are errors; the command
does not fetch or choose a different comparison silently.

## Limits and outputs

At most 200 changed candidate files and 1,000 findings are inspected/reported.
Each source read is limited to 500,000 bytes and each syntax tree to 50,000 nodes.
An additional eligible item beyond a budget makes inspection incomplete.
Malformed, unavailable, non-UTF-8, oversized or nonregular changed sources are
reported as limitations while other findings are preserved. Deletion evidence
uses Git tree metadata and does not need the removed source to parse.

| Exit | Meaning |
| --- | --- |
| `0` | Inspection completed within the declared scope, with or without findings. |
| `1` | Inspection incomplete; review the reported limitations. |
| `2` | Invalid input, unavailable Git metadata, operational error or oversized Markdown output. |

Formats are `text`, `json`, `markdown` and `github-annotations`. JSON uses the
separate `test-changes.schema.json` preview contract. Policy remains
`not_evaluated`. Outputs redact sensitive values and contain repository-derived
text. Redacted display identities must not be reused as raw evidence keys.
Deleted-file notices do not attach old-tree locations to head lines.

`--tests`, `--scripts` and `--references` are mutually exclusive. Existing
commands, schemas and exit codes are unchanged without the new option. This
mode is not yet included in the combined PR summary or automatic CI report.
