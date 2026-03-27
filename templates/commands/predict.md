---
description: Predict and analyze potential PR/MR comments on current branch changes without API authentication
handoffs:
  - label: Generate Fix
    agent: codereview.fix
    prompt: Generate fix for confirmed issues
  - label: Add Rule
    agent: codereview.learn
    prompt: Add new rule to prevent this issue
scripts:
  sh: scripts/bash/predict-review.sh "{ARGS}"
  ps: scripts/powershell/predict-review.ps1 "{ARGS}"
---

## User Input

```text
$ARGUMENTS
```

## Overview

This command simulates a code review from other developers' perspective, predicting potential comments and questions without requiring API authentication. It analyzes your current branch changes and identifies:

1. **Potential Issues** - Problems others might catch
2. **Likely Questions** - Clarifications others might ask
3. **Style Suggestions** - Improvements others might suggest

## Workflow

### Step 1: Gather Branch Changes

```bash
# Get diff between current branch and base branch
git diff main...HEAD

# Or compare with specific branch
git diff origin/main...HEAD

# Get list of changed files
git diff main...HEAD --name-only --diff-filter=AM
```

### Step 2: Analyze from Multiple Perspectives

Simulate reviews from different roles:

| Role | Focus Areas | Typical Concerns |
|------|-------------|------------------|
| **Security Reviewer** | Vulnerabilities, data exposure | SQL injection, XSS, auth bypass |
| **Senior Developer** | Architecture, maintainability | Design patterns, coupling |
| **Junior Developer** | Readability, learning | Code clarity, documentation |
| **QA Engineer** | Edge cases, testing | Error handling, test coverage |
| **Product Owner** | Business logic | Requirements alignment |
| **Performance Engineer** | Efficiency | Memory, latency, scalability |

### Step 3: Predict Comments

For each code change, predict:

**Category 1: Confirmed Issues (Likely to be flagged)**
```markdown
## Predicted Comment: Security Issue
**Role**: Security Reviewer
**Severity**: P0
**Location**: `service/auth.go:45`
**Predicted Comment**:
> This token validation has a timing attack vulnerability. Use constant-time comparison.

**Analysis**: ✅ This is a real issue. Token comparison using `==` can leak timing information.

**Fix Suggestion**:
```go
// Before
if token == storedToken { ... }

// After
if subtle.ConstantTimeCompare([]byte(token), []byte(storedToken)) != 1 {
    return errors.New("invalid token")
}
```
```

**Category 2: Likely Questions (May or may not be issues)**
```markdown
## Predicted Comment: Design Question
**Role**: Senior Developer
**Location**: `handler/user.go:102`
**Predicted Comment**:
> Why did you choose to use a mutex here instead of a channel? This might cause contention under high load.

**Analysis**: ⚠️ This could be either:
- A valid concern if high concurrency is expected
- An over-optimization if traffic is low

**Response Options**:
A. "Good point. I'll refactor to use a channel-based approach"
B. "Current traffic is low, but I'll add a TODO for future optimization"
C. "This mutex is for configuration cache which is read-heavy, using RWMutex for better performance"

**Recommendation**: Based on codebase context, option C seems appropriate.
```

**Category 3: Style Suggestions (Optional improvements)**
```markdown
## Predicted Comment: Style Suggestion
**Role**: Code Style Reviewer
**Location**: `utils/helper.go:30`
**Predicted Comment**:
> Consider extracting this logic into a separate function for reusability.

**Analysis**: ℹ️ Style suggestion, not a bug.

**Your Call**:
- Accept if it improves maintainability
- Decline if the logic is specific to this context
```

### Step 4: User Decision Loop

For each predicted comment:

```
┌─────────────────────────────────────────────────────────────┐
│ Predicted Comment #1: Security Issue                        │
├─────────────────────────────────────────────────────────────┤
│ Location: service/auth.go:45                                │
│ "Token validation has timing attack vulnerability"          │
│                                                             │
│ AI Analysis: ✅ This is a real security issue               │
│                                                             │
│ Your Decision:                                              │
│ [F] Fix this issue                                          │
│ [R] Respond to reviewer (provide justification)             │
│ [S] Skip (not an issue in our context)                      │
│ [M] Mark as false positive (improve detection rules)        │
└─────────────────────────────────────────────────────────────┘
```

### Step 5: Learning from Decisions

