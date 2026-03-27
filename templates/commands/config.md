---
description: Initialize code review kit for a project with language-specific configuration
scripts:
  sh: scripts/bash/init-config.sh "{ARGS}"
  ps: scripts/powershell/init-config.ps1 "{ARGS}"
---

## User Input

```text
$ARGUMENTS
```

## Workflow

### 1. Detect Project Language

Scan the project root directory to identify the primary programming language:
- Look for language-specific files (go.mod, requirements.txt, package.json, build.gradle.kts)
- Check file extensions distribution
- Default to "auto" if multiple languages detected

### 2. Load Default Configuration

Load the default configuration template based on detected language:
- `.review/config.yaml` - Main configuration file
- `.review/rules/` - Custom rules directory

### 3. Create Configuration Files

Create the following structure:

```
.review/
├── config.yaml           # Main configuration
├── rules/                # Custom rules (optional)
│   └── custom.yaml
└── results/              # Review results (created on first review)
```

### 4. Configuration Template

```yaml
# Code Review Kit Configuration
language: auto            # go, python, kotlin, typescript, auto
ai_assistant: claude      # claude, gemini, copilot, cursor

rules:
  severity_threshold: P2  # Minimum severity to report (P0, P1, P2)
  enabled_categories:
    - security            # Security vulnerabilities
    - performance         # Performance issues
    - quality            # Code quality
    - style              # Code style
  custom_rules: []       # Path to custom rule files

output:
  format: markdown       # markdown, json, html
  save_history: true     # Save results to .review/results/
  language: zh-CN        # Output language (zh-CN, en-US)
```

### 5. Output

Report completion with:
- Detected language
- Configuration file path
- Next steps (run `/codereview.review`)

## Notes

- Configuration is stored in `.review/` directory at project root
- Add `.review/results/` to `.gitignore` to avoid committing review history
- Custom rules in `.review/rules/` override built-in rules
