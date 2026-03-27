---
description: Execute comprehensive code review with multi-tier analysis and AI-powered insights
handoffs:
  - label: Deep Analyze Issues
    agent: codereview.analyze
    prompt: Deep analyze the discovered issues
  - label: Auto Fix Issues
    agent: codereview.fix
    prompt: Auto-fix issues where possible
scripts:
  sh: scripts/bash/run-review.sh "{ARGS}"
  ps: scripts/powershell/run-review.ps1 "{ARGS}"
---

## User Input

```text
$ARGUMENTS
```

## Pre-Execution Checks

1. **Check for configuration**
   - Look for `.review/config.yaml` in project root
   - If not found, suggest running `/codereview.config` first

2. **Load configuration**
   - Read language setting
   - Load enabled rule categories
   - Set severity threshold

## Review Workflow

### Step 1: Gather Changed Files

```bash
# Get changed files from git
git diff HEAD --name-only --diff-filter=AM

# Or from specific branch
git diff main...HEAD --name-only --diff-filter=AM

# Or specific files/directories
# Use user-provided target if specified
```

### Step 2: Language Detection & Tool Selection

Based on detected language, select appropriate tools:

| Language | Build Tool | Linter | Static Analysis |
|----------|-----------|--------|-----------------|
| Go | go build | go vet | staticcheck |
| Python | python -m py_compile | pylint, flake8 | mypy |
| Kotlin | gradle build | ktlint | detekt |
| TypeScript | tsc | eslint | typescript-eslint |

### Step 3: Run Tier 1 - Build & Compile Check

Run build tools to catch compilation errors:
- **P0**: Build errors (must fix)
- **P0**: Type errors
- **P1**: Warnings

Output: `diagnostics.json`

### Step 4: Run Tier 2 - Linter & Static Analysis

Run linters and static analyzers:
- **P0**: Critical issues (security, crashes)
- **P1**: Important issues (performance, bugs)
- **P2**: Style and best practices

Output: `linter-results.json`

### Step 5: Run Tier 3 - Rule Scanning

Scan against YAML-defined rules:
- Security rules (SQL injection, XSS, sensitive data)
- Performance rules (N+1 queries, memory leaks)
- Quality rules (complexity, duplication)
- Style rules (naming, formatting)

Output: `rule-hits.json`

### Step 6: Run Tier 4 - AI Agent Analysis

Dispatch domain-expert agents based on language:

**For Go:**
- safety - Concurrency, error handling, nil safety
- data - Database operations, GORM patterns
- design - Architecture, UNIX philosophy
- quality - Code metrics, readability
- observability - Logging, error messages
- business - Business logic, edge cases
- naming - Naming conventions

**For Python:**
- safety - Type safety, exception handling
- data - Database patterns, serialization
- design - Design patterns, SOLID
- quality - Complexity, documentation
- security - Security vulnerabilities
- performance - Performance optimization

### Step 7: Aggregate Results

1. Merge all findings
2. Deduplicate by file:line
3. Sort by severity (P0 → P1 → P2)
4. Generate report

## Output Format

All output **MUST be in the configured language** (default: Chinese).

```markdown
# Code Review Report

## Summary

| Metric | Count |
|--------|-------|
| P0 (Must Fix) | X |
| P1 (Should Fix) | X |
| P2 (Suggested) | X |

## P0 Issues (Must Fix)

### Issue 1: [P0] Security - SQL Injection Risk
**Location**: `service/user.go:45`
**Category**: Security
**Original Code**:
```go
query := "SELECT * FROM users WHERE id = " + userId
```
**Problem**: String concatenation in SQL query creates injection vulnerability
**Suggested Fix**:
```go
stmt := db.Prepare("SELECT * FROM users WHERE id = ?")
rows, err := stmt.Query(userId)
```

## P1 Issues (Should Fix)
...

## P2 Issues (Suggested)
...
```

## Output Artifacts

```
.review/results/YYYYMMDD-HHMMSS/
├── report.md           # Human-readable report
├── issues.json         # Machine-readable issues
├── diagnostics.json    # Tool output
└── metrics.json        # Review metrics
```
