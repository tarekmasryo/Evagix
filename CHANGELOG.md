# Changelog

All notable user-facing changes to Evagix are documented here.

## [Unreleased]

### Added

- Preview `junit-github` command for associating an original local artifact ZIP with live GitHub run metadata. It compares the archive digest, run identity, expected provider revision and selected-attempt currentness; producing-attempt and tested-code provenance remain unknown. Existing offline JUnit and automatic PR-summary behavior are unchanged.
- Optional `--junit-report PATH` in the preview combined PR summary. Local pytest outcomes are displayed separately from GitHub evidence, with unverified source and unknown revision/run binding. Incomplete reports remain visible; JUnit reader errors fail before GitHub collection. Existing behavior without the option is unchanged.
- Preview `junit-report PATH` for local pytest JUnit XML, with reported case outcomes, separate marker counts, incomplete-data diagnostics and bounded XML parsing. Source verification and execution/revision binding remain unverified or unknown. Text and JSON omit logs and failure bodies; existing scans and reports are unchanged.

### Changed

- Include minimized `Quality gates` JUnit results in this repository's advisory PR summary. Only counters and outcome markers are transferred, with ordinal labels and one-day retention; missing, incomplete or stale transfers are explicit. The reviewed tool pin includes JUnit support. Test gates, public CLI contracts and unverified report semantics are unchanged.

### Fixed

- Keep JSON output parseable when final text redaction would consume string delimiters or insert literal newlines, including credential examples in test identifiers. The fallback redacts structured values before serializing; ordinary text and valid redacted JSON are unchanged.

## 0.2.0a1 (unreleased preview)

Prepared for local evaluation; not published. See the
[preview installation and upgrade guide](docs/guides/preview-release.md).

### Added

- Include deleted-script instruction findings in preview combined PR summaries, using the same immutable revisions as checks and deleted-file references. Findings remain advisory; incomplete script inspection makes the summary incomplete. Standalone report contracts are unchanged.
- Preview `changed --scripts` mode for literal script instructions left behind by committed deletions or renames. It reports source locations and incomplete inspection, declares its repository-root working-directory assumption, and excludes ambiguous shell contexts. Existing changed-file and Markdown-link behavior is unchanged.
- Run advisory PR summaries in this repository's CI after existing jobs finish, using an independently pinned tool and read-only permissions. Findings remain advisory; incomplete or unavailable reviews are visible job failures. Existing scan commands and release gates are unchanged.
- Advisory Markdown summaries for PR check inventories, expected-check comparisons, and deleted-file references. An optional CI helper combines reports for matching immutable revisions without requiring an expectations file, leaving required-check coverage unknown. Explicit expectations are still read only from the base commit; existing outputs and exit codes are unchanged.
- Optional `pr-checks --expectations` comparison against caller-supplied check names, producer IDs, kinds, and revision scopes. The advisory report distinguishes missing, pending, failed, and unverified expectations without changing default reports or collection exit codes.
- Preview `changed --references` mode for advisory detection of explicit local Markdown links in root `README.md` and `AGENTS.md` whose file targets were deleted between the merge base and committed head. It reports source locations and inspection completeness without changing existing changed-file risk gates or schemas.
- Preview `pr-checks <PR_URL>` report with no request file or manual execution IDs. It shows head and available test-merge check outcomes separately, keeps provider identity and detail links, and hides passed text rows by default. Collection status is separate from check success; required-check policy and merge readiness are not evaluated.
- Preview `verify-check` command and optional GitHub.com collector for an explicitly selected push job execution. Collection verifies the provider endpoint, attempt scope, pagination, and observed run stability; results describe provider-reported outcomes, not checkout/test provenance or merge approval. Existing scans stay offline, and no runtime dependency or existing report schema changes.
- Preview Python contract for verifying a specified check against supplied execution evidence and a separate caller assessment, with redacted results, a packaged schema, and a reproducible synthetic evaluation. It does not authenticate CI sources or change existing CLI behavior.

### Changed

- Update this repository's pinned advisory PR tool to include deleted-script instruction findings. Workflow permissions, isolation, and existing quality and release gates are unchanged.

### Fixed

- Detect deleted-file links in adjacent continuation lines of plain Markdown list paragraphs, preserving source locations and conservative code-example filtering.
- Inspect agent-context command safety, prompt-injection indicators, and incomplete reads in default `doctor`, including configured custom targets. Strict mode retains its additional checks without duplicating context safety findings.
- Detect supported `.env` reads with relative paths, options, multiple arguments, and PowerShell `Get-Content` / `gc`, including bare commands in agent instructions. Environment templates remain excluded.
- Filter nonmatching filenames before repository-boundary resolution during named-file and suffix discovery, while preserving traversal budgets and validation for returned files.

### Compatibility

- Default `doctor` can now report additional findings and lower scores. Existing thresholds and error-level findings still determine its exit status. Review CI expectations before upgrading; CLI flags, JSON schemas, and exit-code values are unchanged.

## [0.1.2]

### Fixed

- Redacted quoted CLI secrets and rejected unsafe multiline commands, shell wrappers, referenced scripts, and inline Make recipes.
- Aligned generated-context evaluation with integrity checks and configured custom targets.
- Corrected Python dependency-file risk classification and diagnosed malformed dependency metadata without crashes.
- Quoted generated command paths containing spaces and respected configured doctor thresholds in the pre-commit hook.
- Reported truncated configuration and oversized discovered files as incomplete.
- Kept custom context generation fresh on the first run and stable across repeated generation.
- Safely handled supported repository-derived paths in generated command arguments and rejected unsupported shell-sensitive path characters before publication.
- Reserved built-in and integrity output paths, rejected conflicting or duplicate custom targets, and validated all output paths before writing to prevent silent overwrites or partial generation from invalid configuration.

## [0.1.1]

Backward-compatible CLI presentation and terminal UX patch.

### Changed

- Improved hierarchy, spacing, alignment, and restrained semantic status styling for human-readable CLI output.
- Added TTY-aware ANSI styling with `--no-color` and `NO_COLOR`; non-TTY, redirected, piped, CI, and machine-readable output remains plain.
- Expanded regression coverage for terminal behavior and structured-output contracts.
- No runtime dependencies were added; rules, scoring, evidence, validation semantics, schemas, exit-code calculations, and machine-readable contracts remain unchanged.

## [0.1.0]

First public release.

### Added

- Local-first repository classification, readiness checks, and explainable findings.
- README claim auditing against static repository evidence.
- Agent-context discovery, safety analysis, scoring, and generated context exports.
- Generated-context ownership, fingerprint, integrity, drift, and tamper checks.
- CI workflow generation, changed-file risk analysis, and PR-oriented reports.
- JSON, Markdown, SARIF, annotation, and machine-readable report formats.
- Python, Node.js, GitHub Actions, container, infrastructure, and AI/ML repository evidence.
- Packaged JSON schemas for stable machine-readable outputs.

### Important behavior

- Scans are static and do not execute project commands, install dependencies, call model APIs, or upload repository content.
- Risky generated commands and unsafe output paths are rejected conservatively.
- Ambiguous evidence is reported for review rather than treated as verified truth.
- The package supports Python 3.11 through 3.14 and has no runtime dependencies.

[0.1.2]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.2
[0.1.1]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.1
[0.1.0]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.0
