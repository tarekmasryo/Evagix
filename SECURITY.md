# Security Policy

## Scope

Evagix is a local, static repository scanner and context-governance CLI. It is designed to be read-only by default:

- It does not call external model APIs.
- It does not send repository content over the network.
- It does not run project commands during scanning.
- It does not install project dependencies during scanning.
- It skips common secret-bearing files such as `.env` files and private-key formats during text scanning.
- It skips symlinked paths and rejects output paths that resolve outside the repository root.
- It centrally redacts common direct tokens, compound credential assignments, and credential-bearing mapping fields before findings, reports, generated context, terminal streams, or machine-readable output are emitted.


## Agent-command safety boundary

Commands that may be published to agent-facing context are normalized and inspected before generation. The checks cover destructive Bash, PowerShell, and CMD variants; remote-content-to-interpreter pipelines; shell wrappers; encoded PowerShell execution; literal credential arguments and credential-bearing environment assignments; supported package/task recipes; and referenced local shell scripts. Ambiguous or unsupported execution semantics are not treated as proof that a command is safe. Evagix never executes repository commands during this analysis.

Agent-context discovery uses one canonical registry across discovery, context evaluation, poisoning checks, and generated targets. Explicitly supported agent directories such as `.cursor/rules`, `.continue/rules`, `.roo/rules`, and `.openhands/skills` remain inside the safety scan even when their parent tool directories are ignored by general repository scans.

Any safety-critical read or traversal that reaches a configured bound produces an explicit incomplete-scan finding. A partial read is never reported as a complete safety verdict.

## Atomic-write permission policy

Atomic replacement preserves the existing POSIX permission bits of files that Evagix rewrites, including executable bits. New repository-managed context, configuration, and workflow files are created as `0644`; new report or output files that may contain repository-derived data default to owner-only `0600`. Windows retains its native permission behavior.

## Output redaction

Evagix treats repository text as untrusted. Before evidence leaves an output boundary, common direct tokens, compound credential assignments, credential-bearing mapping fields, nested structures, final CLI streams, and unexpected exception payloads are replaced with `[REDACTED]` across terminal, JSON, Markdown, SARIF, report, annotation, PR-comment, and generated-context outputs. The redaction layer is deterministic and idempotent so repeated rendering remains stable.

Redaction is defense in depth, not a substitute for secret management or a complete secret-scanning product. Do not intentionally store live credentials in repositories, examples, fixtures, or generated artifacts. Report any credential form that Evagix fails to redact as a security issue.

## Supported versions

Security fixes are accepted for the latest stable release line.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| < 0.1 | No |

## Reporting a vulnerability

Use GitHub Private Vulnerability Reporting for the public repository before publishing details. If that channel is temporarily unavailable, open a minimal public issue that contains no exploit, credential, or sensitive reproduction data and request a private maintainer contact. Include:

- the affected Evagix version,
- the command used,
- a minimal reproduction repository or file tree,
- expected versus actual behavior,
- whether the issue can read outside the repository, write outside the repository, or expose secrets.

Evagix treats path traversal, unsafe symlink handling, unintended command execution, and secret exposure as security issues.
