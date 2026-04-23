# Go AI Code Review Skill — 设计文档

## 1. 系统概述

### 1.1 目标

构建一套 Claude Code Skill，工作流由 Skill 规范约束，由开发者在本地手动触发（或集成到 CI/CD），对当前分支的代码变更执行多维度审查，结果输出到终端和本地报告文件。

确定性步骤（git 操作、分流判断、Tier 1/2 扫描、Context 组装、findings 聚合过滤、输出格式化）由 Python/shell 脚本实现，Claude Code 通过 Bash tool 调用；AI 分析步骤（专家审查、Verifier）由 Claude Code 通过 Agent tool 派发子 Agent 执行。

**除 Claude Code 外，无任何外部服务依赖（不需要 Anthropic SDK）。**

**核心指标：**
- 误报率 FPR < 10%
- 单次审查输出问题上限 15 条

### 1.2 触发方式

Skill 通过 Claude Code slash command 触发：

```
/go-code-review                        # 审查当前分支 vs main 的变更
/go-code-review --branch feat/xxx      # 指定源分支
/go-code-review --base main            # 指定对比基准分支
/go-code-review --output report.md     # 额外输出本地 Markdown 报告
/go-code-review --resume               # 恢复中断的 Full 档审查
```

Skill 文件注册于 `languages/go/SKILL.md`，frontmatter 声明 `allowed-tools`：Bash、Agent、Read、Write、Glob、Grep。

### 1.3 系统边界

```
开发者调用 Skill
      │
      ▼
┌──────────────────────────────────────────────────────┐
│                  Claude Code Skill                   │
│                                                      │
│  Bash(scripts)  →  Agent(experts)  →                │
│  Bash(aggregate-findings.py)  →  Write(report)      │
│                      ↑                               │
│                 Loop（大型变更）                      │
└──────────────────────────────────────────────────────┘
      │
      ▼
终端输出 + .review/results/review-{timestamp}.md
```

---

## 2. 主流程设计

### 2.1 流程总览

```
开发者执行 skill
    │
    ▼
步骤 1：代码获取
    │
    ▼
步骤 2：变更分析与分流
    │
    ├── Trivial ──→ 总结 Agent → 输出摘要 → [结束]
    │
    ├── Lite ──→ 步骤 3 → 步骤 4（基础 Agent）→ 步骤 5 → 步骤 6
    │
    └── Full ──→ 步骤 3 → 步骤 3.5（架构预扫描）→ 步骤 4（全量 Agent + Loop）→ 步骤 5 → 步骤 6
```

---

### 步骤 1：代码获取

**输入：** skill 参数（分支名 / 基准分支）

**输入模板：**
```json
{
  "source_branch": "string",    // --branch，默认为当前所在分支
  "base_branch": "main",        // --base，默认为 "main"
  "output_file": "string | null" // --output，null 表示不生成报告文件
}
```

**操作：**
1. 通过 `git rev-parse` 确定 base SHA 和 head SHA
2. 执行 `git diff base_branch...source_branch` 获取完整 Diff
3. 执行 `git show` 提取变更行所在的完整函数原文
4. 读取本地规范文件（查找顺序见步骤 3）
5. 读取 `git log --oneline -5` 获取最近提交摘要（用于理解变更意图）

**输出：**
```json
{
  "base_sha": "abc123",
  "head_sha": "def456",
  "diff_raw": "...",
  "files_changed": ["src/auth.go", "..."],
  "diff_lines": 320,
  "recent_commits": "最近 5 条提交摘要",
  "project_rules": "规范文件内容"
}
```

**异常处理：** 非 git 仓库 / 分支不存在 → 终端报错并终止

**完成标准（Checkpoint）：**
- ✓ `diff_raw` 非空，`diff_lines > 0`
- ✓ `files_changed` 不为空
- ✓ `project_rules` 已填充（任意来源均可，空字符串表示使用内置规范）

---

### 步骤 2：变更分析与分流

**输入：** 步骤 1 输出

**分流规则（按优先级顺序判断）：**

| 档位 | 条件 | 下一步 |
|------|------|--------|
| **Trivial** | `diff_lines < 20` 且所有变更文件均属于以下类型之一：文档类（`.md`、`.txt`、`.rst`）、配置类（`.yml`、`.yaml`、`.toml`、`.json`、`.ini`、`.env.example`）、注释变更的 `.go` 文件（变更行 100% 为注释行，即以 `//` 开头或在 `/* */` 块内） | 总结 Agent → 输出摘要 |
| **Lite** | `20 <= diff_lines < 400` 且 `files_changed < 5` 且未触及敏感路径 | 基础安全 + 性能 Agent |
| **Full** | `diff_lines >= 400` 或 `files_changed >= 5` 或路径匹配敏感模块 | 全量专家 Agent + Loop |

**敏感路径正则：** `(auth|crypto|payment|permission|admin)/`

**执行：** Claude 调用 `Bash(python3 languages/go/tools/classify-diff.py --diff-lines $diff_lines --files-changed $files_changed --files "$file_list")`

**输出：**
```json
{
  "tier": "FULL",
  "trigger_reason": "diff_lines=620",
  "agent_roster": ["safety", "data", "design", "quality", "observability", "business", "naming"],
  // Lite 档：["safety", "quality", "observability"]
  "rules_source": "project_redlines | project_rules | built_in",
  "has_redlines": true
}
```

> `rules_source` 说明：
> - `project_redlines`：找到 `.claude/review-rules.md`，其条目视为**不可降级红线**
> - `project_rules`：找到 AGENTS.md / CLAUDE.md 等，作为普通参考规范
> - `built_in`：均未找到，使用内置通用 Go 审查规范兜底

**完成标准（Checkpoint）：**
- ✓ `tier` 已确定（TRIVIAL / LITE / FULL）
- ✓ `agent_roster` 不为空（TRIVIAL 档除外）
- ✓ `rules_source` 已确定，`has_redlines` 已标记

---

### 步骤 3：上下文组装

**输入：** Diff、分流结果

**上下文来源（全部本地，无网络请求）：**

| 类型 | 来源 | 用途 |
|------|------|------|
| 变更代码原文 | `git show` 提取变更函数完整定义 | 语义连贯性 |
| 项目规范 | 本地 md 文件 | 注入审查规则 |
| 变更意图 | `git log` 最近提交摘要 | 理解变更目的 |

