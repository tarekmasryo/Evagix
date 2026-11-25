# Find links broken by committed file deletions

The development-version `changed --references` preview checks explicit local
Markdown links in the repository-root `README.md` and `AGENTS.md`.

```bash
evagix changed . --references --base main --head HEAD
evagix changed . --references --base main --head HEAD --format json
evagix changed . --references --base main --head HEAD --format github-annotations
evagix changed . --references --base main --head HEAD --format markdown
```

For example, a PR deletes `scripts/test.sh` while `AGENTS.md` still contains
`[test script](scripts/test.sh)`. The report identifies the document, line,
column, and deleted target. Findings are advisory: they establish a broken local
file reference within the supported syntax, not whether instructions are
semantically correct or the PR should be blocked.

## Comparison and evidence

The command resolves `--base` and `--head` to immutable commits and compares their
merge base with the head. It reads documents and target files from Git objects;
staged, unstaged, and untracked working files are excluded. The report records
the resolved base, head, and merge-base revisions. Missing revisions, unrelated
histories, or ambiguous merge bases produce an error rather than a fallback
comparison.

A finding requires both evidence that the target was a regular tracked file at
the merge base and evidence that it is absent at the head. Existing broken links
are excluded. Renaming a file can leave its old path absent; a finding does not
prove which replacement path is appropriate. No automatic fix is applied.

## Scope and limitations

- Only root `README.md` and `AGENTS.md` are inspected, including documents not
  changed by the PR. Nested instructions and other documents are outside scope.
- The first preview supports explicit inline Markdown links, such as
  `[guide](docs/guide.md)`. Bare paths, code-span paths, shell commands, reference
  link definitions, URLs, and dynamic paths are not interpreted.
- Code fences and HTML comments are excluded. This is a conservative extractor,
  not a full Markdown parser or a natural-language instruction checker.
- Directories and nonregular Git entries are not ordinary file targets. The
  command does not follow filesystem links or read files outside the repository.
- Missing documents are inapplicable. Documents that cannot be safely inspected
  make the report incomplete; an empty findings list is not a clean result when
  `completeness` is `incomplete`.
- Document reads are limited to 500,000 bytes and findings to 1,000. Hitting an
  inspection limit is reported as incomplete. Git tree output is bounded to
  8 MB per snapshot; exceeding this bound is an operational error.
- The scan executes read-only Git inspection, never project test/build commands,
  and makes no network request. Secrets are redacted from report output.

## Output and exit status

| Exit | Meaning |
| --- | --- |
| `0` | Inspection completed for the declared scope, including reports with advisory findings. |
| `1` | Inspection is incomplete; review the reported limitations. |
| `2` | Invalid input or operational failure; the error is written to stderr. |

JSON follows the preview `reference-drift.schema.json` contract. GitHub
annotations use notices for findings and warnings for incomplete inspection,
not a merge gate. Do not treat exit `0` as a
claim that all repository references or task requirements are correct.

Without `--references`, `changed` retains its existing changed-file risk report,
schema, working-tree behavior, and exit codes. `pr-risk` is unchanged.

## Markdown summaries

`--format markdown` is supported only with `--references`; it is not a new
output format for the existing changed-file risk report. The summary records
base, head, merge base, inspected documents, completeness, finding locations,
limitations, and a suggested next action. Findings remain advisory.

Repository text is redacted and rendered as literal code, with control and
direction-formatting characters escaped. It cannot introduce active Markdown
images or HTML. Markdown output is limited to 450,000 UTF-8 bytes; exceeding
the limit returns exit `2` without partial stdout. Use JSON for the full report.

The [optional PR summary recipe](pr-review-summary.md) combines these findings
with observed checks or an explicit expected-check comparison for the same
immutable base/head revisions.
