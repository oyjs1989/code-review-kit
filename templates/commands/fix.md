---
description: Auto-fix issues where possible, generating patches or direct code changes
---

## User Input

```text
$ARGUMENTS
```

## Workflow

### 1. Load Fixable Issues

Filter issues that are auto-fixable:
- Rule has `auto_fixable: true`
- Issue has a defined fix pattern
- Issue doesn't require business context judgment

### 2. Categorize Issues

| Category | Auto-fixable | Examples |
|----------|--------------|----------|
| Formatting | ✅ Yes | Indentation, line length |
| Naming | ✅ Yes | Variable renaming |
| Simple patterns | ✅ Yes | Missing error check |
| Logic errors | ❌ No | Business logic bugs |
| Architecture | ❌ No | Design pattern issues |

### 3. Generate Fixes

For each fixable issue:

```python
# Pseudocode for fix generation
def generate_fix(issue):
    if issue.rule.auto_fix_template:
        return apply_template(issue)
    elif issue.rule.fix_pattern:
        return apply_pattern(issue.code, issue.rule.fix_pattern)
    else:
        return suggest_fix_with_ai(issue)
```

### 4. Validate Fixes

- Run linter on fixed code
- Check no new issues introduced
- Verify fix is correct

### 5. Apply or Preview

**Dry-run mode:**
- Show diff of changes
- List files affected
- Estimate impact

**Apply mode:**
- Apply changes to files
- Run tests (if available)
- Create commit message

## Output Format

```markdown
# Auto-Fix Report

## Summary
- Total issues: X
- Auto-fixable: Y
- Fixed: Z
- Skipped: W (require manual review)

## Applied Fixes

### Fix 1: [Rule ID] in file.go:45
**Before**:
```go
// Original code
```
**After**:
```go
// Fixed code
```

## Skipped Issues (Require Manual Review)

### Issue [ID]: [Description]
**Location**: file.go:100
**Reason**: Requires business context judgment
**Suggestion**: [Manual fix suggestion]

## Next Steps
1. Review applied changes
2. Run tests: `go test ./...`
3. Commit: `git commit -m "fix: auto-fix code review issues"`
```

## Safety Measures

1. **Backup**: Create backup before applying fixes
2. **Tests**: Run tests after each fix
3. **Rollback**: Provide rollback instructions
4. **Review**: Require user confirmation for non-trivial fixes