**规范文件查找顺序（找到即停止）：**
1. `.claude/review-rules.md`
2. `AGENTS.md`
3. `CLAUDE.md`
4. `languages/go/SKILL.md`
5. `docs/` 目录下 `*style*`、`*rule*`、`*convention*` 命名的 md 文件

若均不存在，使用内置通用 Go 审查规范兜底。

**拼装格式：**
```markdown
## [Intent]
{git log 最近提交摘要}

## [Rules]
{本地规范文件内容}

## [Change Set]
{Diff 原文}

## [Context]
{变更函数完整定义}

（以下 section 仅 Full 档，由步骤 3.5 完成后追加注入，步骤 3 初始产物不含此块）
## [Architecture Context]
{architecture_context — 分层结构、高风险模块、关键 interface 摘要}
```

**截断规则：** Change Set 优先保留全文；Rules 超过 4k Token 时截取与变更模块相关段落；Context 超限时只保留函数签名。

**执行：** Claude 调用 `Bash(python3 languages/go/tools/assemble-context.py --diff /tmp/diff.txt --rules-source $rules_source --git-log /tmp/gitlog.txt > /tmp/context-package.md)`

**输出：** Context Package（Markdown 格式，写入 `/tmp/context-package.md`）

**输出模板：**
```markdown
## [Intent]
feat: add OAuth2 login support
fix: resolve token expiry race condition

## [Rules]
# 安全规范
- 所有外部输入必须验证
- 禁止在日志中记录敏感字段（token、password）
...

## [Change Set]
diff --git a/src/auth/login.go b/src/auth/login.go
index abc123..def456 100644
--- a/src/auth/login.go
+++ b/src/auth/login.go
@@ -42,7 +42,12 @@ func UserLogin(db *sql.DB, username, password string) ...

## [Context]
// 变更函数完整定义
func UserLogin(db *sql.DB, username, password string) (*User, error) {
    ...
}

// 直接调用方
func HandleLoginRequest(w http.ResponseWriter, r *http.Request) {
    ...
}
```

**Context Package 元数据：**
```json
{
  "estimated_tokens": 8200,
  "token_limit": 16000,
  "sections_included": ["intent", "rules", "change_set", "context"],
  "truncated_sections": []
}
```

> `sections_included` 初始值为 `["intent", "rules", "change_set", "context"]`。Full 档步骤 3.5 完成后，若 `architecture_context` 非空，追加为 `["intent", "rules", "change_set", "context", "architecture_context"]`，`estimated_tokens` 同步重新估算。

**完成标准（Checkpoint）：**
- ✓ Context Package 包含 `[Intent]` / `[Rules]` / `[Change Set]` / `[Context]` 四个 section
- ✓ `estimated_tokens < 16000`
- ✓ `"change_set"` 不在 `truncated_sections` 中（若在，降档为 Lite 处理并告知用户）

---

### 步骤 3.5：架构预扫描（仅 Full 档）

**触发条件：** `tier == FULL`

**输入：** 步骤 1 输出（files_changed、diff_raw）

**操作：**
1. 读取 `go.mod`，获取模块名和主要外部依赖列表
2. 扫描变更文件所在目录，提取 `package` 声明、主要 `interface` 和 `struct` 定义（不读函数体）
3. 识别本次变更涉及的模块边界（哪些 package 被修改、互相调用关系）
4. 标记高风险模块（匹配敏感路径正则的 package）

**输入模板：**
```json
{
  "files_changed": ["src/auth/login.go", "src/service/order.go"],
  "diff_summary": "变更函数列表及各文件行数"
}
```

**输出模板：**
```json
{
  "module_map": {
    "auth": ["login.go", "middleware.go"],
    "service": ["order.go", "user.go"]
  },
  "high_risk_modules": ["auth"],
  "key_interfaces": [
    "type AuthService interface { Login(...) }",
    "type OrderRepository interface { FindByID(...) }"
  ],
  "architecture_context": "分层架构：handler → service → repository，auth 为核心安全模块，service 层禁止直接访问 DB",
  "skipped_files": []
}
```

**用途：** 将 `architecture_context` 注入所有 Full 档 Subagent 的 `[Architecture Context]` 块，赋予每个 Agent 全局架构视角，避免孤立看片段时的误判（尤其是架构边界违反和跨层调用问题）。

**注入行为：** 步骤 3.5 完成后，将 `architecture_context` 以 `## [Architecture Context]` section 追加到步骤 3 产出的 Context Package 末尾。Context Package 元数据中 `sections_included` 同步更新（添加 `"architecture_context"`），`estimated_tokens` 重新估算。若步骤 3.5 超时跳过，Context Package 保持不变，无 `[Architecture Context]` section。

**执行：** Claude 调用 `Bash(python3 languages/go/tools/scan-architecture.py --files "$files_changed" > /tmp/architecture-context.json)`

**异常处理：** 预扫描超时（> 30s）或 go.mod 不存在 → 跳过，`architecture_context` 置为空字符串，其余步骤正常继续。

**完成标准（Checkpoint）：**
- ✓ `architecture_context` 已生成（超时/缺失时为空字符串，不阻塞后续步骤）
- ✓ `module_map` 包含本次变更涉及的所有 package
- ✓ `high_risk_modules` 已标记（无高风险模块时为空数组）

---

### 步骤 4：Agent 审查执行

**流程管控机制：**
Skill 规范约束 Claude 严格按顺序执行：先运行 golangci-lint（Bash tool），再顺序派发专家子 Agent（Agent tool），每步完成后验证输出文件存在性（Bash tool），文件缺失则终端报错并终止。所有 AI 分析仅在专家 Subagent 和 Verifier 执行期间进行，其余步骤为确定性 shell/Python 脚本。

**输入：** Context Package、分流结果（agent_roster）

**lint 与 Agent 的分工：**

| 层 | 工具 | 负责内容 |
|----|------|---------|
| 机械层 | `golangci-lint` | 格式、简单静态错误、基础安全模式、基础性能警告 |
| 语义层 | 专家 Subagent | 业务逻辑安全、架构边界、复杂运行时问题、规范语义 |

两者**顺序运行**，结果在步骤 5 合并。每个专家 Agent 作为独立 Subagent 执行，互不干扰。

#### 4.1 普通变更（Lite / 小型 Full）

