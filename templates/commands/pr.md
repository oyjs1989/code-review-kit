---
description: Analyze pull/merge request comments, validate correctness, and provide fix or reply solutions
handoffs:
  - label: Apply Fix
    agent: codereview.fix
    prompt: Apply the selected fix solution
  - label: Reply to Comment
    agent: codereview.reply
    prompt: Reply to the comment on the PR
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

### 2. Detect Platform

From git remote URL.

## Workflow

### Step 1: Fetch PR Information

Fetch PR details including:
- Title, description, author
- Changed files and diffs
- Review status

### Step 2: Fetch All Comments

Fetch all comment types:
- **Review Comments** - Code-level comments on specific lines
- **Issue Comments** - General PR comments
- **Reviews** - Approve/Request Changes summaries

### Step 3: Analyze Each Comment

For each actionable comment:

```python
# 分析流程
def analyze_comment(comment, code_context, diff):
    # 1. 理解评论内容
    comment_intent = understand_comment(comment.body)
    
    # 2. 获取相关代码上下文
    relevant_code = get_code_context(comment.location, diff)
    
    # 3. 验证评论是否正确
    validation = validate_comment(comment_intent, relevant_code)
    
    if validation.is_correct:
        # 评论正确，生成修复方案
        return {
            "status": "CORRECT",
            "solution": generate_fix_solution(comment, relevant_code),
            "reason": validation.reason
        }
    else:
        # 评论错误，生成回复方案
        return {
            "status": "INCORRECT", 
            "solution": generate_reply_solution(comment, validation.reason),
            "reason": validation.reason
        }
```

### Step 4: Comment Validation Logic

**判断评论是否正确：**

```
┌─────────────────────────────────────────────────────────────┐
│                   Comment Validation                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  输入：评论内容 + 代码上下文 + Diff                          │
│                                                              │
│  分析维度：                                                   │
│  1. 理解评论意图（指出什么问题）                              │
│  2. 检查代码是否确实存在该问题                                │
│  3. 验证问题的影响范围                                       │
│                                                              │
│  验证方法：                                                   │
│  - 静态分析：代码逻辑检查                                     │
│  - 上下文分析：考虑业务场景                                   │
│  - 最佳实践对比：参考行业标准                                 │
│                                                              │
│  输出：                                                       │
│  - CORRECT: 评论正确，问题确实存在                           │
│  - INCORRECT: 评论错误，问题不存在或理解有误                 │
│  - NEEDS_CLARIFICATION: 需要更多信息                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Step 5: Generate Solutions

#### 如果评论正确 → 生成修复方案

```markdown
## 修复方案

### 问题分析
评论者指出的问题是正确的：[问题描述]

### 修复建议
```diff
- // 原代码
+ // 修复后代码
```

### 影响范围
- 影响文件: file.go
- 影响行数: 45-50
- 测试建议: 添加单元测试验证修复

### 工具自检
问题：为什么 Code Review Kit 没有自动检测出这个问题？

检查项：
- [ ] 是否有对应规则？→ 规则 ID: XXX-NNN (存在/不存在)
- [ ] 规则是否启用？→ 是/否
- [ ] 规则是否匹配？→ 匹配/不匹配（原因）
- [ ] 是否是假阳性？→ 是/否

如果工具未检测到，需要：
1. 创建新规则 / 更新现有规则
2. 调整规则优先级
3. 更新工具链配置
```

#### 如果评论错误 → 生成回复方案

```markdown
## 回复方案

### 为什么评论不正确
[详细解释为什么代码没有问题，或者评论者理解有误]

### 回复草稿
> 感谢您的审查！关于您提到的 [问题]，
> 
> [解释原因]
> 
> [提供支持证据：文档链接、测试结果、设计说明等]

### 代码说明
```go
// 这段代码的设计考虑了以下因素：
// 1. ...
// 2. ...
// 因此 [评论中的问题] 在这个场景下不适用。
```

### 建议
- [ ] 直接使用此回复
- [ ] 修改后回复
- [ ] 补充更多信息
```

### Step 6: User Interaction

对每个评论，让用户选择：

```
┌─────────────────────────────────────────────────────────────┐
│ Comment #1: SQL Injection Risk                              │
│ Status: CORRECT (评论正确)                                   │
├─────────────────────────────────────────────────────────────┤
│ 评论内容: This query is vulnerable to SQL injection...      │
│                                                             │
│ 修复方案:                                                    │
│ - 使用参数化查询替代字符串拼接                               │
│ - 影响文件: service/user.go:45                              │
│                                                             │
│ 工具自检:                                                    │
│ - 当前无对应规则检测此问题                                   │
│ - 建议新增规则: SEC-001 (SQL Injection)                     │
├─────────────────────────────────────────────────────────────┤
│ 请选择操作:                                                  │
│ [1] 应用修复方案                                             │
│ [2] 查看工具自检详情                                         │
│ [3] 跳过此评论                                               │
│ [4] 标记为需要讨论                                           │
└─────────────────────────────────────────────────────────────┘
```

### Step 7: Fix Flow (用户选择修复)

```
用户选择修复
    ↓
