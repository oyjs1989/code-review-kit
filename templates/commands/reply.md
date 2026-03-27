---
description: Reply to PR/MR comments with generated responses
---

## User Input

```text
$ARGUMENTS
```

Expected input:
- Comment ID or "all" to reply to all pending comments
- Optional: custom message to append

## Workflow

### 1. Load Pending Replies

Load comments marked for reply from previous analysis:
- `.review/results/pr-{number}-pending.json`

### 2. Select Comment to Reply

If specific comment ID provided:
- Load that comment's reply draft

If "all" specified:
- Process all pending replies sequentially

### 3. Display Reply Preview

```
┌─────────────────────────────────────────────────────────────┐
│ 回复预览                                                     │
├─────────────────────────────────────────────────────────────┤
│ 原评论:                                                      │
│ @reviewer: 变量名应该使用下划线命名法                        │
│                                                             │
│ 回复内容:                                                    │
│ 感谢您的审查！关于命名规范的问题，                           │
│ 根据 Go 官方代码审查建议，Go 语言推荐使用驼峰命名法。        │
│ 参考: https://github.com/golang/go/wiki/CodeReviewComments │
└─────────────────────────────────────────────────────────────┘
```

### 4. User Actions

- **[1] 确认发送** - Post reply via API
- **[2] 编辑回复** - Open editor to modify
- **[3] 跳过** - Skip this reply
- **[4] 标记已处理** - Mark as resolved without replying

### 5. Post Reply

```python
def post_reply(platform, repo, pr_number, comment_id, reply_body):
    if platform == "github":
        # Reply to review comment
        response = requests.post(
            f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments",
            headers={"Authorization": f"token {token}"},
            json={
                "body": reply_body,
                "in_reply_to": comment_id
            }
        )
    elif platform == "gitlab":
        # Reply to discussion
        response = requests.post(
            f"{gitlab_host}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions/{discussion_id}/notes",
            headers={"PRIVATE-TOKEN": token},
            json={"body": reply_body}
        )
```

### 6. Update Status

Update pending replies file:
- Remove replied comments
- Add reply timestamp and content
- Log for future reference

## Output Format

```markdown
# 回复结果

## 已发送回复

### 回复 #1
- **原评论**: @reviewer 关于命名规范...
- **回复内容**: 感谢您的审查！...
- **发送时间**: 2026-03-27 14:30:00
- **状态**: ✅ 成功

### 回复 #2
- **原评论**: @senior 关于性能问题...
- **回复内容**: 已经优化，请查看最新提交...
- **发送时间**: 2026-03-27 14:32:00
- **状态**: ✅ 成功

## 待处理回复

| ID | 评论者 | 主题 | 状态 |
|----|--------|------|------|
| 5 | @lead | 架构问题 | 待确认 |

## 下一步
- 所有回复已发送
- 等待审查者反馈
- 如有新评论，运行 `/codereview.pr` 重新分析
```
