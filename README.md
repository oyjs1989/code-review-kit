# Code Review Kit

Structured code review workflow with multi-language support. Combines static analysis tools with AI agents to produce P0/P1/P2 severity-graded reports.

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
uv venv && source .venv/bin/activate
uv pip install git+https://github.com/oyjs1989/code-review-kit.git
```

**From source:**
```bash
uv pip install -e ".[test]"
```

## Installing Skills into Your AI Agent

After installing the CLI, run `codereview install` inside your project directory to deploy the AI skill into your agent:

```bash
# Claude Code (default)
codereview install

# Gemini CLI
codereview install --ai gemini

# GitHub Copilot
codereview install --ai copilot

# Install into a specific directory
codereview install --ai claude /path/to/project
```

What this does:
1. Copies `languages/` tools to `.review/languages/` in your project
2. Writes the skill file into the agent's command directory with paths rewritten:
   - Claude Code → `.claude/skills/codereview/SKILL.md`
   - Gemini CLI → `.gemini/commands/codereview-go.md`
   - GitHub Copilot → `.github/agents/codereview-go.md`

After installation, invoke the skill in Claude Code:

```
/codereview go                       # Review current branch vs main
/codereview go --base develop        # Review vs develop branch
/codereview go --resume              # Resume an interrupted review
/codereview go --output report.md    # Save full report to file
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `codereview install` | Install AI skills into your agent's command directory |
| `codereview init` | Create `.review/config.yaml` |
| `codereview scan` | Run static analysis tools, save to `.review/scanner-results/` |
| `codereview review` | Full pipeline: scan → analyze → report → interactive fix |
| `codereview pr <owner/repo> <number>` | Fetch PR comments, run fix/reply workflow |
| `codereview reply` | Send queued PR replies |
| `codereview auth` | Store platform tokens |

## PR Analysis

```bash
codereview scan
codereview pr owner/repo 123

# Send queued replies
codereview reply
```

For each comment the workflow checks whether a scanner already caught the issue, then prompts you to fix or reply.

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

## AI Skill — Go (`/codereview go`)

The Go skill (`languages/go/SKILL.md`) auto-classifies the diff and picks a review depth:

| Classification | Condition | Agents |
|----------------|-----------|--------|
| TRIVIAL | Docs/config only | Skipped |
| LITE | diff < 400 lines, < 5 files | safety, quality, observability |
| FULL | diff ≥ 400 lines or ≥ 5 files or sensitive paths | safety, data, design, quality, observability, business, naming |

For FULL reviews with large diffs (≥ 400 lines), the diff is split into batches to stay within token limits.

Linting priority: `make lint-inc` (fscan-toolchain) > fallback tools.

**Install fscan-toolchain (recommended):**
```bash
curl -sSL https://gitlab.futunn.com/fscan/fscan-toolchain/-/raw/main/install.sh | sh
```

**Fallback tools (if fscan-toolchain unavailable):**
```bash
go install honnef.co/go/tools/cmd/staticcheck@latest
go install github.com/uudashr/gocognit/cmd/gocognit@latest
go install github.com/securego/gosec/v2/cmd/gosec@latest
go install github.com/gordonklaus/ineffassign@latest
```

## Supported Languages

| Language | Status | Tools |
|----------|--------|-------|
| Go | Complete | fscan-toolchain (`make lint-inc`) or fallback (go build, go vet, staticcheck, gosec, gocognit) |
| Python | Planned | pylint, mypy, flake8, ruff, bandit |
| TypeScript | Planned | tsc, eslint |

## Severity Levels

- **P0** — Must fix (security, crashes, data loss)
- **P1** — Should fix (bugs, performance, maintainability)
- **P2** — Suggested (style, best practices)

Reports are output in Chinese (zh-CN) by default. Configurable via `.review/config.yaml`.

## Development

```bash
uv run pytest
bash scripts/bash/run-scanners.sh <target_dir> <output_dir>
```
