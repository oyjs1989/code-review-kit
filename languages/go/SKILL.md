---
name: go-code-review
description: 'This skill should be used when the user asks to "review Go code", "check Go code quality", "review this PR", "code review", or mentions Go code standards, GORM best practices, error handling patterns, concurrency safety, design philosophy, naming conventions, or UNIX principles. Orchestrates comprehensive Go code reviews using a three-tier architecture: quantitative tools + YAML pattern scanning + 7 domain-expert AI agents.'
version: 6.0.0
allowed-tools:
  - Bash(git:*)
  - Bash(bash:*)
  - Bash(go:*)
  - Bash(grep:*)
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(head:*)
  - Bash(cat:*)
  - Bash(awk:*)
  - Bash(sed:*)
  - Bash(wc:*)
  - Bash(python3:*)
---

# Go Code Review Skill (v6.0.0)

## When to Use This Skill

This skill activates when users need help with:
- Reviewing Go code changes against coding standards
- Checking code quality and identifying potential issues
- Performing PR reviews for Go projects
- Validating database operations and data layer correctness
- Checking error handling, concurrency safety, and nil safety
- Analyzing design philosophy and UNIX principles compliance
- Evaluating observability: logging strategy and error message quality
- Reviewing naming conventions, code structure, and readability

## Architecture: Three-Tier Expert Review

```
输入：git diff 变更的 Go 文件
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Tier 1: tools/run-go-tools.sh                      │  → diagnostics.json
│  go build（编译错误, P0）                             │
│  go vet（类型/格式检查, ~0 假阳性）                   │
│  staticcheck（SSA 分析，可选安装）                    │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Tier 2: tools/scan-rules.sh                        │  → rule-hits.json
│  修复后的 YAML 规则（兜底扫描）                       │
│  预期 <50 条命中，假阳性大幅降低                       │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Tier 3: 7 个领域专家 Agent（并行）                         │
│  🔴 safety      │ 安全与正确性，上下文并发判断              │
│  🗄️  data        │ 数据层，N+1，序列化，类型语义             │
│  🏗️  design      │ UNIX 7 原则，领域模型，代码变坏根源       │
│  📐 quality     │ 综合 metrics.json，复杂度，可读性         │
│  👁️  observability│ 日志分层策略，错误消息质量               │
│  🧩 business    │ 业务需求推断，逻辑漏洞，边界缺失分析       │
│  🏷️  naming      │ 命名语义准确性，一致性，Go 惯用法         │
└──────────────────────────────────────────────────────────┘
         │
         ▼
聚合：P0 → P1 → P2，去重，中文报告输出到 code_review.result
```

### Tier 1 — 量化分析工具

Script: `tools/run-go-tools.sh`
Output: `/tmp/diagnostics.json`

Runs per changed Go file:
- `go build`（编译错误检测）
- `go vet`（类型/格式问题）
- `staticcheck`（SSA 静态分析，可选）
- `gocognit`（认知复杂度，可选；>15 报告，>25 → P1，16-25 → P2）
- 文件行数检测（threshold: 800 lines → `large_files`）

### Tier 2 — YAML 规则扫描

Script: `tools/scan-rules.sh`
Output: `/tmp/rule-hits.json`

Scans against 38 deterministic regex rules across four YAML files:
- `rules/safety.yaml` — SAFE-001 to SAFE-010
- `rules/data.yaml` — DATA-001 to DATA-010
- `rules/quality.yaml` — QUAL-001 to QUAL-010
- `rules/observability.yaml` — OBS-001 to OBS-008

### Tier 3 — 7 个领域专家 Agent

| Agent | Expert Perspective |
|-------|--------------------|
| safety (red) | 安全与正确性：会崩/死锁/数据损坏吗？ |
| data (blue) | 数据层：存取正确高效吗？ |
| design (purple) | 架构设计哲学：能活过百万行代码吗？ |
| quality (green) | 代码质量：新人 5 分钟能看懂吗？ |
| observability (yellow) | 可观测性：凌晨 3 点能快速定位吗？ |
| business (orange) | 业务需求：实现的是用户真正需要的吗？ |
| naming (magenta) | 命名质量：代码能自解释吗？ |

Each agent receives the full code diff plus the subset of `rule-hits.json` relevant to its domain. Agents confirm Tier 2 hits with business context and surface additional judgment-based issues that regex cannot detect.

## Review Workflow

### Step 1: 获取变更文件

```bash
# --diff-filter=AM 只取新增(A)和修改(M)的文件，排除已删除文件避免工具报 "file not found"
git diff master --name-only --diff-filter=AM | grep '\.go$'
# 或针对特定 commit
git diff HEAD~1 --name-only --diff-filter=AM | grep '\.go$'

# 设置 Session 目录（防止并发 review 相互覆盖）
HEAD_SHA=$(git rev-parse HEAD | head -c 8)
SESSION_DIR=".review/run-${HEAD_SHA}-$$"
mkdir -p "$SESSION_DIR"
```

