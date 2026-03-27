---
description: Configure authentication for remote repositories (GitHub, GitLab, Gitee)
scripts:
  sh: scripts/bash/config-auth.sh "{ARGS}"
  ps: scripts/powershell/config-auth.ps1 "{ARGS}"
---

## User Input

```text
$ARGUMENTS
```

## Workflow

### 1. Platform Selection

Prompt user to select platform:
- GitHub (github.com)
- GitLab (gitlab.com or self-hosted)
- Gitee (gitee.com)
- Azure DevOps
- Bitbucket

### 2. Authentication Configuration

**GitHub:**
```yaml
# .review/auth.yaml
github:
  token: ghp_xxxxxxxxxxxx  # Personal Access Token
  # Required scopes: repo, read:org
```

**GitLab:**
```yaml
gitlab:
  host: gitlab.com  # or self-hosted URL
  token: glpat-xxxxxxxxxxxx  # Personal Access Token
```

**Gitee:**
```yaml
gitee:
  token: xxxxxxxxxxxx  # Personal Access Token
```

### 3. Token Scope Requirements

| Platform | Required Scopes |
|----------|----------------|
| GitHub | `repo`, `read:org`, `read:discussion` |
| GitLab | `api`, `read_api` |
| Gitee | `projects`, `pull_requests` |

### 4. Security Notes

**IMPORTANT:**
- Tokens are stored in `.review/auth.yaml`
- This file is automatically added to `.gitignore`
- Never commit tokens to version control
- Tokens can be stored in environment variables as alternative:
  - `GITHUB_TOKEN`
  - `GITLAB_TOKEN`
  - `GITEE_TOKEN`

### 5. Validation

After configuration, validate by:
- Fetching user info
- Listing accessible repositories
- Testing PR read permission

## Output

```markdown
# Authentication Configuration

## Platform: GitHub

✓ Token validated successfully
✓ User: username
✓ Permissions: repo, read:org

## Connected Repositories
- owner/repo-1
- owner/repo-2

## Next Steps
Run `/codereview.pr` to analyze pull request comments
```

## Security Best Practices

1. **Environment Variables (Recommended)**
   ```bash
   export GITHUB_TOKEN="ghp_xxxx"
   codereview pr analyze owner/repo 123
   ```

2. **Config File (Convenient but less secure)**
   ```bash
   codereview auth config
   # Token stored in .review/auth.yaml (gitignored)
   ```

3. **Token Rotation**
   - Remind users to rotate tokens periodically
   - Support for multiple tokens per platform