**If user chooses [F] Fix:**
- Apply the suggested fix
- Record the issue type for future detection

**If user chooses [R] Respond:**
- Help draft a response to the reviewer
- Record the justification for this pattern

**If user chooses [S] Skip:**
- Note the context where this pattern is acceptable
- Adjust severity for similar future predictions

**If user chooses [M] False Positive:**
- Ask: "Why didn't our rules catch this correctly?"
- Options:
  1. Add new rule to prevent similar false positives
  2. Adjust existing rule's pattern
  3. Add context-aware exceptions

## Output Format

```markdown
# Predictive Code Review Report

## Summary
- Analyzed: 15 files changed, +450/-120 lines
- Predicted Comments: 8
- Confirmed Issues: 3 (P0: 1, P1: 2)
- Likely Questions: 3
- Style Suggestions: 2

---

## P0 Issues (Critical - Likely to be flagged)

### Issue 1: Timing Attack Vulnerability
**Predicted by**: Security Reviewer persona
**Location**: `service/auth.go:45`
**Confidence**: High (95%)

**Predicted Comment**:
> Token comparison using `==` is vulnerable to timing attacks

**AI Analysis**: ✅ **Confirmed Issue**
This is a real security vulnerability. Use `crypto/subtle.ConstantTimeCompare`.

**Suggested Fix**:
```go
import "crypto/subtle"

func validateToken(token string, storedToken string) bool {
    return subtle.ConstantTimeCompare(
        []byte(token),
        []byte(storedToken),
    ) == 1
}
```

**Your Decision**: [ ] Fix  [ ] Respond  [ ] Skip  [ ] False Positive

---

## Likely Questions (May or may not be issues)

### Question 1: Concurrency Design Choice
**Predicted by**: Senior Developer persona
**Location**: `handler/order.go:78`
**Confidence**: Medium (60%)

**Predicted Comment**:
> Why use mutex here instead of channels? Might cause contention.

**AI Analysis**: ⚠️ **Depends on Context**
- If expecting >1000 QPS: Valid concern
- If expecting <100 QPS: Acceptable trade-off

**Response Options**:
A. "Good point, I'll refactor to channels"
B. "Acceptable for current scale, added TODO for optimization"
C. "Using RWMutex since read >> write ratio"

**Your Decision**: [ ] Fix  [ ] Respond (choose A/B/C)  [ ] Skip

---

## Style Suggestions (Optional)

### Suggestion 1: Extract Function
**Predicted by**: Code Style Reviewer
**Location**: `utils/format.go:23`
**Confidence**: Low (40%)

**Predicted Comment**:
> Consider extracting this into a reusable utility function

**AI Analysis**: ℹ️ **Style Preference**
Code works correctly. Extracting might improve reusability.

**Your Decision**: [ ] Accept  [ ] Decline  [ ] N/A

---

## Why Didn't AI Catch These Earlier?

### Review of Missed Issues

| Issue | Why Missed | Action |
|-------|------------|--------|
| Timing attack | Rule didn't cover `==` comparison for secrets | Add rule: `SEC-NEW-001` |
| Concurrency pattern | Context-dependent, no clear rule | Add architecture guideline |
| Long function | Complexity analyzer threshold too high | Lower threshold to 50 lines |

---

## Generated Rules for New Issues

### SEC-NEW-001: Timing-Safe Token Comparison
```yaml
id: SEC-NEW-001
name: Use constant-time comparison for secrets
severity: P0
pattern:
  type: semantic
  match: 'token == | password == | secret == '
message: "Use crypto/subtle.ConstantTimeCompare for secret comparison"
auto_fixable: false
```

---

## Next Steps

1. [ ] Fix P0 timing attack issue
2. [ ] Respond to concurrency question
3. [ ] Review and add new rule SEC-NEW-001
4. [ ] Commit changes and updated rules
```

## Key Features

### 1. No API Authentication Required
- Works offline using git diff
- No need to configure tokens

### 2. Multiple Reviewer Personas
- Simulates different perspectives
- Covers blind spots

### 3. User-Driven Decisions
- User decides what's actually an issue
- AI provides analysis, not final verdict

### 4. Learning Loop
- User decisions improve future predictions
- Rules can be added on-the-fly

### 5. Reflection on Missed Issues
- Analyzes why AI didn't catch issues earlier
- Suggests rule improvements
