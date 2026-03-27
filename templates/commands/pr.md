---
description: Analyze pull/merge request comments and provide actionable insights
handoffs:
  - label: Fix Issues
    agent: codereview.fix
    prompt: Generate fixes for identified issues
scripts:
  sh: scripts/bash/analyze-pr.sh "{ARGS}"
  ps: scripts/powershell/analyze-pr.ps1 "{ARGS}"
---

## User Input

```text
$ARGUMENTS
```

Expected input format:
- `owner/repo 123` - Repository and PR number
- `123` - PR number (uses current git remote)
- `https://github.com/owner/repo/pull/123` - Full URL

## Pre-Execution Checks

### 1. Check Authentication

Load authentication from:
1. Environment variables (`GITHUB_TOKEN`, `GITLAB_TOKEN`)
2. Config file (`.review/auth.yaml`)
3. Prompt user if not configured

```bash
# Check for token
if [ -z "$GITHUB_TOKEN" ] && [ ! -f ".review/auth.yaml" ]; then
    echo "Error: No authentication configured"
    echo "Run '/codereview.auth' to configure or set GITHUB_TOKEN environment variable"
    exit 1
fi
```

### 2. Detect Platform

From git remote:
```bash
git remote get-url origin
# github.com -> GitHub API
# gitlab.com -> GitLab API
# gitee.com -> Gitee API
```

## Workflow

### Step 1: Fetch PR Information

**GitHub API:**
```bash
curl -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER"
```

**GitLab API:**
```bash
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$PROJECT_ID/merge_requests/$MR_IID"
```

### Step 2: Fetch PR Comments

Fetch all comment types:
- **Review Comments** - Code-level comments on specific lines
- **Issue Comments** - General PR comments
- **Commit Comments** - Comments on specific commits
- **Review Summaries** - Approve/Request Changes comments

```json
// Example response structure
{
  "review_comments": [...],
  "issue_comments": [...],
  "reviews": [...]
}
```

### Step 3: Parse and Categorize Comments

Categorize comments by type:

| Category | Patterns | Examples |
|----------|----------|----------|
| Bug Report | "bug", "error", "crash", "broken" | "This will crash if input is null" |
| Security | "security", "vulnerability", "injection" | "SQL injection risk here" |
| Performance | "slow", "optimize", "performance" | "N+1 query problem" |
| Style | "style", "naming", "format" | "Use camelCase for variables" |
| Suggestion | "suggest", "consider", "could" | "Consider using a map instead" |
| Question | "?", "why", "how" | "Why did you use this approach?" |
| Approval | "LGTM", "looks good", "approved" | "LGTM!" |

### Step 4: Identify Actionable Items

Filter comments that require action:
- Comments with code suggestions
- Comments requesting changes
- Comments marked as unresolved
- Comments with specific severity indicators

### Step 5: AI Analysis

For each actionable comment, use AI to:
1. Understand the context
2. Validate if comment is valid
3. Generate fix suggestion
4. Estimate effort

### Step 6: Generate Report

## Output Format

```markdown
# PR Analysis Report

## PR Information
- **Repository**: owner/repo
- **PR Number**: #123
- **Title**: Add user authentication
- **Author**: @developer
- **Status**: Open
- **Created**: 2026-03-27

## Comment Summary

| Category | Count | Actionable |
|----------|-------|------------|
| Bug Report | 3 | 3 |
| Security | 2 | 2 |
| Performance | 1 | 1 |
| Style | 5 | 2 |
| Suggestion | 8 | 4 |
| Question | 3 | 0 |
| Approval | 2 | 0 |

## Actionable Comments

### P0: Security Issue - SQL Injection Risk
**Comment by**: @reviewer
**Location**: `service/user.go:45`
**Original Comment**:
> This query is vulnerable to SQL injection. User input should be parameterized.

**Code Context**:
```go
query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userId)
```

**Suggested Fix**:
```go
stmt := db.Prepare("SELECT * FROM users WHERE id = ?")
rows, err := stmt.Query(userId)
```

---

### P1: Bug - Nil Pointer Dereference
**Comment by**: @reviewer
**Location**: `handler/user.go:102`
**Original Comment**:
> user.Profile could be nil here, need to add nil check.

**Code Context**:
```go
return user.Profile.Name
```

**Suggested Fix**:
```go
if user.Profile == nil {
    return ""
}
return user.Profile.Name
```

---

## Unresolved Questions

1. **@reviewer** asked: "Why use Redis instead of Memcached?"
   - Location: `config/cache.go:15`
   - Need to respond or clarify

2. **@reviewer** asked: "Is this rate limit sufficient for production?"
   - Location: `middleware/rate_limit.go:30`
   - Need to discuss with team

## Approved By
- @senior-dev (LGTM)
- @tech-lead (Approved with minor suggestions)

## Next Steps
1. [ ] Fix P0 security issue (SQL injection)
2. [ ] Fix P1 bug (nil pointer)
3. [ ] Respond to unresolved questions
4. [ ] Address style suggestions (optional)
```

## API Integration Details

### GitHub API Endpoints

```
GET /repos/{owner}/{repo}/pulls/{pull_number}
GET /repos/{owner}/{repo}/pulls/{pull_number}/comments
GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews
GET /repos/{owner}/{repo}/issues/{issue_number}/comments
```

### GitLab API Endpoints

```
GET /projects/:id/merge_requests/:merge_request_iid
GET /projects/:id/merge_requests/:merge_request_iid/notes
GET /projects/:id/merge_requests/:merge_request_iid/discussions
```

### Rate Limiting

Handle API rate limits gracefully:
- GitHub: 5000 requests/hour (authenticated)
- GitLab: 2000 requests/minute
- Implement exponential backoff
- Cache responses when possible

## Environment Variables

```bash
# GitHub
GITHUB_TOKEN=ghp_xxxx

# GitLab
GITLAB_TOKEN=glpat-xxxx
GITLAB_HOST=gitlab.com  # optional, for self-hosted

# Gitee
GITEE_TOKEN=xxxx
```
