---
name: go-code-review
description: 'Use when the user asks to "review Go code", "check Go code quality", "review this PR", "code review", or mentions Go error handling, concurrency safety, GORM patterns, UNIX principles, naming conventions. Orchestrates Go code review: golangci-lint + YAML rules + 7 domain-expert AI agents. Supports --branch, --base, --output, --resume flags.'
version: 8.0.0
allowed-tools:
  - Bash(git:*)
  - Bash(bash:*)
  - Bash(go:*)
  - Bash(golangci-lint:*)
  - Bash(grep:*)
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(wc:*)
  - Bash(python3:*)
  - Bash(timeout:*)
  - Bash(mkdir:*)
  - Bash(rm:*)
  - Bash(date:*)
  - Agent
  - Read
  - Write
---

<objective>
审查 Go 代码变更，输出 ≤15 条优先级排序问题到终端。三档处理：TRIVIAL（文档/配置变更，直接跳过）、LITE（小型变更，3 个 Agent）、FULL（大型变更，7 个 Agent + Verifier + Coordinator）。
</objective>

<mental_model>
工作流由脚本控制（确定性），Claude 只做代码分析（推理）。每步输入输出都是文件——不依赖对话上下文传递状态。分档由 classify-diff.py 决定，不由 Claude 判断。
</mental_model>

<critical_rules>
- 分档（Tier）由 classify-diff.py 输出决定，不自行判断
- SESSION_DIR 和 $$ PID 在 workflow 文件中定义，不在此路由器中
- 每个 Agent 完成后验证 findings 文件存在且包含 `### [P` 再继续
- --resume 时必须验证 head_sha 匹配当前 HEAD，代码变更则拒绝恢复
- 所有输出使用中文
</critical_rules>

<routing>
执行完整审查（FULL 档，diff ≥ 400 行或文件数 ≥ 5 或触碰敏感路径）：
  Read `languages/go/workflows/full-review.md`

执行轻量审查（LITE 档，小型变更）：
  Read `languages/go/workflows/lite-review.md`

理解报告输出格式与 finding 字段定义：
  Read `languages/go/templates/report.md`

理解 Context Package 段落格式与 token 预算：
  Read `languages/go/templates/context-package.md`
</routing>

<quick_reference>
```bash
# 审查当前分支 vs main（最常用）
/go-code-review

# 指定分支和基准
/go-code-review --branch feat/xxx --base develop

# 恢复中断的审查（需要 workflow-state.json 存在且代码未变更）
/go-code-review --resume

# 保存完整报告到指定文件
/go-code-review --output report.md
```
</quick_reference>

<flags>
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--branch` | 当前分支 | 待审查的源分支 |
| `--base` | `main` | 基准分支 |
| `--output` | 无 | 将完整报告另存至指定路径 |
| `--resume` | false | 恢复中断的审查（Loop 模式） |
</flags>