### Step 1.5: 变更分流（Triage）

执行以下 Bash 命令判断本次变更的规模：

```bash
# 获取变更行数
DIFF_LINES=$(git diff master --diff-filter=AM -- '*.go' | wc -l)
# 获取变更文件数
FILES_CHANGED=$(git diff master --name-only --diff-filter=AM | grep '\.go$' | wc -l)
# 检查是否涉及敏感路径
SENSITIVE=$(git diff master --name-only --diff-filter=AM | grep -E '(auth|crypto|payment|permission|admin)/' | wc -l)

echo "diff_lines=$DIFF_LINES files=$FILES_CHANGED sensitive=$SENSITIVE"
```

根据结果路由：

| 档位 | 条件 | 行为 |
|------|------|------|
| **Trivial** | `DIFF_LINES < 20` 且所有变更文件均为 `.md`/`.yaml`/`.yml`/`.json`/`.toml`/`.txt` 或仅注释行变更 | 跳过 Tier 1/2 扫描和全部 Agents，输出一句简短摘要说明变更内容，结束。 |
| **Lite** | `20 <= DIFF_LINES < 400` 且 `FILES_CHANGED < 5` 且 `SENSITIVE == 0` | 执行 Tier 1/2 扫描 + 仅派发 3 个 Agent：safety、quality、observability |
| **Full** | `DIFF_LINES >= 400` 或 `FILES_CHANGED >= 5` 或 `SENSITIVE > 0` | 执行 Tier 1/2 扫描 + 全量 7 个 Agent + Verifier |

> **注意**：Trivial 档 `.go` 文件中纯注释变更判断：`git diff master --diff-filter=AM -- '*.go' | grep '^+' | grep -v '^+++' | grep -vE '^\+\s*(//|/\*)' | wc -l` 若输出为 0，视为纯注释变更。

### Step 2: 运行 Tier 1 工具链分析

```bash
git diff master --name-only --diff-filter=AM | grep '\.go$' | bash tools/run-go-tools.sh > /tmp/diagnostics.json
```

读取 `/tmp/diagnostics.json`，记录：
- `build_errors`：编译错误（P0，必须修复，来自 `go build`）
- `vet_issues`：类型/格式问题（P0/P1，来自 `go vet`）
- `staticcheck_issues`：SSA 分析结果（SA*→P0，S1*/ST1*→P2，来自 `staticcheck`，未安装则为空）
- `large_files`：行数 > 800 的文件（参考数据）

如未安装 staticcheck 或 gocognit，可提前安装（可选，未安装时工具会跳过对应检查）：
```bash
go install honnef.co/go/tools/cmd/staticcheck@latest
go install github.com/uudashr/gocognit/cmd/gocognit@latest
```

### Step 3: 运行 Tier 2 规则扫描

```bash
git diff master --name-only --diff-filter=AM | grep '\.go$' | bash tools/scan-rules.sh > /tmp/rule-hits.json
```

读取 `/tmp/rule-hits.json`。**实际 JSON 结构**：

```json
{
  "hits": [
    {
      "rule_id": "SAFE-001",
      "severity": "P0",
      "file": "service/user.go",
      "line": 45,
      "matched": "return fmt.Errorf(\"get user failed: %v\", err)",
      "message": "禁止使用 fmt.Errorf() 创建错误..."
    }
  ],
  "summary": { "total": 12, "P0": 3, "P1": 8, "P2": 1 }
}
```

字段说明：`file`（文件路径）、`line`（行号）、`matched`（匹配的源码行）、`summary.total`（总命中数）。

### Step 3.5: 列出 Agent 工具库

在启动 agents 前，列出已沉淀的可复用工具，并将工具列表传给各 agent：

```bash
ls skills/go-code-review/tools/agents/*.sh skills/go-code-review/tools/agents/*.py 2>/dev/null || echo "（工具库为空）"
```

将输出传给所有 agents，提示他们优先复用已有工具。

### Step 4: 读取代码内容，启动 Agent

**先用 Bash 读取变更代码**，再将内容以文本形式传给 agents。

```bash
# 读取变更内容（供 agent 分析）
git diff master --diff-filter=AM -- $(git diff master --name-only --diff-filter=AM | grep '\.go$' | tr '\n' ' ')
```

各 agent 将输出写入 `$SESSION_DIR/findings-{agent}.md`（如 `$SESSION_DIR/findings-safety.md`）。

根据 Step 1.5 分流结果派发 Agent：

**Lite 档**（只派发 3 个 agent）：

- **safety agent** — 读取 diagnostics.json（build_errors + vet_issues + staticcheck SA*）；确认 rule-hits.json 中 SAFE-001~010 命中（按规则说明过滤假阳性）
- **quality agent** — 读取 diagnostics.json（large_files + staticcheck S1*/ST1*）；确认 QUAL-001~010 命中（命名语义类问题交由 naming agent 主责）
- **observability agent** — 确认 OBS-001~008 命中；处理日志分层策略/错误消息质量

