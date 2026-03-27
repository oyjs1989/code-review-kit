# Code Review Kit - AI Agent Context

## Project Overview

**Project Name:** Code Review Kit

**Project Type:** CLI Tool + AI Skills

**Purpose:** Structured code review workflow with multi-language support, following Spec-Kit's workflow-driven architecture.

## Directory Structure

```
code-review-kit/
├── src/
│   └── review_cli/           # CLI implementation (Python + Typer)
│       └── __init__.py       # Main entry point
│
├── templates/
│   └── commands/             # Command templates (Markdown)
│       ├── config.md         # Initialize configuration
│       ├── review.md         # Main review command
│       ├── analyze.md        # Deep analysis
│       ├── fix.md            # Auto-fix
│       ├── report.md         # Generate report
│       └── learn.md          # Learn from history
│
├── languages/                # Language-specific implementations
│   └── go/                   # Go language support
│       ├── SKILL.md          # Main orchestrator
│       ├── agents/           # Domain experts
│       ├── rules/            # YAML rules
│       ├── tools/            # Shell scripts
│       └── references/       # Standards documentation
│
├── rules/                    # Shared rules
├── scripts/                  # CLI scripts
│   ├── bash/
│   └── powershell/
│
├── docs/                     # Documentation
├── tests/                    # Test cases
│
├── pyproject.toml            # Python project config
└── .gitignore
```

## Supported AI Agents

| Agent | Directory | Format | CLI Tool |
|-------|-----------|--------|----------|
| Claude Code | .claude/commands/ | Markdown | claude |
| Gemini CLI | .gemini/commands/ | TOML | gemini |
| GitHub Copilot | .github/agents/ | Markdown | N/A (IDE) |
| Cursor | .cursor/commands/ | Markdown | cursor-agent |

## Commands (Workflow-Driven)

| Command | Description | Output |
|---------|-------------|--------|
| `/codereview.config` | Initialize configuration | .review/config.yaml |
| `/codereview.scan` | Run integrated scanning tools | scanner-results.json |
| `/codereview.review` | Execute full review | report.md, issues.json |
| `/codereview.analyze` | Deep analyze issue | analysis.md |
| `/codereview.fix` | Auto-fix issues | patches |
| `/codereview.report` | Generate formatted report | html/md/json |
| `/codereview.learn` | Learn from history | config updates |
| `/codereview.auth` | Configure authentication | .review/auth.yaml |
| `/codereview.pr` | Analyze PR/MR comments with fix/reply workflow | fixes.json, replies.json |
| `/codereview.reply` | Send replies to PR comments | API response |

## Integrated Scanning Tools

### Go
| Tool | Purpose | Tier |
|------|---------|------|
| go build | Compile check | P0 |
| go vet | Static analysis | P1 |
| staticcheck | Advanced analysis | P1 |
| gosec | Security scanner | P0 |
| gocognit | Complexity analysis | P2 |

### Python
| Tool | Purpose | Tier |
|------|---------|------|
| pylint | Code quality | P1 |
| mypy | Type checking | P1 |
| flake8 | Style guide | P2 |
| ruff | Fast linter | P1 |
| bandit | Security | P0 |

### TypeScript
| Tool | Purpose | Tier |
|------|---------|------|
| tsc | Type check | P0 |
| eslint | Linter | P1 |

## PR Analysis Workflow

```
/codereview.scan              # Run scanners first
    ↓
/codereview.pr owner/repo 123
    ↓
Fetch PR + Comments
    ↓
┌─────────────────────────────────────┐
│ For each comment:                    │
│   1. Check if scanner detected it    │
│   2. If detected → Mark as correct   │
│      - Show scanner tool + rule      │
│   3. If not detected → Analyze       │
│      - Check if comment is valid     │
│      - Suggest rule improvement      │
│   4. User selects action             │
└─────────────────────────────────────┘
    ↓
Save pending fixes → /codereview.fix
Save pending replies → /codereview.reply
```

## Supported Platforms for PR Analysis

| Platform | API | Auth Method |
|----------|-----|-------------|
| GitHub | REST API v3 | Personal Access Token |
| GitLab | REST API v4 | Personal Access Token |
| Gitee | REST API v5 | Personal Access Token |

## Authentication Setup

```bash
# Environment variable (recommended)
export GITHUB_TOKEN="ghp_xxxx"

# Or use CLI
codereview auth --platform github --token "ghp_xxxx"

# For self-hosted GitLab
codereview auth --platform gitlab --host "https://gitlab.company.com" --token "glpat-xxxx"
```

## Required Token Scopes

| Platform | Required Scopes |
|----------|----------------|
| GitHub | `repo`, `read:org` |
| GitLab | `api`, `read_api` |
| Gitee | `projects`, `pull_requests` |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Code Review Workflow                      │
├─────────────────────────────────────────────────────────────┤
│  /codereview.config                                          │
│  ↓ Initialize                                                │
│  /codereview.review                                          │
│  ↓ Tier 1: Build Tools (go build, mypy, tsc)                 │
│  ↓ Tier 2: Linters (go vet, pylint, eslint)                  │
│  ↓ Tier 3: Rule Scanning (YAML patterns)                     │
│  ↓ Tier 4: AI Agents (domain experts)                        │
│  ↓ Aggregate & Report                                        │
│  /codereview.analyze (optional)                              │
│  /codereview.fix (optional)                                  │
│  /codereview.report                                          │
│  /codereview.learn (periodic)                                │
└─────────────────────────────────────────────────────────────┘
```

## Supported Languages

| Language | Status | Tools | Agents |
|----------|--------|-------|--------|
| Go | ✅ Complete | go build, go vet, staticcheck | 7 agents |
| Python | 🚧 Planned | py_compile, pylint, mypy | TBD |
| Kotlin | 🚧 Planned | gradle, ktlint, detekt | TBD |
| TypeScript | 🚧 Planned | tsc, eslint | TBD |

## Development Conventions

### Code Style
- Python: Follow PEP 8, use black formatter
- Shell scripts: ShellCheck compliant
- YAML: 2-space indentation

### Output Language
- Default: Chinese (zh-CN)
- Configurable via config.yaml

### Severity Levels
- P0: Must fix (security, crashes, data loss)
- P1: Should fix (performance, bugs, maintainability)
- P2: Suggested (style, best practices)

## Quick Start

```bash
# Initialize
codereview init --lang go

# Run review
codereview review ./...

# Deep analyze
codereview analyze ISSUE-001

# Auto-fix
codereview fix --issues P0

# Generate report
codereview report --format html
```

## Version History

- v0.1.0: Initial setup, Go language support migrated from marketplace

---

**Last Updated:** 2026-03-27
**Status:** In Development
