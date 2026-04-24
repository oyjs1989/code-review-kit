# feat: Go Code Review Skill — Workflow Restructure (v7 → v8)

## Overview

Restructure `languages/go/SKILL.md` from a monolithic 590-line file into a router-pattern architecture with separate workflow files and output templates. Goal: Claude only does reasoning; deterministic flow is encoded in discrete files with explicit input/output contracts per step.

**No Python scripts or Shell tools are modified. Agent body content is not modified.**

## Problem Statement

Current `SKILL.md` mixes routing intent, step-by-step workflow, output format templates, agent dispatch logic, and installation notes into a single 590-line file. Claude must parse the entire document every invocation even when only executing one step. The output template and context assembly format have no canonical single source — they drift across SKILL.md and agent files.

## Proposed Solution

Split into five concerns:

1. `SKILL.md` — router only (~120 lines, XML-tag pattern from gsd-2)
2. `workflows/full-review.md` — Steps 1–6 with per-step input/output contracts
3. `workflows/lite-review.md` — Lite-tier simplified version of the above
4. `templates/report.md` — report output format (extracted from SKILL.md Output Format section)
5. `templates/context-package.md` — context package format + per-section token budgets

Agent frontmatter gets two new fields: `output_file` and `required_sections`, upgrading checkpoint validation from existence-only to content-aware.

## Critical Invariants — Do Not Break

These are load-bearing strings and behaviors that must be preserved exactly:

| Invariant | Where it matters |
|-----------|-----------------|
| Section headers: `## [Intent]` `## [Rules]` `## [Change Set]` `## [Context]` `## [Architecture Context]` | Parsed by `aggregate-findings.py`. Any capitalization or punctuation change silently breaks report generation. |
| `SESSION_DIR=".review/run-${HEAD_SHA}-$$"` | `$$` is the shell PID. Must remain in one bash scope inside `full-review.md`, not in the router. |
| `ASSEMBLE_EXIT` / exit code 2 → LITE downgrade | Must stay inside `full-review.md` Step 3 block, not delegated to router. |
| `AGENT_ROSTER` read from `classification.json` | Not hardcoded. `full-review.md` reads: `python3 -c "import json; print(' '.join(...))" "$SESSION_DIR/classification.json"` |
| `--resume` reads `workflow-state.json` → checks `head_sha` | Must stay inside `full-review.md` before Step 1. |
| Coordinator triple-input pattern | Context Package + Filtered Findings + Coverage Summary must all be passed to coordinator agent. |
| `### [P` finding boundary | Used by `aggregate-findings.py` grep count and by checkpoint validation. |

## Implementation Phases

### Phase 1: Create Template Files (do first)

`full-review.md` references both templates; create them first so paths are settled.

#### 1a. `languages/go/templates/report.md`

Extract from SKILL.md lines 518–558 (the "Output Format" section).

Content must include:
- Full report skeleton with `# Go 代码审查报告`
- `## 审查摘要` table structure (P0/P1/P2 counts)
- `## P0（必须修复）` / `## P1（强烈建议）` / `## P2（建议优化）` section headers
- Per-finding block schema:
  ```
  ### [P{level}] {rule_id} · {file}:{line}
  **来源**: {agent}
  **置信度**: {confidence}
  **needs_clarification**: {null | "question"}
  **问题描述**: ...
  **修改建议**: ...go code block...
  ```
- `## Appendix` section (findings > 15 overflow)
- Truncation note: `（另有 N 条...完整报告见 {REPORT_FILE}）`

**Verification**: Grep for `### [P` — must appear in this file. This is what `aggregate-findings.py` uses as finding boundary.

#### 1b. `languages/go/templates/context-package.md`

Document the context assembly format and per-section token budgets. Content:

```
# Context Package 格式规范

## 段落结构与 Token 预算（总限 16,000 tokens）

| 段落 | 内容来源 | 预算 | 截断优先级 |
|------|---------|------|-----------|
| [Intent] | gitlog.txt 最近5条 | ~500 tokens | 永不截断 |
| [Rules] | rules/*.yaml 或项目规则文件 | ~2,400 tokens | 按关键词过滤 |
| [Change Set] | diff.txt | ~8,800 tokens | 优先截断（exit 2）|
| [Context] | 变更函数完整体 | ~3,200 tokens | 超限降为签名 |
| [Architecture Context] | scan-architecture.py 输出 | ~1,600 tokens | Full 档专属 |
```

Must include the **exact** section header strings (load-bearing):
```
## [Intent]
## [Rules]
## [Change Set]
## [Context]
## [Architecture Context]
```

Also document:
- Exit code 2 from `assemble-context.py` means `[Change Set]` was truncated → TIER downgraded to LITE
- `context-meta.json` written to stderr contains `truncated_sections` list
- Constants in `assemble-context.py`: `TOKEN_LIMIT=16000`, `RULES_MAX_LINES=300`, `CONTEXT_MAX_LINES=200`, `FUNC_MAX_LINES=80`

