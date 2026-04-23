# Go Code Review Skill — Review Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply the consensus fixes from three parallel code reviews of design.md vs the current SKILL.md implementation — fix version inconsistency, add triage, add 15-finding cap, add review:ignore support, create Verifier agent, and correct Rule ID discrepancies.

**Architecture:** All changes are inline to existing files. No new Python scripts. The four proposed helper scripts (classify-diff.py, assemble-context.py, scan-architecture.py, aggregate-findings.py), workflow-state.json, and Coordinator Agent are intentionally NOT implemented (YAGNI per review consensus).

**Tech Stack:** Claude Code SKILL.md (Markdown + Bash), YAML rule files, Markdown agent prompts.

---

## Context: What's Wrong and Why

| Issue | Location | Impact |
|-------|----------|--------|
| Three different version numbers | `SKILL.md` (frontmatter v6.0.0, title v4.0.0, output v5.0.0) | Confusing, signals unmaintained file |
| No triage — always runs 7 agents on any diff | `SKILL.md` Step 4 | Wasteful on 5-line doc changes |
| No 15-finding cap | `SKILL.md` Step 5 | Can output 40+ findings, trains devs to ignore reviews |
| No `review:ignore` support | `SKILL.md` | No way for devs to suppress known false positives |
| No Verifier agent | `languages/go/agents/` | P0/P1 false positives not adversarially checked |
| Rule ID conflict | `design.md` §4.6 vs `rules/safety.yaml` | design.md says SAFE-001=SQL injection; YAML says SAFE-001=fmt.Errorf — wrong in design doc |
| `.tmp/` concurrent collision | `design.md` §6.4 | Two concurrent reviews in same repo overwrite each other's findings |

---

## Task 1: Fix Version Inconsistency in SKILL.md

**Files:**
- Modify: `languages/go/SKILL.md`

**Step 1: Update SKILL.md to use a single version number**

The file has three conflicting versions:
- Frontmatter: `version: 6.0.0`
- Title: `# Go Code Review Skill (v4.0.0)`
- Output format header: `# Go 代码审查报告（v5.0.0）`

Canonical version: **6.0.0** (use frontmatter as source of truth).

Change title from:
```
# Go Code Review Skill (v4.0.0)
```
To:
```
# Go Code Review Skill (v6.0.0)
```

