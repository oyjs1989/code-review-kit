---
description: Deep analyze a specific issue with root cause and impact assessment
handoffs:
  - label: Generate Fix
    agent: codereview.fix
    prompt: Generate fix for this issue
---

## User Input

```text
$ARGUMENTS
```

## Workflow

### 1. Load Issue Context

- Read issue_id from input
- Load issue from `.review/results/latest/issues.json`
- Load related code context

### 2. Root Cause Analysis

Perform deep analysis to understand:

**Why did this issue occur?**
- Missing validation?
- Incorrect pattern?
- Architectural flaw?
- Knowledge gap?

### 3. Impact Assessment

**Security Impact:**
- Can this be exploited?
- What data is at risk?
- What's the attack vector?

**Performance Impact:**
- How does this affect performance?
- Scale at which it becomes critical?

**User Experience Impact:**
- How does this affect users?
- What scenarios trigger the issue?

### 4. Related Code Analysis

- Find similar patterns in codebase
- Identify dependencies
- Check if issue exists elsewhere

### 5. Solution Options

Provide multiple solution approaches:

| Option | Approach | Pros | Cons | Effort |
|--------|----------|------|------|--------|
| A | Quick fix | Low effort | May not address root cause | 1h |
| B | Refactor | Addresses root cause | Higher effort | 4h |
| C | Redesign | Best long-term solution | High effort | 2d |

### 6. Recommendation

Provide recommended solution with:
- Rationale
- Implementation steps
- Testing strategy
- Rollback plan

## Output Format

```markdown
# Deep Analysis: Issue {issue_id}

## Issue Summary
[Brief description of the issue]

## Root Cause Analysis
[Detailed analysis of why this issue occurred]

## Impact Assessment

### Security Impact
[Security implications]

### Performance Impact
[Performance implications]

### User Experience Impact
[UX implications]

## Related Code
[Links to related code in the project]

## Solution Options

### Option A: [Name]
[Description]

### Option B: [Name]
[Description]

### Option C: [Name]
[Description]

## Recommendation
[Recommended solution with rationale]

## Implementation Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]
```
