# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses `uv` for Python package management.

```bash
# Install dependencies
uv pip install -e ".[test]"

# Run the CLI
uv run codereview --help

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_foo.py::TestClass::test_method -v

# Run scanners via bash script
bash scripts/bash/run-scanners.sh <target_dir> <output_dir>
```

## Architecture

This project has two distinct layers:

### 1. Python CLI (`src/review_cli/__init__.py`)
A single-file Typer app that implements all `codereview` subcommands:
- `init` — creates `.review/config.yaml`
- `scan` — runs language-specific scanners, saves to `.review/scanner-results/aggregated-<timestamp>.json`
- `review` — full pipeline: scan → analyze → report → interactive fix
- `pr <owner/repo> <number>` — fetches PR comments via GitHub/GitLab/Gitee APIs, runs interactive fix/reply workflow
- `reply` — sends queued replies from `.review/results/pr-*-replies-*.json`
- `auth` — stores tokens in `.review/auth.yaml` (gitignored)

Auth resolution order: env vars (`GITHUB_TOKEN`, `GITLAB_TOKEN`, `GITEE_TOKEN`) → `.review/auth.yaml`.

### 2. AI Skill System (`languages/go/`)
The `languages/go/SKILL.md` is a Claude Code skill that orchestrates a three-tier Go code review:

- **Tier 1** (`tools/run-go-tools.sh`): `go build` → `go vet` → `staticcheck` → `gocognit`. Takes Go file paths on stdin, outputs JSON to stdout. Must run from project root (where `go.mod` lives).
- **Tier 2** (`tools/scan-rules.sh`): Scans files against 38 regex rules in `rules/*.yaml` (SAFE-001–010, DATA-001–010, QUAL-001–010, OBS-001–008). Takes file paths on stdin, outputs `{"hits":[...],"summary":{...}}`.
- **Tier 3**: 7 parallel AI agents (`agents/safety.md`, `data.md`, `design.md`, `quality.md`, `observability.md`, `business.md`, `naming.md`).

The skill aggregates all tiers and outputs a Chinese-language review report to `code_review.result`.

### Command Templates (`templates/commands/`)
Markdown files that define slash commands for AI assistants (e.g., `/codereview.review`). These are workflow specifications, not code — they describe steps the AI should follow.

## Key Conventions

- **Output language**: Default Chinese (zh-CN) for review reports
- **Severity levels**: P0 (must fix), P1 (should fix), P2 (suggested)
- **Review results** are saved to `.review/results/` (gitignored); scanner results go to `.review/scanner-results/` (not gitignored)
- **YAML rules** format: each rule has `id`, `severity`, `pattern.match` (regex), and `message`
- The `_run_typescript_scanners` function signature at `src/review_cli/__init__.py:819` is missing the `auto_install` parameter that Go/Python equivalents have — this is a known inconsistency

## Go Tool Installation

Optional tools auto-installed by the CLI when `--install` is set (default on):
```bash
go install honnef.co/go/tools/cmd/staticcheck@latest
go install github.com/securego/gosec/v2/cmd/gosec@latest
go install github.com/uudashr/gocognit/cmd/gocognit@latest
go install github.com/gordonklaus/ineffassign@latest
```