```
Context Package
      │
      ▼
[Bash: golangci-lint run ... → 格式化] ──→ [写 .tmp/findings-lint.md]
      │
      ▼
[FAN_OUT: Claude 顺序通过 Agent tool 派发 Subagent]
      │  Lite: 3 个  Full: 7 个 + Verifier
      ├──→ Agent(safety)       ──→ [写 .tmp/findings-safety.md]
      ├──→ Agent(quality)      ──→ [写 .tmp/findings-quality.md]
      ├──→ Agent(observability)──→ [写 .tmp/findings-observability.md]
      │   （以上 3 个为 Lite 档；Full 档继续派发：）
      ├──→ Agent(data)         ──→ [写 .tmp/findings-data.md]
      ├──→ Agent(design)       ──→ [写 .tmp/findings-design.md]
      ├──→ Agent(business)     ──→ [写 .tmp/findings-business.md]
      └──→ Agent(naming)       ──→ [写 .tmp/findings-naming.md]
                                                        │
      [FAN_IN: 顺序执行后 Claude 执行 Bash 合并]
      [Bash: cat .tmp/findings-*.md > .tmp/all-findings.md]
                                                        │
                  [SEQUENTIAL] Agent(verifier)（仅 P0/P1）
                                                        │
                                                   步骤 5 聚合
```

**派发标记说明：**

| 标记 | 执行单元 | 前置条件 |
|------|---------|---------|
| `[Bash]` | golangci-lint | 无；FAN_OUT 前运行 |
| `[Agent tool]` | safety | 无 |
| `[Agent tool]` | quality | 无 |
| `[Agent tool]` | observability | 无 |
| `[Agent tool]` | data | **仅 Full 档** |
| `[Agent tool]` | design | **仅 Full 档** |
| `[Agent tool]` | business | **仅 Full 档** |
| `[Agent tool]` | naming | **仅 Full 档** |
| `[Agent tool: 以上全部完成后]` | verifier | 仅对 P0/P1 findings 执行对抗验证 |

#### 4.2 大型变更（Full + Loop 模式）

当 `diff_lines >= 400` 时启动 Loop：

**拆分策略：**
1. 用 AST 提取变更涉及的函数调用图
2. 将逻辑相关的变更聚类为一个"任务包"（互相调用的函数归为同一包）
3. 单个任务包代码量控制在 **150 行**以内
4. 任务包数量上限 **20 个**，超出则合并低优先级包

**Skill 约束**：Loop 由 Skill 规范约束 Claude 执行，最多迭代 20 次（`task_packs` 上限即为 20 个）。Claude 在每次迭代前更新 `workflow-state.json`，完成后验证 findings 文件存在性，失败则终止。

**Loop 模式 Context 分发规则：**

Loop 模式下，每个 Subagent 收到的是**任务包局部 Context**（非全量 Context Package），结构如下：

```markdown
## [Intent]
{git log 最近提交摘要（全量，始终保留）}

## [Rules]
{本地规范文件相关段落（截取至 300 行，同全量）}

## [Architecture Context]
{architecture_context（Full 档始终保留）}

## [Change Set — 当前任务包]
{当前任务包（≤150 行）的 diff 片段}

## [Context — 当前任务包]
{当前任务包中变更函数的完整定义 + 直接调用方}
```

全量 Context Package（步骤 3 产物）仅用于步骤 3.5 架构预扫描和 Verifier Agent；专家 Subagent 只接收任务包局部 Context。

**task_id 命名规范：** `task-{pack_index}:{agent_type}`，例如 `task-2:safety`、`task-2:quality`。同一任务包的不同 Agent 共享 `pack_index`，便于 `workflow-state.json` 按包分组和人工排查。

**单任务包重试上限：** Subagent 无响应或超时时最多重试 **2 次**；仍失败则在 `workflow-state.json` 中记录 `status: skipped`，继续执行其余任务包，最终报告中标注跳过原因。

**Loop 执行（Subagent 顺序）：**
```
生成任务队列 [Task-1, Task-2, ..., Task-N]
      │
      ▼
识别任务包之间的依赖关系
      │
      ├── 无依赖的任务包 ──→ 写入 in_progress → [FAN_OUT] 顺序派发给多个 Subagent
      │                              │
      │                    Subagent 完成 → 写入 completed / skipped
      │                              │
      │                     [FAN_IN] 本批次全部完成（顺序执行后自动）
      │
      └── 有依赖的任务包 ──→ 前置 [FAN_IN] 完成后串行执行
              │
              ▼
      所有任务包完成 → 全局聚合审查
```

**状态文件 `workflow-state.json`：**

任务包状态三态：`pending → in_progress → completed | skipped`。每个任务包**开始执行前**立即写入 `in_progress`，完成后更新为 `completed`；异常崩溃重启时，处于 `in_progress` 的任务包视为未完成，重新执行。

```json
{
  "head_sha": "def456",
  "completed_tasks": [
    {
      "task_id": "task-1:safety",
      "files": ["src/auth.go"],
      "summary": "发现 1 个 SQL 注入风险，已记录",
      "findings_count": 1,
      "status": "completed"
    }
  ],
  "in_progress_tasks": ["task-2:safety", "task-2:quality"],
  "pending_tasks": ["task-3:safety", "task-3:quality"],
  "skipped_tasks": [
    {
      "task_id": "task-4:design",
      "reason": "retry_exceeded",
      "retry_count": 2
    }
  ]
}
```

**每个 Agent 输出（Markdown finding 格式，写入 `.tmp/findings-{agent}.md`）：**
```markdown
### [P0] SAFE-003 · src/auth.go:42-47

**SQL Injection vulnerability in user_login()**

**建议：** 使用参数化查询替代字符串拼接
**置信度：** 0.98
**needs_clarification：** null
```

> `rule_id` 格式：`SAFE-NNN`（安全）、`DATA-NNN`（数据）、`QUAL-NNN`（质量）、`OBS-NNN`（可观测性）、`PERF-NNN`（性能）、`ARCH-NNN`（架构）、`BIZ-NNN`（业务逻辑）、`LINT-NNN`（静态检查）。完整映射见 §4.6。
>
> `needs_clarification`：当 Agent 无法独立判定问题是否成立时填写（如"无法确认此函数的调用方是否已做鉴权"），终端输出时以 `[?]` 标注提示开发者人工判断；确定问题则为 `null`。

**严重等级定义：**
- P0：安全漏洞、生产崩溃风险
- P1：显著业务逻辑错误
- P2：性能优化、架构建议
- P3：代码风格、命名规范

**Findings 传递机制：**