检查为什么 CR 工具没检测到
    ↓
┌─────────────────────────────────┐
│ 情况 A: 规则不存在              │
│ → 创建新规则                    │
│ → 更新规则库                    │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ 情况 B: 规则存在但未启用        │
│ → 启用规则                      │
│ → 更新配置                      │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ 情况 C: 规则存在但未匹配        │
│ → 分析未匹配原因                │
│ → 更新规则模式                  │
└─────────────────────────────────┘
    ↓
应用修复
    ↓
验证修复（运行测试）
    ↓
生成 commit message
```

### Step 8: Reply Flow (用户选择回复)

```
用户选择回复
    ↓
生成回复内容
    ↓
用户确认/修改回复
    ↓
通过 API 发布回复
    ↓
记录回复内容
```

## Output Format

### PR Analysis Summary

```markdown
# PR 分析报告

## PR 信息
- **仓库**: owner/repo
- **PR**: #123 - Add user authentication
- **作者**: @developer
- **评论数**: 8 条

## 评论分析汇总

| # | 评论者 | 类型 | 状态 | 操作 |
|---|--------|------|------|------|
| 1 | @reviewer | Bug | ✅ 正确 | 待修复 |
| 2 | @reviewer | Security | ✅ 正确 | 待修复 |
| 3 | @senior | Question | ℹ️ 需回复 | 待回复 |
| 4 | @reviewer | Style | ❌ 不正确 | 待回复 |
| 5 | @lead | Approval | ✅ 已批准 | - |

## 需要处理的问题

### P0: [修复] SQL 注入风险
**状态**: 评论正确，需要修复
**位置**: `service/user.go:45`
**评论者**: @reviewer

**问题**: 字符串拼接构造 SQL 存在注入风险

**修复方案**:
```diff
- query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userId)
+ stmt := db.Prepare("SELECT * FROM users WHERE id = ?")
+ rows, err := stmt.Query(userId)
```

**工具自检结果**:
- 当前无规则检测此问题
- 建议新增规则: `SEC-001-sql-injection`
- 规则类别: Security
- 严重程度: P0

**选择**: [应用修复] [查看详情] [跳过]

---

### P1: [回复] 命名规范问题
**状态**: 评论不正确，需要回复
**位置**: `handler/user.go:102`
**评论者**: @reviewer

**评论内容**: 变量名应该使用下划线命名法

**为什么不正确**:
Go 语言官方规范推荐使用驼峰命名法（camelCase），而非下划线命名法。
参考: [Go Code Review Comments - naming](https://github.com/golang/go/wiki/CodeReviewComments#initialisms)

**回复方案**:
> 感谢您的审查！关于命名规范的问题，
> 
> 根据 Go 官方代码审查建议，Go 语言推荐使用驼峰命名法而非下划线命名法。
> 参考: https://github.com/golang/go/wiki/CodeReviewComments
> 
> `userId` 符合 Go 的命名惯例，暂时不做修改。

**选择**: [发送回复] [编辑回复] [跳过]

---

## 处理进度
- [ ] 修复 #1: SQL 注入风险
- [ ] 回复 #4: 命名规范问题
- [ ] 回答 #3: 技术问题

## 工具改进建议
本次分析发现以下工具改进机会：

| 规则 ID | 类别 | 说明 | 优先级 |
|---------|------|------|--------|
| SEC-001 | Security | SQL 注入检测 | P0 |
| SEC-002 | Security | XSS 检测 | P1 |
```

## API Integration

### GitHub API

```
# 获取 PR 信息
GET /repos/{owner}/{repo}/pulls/{pull_number}

# 获取评论
GET /repos/{owner}/{repo}/pulls/{pull_number}/comments
GET /repos/{owner}/{repo}/issues/{issue_number}/comments

# 发布回复
POST /repos/{owner}/{repo}/pulls/{pull_number}/comments
POST /repos/{owner}/{repo}/issues/{issue_number}/comments
```

### GitLab API

```
# 获取 MR 信息
GET /projects/:id/merge_requests/:merge_request_iid

# 获取讨论
GET /projects/:id/merge_requests/:merge_request_iid/discussions

# 发布回复
POST /projects/:id/merge_requests/:merge_request_iid/discussions/:discussion_id/notes
```

## Environment Variables

```bash
# 认证
GITHUB_TOKEN=ghp_xxxx
GITLAB_TOKEN=glpat-xxxx
GITEE_TOKEN=xxxx
```