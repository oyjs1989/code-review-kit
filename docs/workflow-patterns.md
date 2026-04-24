# Workflow Control Patterns — 来自 gsd-2 & spec-kit

> 核心问题：**如何让 Claude Code 优雅执行固定流程**。
> 答案来自 gsd-2 的工程化实践：确定性代码控制流程，LLM 只做推理。

---

## 第一原则：确定性 vs LLM 的分工

gsd-2 的核心原则：

> *If you could write an if-else that handles it correctly every time, it should NOT be in the LLM's context. Every token the model spends reasoning about something deterministic is wasted.*

| 谁来做 | 什么工作 |
|--------|---------|
| **脚本（确定性）** | 流程控制、状态转换、文件读写、参数校验、进度报告 |
| **LLM（推理）** | 代码理解、问题判断、建议生成、自然语言输出 |

**对 go-code-review 的意义**：SKILL.md 里目前混合了两类工作。流程控制（步骤顺序、checkpoint、错误处理）应该由脚本完成，Claude 只负责分析代码。

---

## 输入标准化

### gsd-2 模式：spec.md 作为唯一输入契约

```markdown
# Product Name

## What
[一段话，具体描述]

## Requirements
- [用户能做什么，可测试]
- [系统自动做什么]

## Technical Constraints
- Language / Framework / Environment

## Out of Scope
- [明确不包含什么]
```

每个命令的输入结构是固定的。`--context spec.md` 是唯一的用户输入点。

### spec-kit 模式：命令接受 `$ARGUMENTS`，立即存储到状态文件

```markdown
## User Input
$ARGUMENTS

## Outline
1. Ask user for feature directory
2. Write .specify/feature.json  ← 输入立即固化到文件
3. Write spec.md                ← 输出到约定路径
```

**关键原则**：用户输入在第一步就固化到文件，后续步骤从文件读取，不依赖对话上下文。

---

## 输出标准化

### gsd-2 模式：stdout/stderr 分离 + JSON 结构化输出

```bash
# JSON 结果走 stdout，进度信息走 stderr
RESULT=$(gsd headless --output-format json next 2>/dev/null)
EXIT=$?

# 结构化字段，不是自由文本
STATUS=$(echo "$RESULT" | jq -r '.status')
PHASE=$(echo "$RESULT" | jq -r '.phase')
COST=$(echo "$RESULT" | jq -r '.cost.total')
```

输出格式是 schema，不是 prose。调用方用 exit code + JSON 做流程判断，不解析文字。

### 退出码作为状态机信号

```
0  → success  → 继续下一步
1  → error    → 检查错误，重试或终止
10 → blocked  → 需要人工介入
11 → cancelled → resume 或重启
```

**对 go-code-review 的意义**：当前 Python 脚本输出都是 plain text。应该改为 JSON + exit code，让 SKILL.md 的流程控制基于结构化信号，而不是文字解析。

---

## 流程固定化

### gsd-2 模式：状态机 + 文件即状态

```
.gsd/
  STATE.md          ← 当前 phase（确定性，不是 LLM 推断）
  ROADMAP.md        ← 任务勾选（checkbox = source of truth）
  milestones/M001/
    M001-CONTEXT.md ← 该阶段的工作上下文（只包含当前需要的）
    M001-SUMMARY.md ← 完成摘要（50-100 token，高度压缩）
    slices/S01/
      T01-PLAN.md   ← 单任务规格
      T01-SUMMARY.md
```

每个 phase 有独立的 context 文件，切换 phase 时 context 重建，不累积。

### SKILL.md 作为路由器，不作为流程手册

gsd-2 的 SKILL.md 结构：

```markdown
<objective>一句话说你是什么</objective>
<mental_model>用什么心智模型</mental_model>
<critical_rules>6条绝对规则</critical_rules>
<routing>
  做 X → 读 workflows/x.md
  做 Y → 读 workflows/y.md
  理解 Z → 读 references/z.md
</routing>
<quick_reference>最常用的 4 个命令</quick_reference>
```

SKILL.md 不包含流程细节，只包含路由逻辑。细节在 `workflows/` 下的专门文件里。

---

## 上下文工程

### gsd-2 的分层上下文模型

```
L1 工作上下文（每次 LLM 调用动态组装，8k-25k tokens）
  ├── 当前任务规格 + 验收标准  ← 20% token budget
  ├── 活跃代码文件             ← 40% token budget
  ├── 接口契约                 ← 10% token budget
  └── 工具定义                 ← 15% token budget

L2 会话记忆（压缩摘要，不是全量）
L3 项目语义（只存指针，按需拉取）
L4 源代码（filesystem，不在 prompt 里）
```

**关键**：每次 LLM 调用的 context 是**新鲜组装**的，不是上一次的累积。Agent 完成后写入 findings 文件，下次 Agent 读文件，不依赖对话历史。

### 对应 go-code-review 的 Context Package

当前 context-package.md 是一次性全量组装。应该拆分：

```
[Intent]       ← 来自 git log（小，固定）
[Rules]        ← 来自 rules/*.yaml（中，按需选择）
[Change Set]   ← 来自 diff（大，截断策略明确）
[Architecture] ← 来自扫描结果（Full 档专属）
```

每个 section 有独立 token budget。超出时有明确的截断/摘要策略，不是随机截断。

---

## 恢复机制

### gsd-2 模式：session ID + resume

```bash
# 保存 session ID
SESSION_ID=$(echo "$RESULT" | jq -r '.sessionId')

# 恢复
gsd headless --resume "$SESSION_ID" --output-format json next
```

### 对应 go-code-review 的 --resume

```json
// .review/workflow-state.json
{
  "head_sha": "abc123",
  "session_dir": ".review/run-abc123-1234",
  "completed_tasks": ["safety", "data"],
  "pending_tasks": ["design", "quality", "observability"],
  "in_progress_tasks": []
}
```

`--resume` 时：验证 `head_sha` 匹配当前 HEAD（代码未变更），从 `pending_tasks` 继续。这是对的工程化恢复模式。

---

## 文件结构建议（对 go-code-review）

借鉴 gsd-2 的路由模式，当前 SKILL.md 应拆分为：

```
languages/go/
  SKILL.md                    ← 路由器（<100行）
    - objective, mental_model
    - critical_rules
    - routing → workflows/
    - quick_reference

  workflows/
    full-review.md            ← 完整审查流程（当前 SKILL.md 主体）
    lite-review.md            ← 轻量流程
    resume.md                 ← 恢复中断流程

  templates/
    context-package.md        ← Context 组装格式 + token budget
    report.md                 ← 报告输出格式

  references/
    rule-registry.md          ← 规则 ID 说明
    agent-contracts.md        ← 每个 agent 的输入/输出契约

  agents/
    safety.md                 ← （现有，加 frontmatter）
    data.md
    ...
```

---

## 核心结论

| 模式 | spec-kit | gsd-2 | 应用到 go-code-review |
|------|---------|-------|----------------------|
| 命令结构 | Outline（步骤列表） | routing → workflows/ | SKILL.md 做路由，流程在 workflows/ |
| 输入固化 | feature.json | spec.md + --context | 参数解析后立即写 session 状态文件 |
| 输出契约 | spec.md/plan.md 固定格式 | JSON + exit code | findings-{agent}.md 有明确 schema |
| 状态机 | .specify/feature.json | STATE.md + checkbox | workflow-state.json（已有） |
| 上下文组装 | 读上一步输出文件 | 动态组装 L1 context | context-package.md 分 section + token budget |
| 恢复 | 无 | --resume sessionId | --resume + workflow-state.json（已有） |
