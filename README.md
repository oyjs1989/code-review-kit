# Code Review Kit

Structured code review workflow with multi-language support. Combines static analysis tools with AI agents to produce P0/P1/P2 severity-graded reports.

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

**Without cloning the repo:**
```bash
# Install into a virtual environment (recommended)
uv venv && source .venv/bin/activate
uv pip install git+https://github.com/oyjs1989/code-review-kit.git

# Or install into the system Python (may require sudo)
sudo uv pip install --system git+https://github.com/oyjs1989/code-review-kit.git
```

**From source:**
```bash
uv pip install -e ".[test]"
```

## Quick Start

```bash
# Initialize config in current project
codereview init --lang go

# Run full review (scan → analyze → report → interactive fix)
codereview review ./...
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `codereview init` | Create `.review/config.yaml` |
| `codereview scan` | Run static analysis tools, save to `.review/scanner-results/` |
| `codereview review` | Full pipeline: scan → analyze → report → interactive fix |
| `codereview pr <owner/repo> <number>` | Fetch PR comments, run fix/reply workflow |
| `codereview reply` | Send queued PR replies |
| `codereview auth` | Store platform tokens |

## PR Analysis

Fetch and triage code review comments from GitHub, GitLab, or Gitee:

```bash
# Scan first, then analyze PR comments
codereview scan
codereview pr owner/repo 123

# Send queued replies
codereview reply
```

For each comment, the workflow checks whether the issue was already caught by a scanner, then prompts you to fix or reply.

## Authentication

```bash
# Environment variable (recommended)
export GITHUB_TOKEN="ghp_xxxx"
export GITLAB_TOKEN="glpat-xxxx"
export GITEE_TOKEN="xxxx"

# Or store via CLI
codereview auth --platform github --token "ghp_xxxx"

# Self-hosted GitLab
codereview auth --platform gitlab --host "https://gitlab.company.com" --token "glpat-xxxx"
```

Required token scopes: GitHub (`repo`, `read:org`), GitLab (`api`), Gitee (`projects`, `pull_requests`).

## AI Skill System (Go)

For Go projects, a Claude Code skill runs a three-tier review:

- **Tier 1** — `go build`, `go vet`, `staticcheck`, `gocognit`
- **Tier 2** — 38 regex rules across safety, data, quality, and observability categories
- **Tier 3** — 7 parallel AI agents (safety, data, design, quality, observability, business, naming)

In Claude Code, use the slash commands:

```
/go-code-review:go-code-review-full   # All three tiers
/go-code-review:go-code-review-t1     # Tier 1 only (build tools)
/go-code-review:go-code-review-t2     # Tier 2 only (rule scanning)
/go-code-review:go-code-review-t3     # Tier 3 only (AI agents)
```

Go tools are auto-installed on first run (requires Go in PATH).

## Supported Languages

| Language | Status | Tools |
|----------|--------|-------|
| Go | Complete | go build, go vet, staticcheck, gosec, gocognit |
| Python | Planned | pylint, mypy, flake8, ruff, bandit |
| TypeScript | Planned | tsc, eslint |

## Severity Levels

- **P0** — Must fix (security, crashes, data loss)
- **P1** — Should fix (bugs, performance, maintainability)
- **P2** — Suggested (style, best practices)

Reports are output in Chinese (zh-CN) by default. Configurable via `.review/config.yaml`.

## Development

```bash
# Run tests
uv run pytest

# Run scanners directly
bash scripts/bash/run-scanners.sh <target_dir> <output_dir>
```
