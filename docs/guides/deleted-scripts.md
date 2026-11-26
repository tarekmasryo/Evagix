# Find script instructions left behind by deletions

The development-version `changed --scripts` preview reviews supported script
commands in root `README.md` and `AGENTS.md` against committed Git snapshots.
It reports a literal target only when it was a regular tracked file at the merge
base and its path is absent at the head. A rename can therefore leave a finding
for the old path, without establishing which new path should replace it.

```bash
evagix changed . --scripts --base main --head HEAD
evagix changed . --scripts --base main --head HEAD --format json
evagix changed . --scripts --base main --head HEAD --format markdown
```

For example, a change removes `scripts/check.py` while `AGENTS.md` still contains:

```markdown
Run `python scripts/check.py`.
```

The report identifies the instruction's file, line, column, and removed target.
Updating the committed instruction to an existing replacement removes the finding.
Editing an uncommitted working file
does not affect the result.

This command is offline and advisory. It reads Git objects without executing
scripts, importing project code, fetching objects, or following filesystem links.
No fix is applied. The feature is not included in the published `0.1.2` release.

## Supported instructions

The initial extractor accepts these forms:

- A whole-line `Run` or `Execute` instruction with one inline code span,
  optionally preceded by a simple list marker and followed by a period. Its
  contiguous block must contain only supported instructions, separated from
  other prose by blank lines, headings, or fences. Wrapped negations, examples,
  mixed prose, and mixed lists are excluded, including a supported instruction
  adjacent to an unsupported sibling list item.
- A closed, top-level code fence labeled `bash`, `sh`, `shell`, `zsh`,
  `powershell`, `pwsh`, or `ps1`. Every nonblank, noncomment line must be a
  supported direct invocation. Mixed or ambiguous fences are excluded as a whole.

Supported direct invocations are:

| Form | Accepted interpreter options before the script |
| --- | --- |
| `python scripts/check.py`, `python3 scripts/check.py`, `python3.11 scripts/check.py` | `-B`, `-E`, `-I`, `-O`, `-OO`, `-s`, `-S`, `-u` |
| `sh scripts/check.sh`, `bash scripts/check.sh`, `zsh scripts/check.sh` | `-e`, `-u`, `-x`, `-n`, `-eu`, `-ue`, `-eux` |
| `node scripts/check.js` | None |
| `pwsh -File scripts/check.ps1`, `powershell -File scripts/check.ps1` | `-NoLogo`, `-NoProfile`, `-NonInteractive`, before the required `-File` |
| `./scripts/check` | Explicit local executable; no interpreter inferred |

Python, Node, and PowerShell executable names may end in `.exe`. Paths use
forward slashes and may contain literal quoted spaces. Leading `./` and
redundant `.` components are normalized; percent escapes are not URL-decoded.
The column points to the original script argument, including an opening quote.

## Scope and interpretation

**The working directory is assumed to be the repository root.** Prose that
changes that assumption is not understood. A finding proves removal of a
tracked target under that interpretation, not that the documented command was
previously executable or will fail at runtime. Review its context before editing.

- Only the two root documents are inspected, including documents unchanged by
  the PR. Nested instruction files and arbitrary prose are outside scope.
- Bare paths, Markdown links, unlabeled or non-shell fences, indented code,
  blockquotes, HTML, and unclosed fences are excluded.
- Shell chains, cwd changes, wrappers, module/eval execution, heredocs, variables,
  globs, redirections, parentheses, backslash escapes, quoted executable names,
  and multiline continuations are not interpreted. One such line excludes its
  whole fence, even if other lines look
  like direct invocations.
- Paths outside the root, `..` components, URLs, and dynamic paths are excluded.
  A non-directory Git entry in a target's ancestor path at the head makes that
  inspection incomplete; the tool does not resolve symlinks or submodules.
- An already missing target is not new deletion drift. A path still present at
  the head is not reported, regardless of its contents or file type.
- Unsupported syntax is outside the declared scope. Complete inspection does
  not mean every instruction was understood or that all commands are valid.
- Staged, unstaged, and untracked files are excluded. Base and head are resolved
  to immutable commits, and deletions are measured from their unique merge base.

Document reads are bounded to 500,000 bytes, command lines to 4,096 characters,
and targets to 2,048 characters. At most 1,000 findings are returned; an additional
eligible finding makes the report incomplete. Unreadable, oversized, invalid
UTF-8, binary, or nonregular documents also produce an incomplete report. Missing
Git objects or ambiguous history fail rather than falling back to another comparison.

## Outputs and compatibility

| Exit | Meaning |
| --- | --- |
| `0` | Inspection completed within the declared scope, with or without advisory findings. |
| `1` | Inspection is incomplete; review its reported limitations. |
| `2` | Invalid input, unavailable Git data, operational failure, or oversized Markdown output. |

Formats are `text`, `json`, `markdown`, and `github-annotations`.
JSON uses the separate `script-drift.schema.json` preview contract.
Findings use `context.deleted-script-reference`, with advisory severity.
Outputs redact secrets; Markdown renders repository-derived values literally and
rejects oversized output instead of silently truncating it.

`--scripts` and `--references` are mutually exclusive. The existing
`changed`, `changed --references`, and `pr-risk` report contracts and exit
codes are unchanged. The automatic PR-summary workflow is also unchanged; this
preview is explicitly invoked through `changed --scripts`.