每个专家 Subagent 通过 Write tool 将 findings 写入临时文件：
```
.tmp/findings-lint.md
.tmp/findings-safety.md
.tmp/findings-quality.md
.tmp/findings-observability.md
.tmp/findings-data.md         （仅 Full 档）
.tmp/findings-design.md       （仅 Full 档）
.tmp/findings-business.md     （仅 Full 档）
.tmp/findings-naming.md       （仅 Full 档）
```

FAN_IN 后，Claude 执行 Bash 合并：
```bash
cat .tmp/findings-*.md > .tmp/all-findings.md
```

Verifier Agent 读取 `.tmp/all-findings.md` 中 P0/P1 条目作为输入。

**完成标准（Checkpoint）：**
- ✓ 所有 `agent_roster` 中的 Subagent 均已写入对应 `.tmp/findings-{agent}.md`（文件可为空，表示无发现）
- ✓ `.tmp/all-findings.md` 已生成（Bash 合并完成）
- ✓ Loop 模式下：`workflow-state.json` 中 `pending_tasks` 为空

---

### 步骤 5：结果聚合与误报过滤

**输入：** `.tmp/all-findings.md`（经 Verifier 核实后的聚合 findings）

```
原始 findings
      │
      ▼
① 去重（规则匹配，无需向量计算）
  - 相同文件 + 相同行号 + 相同 category → 合并，取最高严重等级
  - 相同文件 + 相邻行（±3 行）+ 相同 category → 合并
      │
      ▼
② 红线优先（仅当 rules_source == "project_redlines"）
  - 来源于 .claude/review-rules.md 的 findings → 强制 severity >= P1
  - 即使 confidence < 0.75 也保留（不受③过滤）
  - 仅 review:ignore 注释可显式豁免，其他过滤规则对红线 findings 无效
      │
      ▼
③ 误报过滤
  - review:ignore 注释：含 `// review:ignore <category>` 的行跳过对应类别
  - 静态工具反证：语法级警告经 golangci-lint 反校验，工具报 OK 则降级为 P3
  - Verifier Agent：对 P0/P1 执行对抗验证，通不过则保留
      │
      ▼
④ 置信度过滤：仅保留 confidence >= 0.75（红线 findings 豁免此步骤）
      │
      ▼
⑤ 模糊发现截断
  - 同一 category 内 confidence < 0.85 的 findings 最多保留 3 条
  - 超出部分合并为一条 P3 摘要性建议（"另有 N 条低置信度 [category] 建议，详见报告附录"）
      │
      ▼
⑥ 优先级排序：Severity（P0→P3）→ Confidence → Business Impact
      │
      ▼
⑦ 数量截断：取前 15 条输出，剩余写入报告附录
```

**执行：** Claude 调用 `Bash(python3 languages/go/tools/aggregate-findings.py --findings-dir .tmp --redlines $redlines_file --max-output 15 > .review/results/review-$timestamp.md)`

**输出：** `.review/results/review-{timestamp}.md` + 终端摘要

步骤 5 不产生 JSON 中间态，最终 Markdown 报告即为输出（格式见步骤 6 终端输出格式）。

**完成标准（Checkpoint）：**
- ✓ `.review/results/review-{timestamp}.md` 已生成，finding 数量 ≤ 15
- ✓ 红线 findings 未被置信度过滤丢弃
- ✓ 审查覆盖文件数 + 跳过文件数 == `files_changed` 总数

---

### 步骤 6：结果输出（本地）

**输入：** 最终 findings 列表（≤15 条）

**终端输出格式：**
```
════════════════════════════════════
  Go Code Review 结果
════════════════════════════════════

[P0] SAFE-003  src/auth.go:42-47  SECURITY
  SQL Injection vulnerability in user_login()
  建议：使用参数化查询替代字符串拼接

[P2] PERF-007  src/service.go:88  PERFORMANCE
  goroutine 泄漏风险：channel 未设超时
  建议：添加 context 超时控制

[P1][?] SAFE-011  src/api/handler.go:55  SECURITY
  无法确认此接口是否经过鉴权中间件，若已在 router 层统一处理则不成立
  建议：人工确认调用链上的鉴权位置

────────────────────────────────────
  共 11 条问题（P0:1 P1:2 P2:5 P3:3），其中 1 条待人工确认 [?]
  审查覆盖：12/14 文件（2 个文件被跳过）
  ⚠ 跳过：src/legacy/migrate.go（上下文超限）
           src/gen/pb.go（自动生成文件）
  完整报告：./review-report.md
════════════════════════════════════
```

**本地报告文件（`--output` 指定时生成）：** Markdown 格式，包含全部 findings（含超出 15 条的附录部分）及每条问题的完整上下文。

**报告文件模板（`--output report.md`）：**
````markdown
# Go Code Review Report

- **Branch:** feat/xxx → main
- **Commits:** abc123..def456
- **Files Changed:** 12
- **Generated:** 2026-04-23 10:30:00

## Summary

| Severity | Count |
|----------|-------|
| P0 | 1 |
| P1 | 2 |
| P2 | 5 |
| P3 | 3 |

## Review Assumptions

> 本节由 Review Coordinator 自动生成，描述本次审查的边界与假设。

- `auth/` 模块被识别为核心安全边界，已完整审查
- `src/gen/` 目录为自动生成文件，已跳过
- 未在 go.mod 中找到 Redis 客户端，goroutine 泄漏分析基于函数内部可见范围
- `.claude/review-rules.md` 已加载（v1.2.0），规则作为红线约束，违反时 severity >= P1

## Findings

### [P0] SAFE-003 · src/auth/login.go:42-47 · SECURITY

**SQL Injection vulnerability in user_login()**

```go
query := "SELECT * FROM users WHERE username='" + username + "'"
rows, err := db.Query(query)
```

**建议：** 使用参数化查询替代字符串拼接
**置信度：** 0.98 | **规则：** SAFE-003 | **来源：** security agent

---

### [P1][?] SAFE-011 · src/api/handler.go:55 · SECURITY

**⚠ 需人工确认：** 无法确认此接口是否经过鉴权中间件，若已在 router 层统一处理则不成立

**建议：** 确认调用链上的鉴权位置
**置信度：** 0.71 | **规则：** SAFE-011

---

## Appendix — Additional Findings (>15)

> 以下问题因数量截断未在终端显示，完整记录于此。

### [P3] QUAL-004 · src/service/order.go:88 · STYLE
...
````

---

## 3. Agent 设计

### 3.1 协调 Agent（Review Coordinator）

**职责：** 生成 Review Assumptions（审查边界与假设说明）+ 将步骤 5 过滤后的 findings 格式化为最终报告。不做过滤、去重、排序——这些由步骤 5 确定性脚本完成。

**输入：** Context Package + 步骤 5 输出的过滤后 findings

**输入模板：**
```markdown
## [Context Package]
{同步骤 3 输出的 Context Package（含 architecture_context）}

