---
description: Learn from past reviews to improve rules and reduce false positives
---

## User Input

```text
$ARGUMENTS
```

## Workflow

### 1. Collect Historical Data

Read all review results from `.review/results/`:
- Parse issues.json from each review
- Track patterns and frequencies
- Note which issues were accepted vs dismissed

### 2. Identify Patterns

**False Positive Detection:**
- Issues consistently marked as "won't fix"
- Issues with low acceptance rate
- Rules that trigger too frequently

**High-Value Rules:**
- Issues consistently fixed
- Issues that caught real bugs
- Rules with high acceptance rate

### 3. Generate Recommendations

```yaml
# Example output
recommendations:
  - rule_id: SAFE-001
    action: adjust_threshold
    reason: "85% false positive rate in fmt.Errorf patterns"
    suggestion: "Exclude %w format patterns"
  
  - rule_id: DATA-006
    action: lower_severity
    reason: "Often dismissed as acceptable complexity"
    suggestion: "Lower from P1 to P2"
  
  - new_rule:
    category: security
    pattern: "jwt.ParseWithoutVerification"
    severity: P0
    reason: "Found in 3 reviews without existing rule coverage"
```

### 4. Apply Learning

**Automatic adjustments:**
- Update rule weights
- Adjust severity thresholds
- Add exclusion patterns

**Manual review required:**
- New rule proposals
- Major severity changes
- Rule deprecations

### 5. Update Configuration

Update `.review/config.yaml` with learned settings:
```yaml
rules:
  learned_adjustments:
    SAFE-001:
      exclude_patterns:
        - '%w'
    DATA-006:
      severity_override: P2
```

## Output Format

```markdown
# Learning Report

## Summary
- Reviews analyzed: X
- Total issues tracked: Y
- Learning period: YYYY-MM-DD to YYYY-MM-DD

## False Positive Analysis

| Rule ID | FP Rate | Recommendation |
|---------|---------|----------------|
| SAFE-001 | 85% | Adjust pattern |
| QUAL-005 | 60% | Lower severity |

## High-Value Rules

| Rule ID | Accept Rate | Issues Caught |
|---------|-------------|---------------|
| SEC-002 | 95% | 12 bugs |
| PERF-001 | 88% | 8 performance issues |

## New Rule Proposals

### Proposal 1: JWT Verification Check
**Pattern**: `jwt.ParseWithoutVerification`
**Category**: Security
**Severity**: P0
**Rationale**: Found in 3 reviews, potential security risk

## Applied Adjustments
- [x] SAFE-001: Added %w exclusion
- [x] DATA-006: Lowered severity to P2
- [ ] NEW-RULE-001: Pending approval

## Next Steps
1. Review new rule proposals
2. Confirm severity adjustments
3. Run `/codereview.config` to update
```
