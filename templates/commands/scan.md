---
description: Run integrated code scanning tools before analysis
scripts:
  sh: scripts/bash/run-scanners.sh "{ARGS}"
  ps: scripts/powershell/run-scanners.ps1 "{ARGS}"
---

## Supported Scanners

### Go
| Tool | Purpose | Install |
|------|---------|---------|
| go build | Compile check | Built-in |
| go vet | Static analysis | Built-in |
| staticcheck | Advanced static analysis | `go install honnef.co/go/tools/cmd/staticcheck@latest` |
| gocognit | Cognitive complexity | `go install github.com/uudashr/gocognit/cmd/gocognit@latest` |
| gosec | Security scanner | `go install github.com/securego/gosec/v2/cmd/gosec@latest` |
| ineffassign | Ineffectual assignments | `go install github.com/gordonklaus/ineffassign@latest` |

### Python
| Tool | Purpose | Install |
|------|---------|---------|
| python -m py_compile | Compile check | Built-in |
| pylint | Code quality | `pip install pylint` |
| mypy | Type checking | `pip install mypy` |
| flake8 | Style guide | `pip install flake8` |
| bandit | Security | `pip install bandit` |
| ruff | Fast linter | `pip install ruff` |

### Kotlin
| Tool | Purpose | Install |
|------|---------|---------|
| gradle build | Compile check | Built-in |
| ktlint | Style | `brew install ktlint` |
| detekt | Static analysis | Gradle plugin |

### TypeScript/JavaScript
| Tool | Purpose | Install |
|------|---------|---------|
| tsc | Type check | Built-in |
| eslint | Linter | `npm install -g eslint` |
| prettier | Format check | `npm install -g prettier` |

## Scanner Output Format

All scanners output unified JSON format:

```json
{
  "tool": "staticcheck",
  "version": "2023.1",
  "issues": [
    {
      "id": "SA1000",
      "severity": "error",
      "category": "style",
      "file": "service/user.go",
      "line": 45,
      "column": 10,
      "message": "should use staticcheck for Go code",
      "suggestion": "Use staticcheck for better code quality",
      "confidence": "high"
    }
  ],
  "stats": {
    "total": 10,
    "errors": 2,
    "warnings": 5,
    "info": 3
  }
}
```

## Integration Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    Scanner Integration                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Detect Language                                          │
│     - From file extensions                                   │
│     - From project config (go.mod, requirements.txt, etc.)   │
│                                                              │
│  2. Check Tool Availability                                  │
│     - which go, which pylint, which eslint                   │
│     - Prompt to install if missing                           │
│                                                              │
│  3. Run Scanners (Tiered)                                    │
│     ┌─────────────────────────────────────┐                 │
│     │ Tier 1: Build/Compile               │                 │
│     │   go build, tsc, gradle build       │                 │
│     │   → Must fix (P0)                   │                 │
│     └─────────────────────────────────────┘                 │
│     ┌─────────────────────────────────────┐                 │
│     │ Tier 2: Linters                     │                 │
│     │   go vet, pylint, eslint            │                 │
│     │   → Should fix (P1/P2)              │                 │
│     └─────────────────────────────────────┘                 │
│     ┌─────────────────────────────────────┐                 │
│     │ Tier 3: Static Analysis             │                 │
│     │   staticcheck, mypy, detekt         │                 │
│     │   → Should fix (P1)                 │                 │
│     └─────────────────────────────────────┘                 │
│     ┌─────────────────────────────────────┐                 │
│     │ Tier 4: Security Scanners           │                 │
│     │   gosec, bandit, snyk               │                 │
│     │   → Must fix (P0)                   │                 │
│     └─────────────────────────────────────┘                 │
│                                                              │
│  4. Aggregate Results                                        │
│     - Deduplicate by file:line                               │
│     - Sort by severity                                       │
│     - Map to internal issue IDs                              │
│                                                              │
│  5. Output                                                   │
│     - scanner-results.json                                   │
│     - Used for PR comment validation                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Usage in PR Analysis

```python
def validate_comment_with_scanner(comment, scanner_results):
    """Validate comment against scanner results."""
    
    # Find matching scanner issue
    matching_issue = find_issue_at_location(
        scanner_results,
        comment.location
    )
    
    if matching_issue:
        # Scanner detected the same issue
        return {
            "is_correct": True,
            "scanner_match": matching_issue,
            "reason": f"Scanner {matching_issue.tool} also detected this issue"
        }
    else:
        # Scanner didn't detect - need to analyze
        return {
            "is_correct": None,  # Need further analysis
            "scanner_match": None,
            "reason": "Scanner did not detect this issue"
        }
```

## Configuration

```yaml
# .review/config.yaml
scanners:
  enabled: true
  languages:
    go:
      - go build
      - go vet
      - staticcheck
      - gosec
    python:
      - python -m py_compile
      - pylint
      - mypy
      - bandit
  
  severity_mapping:
    error: P0
    warning: P1
    info: P2
  
  fail_on:
    - error      # P0 issues cause failure
    - critical   # Critical security issues
```