## [Filtered Findings]
{步骤 5 脚本输出的过滤后 findings（已去重、排序、截断至 ≤15 条）}

## [Coverage Summary]
files_reviewed: 12 / 14
skipped: src/gen/pb.go（auto_generated）, src/legacy/migrate.go（context_overflow）
rules_source: project_redlines（v1.2.0）
```

**输出：** `./review-report.md`（最终报告，含 Review Assumptions 节）

**输出模板：**
```markdown
## Review Assumptions

- `auth/` 模块被识别为核心安全边界，已完整审查
- `src/gen/` 目录为自动生成文件，已跳过
- 未在 go.mod 中找到 Redis 客户端，goroutine 泄漏分析基于函数内部可见范围
- `.claude/review-rules.md` 已加载（v1.2.0），规则作为红线约束

## Findings

{将 Filtered Findings 原样格式化为报告 Findings 节}
```

**Prompt 结构：**
```
[System]
你是代码审查报告生成器。你的任务只有两件：
1. 根据 Context Package 生成 Review Assumptions——描述本次审查的覆盖边界、跳过原因、使用的规则版本、关键架构假设。
2. 将传入的 findings 原样格式化到报告中，不要修改、过滤或重新排序。

不要自行分析代码，不要增减 findings。

[Output Format]
输出完整的 review-report.md，包含 Review Assumptions 节和 Findings 节。

[Context Package]
{Context Package 内容}

[Coverage Summary]
{文件覆盖情况}
```

---

### 3.2 safety Agent

**职责：** 并发安全、错误处理、nil 安全、资源泄漏、认证鉴权边界。

**Prompt 来源：** `languages/go/agents/safety.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<safety.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-safety.md`（由子 Agent 通过 Write tool 写入）

---

### 3.3 data Agent

**职责：** 数据库操作、GORM 模式、事务边界、N+1 查询、数据序列化。

**Prompt 来源：** `languages/go/agents/data.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<data.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-data.md`

---

### 3.4 design Agent

**职责：** 架构边界、分层结构、UNIX 哲学、接口设计、依赖关系。

**Prompt 来源：** `languages/go/agents/design.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<design.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-design.md`

---

### 3.5 quality Agent

**职责：** 代码复杂度、可读性、函数职责单一性、测试覆盖缺口。

**Prompt 来源：** `languages/go/agents/quality.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<quality.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-quality.md`

---

### 3.6 observability Agent

**职责：** 日志分层策略、错误消息质量、日志级别、trace 上下文传递。

**Prompt 来源：** `languages/go/agents/observability.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<observability.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-observability.md`

---

### 3.7 business Agent

**职责：** 业务意图还原、状态机完整性、幂等性、权限归属、业务约束校验。

**Prompt 来源：** `languages/go/agents/business.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<business.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-business.md`

---

### 3.8 naming Agent

**职责：** 命名语义、Go 惯用命名规范、导出/非导出一致性、注释完整性。

**Prompt 来源：** `languages/go/agents/naming.md`

**派发方式：** `Agent(subagent_type="general-purpose", prompt=<naming.md内容 + Context Package>)`

**findings 文件：** `.tmp/findings-naming.md`

---

### 3.9 Verifier Agent（核实者）

**职责：** 对 P0/P1 findings 执行对抗性验证，通过反向思考降低误报率。不产生新的 findings，只对已有结论做 confirm / downgrade / dismiss 判断。

**触发条件：** 步骤 4 所有专家 Subagent 完成后，串行执行，仅处理 severity == P0 或 P1 的条目。

**输入模板：**
```markdown
## [Context Package]
{同步骤 3 输出的 Context Package（Intent + Change Set + Context）}

## [P0/P1 Findings to Verify]
{.tmp/all-findings.md 中严重等级为 P0 或 P1 的 findings sections}
```

**输出模板：**
```markdown
### SAFE-003 — confirm

**理由：** 确认问题成立，call chain 中无其他防护机制

### SAFE-011 — downgrade (P0→P1)

**理由：** 部分场景下已有防护，但边缘路径仍存在风险
**修订置信度：** 0.82
```

`verdict` 说明：
- `confirm`：问题成立，维持原 severity 和 confidence
- `downgrade`：问题可能成立但不够严重，调低 severity（如 P0→P1）或降低 confidence
- `dismiss`：经反向推理，问题不成立（如已有其他机制防护），从 findings 中移除

**Prompt 结构：**
```
[System]
你是代码审查的核实者，采用对抗性验证逻辑。
你的任务：对每条 P0/P1 问题，尝试证伪它。
步骤：
1. 原文输出正在核实的代码片段
2. 尝试找到 3 个理由证明该问题"不成立"（如：已有防护、调用方已处理、范围不可达）
3. 若 3 个理由均不成立，输出 confirm；若有 1-2 个理由有效，输出 downgrade；若核心理由有效，输出 dismiss

不要产生新 findings。
输出 Markdown，每条 verdict 用 ### rule_id — verdict 格式作为标题。

[Context]
{代码原文 + 直接调用方}