### Phase 2: Create Workflow Files

#### 2a. `languages/go/workflows/full-review.md`

Migrate SKILL.md lines 120–514 verbatim (Steps 1–6 + `--resume` block + Loop mode). Add per-step input/output contracts in this format for each step:

```markdown
### Step N: [Name]

**Input:**
- `$SESSION_DIR/file.ext` (required)
- `$VAR` (from Step N-1)

**Command:**
[bash block]

**Output written:**
- `$SESSION_DIR/output.ext`
- Exit 0: success; Exit 2: [meaning]

**Checkpoint:**
[bash test command]
```

Steps to migrate:
- `--resume` handling block (before Step 1)
- Step 1: 获取代码变更 (lines 163–194)
- Step 2: 变更分流 Triage (lines 197–226, include TRIVIAL early exit)
- Step 3: 上下文组装 (lines 230–252, include exit-code-2 LITE downgrade)
- Step 3.5: 架构预扫描 Full 档专属 (lines 255–287)
- Step 4: 执行审查 — Tier 1, Tier 2, agent roster loop, Loop mode with workflow-state.json, Verifier (lines 291–421)
- Step 5: 聚合与过滤 + Coordinator (lines 427–486)
- Step 6: 输出结果与清理 (lines 489–514)

**Key rules for the migration:**
- `SESSION_DIR` with `$$` stays here — not in router
- `ASSEMBLE_EXIT=2` LITE downgrade logic stays here — not in router
- Agent dispatch pattern: `Read agents/{agent}.md → Agent(prompt=agent.md + context-package.md)` → agent writes to `$SESSION_DIR/findings-{agent}.md`
- Coordinator triple-input must match exactly: Context Package + Filtered Findings + Coverage Summary

#### 2b. `languages/go/workflows/lite-review.md`

Create fresh (no existing content to migrate). Lite-tier is currently implicit in the code — LITE_AGENTS = ['safety', 'quality', 'observability'] in classify-diff.py.

Content:
- Same structure as `full-review.md` but with explicit scope limits
- Steps 1–3 identical to full-review.md (parameter parsing, triage, context assembly)
- Step 3.5 **omitted** (no architecture pre-scan for Lite)
- Step 4: only 3 agents: safety, quality, observability (no data/design/business/naming/verifier)
- Step 5: aggregate (same `aggregate-findings.py` invocation)
- Step 6: output (same cleanup)
- **No Loop mode** — Lite tier never triggers it

**Important**: `lite-review.md` must exist at the same time as the router rewrite (Phase 3). Do not create the router that references `lite-review.md` before this file exists.

### Phase 3: Rewrite SKILL.md as Router (Atomic with Phase 2b)

Replace SKILL.md content entirely. Target: ≤120 lines. Use XML-tag structure from gsd-orchestrator pattern:

```markdown
---
name: go-code-review
description: [一句话描述 — third-person, ≤1024 chars]
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
审查 Go 代码变更，输出 ≤15 条优先级排序问题到终端。支持 Full/Lite/Trivial 三档，Full 档启用 7 个专家 Agent；Lite 档启用 3 个。
</objective>

<mental_model>
工作流由脚本控制（确定性），Claude 只做代码分析（推理）。每步输入输出都是文件——不依赖对话上下文传递状态。
</mental_model>

<critical_rules>
- Tier 分类、文件读写、进度报告 → 脚本执行，不用 LLM 推断
- SESSION_DIR 和 `$$` PID 在 full-review.md 中定义，贯穿整个 session
- 每个 Agent 完成后验证 findings 文件存在 + 包含 `### [P` 再继续
- --resume: 必须验证 head_sha 匹配当前 HEAD
- 所有输出使用中文
</critical_rules>

<routing>
执行完整审查（FULL/LITE tier）:
  Read `languages/go/workflows/full-review.md`

Lite 档（diff < 400行，files < 5）:
  Read `languages/go/workflows/lite-review.md`

理解报告输出格式:
  Read `languages/go/templates/report.md`

理解 Context Package 格式与 token 预算:
  Read `languages/go/templates/context-package.md`
</routing>

