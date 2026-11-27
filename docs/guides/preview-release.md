# Preview release: 0.2.0a1

`0.2.0a1` is the first alpha for the new check-evidence and change-review
features. It is prepared for local evaluation and has not been published to
PyPI or tagged. The stable release remains `0.1.2`.

## What is included

| Capability | What the report establishes |
| --- | --- |
| `verify-check` | Whether a selected GitHub Actions push job reports success for the requested repository, revision, run, and attempt. It does not prove checkout or test provenance. |
| `pr-checks` | Observed head and available test-merge check outcomes, with optional comparison against caller-supplied expectations. It does not discover required-check policy or approve merging. |
| `changed --references` | Supported local Markdown links in root `README.md` and `AGENTS.md` whose tracked file targets disappeared since the merge base. |
| `changed --scripts` | Supported literal script instructions in those same documents whose targets were removed or renamed. Commands are interpreted relative to the repository root. |
| `evagix.pr_summary` | An advisory Markdown summary of checks, deleted-file links, and deleted-script instructions for matching immutable revisions. No expectations file is required. |

The preview also includes the default-context safety checks, command analysis
fixes, and scan-discovery optimization described in the
[changelog](https://github.com/tarekmasryo/Evagix/blob/main/CHANGELOG.md).
Existing readiness, generated-context, and README-audit commands remain available.

## Install the local wheel

Use a separate environment so evaluation does not replace a working stable
installation. Maintainers with the development build tools installed can build
the wheel and source distribution from this checkout:

```bash
python -m build --no-isolation --outdir dist/preview-0.2.0a1
```

The following installation uses only the local wheel and does not contact a
package index. Evagix still has no runtime dependencies.

Windows PowerShell:

```powershell
python -m venv .venv-preview
.\.venv-preview\Scripts\python.exe -m pip install --no-index --no-deps dist/preview-0.2.0a1/evagix-0.2.0a1-py3-none-any.whl
.\.venv-preview\Scripts\python.exe -I -m evagix --version
```

Linux or macOS:

```bash
python -m venv .venv-preview
./.venv-preview/bin/python -m pip install --no-index --no-deps dist/preview-0.2.0a1/evagix-0.2.0a1-py3-none-any.whl
./.venv-preview/bin/python -I -m evagix --version
```

Expected version: `evagix 0.2.0a1`. Use this environment's interpreter or
`evagix` executable for subsequent commands, rather than a global stable
installation. `-I -m evagix` also avoids importing the source checkout in place
of the installed package.

## Try the reports

The offline deletion checks inspect committed Git snapshots. Choose the actual
base branch and committed head you want to compare; uncommitted changes are not
included.

```bash
evagix changed . --references --base main --head HEAD
evagix changed . --scripts --base main --head HEAD
```

See the supported [Markdown links](deleted-references.md) and
[script instructions](deleted-scripts.md). These reports do not search every
document or infer replacement paths.

For optional live GitHub.com metadata, use
[PR check collection](pull-request-checks.md) or
[selected-check verification](github-check-collection.md). Network access is
limited to those explicit collectors; local scans remain offline. The
[combined summary recipe](pr-review-summary.md) explains the additional Git
snapshot and revision-matching requirements.

## Upgrade from 0.1.2

- Default `doctor` now checks dangerous commands, prompt-injection indicators,
  and incomplete reads in discovered and configured agent-context files.
  Previously passing repositories may show additional findings, lower scores,
  or fail an existing threshold. Review the findings before changing CI policy.
  `--strict` still enables its additional checks.
- Existing CLI flag meanings, exit-code values, stable JSON schemas, and
  generated-context formats are preserved. `check` still checks generated
  context freshness; it is not a new work-verification command.
- New evidence and drift outputs have separate
  [preview schemas](../schemas.md#preview-evidence-contracts). Pin the preview
  version in consumers; a packaged schema does not make a preview API stable.
- For `pr-checks`, both deletion modes, and the combined summary, exit `0`
  means complete collection or inspection, even when findings are present.
  Exit `1` means incomplete data, and `2` means an input or operational error.
  These are advisory reports. `verify-check` instead uses `0` for supported
  provider-reported success and `1` for contradicted or unverified claims.
- Default scans do not execute repository commands, call model APIs, or upload
  repository files. The preview does not establish overall task completion,
  test quality, or merge readiness.

For rollback, keep using the separate stable environment. Evaluating these
reports does not migrate repository configuration or generated files.

## CI and installation pins

`init-ci` retains its existing defaults: the Git ref follows the installed
version, and PyPI mode uses that version unless overridden. For this unpublished
preview, `v0.2.0a1` and `evagix==0.2.0a1` are not yet available installation
sources. Do not deploy a generated workflow with those defaults yet.

For the existing readiness workflow, explicitly select the released package:

```bash
evagix init-ci . --install-mode pypi --package-version 0.1.2 --fail-under 85
```

That workflow uses the stable features only. To try the new advisory summary in
CI, follow its [separately pinned tool recipe](pr-review-summary.md): use a
reviewed full commit containing the feature, independently of the PR being
inspected. The source checkout's existing CI pin is unchanged by this preview
preparation.

Publication is a separate maintainer operation. The repository's
`release: published` workflow also handles GitHub prereleases and proceeds to
TestPyPI and PyPI after its gates. Preparing local artifacts does not require
creating a tag or a published GitHub release.