Change output format header from:
```markdown
# Go 代码审查报告（v5.0.0）
```
To:
```markdown
# Go 代码审查报告
```
(Remove version from output entirely — the report shouldn't embed the tool version.)

**Step 2: Commit**
```bash
git add languages/go/SKILL.md
git commit -m "fix: unify SKILL.md version number to 6.0.0"
```

---

## Task 2: Add Trivial/Lite/Full Triage to SKILL.md

**Files:**
- Modify: `languages/go/SKILL.md`

**Step 1: Insert triage logic into SKILL.md after Step 1 (获取变更文件)**

After the existing Step 1 (git diff to get changed files), add a new **Step 1.5: 变更分流** section before Step 2 (运行 Tier 1 工具链分析):

```markdown
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
```

**Step 2: Update Step 4 to respect triage result**

In the existing Step 4 (启动 Agent), change "并行启动全部7个agent" to use the triage result:

- **Lite 档**：只派发 safety、quality、observability 三个 agent（顺序派发）
- **Full 档**：派发全部 7 个 agent（顺序派发），然后派发 Verifier（见 Task 5）

**Step 3: Commit**
```bash
git add languages/go/SKILL.md
git commit -m "feat: add Trivial/Lite/Full triage to SKILL.md"
```

---

## Task 3: Add 15-Finding Cap and review:ignore Support

**Files:**
- Modify: `languages/go/SKILL.md`

**Step 1: Add review:ignore check in Step 5 (聚合输出)**

In the existing Step 5 aggregation section, add before dedup/sort:

```markdown
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
```

**Step 2: Add 15-finding cap at end of Step 5**

```markdown
**输出截断（最终步骤）：**

按 P0 → P1 → P2 排序后，**只输出前 15 条**。若总 findings 超过 15 条，在终端摘要行添加：
`（另有 N 条问题因数量限制未显示，使用 --output report.md 查看完整报告）`

若使用了 `--output` 参数，完整 findings（含超出 15 条部分）写入报告文件的 `## Appendix` 节。
```

**Step 3: Commit**
```bash
git add languages/go/SKILL.md
git commit -m "feat: add 15-finding cap and review:ignore support to SKILL.md"
```

---

## Task 4: Fix .tmp/ Concurrent Collision in SKILL.md

**Files:**
- Modify: `languages/go/SKILL.md`

**Step 1: Replace all `.tmp/` references with session-scoped directory**

Current SKILL.md (and design.md) use `.tmp/findings-{agent}.md` as inter-agent state. Two concurrent review sessions in the same repo would overwrite each other.

In SKILL.md Step 4, wherever agent output files are referenced, replace `.tmp/` with a session-scoped path:

```bash
# 在 Step 1 开始时设置 SESSION_DIR
HEAD_SHA=$(git rev-parse HEAD | head -c 8)
SESSION_DIR=".review/run-${HEAD_SHA}-$$"
mkdir -p "$SESSION_DIR"
```

All agent findings files use `$SESSION_DIR/findings-{agent}.md` instead of `.tmp/findings-{agent}.md`.

In Step 5 aggregation:
```bash
cat "$SESSION_DIR"/findings-*.md > "$SESSION_DIR/all-findings.md"
```

After the full review completes (Step 5 done), clean up:
```bash
rm -rf "$SESSION_DIR"
```

**Step 2: Commit**
```bash
git add languages/go/SKILL.md
git commit -m "fix: use session-scoped dir for findings to prevent concurrent collision"
```

---

## Task 5: Create Verifier Agent (agents/verifier.md)

**Files:**
- Create: `languages/go/agents/verifier.md`
- Modify: `languages/go/SKILL.md` (add Verifier call in Step 4, Full tier)

**Step 1: Create the verifier agent file**

```markdown
---
name: verifier
description: |
  Adversarial verifier for Go code review P0/P1 findings. Attempts to dismiss false positives
  by finding evidence that contradicts each finding. Use after all expert agents complete (Full tier only).
model: inherit
color: white
tools: ["Read", "Grep"]
---

# Go 代码审查 — 对抗性核实者

## 代理标识

- **名称**：verifier
- **颜色**：white
- **角色**：对抗性验证者。在所有专家 Agent 完成后执行，专门针对 P0/P1 findings 尝试证伪，降低误报率。
- **关注点**：不产生新 findings，只对已有 P0/P1 结论做 confirm / downgrade / dismiss 判断。

## 核心职责

对每条 P0/P1 finding，尝试找到代码中已存在的防护机制来证伪它。

## 执行步骤

对每条 P0/P1 finding：

1. **原文引用**：输出该 finding 审查的代码片段（防止幻觉）
2. **证伪尝试**：在代码中查找能证明该 finding 不成立的证据：
   - 调用方是否已有前置校验？
   - 是否有其他防护机制（middleware、interceptor、wrapper）？
   - 该代码路径是否在生产中实际不可达？
3. **判断输出**：
   - 若找不到有效证伪证据 → `confirm`
   - 若找到部分证伪证据（某些路径已防护）→ `downgrade`
   - 若找到核心证伪证据（问题实际不存在）→ `dismiss`

## 输入格式

从 `$SESSION_DIR/all-findings.md` 中读取所有 P0/P1 条目（`[P0]` 或 `[P1]` 开头的 findings）。

## 输出格式

每条 finding 输出一个判断块：

```markdown
### <rule_id> — <verdict>

**正在核实的代码**:
```go
// 原始问题代码片段（逐字引用）
```

**证伪尝试**:
- （列举找到或未找到的证伪证据）

**理由**: <中文说明，解释判断依据>
**修订严重度**: （downgrade 时注明，如 P0→P1）
```

`verdict` 取值：
- `confirm` — 问题成立，维持原严重度
- `downgrade` — 问题部分成立，降低严重度（P0→P1 或 P1→P2）
- `dismiss` — 问题不成立，从 findings 中移除

## 限制

- **不产生新 findings** — 只对已有结论做核实
- 仅处理 P0/P1 条目（P2/P3 不经过 Verifier）
- 若 findings 文件为空或不含 P0/P1 条目，输出"无需核实"并结束
```

**Step 2: Add Verifier call to SKILL.md Step 4 (Full tier)**

In SKILL.md's Step 4 section for Full tier, after all 7 expert agents complete and findings are merged:

```markdown
**Verifier（仅 Full 档，所有专家 Agent 完成后）：**

所有专家 findings 合并完成后，派发 Verifier agent 对 P0/P1 进行对抗性核实：

Agent(agents/verifier.md, prompt=<verifier.md内容 + $SESSION_DIR/all-findings.md 中的P0/P1条目 + 代码变更内容>)

Verifier 完成后：
- `confirm` 条目：保留原严重度
- `downgrade` 条目：按修订后严重度重新排序
- `dismiss` 条目：从 findings 列表中移除
```

**Step 3: Commit**
```bash
git add languages/go/agents/verifier.md languages/go/SKILL.md
git commit -m "feat: add Verifier agent for adversarial P0/P1 validation"
```

---

## Task 6: Fix Rule ID Discrepancy in design.md

**Files:**
- Modify: `design.md` (§4.6 Rule ID 注册表)

**Problem:** design.md §4.6 defines a completely different rule set than what exists in `rules/safety.yaml`:

| Rule ID | design.md says | rules/safety.yaml actually says |
|---------|---------------|--------------------------------|
| SAFE-001 | SQL注入：字符串拼接构造SQL | 禁用 fmt.Errorf 包装错误 |
| SAFE-002 | XSS：未转义输出写入HTTP响应 | 业务函数禁用 panic |
| SAFE-003 | 命令注入：未校验参数传入exec.Command | error 必须作为最后一个返回值 |
| ... | Generic Go security rules | Project-specific conventions |

The YAML files + agent prompts are the **authoritative implementation**. design.md's rule registry must be corrected to match them.

**Step 1: Update design.md §4.6 SAFE rules table to match safety.yaml**

Replace the SAFE rules table in §4.6 with the actual rules from `rules/safety.yaml`:

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

Similarly update DATA/QUAL/OBS tables to match their respective YAML files.

Also update the note at the top of §4.6 to clarify: "规则 ID 以 `rules/*.yaml` 文件为准，以下为当前实际规则列表。"

**Step 2: Fix concurrent collision note in §6.4 output paths table**

In §6.4 输出路径 table, change `.tmp/findings-{agent}.md` to `.review/run-{sha}-{pid}/findings-{agent}.md` and add note:

> Session 目录命名格式：`.review/run-{head_sha_8位}-{pid}/`，确保同一仓库中并发执行的 review 不互相覆盖。审查完成后自动清理。

**Step 3: Commit**
```bash
git add design.md
git commit -m "fix: correct Rule ID registry in design.md to match actual YAML rules"
```

---

## What We're NOT Building (Intentional)

Per review consensus — these are YAGNI and should remain unimplemented:

- `classify-diff.py` — triage is now inline Bash in SKILL.md
- `assemble-context.py` — Claude assembles context natively
- `scan-architecture.py` — agents analyze architecture themselves
- `aggregate-findings.py` — aggregation is inline in SKILL.md Step 5
- `workflow-state.json` / `--resume` — no user demand
- Coordinator Agent — Review Assumptions replaced by the coverage summary line
- Numeric confidence scores — binary report/don't-report is sufficient; keep `needs_clarification` / `[?]` markers

---

## Verification

After all tasks complete, verify:

```bash
# 1. Version number is consistent
grep -n "v[0-9]" languages/go/SKILL.md | grep -v "go install\|@latest"
# Expected: only one occurrence, showing v6.0.0

# 2. Triage section exists
grep -n "Trivial\|Lite\|Full\|分流" languages/go/SKILL.md | head -5
# Expected: shows the new Step 1.5 section

# 3. 15-finding cap instruction exists  
grep -n "15" languages/go/SKILL.md
# Expected: shows the 15-finding cap instruction

# 4. review:ignore instruction exists
grep -n "review:ignore" languages/go/SKILL.md
# Expected: shows the review:ignore handling

# 5. Verifier agent file exists
ls -la languages/go/agents/verifier.md
# Expected: file exists

# 6. SESSION_DIR used instead of .tmp/
grep -n "SESSION_DIR\|\.tmp/" languages/go/SKILL.md
# Expected: SESSION_DIR references, no raw .tmp/ references
```