**Full 档**（变更文件数 ≤ 30，全量 7 个 agent）：

- **safety agent** — 读取 diagnostics.json（build_errors + vet_issues + staticcheck SA*）；确认 rule-hits.json 中 SAFE-001~010 命中（按规则说明过滤假阳性）
- **data agent** — 确认 DATA-001~010 命中；处理 N+1/序列化/事务边界判断
- **design agent** — 无 Tier 2 规则；专注 UNIX 7 原则 + 5 大代码变坏根源
- **quality agent** — 读取 diagnostics.json（large_files + staticcheck S1*/ST1*）；确认 QUAL-001~010 命中（命名语义类问题交由 naming agent 主责）
- **observability agent** — 确认 OBS-001~008 命中；处理日志分层策略/错误消息质量
- **business agent** — 无 Tier 2 规则；读取变更文件**完整内容**（非仅 diff）；推断业务意图，识别业务逻辑漏洞、边界缺失、状态机错误、幂等性风险、权限归属缺漏
- **naming agent** — 确认 QUAL-001/008/010 命名相关命中；深度审查所有标识符命名质量（语义准确性、一致性、Go 惯用法、上下文冗余）

**Full 档**（变更文件数 > 30，大 diff 分批启动，避免上下文溢出和权限弹窗堆积）：
- **第一批**（高风险域）：safety + data + business — 等三个 agent 返回后
- **第二批**：design + quality + observability + naming

**Verifier（仅 Full 档，所有专家 Agent 完成后）：**

所有专家 findings 合并完成后，派发 Verifier agent 对 P0/P1 进行对抗性核实：

Agent(agents/verifier.md, prompt=<verifier.md内容 + $SESSION_DIR/all-findings.md 中的P0/P1条目 + 代码变更内容>)

Verifier 完成后：
- `confirm` 条目：保留原严重度
- `downgrade` 条目：按修订后严重度重新排序
- `dismiss` 条目：从 findings 列表中移除

### Step 5: 聚合输出

合并所有 agent findings：

```bash
cat "$SESSION_DIR"/findings-*.md > "$SESSION_DIR/all-findings.md"
```

收集所有 agent 输出后：

**review:ignore 过滤（聚合前）：**

执行以下命令找出所有 `review:ignore` 注释行：

```bash
git diff master --diff-filter=AM -- '*.go' | grep '^+' | grep 'review:ignore'
```

格式：`// review:ignore <category>` 其中 category 为：`security`、`performance`、`architecture`、`style`、`quality`、`data`

Category 与 Rule 前缀的映射：
- `security` → 过滤 SAFE-* findings
- `data` → 过滤 DATA-* findings
- `quality` / `style` → 过滤 QUAL-* findings
- `architecture` → 过滤 ARCH-* findings (如有)
- `performance` → 过滤 PERF-* findings (如有)

对于标记了 `review:ignore` 的行，跳过该行对应 category 的 findings。

1. 合并 Tier 2 命中（已在 rule-hits.json 中）和 agent 补充的判断性问题
2. 去重：同一位置的问题只保留最高严重度
3. 按 P0 → P1 → P2 排序
4. 输出到 `code_review.result`

**输出截断（最终步骤）：**

按 P0 → P1 → P2 排序后，**只输出前 15 条**。若总 findings 超过 15 条，在终端摘要行添加：
`（另有 N 条问题因数量限制未显示，使用 --output report.md 查看完整报告）`

若使用了 `--output` 参数，完整 findings（含超出 15 条部分）写入报告文件的 `## Appendix` 节。

审查完成后清理 session 目录：

```bash
rm -rf "$SESSION_DIR"
```

## Output Format

**重要**：所有审查输出必须使用中文。

```markdown
# Go 代码审查报告

## 审查摘要

| 指标 | 数量 |
|------|------|
| P0（必须修复） | X 个 |
| P1（强烈建议） | X 个 |
| P2（建议优化） | X 个 |

## 量化违规（Tier 1）

（来自 metrics.json，由 quality agent 报告）

## P0 问题（必须修复）

### 问题 - [P0] <问题类别>（来自：<agent名称>/<rule-id>）
**位置**: path/to/file.go:行号
**类别**: <具体类别>
**原始代码**:
```go
// 问题代码
```
**问题描述**: <中文说明>
**修改建议**:
```go
// 修复代码
```

## P1 问题（强烈建议）
...

## P2 问题（建议优化）
...
```

## Manual Agent Invocation

Individual agents can be invoked directly without running the full orchestrator:

```
直接调用 safety agent
直接调用 data agent
直接调用 design agent
直接调用 quality agent
直接调用 observability agent
直接调用 business agent
直接调用 naming agent
```