[Findings to Verify]
{P0/P1 findings 列表（来自 .tmp/all-findings.md）}
```

---

## 4. 关键机制

### 4.1 Agent 代码阅读结构：总 — 分 — 总

每个专家 Agent 必须遵循三段式阅读结构，**每阶段都需输出正在阅读的业务代码内容**（防止幻觉）：

```
┌─────────────────────────────────────────┐
│  第一总：全局视角                         │
│  - 理解整体业务意图                      │
│  - 识别模块边界和架构层级                │
│  - 输出：业务逻辑摘要                    │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  分：局部视角（Loop 在此展开）            │
│  对每个任务包逐一执行：                  │
│  1. 原文输出当前审查的代码片段           │
│  2. 针对该片段进行细节审查              │
│  3. 输出该片段的 findings               │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  第二总：反思视角                         │
│  - 整体设计是否合理                     │
│  - 检查跨任务包的关联问题               │
│  - 实现是否符合业务意图                 │
└─────────────────────────────────────────┘
```

| 阶段 | 视角 | 主要关注 |
|------|------|---------|
| 第一总 | 全局 | 架构层、整体业务逻辑、模块边界 |
| 分 | 局部 | 具体细节、规范、局部逻辑、安全/性能细节 |
| 第二总 | 反思 | 设计合理性、实现与意图的一致性 |

---

### 4.2 上下文长度约束

**各阶段输入限制：**

| 阶段 | 内容 | 上限 |
|------|------|------|
| 第一总 | 文件名 + 函数签名 + 变更行 | 200 行 |
| 分（单次） | 代码片段原文 + 直接调用方 | 150 行 |
| 第二总 | 各片段分析结论摘要 | 100 行 |
| Rules 注入 | 本地规范文件 | 300 行 |

**超限处理：**
- 第一总超限 → 仅保留函数签名，跳过函数体
- 分阶段单片段超限 → 按逻辑块（条件分支、循环体）拆分为子片段
- Rules 超限 → 优先保留与变更模块相关段落
- 第二总超限 → 仅保留 P0/P1 findings 摘要

**整体 Context 上限：16000 Token**，超出时优先裁减顺序：

```
保留（高优先级）       裁减（低优先级）
  代码原文               间接调用方函数体
  直接函数定义           注释说明文字
  Rules 红线规则         已完成任务详细摘要
```

**高风险优先：** 多文件超限时，敏感路径（`auth/`、`payment/` 等）文件优先保留完整上下文。

---

### 4.3 Subagent 编排原则

**核心原则：编排确定性由两层保证，AI 不确定性严格封装在单步内。**

**【层 1】Python/shell 脚本（确定性工具层）：**
- git 操作、Tier 1/2 扫描、分流判断、Context 组装、架构预扫描、findings 聚合过滤
- 完全确定性，无 AI 介入；由 Claude 通过 Bash tool 调用

**【层 2】Skill 规范约束 Claude Code（流程控制层）：**
- Skill 按步骤顺序执行，每步完成后验证输出文件存在性（Checkpoint）
- 文件缺失则终端报错并终止，不会跳步或绕过
- 所有 AI 分析通过 Agent tool 顺序派发，Claude 通过 Write tool 维护 `workflow-state.json`

| 职责 | 由谁负责 | 稳定性 |
|------|---------|--------|
| 执行顺序、条件判断、路由决策 | Skill 规范 + shell/Python 脚本 | 100% 可预期 |
| 暂停/恢复、状态持久化 | workflow-state.json（Write tool） | 幂等，可回溯 |
| 生成内容（findings） | 专家 Subagent（Agent tool） | 非确定，仅影响单步输出 |

**顺序执行规则：**

| 情况 | 处理方式 |
|------|---------|
| 不同审查维度（safety vs data vs design） | 顺序（Skill 规范约束 Claude 依次调用 Agent tool） |
| 不同任务包（无调用关系） | 顺序 |
| 同一任务包的不同审查维度 | 顺序 |
| 有调用依赖的任务包（A 调用 B） | 串行，先审 B |
| 第二总（反思）阶段 | 串行，等所有"分"完成 |

**数量控制：**
- Lite：Bash(golangci-lint) + 顺序调用 3 次 Agent tool（safety + quality + observability）
- Full：Bash(golangci-lint) + 顺序调用 7 次 Agent tool + verifier 1 次（共 8 次 Agent tool）
- 每次 Agent tool 完成后，Claude 验证 `.tmp/findings-{agent}.md` 存在性，缺失则终止
- 每个 Subagent 的 prompt = `languages/go/agents/{agent}.md` 内容 + Context Package

**状态同步：** 子 Agent 完成后通过 Write tool 写入 `.tmp/findings-{agent}.md`，Claude 读取汇总，子 Agent 间不直接通信。

**`workflow-state.json` 存储说明：** 由 Claude 通过 Write tool 维护，存储于 `.review/workflow-state.json`，生命周期仅限于当次 Loop 审查会话（`--resume` 用于跨会话恢复）。

---

### 4.4 规范文件管理

| 文件 | 内容 |
|------|------|
| `.claude/review-rules.md` | 项目专属审查红线（优先读取） |
| `AGENTS.md` | AI 协作规范 |
| `CLAUDE.md` | 项目规范 |
| `docs/style-guide.md` | 代码风格规范 |

均不存在时使用内置通用 Go 审查规范兜底。

**规则优先级栈（三层覆盖模型）：**

```
Layer 3（最高优先级）：.claude/review-rules.md
  └── 条目视为不可降级红线；severity 强制 >= P1；
      confidence < 0.75 时不过滤；仅 review:ignore 可豁免
        ↓ 覆盖
Layer 2：AGENTS.md / CLAUDE.md / docs/style-guide.md
  └── 作为普通参考规范；受置信度过滤；可被 review:ignore 抑制
        ↓ 兜底
Layer 1（最低优先级）：内置通用 Go 审查规范
  └── 上层不存在时自动生效；不可被下层替换
```

合并语义：
- 高层存在时覆盖低层同类规则；高层不存在时低层自动生效
- Layer 3 条目不受步骤 5 的置信度过滤（④）和模糊发现截断（⑤）影响
- 内置规则（Layer 1）始终作为兜底生效，不因项目规则存在而完全失效

**`.claude/review-rules.md` 治理格式：**

```markdown
---
version: 1.2.0
effective_date: 2026-04-01
governance: 变更需经 tech lead 审批，修改须更新 version 和 effective_date
---

# 项目审查红线

## 安全红线

- 所有外部输入必须经过校验，无例外
- 禁止在日志中记录 token、password、secret 等敏感字段
- 数据库查询必须使用参数化查询，禁止字符串拼接 SQL

## 架构红线

- handler 层禁止直接访问 repository，必须经过 service 层
- auth 模块变更必须附带安全说明注释
```

> `version` 字段由审查 Skill 读取，输出于报告 `Review Assumptions` 节（如：`.claude/review-rules.md` 已加载 v1.2.0）。版本变更时旧缓存自动失效。

---

### 4.5 review:ignore 注释

```go
// review:ignore security - 测试环境 mock 数据
var testToken = "mock-token-123"

