# Changelog

All notable user-facing changes to Evagix are documented here.

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

[0.1.1]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.1
[0.1.0]: https://github.com/tarekmasryo/Evagix/releases/tag/v0.1.0