<quick_reference>
```bash
# 审查当前分支 vs main（最常用）
/go-code-review

# 指定分支
/go-code-review --branch feat/xxx --base develop

# 恢复中断的审查
/go-code-review --resume

# 保存完整报告到文件
/go-code-review --output report.md
```
</quick_reference>
```

**Note**: Routing uses classification tier from `classify-diff.py` output, not manual judgment. The router reads the classification result and dispatches to the appropriate workflow file. The `--resume` flag is handled inside the workflow file before Step 1 — the router simply invokes the workflow.

### Phase 4: Update Agent Frontmatter (9 files)

Add two fields to each agent's YAML frontmatter. **Do not modify agent body content.**

| Agent | `output_file` | `required_sections` |
|-------|--------------|---------------------|
| safety | `findings-safety.md` | `["### [P"]` |
| data | `findings-data.md` | `["### [P"]` |
| design | `findings-design.md` | `["### [P"]` |
| quality | `findings-quality.md` | `["### [P"]` |
| observability | `findings-observability.md` | `["### [P"]` |
| business | `findings-business.md` | `["### [P"]` |
| naming | `findings-naming.md` | `["### [P"]` |
| verifier | `verifier-results.md` | `["confirm", "downgrade", "dismiss"]` |
| coordinator | `final-report.md` | `["## Review Assumptions"]` |

Also update checkpoint in `full-review.md` Step 4 (after each agent dispatch) from weak to strong:

```bash
# Before (weak — existence only)
test -f "$SESSION_DIR/findings-{agent}.md" || echo "WARNING: {agent} findings missing"

# After (strong — content-aware)
test -f "$SESSION_DIR/findings-{agent}.md" && \
  grep -q '### \[P\|无发现\|未发现问题' "$SESSION_DIR/findings-{agent}.md" || \
  echo "WARNING: {agent} findings incomplete or missing"
```

## Acceptance Criteria

### Functional
- [ ] `/go-code-review` invocation produces identical output to current v7 behavior
- [ ] `--resume` correctly reads `workflow-state.json` and continues from pending tasks
- [ ] TRIVIAL tier exits early without running any agents
- [ ] LITE tier runs exactly 3 agents: safety, quality, observability
- [ ] FULL tier runs all 7 domain agents + Verifier (when P0/P1 findings exist) + Coordinator
- [ ] Section headers in context package exactly match: `## [Intent]`, `## [Rules]`, `## [Change Set]`, `## [Context]`, `## [Architecture Context]`
- [ ] `aggregate-findings.py` can parse findings from `findings-{agent}.md` files produced by updated workflow

### Structural
- [ ] New SKILL.md is ≤120 lines
- [ ] `full-review.md` covers Steps 1–6 with per-step input/output contracts
- [ ] `lite-review.md` exists before SKILL.md references it (atomic deploy)
- [ ] `templates/report.md` contains `### [P` finding boundary marker
- [ ] `templates/context-package.md` lists all 5 section headers with token budgets
- [ ] All 9 agent files have `output_file` and `required_sections` in frontmatter

### Non-Regression
- [ ] All Python scripts unchanged (zero diffs in `tools/*.py`)
- [ ] All Shell scripts unchanged (zero diffs in `tools/*.sh`)
- [ ] All agent body content unchanged (only frontmatter additions)
- [ ] All rules YAML files unchanged

## Dependencies & Risks

### Ordering Dependencies (strict)

```
Phase 1a (templates/report.md)
Phase 1b (templates/context-package.md)
        ↓
Phase 2a (workflows/full-review.md)
Phase 2b (workflows/lite-review.md)
        ↓ [atomic]
Phase 3 (SKILL.md router rewrite)
        ↓
Phase 4 (agent frontmatter)
```

**Never** rewrite SKILL.md router (Phase 3) before `lite-review.md` exists (Phase 2b). The router references both workflow files; a missing `lite-review.md` causes silent failure with no clear error.

### Key Risks

| Risk | Mitigation |
|------|-----------|
| Section header string drift in `context-package.md` | Copy header strings verbatim from `assemble-context.py` lines 281–287. Run grep diff after Phase 1b. |
| `SESSION_DIR` with `$$` split across files | All bash state (`SESSION_DIR`, `AGENT_ROSTER`, `TIER`, `RULES_SOURCE`) lives only in `full-review.md`. Router passes no variables. |
| Exit-code-2 LITE downgrade in wrong file | Must be inside `full-review.md` Step 3 block. Router has no visibility into exit codes from sub-workflow. |
| Agent `output_file` field has no reader yet | The strong checkpoint in `full-review.md` (Phase 4 update) is the reader. Both must be done together. |
| `lite-review.md` not created before router references it | Phases 2b and 3 are atomic — do not commit the router until lite-review.md passes review. |

## References

### Internal
- `docs/design-adjustment.md` — this plan's source spec
- `docs/workflow-patterns.md` — engineering patterns reference
- `languages/go/SKILL.md:120-514` — source for full-review.md content
- `languages/go/SKILL.md:518-558` — source for templates/report.md content
- `languages/go/tools/assemble-context.py:25-30` — TOKEN_LIMIT, RULES_MAX_LINES, CONTEXT_MAX_LINES constants
- `languages/go/tools/assemble-context.py:281-287` — load-bearing section header strings
- `languages/go/tools/aggregate-findings.py:461` — `grep -c '^### \[P'` finding boundary

### Reference Pattern
- `gsd-2/gsd-orchestrator/SKILL.md` — router structure to emulate (XML-tag pattern)
- `gsd-2/gsd-orchestrator/workflows/build-from-spec.md` — per-step input/output contract pattern