// review:ignore performance - 此处数据量极小
for _, v := range items {
```

支持的 category：`security`、`performance`、`architecture`、`style`。在步骤 5 误报过滤阶段识别，跳过对应行的对应类别问题。

---

### 4.6 Rule ID 注册表

Rule ID 格式：`<PREFIX>-<NNN>`（三位数字，001 起步）。每条规则对应唯一 ID，用于 findings 溯源、跨次审查对比和团队规范对齐。

> **规则 ID 以 `rules/*.yaml` 文件为准，以下为当前实际规则列表。**

#### SAFE — 安全类（对应 `rules/safety.yaml`）

| Rule ID | 规则描述 |
|---------|---------|
| SAFE-001 | 禁用 fmt.Errorf 包装/构造错误（应使用 errors.Wrap/Wrapf） |
| SAFE-002 | 业务函数禁用 panic（通过 error 返回值传递错误） |
| SAFE-003 | error 必须作为最后一个返回值（高误报率，需语义确认） |
| SAFE-004 | 禁用 recover 静默吞掉错误（必须记录日志） |
| SAFE-005 | 锁操作必须配合 defer 解锁（防止死锁） |
| SAFE-006 | goroutine 中禁止忽略错误 |
| SAFE-007 | 禁止 errors.New 嵌套 fmt.Sprintf |
| SAFE-008 | 错误消息避免过度格式化（>2个占位符） |
| SAFE-009 | 禁止用 _ 接收 error 返回值 |
| SAFE-010 | 禁止用 fmt.Sprintf 拼接 JSON |
| SAFE-011 | 指针变量使用前必须校验 nil（高误报率，需语义确认） |
| SAFE-012 | ctx 必须通过函数入参传递（禁止中间层新建 context） |
| SAFE-013 | 并发操作应使用 recovered.ErrorGroup 替代 sync.WaitGroup |
| SAFE-014 | for range 中启动 goroutine 必须使用 limiter 控制并发（高误报率） |

#### DATA — 数据层类（对应 `rules/data.yaml`）

| Rule ID | 规则描述 |
|---------|---------|
| DATA-001 | 禁用 db.Save() 全量更新 |
| DATA-002 | 禁用 SELECT * 查询所有字段 |
| DATA-003 | 优先使用 Take() 而非 First() |
| DATA-004 | GORM tag 必须指定 column 名 |
| DATA-005 | 事务函数参数必须命名为 tx |
| DATA-006 | 禁止在循环中单条 Create |
| DATA-007 | 禁止用 fmt.Sprintf 构造 JSON 字符串 |
| DATA-008 | storage 层 struct 禁用 omitempty |
| DATA-009 | 更新/删除必须包含 id 定位条件 |
| DATA-010 | 批量操作禁止循环单条处理 |
| DATA-011 | 一般情况下禁止使用 .Scan() |
| DATA-012 | GORM 条件必须通过 .Where() 明确声明 |
| DATA-013 | GORM 长链式调用必须换行格式化 |
| DATA-014 | 纯数据库映射 struct 禁止添加 json tag |

#### QUAL — 质量类（对应 `rules/quality.yaml`）

| Rule ID | 规则描述 |
|---------|---------|
| QUAL-001 | ID 缩写必须全大写 |
| QUAL-002 | 禁用 iota 定义枚举常量 |
| QUAL-003 | 禁用可变全局变量 |
| QUAL-004 | 禁用 init 函数（server 包除外） |
| QUAL-005 | switch 必须包含 default 分支 |
| QUAL-006 | TODO/NOTE 注释必须标注 owner |
| QUAL-007 | make 初始化应指定容量 |
| QUAL-008 | 公开函数/接口必须有有意义的注释 |
| QUAL-009 | 枚举常量应有中文业务注释 |
| QUAL-010 | 包名与目录名必须一致 |
| QUAL-011 | 禁止使用字面量 {} 初始化切片/map，应使用 make() |
| QUAL-012 | 嵌入结构体必须声明在最顶层 |
| QUAL-013 | 重复使用的常量应统一定义在常量包 |
| QUAL-014 | 单测必须验证具体的返回值结构 |
| QUAL-015 | 代码中不允许出现拼写错误 |
| QUAL-016 | 获取列表的方法应命名为 GetList 或 Search 而非 Get |
| QUAL-017 | 枚举型 switch 应考虑 map 数据驱动替代（Rule of Extensibility） |
| QUAL-018 | 切片变量禁用 var 声明，应使用 make 初始化 |

#### OBS — 可观测性类（对应 `rules/observability.yaml`）

| Rule ID | 规则描述 |
|---------|---------|
| OBS-001 | log.Any 禁止传递数字类型值 |
| OBS-002 | 日志字段 key 必须使用 snake_case |
| OBS-003 | Error 日志必须包含 ErrorField 且放在末尾 |
| OBS-004 | data 层禁止打日志 |
| OBS-005 | Error 日志必须包含上下文字段 |
| OBS-006 | 生产代码禁用 fmt.Println |
| OBS-007 | 生产代码禁用 fmt.Printf |
| OBS-008 | 错误消息避免绝对断言式措辞 |
| OBS-009 | 非简单函数禁止只有 error 日志 |
| OBS-010 | pkg 包禁止打日志 |
| OBS-011 | log.ErrorField 必须放在日志字段末尾 |

#### PERF — 性能类（AI Agent 报告）

| Rule ID | 规则描述 |
|---------|---------|
| PERF-001 | goroutine 泄漏：channel 读写无超时保护 |
| PERF-002 | 内存泄漏：资源未在 defer 中关闭 |
| PERF-003 | 大对象在热路径中频繁复制（应改指针）|
| PERF-004 | sync.Mutex 持有期间执行 I/O 操作 |
| PERF-005 | 循环内重复计算可提前到循环外的不变量 |
| PERF-006 | context 未向下传递导致请求无法取消 |

#### ARCH — 架构类（AI Agent 报告）

| Rule ID | 规则描述 |
|---------|---------|
| ARCH-001 | 违反单一职责：单函数承担多个不相关业务逻辑 |
| ARCH-002 | 错误未向上传递，业务错误在底层被吞掉 |
| ARCH-003 | 全局可变状态（package-level var）影响测试隔离 |

#### BIZ — 业务逻辑类（AI Agent 报告）

| Rule ID | 规则描述 |
|---------|---------|
| BIZ-001 | 状态机缺陷：非法状态跳转无前置校验 |
| BIZ-002 | 幂等性缺失：写操作不可安全重试 |
| BIZ-003 | 权限归属缺失：未校验资源所属关系 |
| BIZ-004 | 业务约束缺失：数值/状态/关系未做有效性校验 |
| BIZ-005 | 并发业务竞争：TOCTOU 导致超卖/超限 |
| BIZ-006 | 业务计算精度：金融金额使用浮点数或时区处理缺失 |

#### LINT — 静态检查类

| Rule ID | 规则描述 |
|---------|---------|
| LINT-001 | go vet / staticcheck — 错误未处理 |
| LINT-002 | staticcheck — 无效代码 |
| LINT-003 | gosec — 基础安全模式 |
| LINT-004 | ineffassign — 无效赋值 |
| LINT-005 | gocognit — 认知复杂度超阈值 |

> **扩展规则：** 项目自定义规则在 `.claude/review-rules.md` 中以 `SAFE-1xx`、`QUAL-1xx` 等百位数段命名，与内置规则不冲突。
>
> **命名空间保护：** 内置规则 ID（`SAFE-001~099`、`DATA-001~099`、`QUAL-001~099`、`OBS-001~099`、`PERF-001~099`、`ARCH-001~099`、`BIZ-001~099`、`LINT-001~099`）不可在 `.claude/review-rules.md` 中重新定义或覆盖；项目扩展规则必须使用 `1xx` 段，避免与内置规则 ID 冲突。

---

## 5. 数据流总览

```
开发者执行 skill
      │
      ▼
[git diff + git log + 本地规范文件]
      │
      ▼
[分流决策] ──Trivial──→ 输出摘要 → [结束]
      │
      ▼ Lite/Full
[Context Package]
(Diff + 变更函数原文 + 规范 md)
      │
      ├── Full ──→ [步骤 3.5 架构预扫描] → architecture_context 注入 Context Package
      │
      ├── Full 且大型变更 ──→ [任务队列] ──Loop──→ [Subagent 顺序执行]
      │                                                    │
      └── 普通变更 ──→ [Subagent 顺序执行] ────────────────┤
                                                           │
                                                           ▼
                                                   [Agent Findings]
                                                           │
                                                           ▼
                                             [去重 → 误报过滤 → 排序 → 截断]
                                                           │
                                                           ▼
                                                   [≤15条 Findings]
                                                           │
                                                           ▼
                                              终端输出 + 本地报告文件（可选）
```

---

## 6. 执行说明

### 6.1 命令参数

Skill 通过 Claude Code slash command 触发，无需安装额外 CLI 工具：

```
/go-code-review                        # 审查当前分支 vs main 的变更
/go-code-review --branch feat/xxx      # 指定源分支
/go-code-review --base develop         # 指定对比基准分支
/go-code-review --output report.md     # 额外输出本地 Markdown 报告
/go-code-review --resume               # 恢复中断的 Full 档 Loop 审查
```

### 6.2 进度输出

```
[1/6] 获取代码变更...              ✓ 320 行变更，12 个文件
[2/6] 变更分流...                  ✓ Full 档，红线规则已加载（review-rules.md）
[3/6] 组装上下文...                ✓ 上下文组装完成
[3.5/6] 架构预扫描（Full 档）...   ✓ 识别 3 个模块，高风险：auth
[4/6] 执行审查（Loop 模式）...     ✓ 任务包 3/5 完成
[5/6] 聚合与过滤...                ✓ 原始 23 条，过滤后 11 条（覆盖 12/14 文件）
[6/6] 输出结果...                  ✓ 终端输出完成
```

### 6.3 Loop 中断恢复

当 Full 档 Loop 模式被中断（Claude Code 超时、会话退出等），可通过 `--resume` 从断点继续：

```
/go-code-review --resume                    # 恢复当前目录的中断审查
/go-code-review --resume --output report.md # 恢复并生成完整报告
```

**恢复条件：**
- `.review/workflow-state.json` 存在
- `head_sha` 与当前 `HEAD` 一致（代码未变更）
- `pending_tasks` 非空（有未完成任务包）

**恢复行为：**
- 跳过 `completed_tasks` 中已完成的任务包
- 从 `pending_tasks` 继续执行剩余任务包
- 完成后合并新旧 findings，执行完整的步骤 5 聚合

**拒绝恢复场景：**
- `head_sha` 不一致 → 提示"代码已变更，请重新执行完整审查"，退出
- `.review/workflow-state.json` 不存在 → 按正常流程执行

---

### 6.4 输出路径

| 文件 | 写入方式 | 说明 |
|------|---------|------|
| `.review/workflow-state.json` | Claude Write tool | Loop 模式任务状态，`--resume` 使用 |
| `.review/results/review-{timestamp}.md` | `aggregate-findings.py` 输出 | 最终审查报告 |
| `.review/run-{sha}-{pid}/findings-{agent}.md` | 子 Agent Write tool | 各专家临时 findings |
| `.review/run-{sha}-{pid}/all-findings.md` | Bash `cat` 合并 | 聚合后全量 findings，Verifier 输入 |

> Session 目录命名格式：`.review/run-{head_sha_8位}-{pid}/`，确保同一仓库中并发执行的 review 不互相覆盖。审查完成后自动清理。

---

### 6.5 工具脚本（Helper Scripts）

Claude Code 通过 Bash tool 调用以下脚本，所有确定性步骤在脚本内执行：

```
languages/go/tools/
├── run-go-tools.sh          # Tier 1：go build / go vet / staticcheck / gocognit
├── scan-rules.sh            # Tier 2：YAML 规则扫描（rules/*.yaml）
├── classify-diff.py         # 步骤 2：分流判断（Trivial / Lite / Full）
├── assemble-context.py      # 步骤 3：Context Package 组装 + 截断
├── scan-architecture.py     # 步骤 3.5：架构预扫描（module_map / high_risk_modules）
└── aggregate-findings.py    # 步骤 5：去重 / 过滤 / 排序 / 截断（全确定性）
```

---

## 7. 方案选型对比

| 方案 | 精度 | 流程管控 | 推荐场景 |
|------|------|---------|---------|
| 单 Agent 直出 | 低 | 软（AI 自主） | Trivial 档（文档/注释） |
| 顺序流水线 | 中 | 软（AI 自主） | — |
| Claude Code Skill + helper scripts | 高 | **硬（Skill 规范 + shell/Python 脚本）** | **全档（当前架构，推荐）** |

Claude Code Skill 架构中，AI 只填充内容（findings），Skill 规范约束执行顺序，Python/shell 脚本执行所有确定性步骤（分流、扫描、聚合）。除 Claude Code 外，无任何外部服务依赖。
