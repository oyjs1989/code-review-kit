# 工程化模式参考 — 来自 spec-kit & gsd-2

> 目标：将 spec-kit 和 gsd-2 的 Claude Code 工具工程化模式应用到 go-code-review skill。

---

## 可借鉴的工程化模式

### 1. 命令定义结构（来自 spec-kit）

spec-kit 每个命令是一个极简 markdown 文件：

```markdown
---
description: 一句话描述
---

## User Input
$ARGUMENTS

## Outline
1. 做什么
2. 读/写哪些文件
3. 输出什么
```

**现状问题**：SKILL.md 把命令定义、流程说明、输出模板全混在一起，近 600 行。

**改进方向**：把 Outline（流程逻辑）和 Template（输出格式）分离成不同文件。

---

### 2. 文件状态协议（来自 gsd-2）

gsd-2 的核心工程原则：**结构化状态用 JSON，叙述性内容用 Markdown，绝不混用。**

推荐目录结构：

```
.review/
  workflow-state.json        ← 机器读：phase, pending_tasks, completed_tasks
  run-{sha}/
    context-package.md       ← AI 读：动态组装的 L1 工作上下文
    findings-safety.md       ← Agent 输出
    findings-data.md
    ...
  results/
    review-{timestamp}.md    ← 最终报告（人读）
```

gsd-2 的 "pull-based context" 原则：**不预加载所有内容，按需拉取**。context-package.md 只包含当前任务需要的内容，不是全量 dump。

---

### 3. 输入/输出 Template 分离（两者共有）

spec-kit 的 `spec-template.md` 和 gsd-2 的 task 文件都是**独立模板**，不内嵌在命令逻辑里。

**改进方向**：报告格式从 SKILL.md 中提取，成为独立文件：

```
languages/go/
  SKILL.md                        ← 流程逻辑（How）
  templates/
    report.md                     ← 报告格式模板
    context-package.md            ← Context Package 组装模板
```

SKILL.md 引用模板，模板独立可维护。

---

### 4. 顺序命令链（来自 spec-kit）

spec-kit 的三步链：`/speckit.specify` → `/speckit.plan` → `/speckit.tasks`，每步读上一步的输出文件，状态通过文件传递。

**对应 go-code-review**：

- `/go-code-review` — 完整流程（主入口，保留）
- `/go-code-review --resume` — 读 `workflow-state.json` 恢复中断，已有，对的

无需强制拆分命令，但 `--resume` 的状态文件协议要严格定义。

---

### 5. Agent Brief 格式（来自 gsd-2 task files）

gsd-2 的任务文件使用 YAML frontmatter + Markdown body：

```yaml
---
status: in_progress
acceptance_criteria:
  - 输出包含所有 P0 findings
  - 置信度 < 0.75 的条目被过滤
---
## 任务描述
...
```

**改进方向**：当前 `agents/*.md` 是纯 prompt，无结构化输出契约。可以加 frontmatter：

```yaml
---
agent: safety
output_file: findings-safety.md
required_sections: [findings, summary]
---
```

让 SKILL.md 能程序化地验证 agent 输出格式。

---

## 对 go-code-review 最直接的 3 个改进

| 模式 | 当前状态 | 借鉴后 |
|------|---------|--------|
| 模板分离 | 报告格式内嵌在 SKILL.md | `templates/report.md` 独立文件 |
| Agent 输出契约 | 纯 prompt，无结构 | YAML frontmatter 定义 `output_file` + `required_sections` |
| Context 组装 | 内嵌在流程脚本里 | `templates/context-package.md` 定义组装格式 |

已经对的（无需改动）：

- `.review/workflow-state.json` — 符合 gsd-2 结构化状态原则
- `[1/N]` 进度显示 — 符合 spec-kit 步骤透明度原则
- `--resume` 恢复机制 — 符合 gsd-2 checkpoint 模式

---

## 参考来源

- `spec-kit/presets/lean/commands/speckit.specify.md` — 命令定义结构
- `spec-kit/presets/lean/commands/speckit.plan.md` — 文件状态传递
- `gsd-2/docs/dev/building-coding-agents/03-state-machine-context-management.md` — 分层上下文架构
- `gsd-2/docs/dev/building-coding-agents/04-optimal-storage-for-project-context.md` — 文件存储协议
