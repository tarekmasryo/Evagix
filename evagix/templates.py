from __future__ import annotations

CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
SETUP_PYTHON_ACTION = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0"
CODEQL_UPLOAD_SARIF_ACTION = "github/codeql-action/upload-sarif@7211b7c8077ea37d8641b6271f6a365a22a5fbfa # v4.36.0"

EVAGIX_CONFIG_TEMPLATE = """# Evagix config

[targets]
universal_md = true
universal_json = true
agents = true
claude = false
gemini = false
cursor = false
copilot = false
windsurf = false
agent_brief = false
safety_policy = false
repo_map = false
agent_tasks = false
continue = false
cline = false
roo = false
aider = false
openhands = false
generic = false

# Optional custom outputs for internal agents or local LLM workflows.
# [[targets.custom]]
# name = "local_agent"
# path = ".evagix/local-agent.json"
# format = "json"
# include = ["facts", "commands", "risks", "policies", "repo_map"]

[profiles]
{profile_lines}

[policy]
fail_on_stale = true
fail_under = 85
# Keep false for lean public repos that generate onboarding reports on demand.
require_onboarding_pack = false
ignore_findings = []

# Optional severity overrides: info, warning, or error.
[severity]
# missing-ci = "error"

# Optional command overrides. Values here replace auto-detected commands with repo-specific truth.
[commands]
# install = "make install"
# test = "make test"
# lint = "make lint"
# typecheck = "make typecheck"
# smoke = "python -m scripts.smoke"

# Optional path ignores for scanner noise in archived/vendor areas.
[ignore]
paths = []
# paths = ["archive/", "vendor/", "examples/large/"]

# Optional README claim audit overrides. Use for repo-specific wording that Evagix cannot infer safely.
[readme_audit]
waive_claims = []
# waive_claims = ["enterprise-ready"]

[rules]
general = [
  "Keep changes scoped to the requested task.",
]
forbidden = []
"""

BASELINE_CONFIG_TEMPLATE = """# Baseline existing findings for staged adoption.
# Remove ignores as issues are fixed.

[profiles]
profiles = [{profiles}]

[policy]
fail_under = 85
require_onboarding_pack = false
ignore_findings = [{ignore_codes}]

[targets]
universal_md = true
universal_json = true
agents = true
claude = false
gemini = false
cursor = false
copilot = false
windsurf = false
"""

TYPECHECK_GUIDE_TEMPLATE = """# Typecheck Guide

Add an explicit typecheck command that matches this repository. Examples:

- Python: `mypy .` or `pyright`
- Frontend: `npm run typecheck`, `pnpm typecheck`, or `tsc --noEmit`

After adding it, run:

```bash
evagix compile .
evagix doctor .
```
"""

AI_EVAL_GUIDE_TEMPLATE = """# AI/Retrieval Evaluation Guide
# Replace these examples with deterministic project-specific validation commands.

[commands]
# eval = "python -m scripts.eval_ai_context"
# smoke = "python -m scripts.smoke"
"""


def evagix_ci_workflow(install_command: str, fail_under: int) -> str:
    return f"""name: Evagix Governance

on:
  pull_request:
    paths:
      - 'evagix.toml'
      - '.evagix/context.md'
      - '.evagix/context.json'
      - '.evagix/agent-brief.md'
      - '.evagix/safety-policy.md'
      - '.evagix/repo-map.md'
      - 'AGENTS.md'
      - 'CLAUDE.md'
      - 'GEMINI.md'
      - '.cursor/rules/**'
      - '.github/copilot-instructions.md'
      - '.windsurf/rules/**'
      - 'pyproject.toml'
      - 'requirements*.txt'
      - 'package.json'
      - '**/package.json'
      - '**/package-lock.json'
      - '**/pnpm-lock.yaml'
      - '**/yarn.lock'
      - '**/bun.lock*'
      - 'Makefile'
      - 'justfile'
      - 'Dockerfile'
      - '**/Dockerfile'
      - 'docker-compose*.yml'
      - 'compose*.yml'
      - '.github/workflows/**'
  push:
    branches: [main, master]

jobs:
  evagix-check:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: {CHECKOUT_ACTION}
      - uses: {SETUP_PYTHON_ACTION}
        with:
          python-version: '3.11'
      - name: Install Evagix
        run: {install_command}
      - name: Check generated Evagix files
        run: evagix check .
      - name: Enforce readiness score
        run: evagix doctor . --strict --fail-under {fail_under}
      - name: Strict safety gates
        run: |
          evagix readme-audit . --strict --fail-on unsupported
          evagix eval-context . --strict --fail-on high
      - name: Write SARIF report
        if: always()
        run: evagix report . --format sarif -o evagix.sarif --force
      - name: Upload SARIF report
        if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)
        uses: {CODEQL_UPLOAD_SARIF_ACTION}
        with:
          sarif_file: evagix.sarif
"""
