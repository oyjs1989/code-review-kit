# Go Code Review Skill — 工程化调整方案

> 基于 gsd-2 & spec-kit 工作流模式，对现有 v7.0.0 进行结构化改造。
> 核心目标：确定性脚本控制流程，Claude 只做推理；输入输出标准化；SKILL.md 轻量化。

---

## 现状评估

### 已经对的（保留）

| 组件 | 状态 | 说明 |
|------|------|------|
| `tools/classify-diff.py` | ✅ | JSON 输出，exit code，结构清晰 |
| `tools/assemble-context.py` | ✅ | stdout/stderr 分离，metadata JSON，截断策略明确 |
| `tools/aggregate-findings.py` | ✅ | 结构化聚合，支持 exit code |
| `agents/safety.md` 等 | ✅ | YAML frontmatter，角色清晰，输出格式有规范 |
| `workflow-state.json` 模式 | ✅ | 对标 gsd-2 状态机文件 |
| `--resume` 机制 | ✅ | 对标 gsd-2 session 恢复 |
| `[1/N]` 进度显示 | ✅ | 对标 spec-kit 步骤透明度 |

### 需要改进的

| 问题 | 当前状态 | 影响 |
|------|---------|------|
| SKILL.md 过重 | 590 行，流程 + 模板 + 说明全混在一起 | Claude 需要解析大量无关内容才能执行当前步骤 |
| 无输出模板文件 | 报告格式内嵌在 SKILL.md 的 "Output Format" 节 | 格式难以独立维护，每次执行都要重新理解 |
| Agent 输出无文件契约 | 约定 `findings-{agent}.md` 但无 schema 定义 | Checkpoint 验证只能检查文件是否存在，无法验证格式 |
| Context Package 无分段预算 | 16k token 全局限制，截断策略分散在代码里 | Claude 不知道每段的重要性权重 |

---

## 调整后的目录结构

```
languages/go/
  SKILL.md                      ← 路由器（目标 <120 行）
  workflows/
    full-review.md              ← 完整流程（当前 SKILL.md 步骤 1-6）
    lite-review.md              ← Lite 档简化流程
  templates/
    report.md                   ← 报告输出模板（从 SKILL.md 提取）
    context-package.md          ← Context Package 格式规范
  agents/                       ← （现有，保持不变）
    safety.md
    data.md
    design.md
    quality.md
    observability.md
    business.md
    naming.md
    verifier.md
    coordinator.md
  tools/                        ← （现有 Python/Shell 脚本，保持不变）
    classify-diff.py
    assemble-context.py
    aggregate-findings.py
    scan-architecture.py
    scan-rules.sh
    run-go-tools.sh
    .golangci.yml
  rules/                        ← （现有，保持不变）
    safety.yaml
    data.yaml
    quality.yaml
    observability.yaml
```

**变化**：新增 `workflows/` 和 `templates/` 两个目录；SKILL.md 瘦身为路由器。

---

## SKILL.md 改造：路由器模式

参考 gsd-2 SKILL.md 结构，新的 SKILL.md 只做三件事：

```markdown
---
name: go-code-review
description: ...
version: 8.0.0
allowed-tools: [...]
---

<objective>
用 /go-code-review 审查 Go 代码变更，输出 ≤15 条优先级排序问题到终端。
</objective>

<routing>
执行完整审查        → 读 workflows/full-review.md
Lite 档（diff<400行）→ 读 workflows/lite-review.md
理解报告格式        → 读 templates/report.md
理解 Context 格式   → 读 templates/context-package.md
</routing>

<quick_reference>
# 最常用的 3 个调用
/go-code-review                              # 审查当前分支 vs main
/go-code-review --branch feat/x --base dev  # 指定分支
/go-code-review --resume                    # 恢复中断的审查
</quick_reference>

<critical_rules>
- 确定性判断（tier 分类、文件读写、进度报告）→ 脚本完成，不用 LLM 推断
- Agent 输出 → 写入约定路径 findings-{agent}.md，格式见 templates/report.md
- 每步执行后 → 验证输出文件存在，再进入下一步
- head_sha 校验 → --resume 时必须验证代码未变更
</critical_rules>
```

---

## 新增：`workflows/full-review.md`

当前 SKILL.md 步骤 1-6 整体迁移，结构不变，但需明确：

**每步的输入/输出契约**（新增，对标 gsd-2 task spec 格式）：

```markdown
### Step 1: 获取代码变更

输入：
- SOURCE_BRANCH（参数或 git branch --show-current）
- BASE_BRANCH（参数，默认 main）

输出（写入 $SESSION_DIR/）：
- diff.txt         ← git diff 内容
- files.txt        ← 变更的 .go 文件列表
- gitlog.txt       ← 最近 5 条 commit
- classification.json ← classify-diff.py 输出

成功条件：diff.txt 非空 && files.txt 非空
失败处理：输出 ERROR，rm -rf $SESSION_DIR，exit 1
```

每步都有明确的**输入来源 → 写入路径 → 成功条件 → 失败处理**四元组。Claude 按此执行，不需要自行判断。

---

## 新增：`templates/report.md`

从 SKILL.md 的 Output Format 节提取，独立成文件。

```markdown
# Go 代码审查报告

## 审查摘要

| 指标 | 数量 |
|------|------|
| P0（必须修复） | {p0_count} 个 |
| P1（强烈建议） | {p1_count} 个 |
| P2（建议优化） | {p2_count} 个 |

## P0（必须修复）

### [P0] {rule_id} · {file}:{line}
**来源**: {agent}
**置信度**: {confidence}
**needs_clarification**: {null | "具体问题"}

**问题描述**: {中文说明}

**修改建议**:
```go
// 修复代码
```

---

## Appendix
（若总 findings > 15，剩余条目放此节）
```

Agent 输出时直接按此格式写 findings-{agent}.md，`aggregate-findings.py` 解析此格式聚合。

---

## 新增：`templates/context-package.md`

明确每段的 token 预算，让 Claude 和脚本都知道截断优先级：

```markdown
# Context Package 格式规范

## 结构与 Token 预算（总限 16k）

| 段落 | 内容来源 | 预算 | 截断策略 |
|------|---------|------|---------|
| [Intent] | gitlog.txt 最近 5 条 | ~200 tokens | 永不截断 |
| [Rules] | rules/*.yaml 或项目规则文件 | ~2k tokens | 按关键词过滤不相关节 |
| [Change Set] | diff.txt | ~8k tokens | 超出时截断尾部，添加 TRUNCATION_WARNING |
| [Context] | 变更函数完整体 | ~4k tokens | 超 FUNC_MAX_LINES 只保留签名 |
| [Architecture] | scan-architecture.py 输出 | ~2k tokens | Full 档专属，Lite 档省略 |

## 截断优先级

超出总预算时，按以下顺序压缩：
1. [Architecture] → 先压缩（最低优先级）
2. [Change Set] → 截断尾部（exit code 2 警告）
3. [Context] → 降为签名模式
4. [Rules] → 关键词过滤
5. [Intent] → 永不截断

## 段落格式

每段用固定 header 标记，供 aggregate-findings.py 解析：
```
## [Intent]
{content}

## [Rules]
{content}

## [Change Set]
\`\`\`diff
{content}
\`\`\`

## [Context]
\`\`\`go
{content}
\`\`\`

## [Architecture Context]
{content}
```
```

---

## Agent 输出契约标准化

现有 agent frontmatter（以 safety.md 为例）已有 `name`、`model`、`tools`，需补充：

```yaml
---
name: safety
output_file: "findings-safety.md"    # ← 新增：约定输出路径（相对 $SESSION_DIR）
required_sections:                   # ← 新增：Checkpoint 验证用
  - "### [P"                         #   至少有一条 finding 或明确的 "无问题" 声明
model: inherit
color: red
tools: ["Read", "Grep", "Glob"]
---
```

Checkpoint 验证从"文件存在"升级为"文件存在 && 包含必要 section"：

```bash
# 当前（弱验证）
test -f "$SESSION_DIR/findings-safety.md" || echo "WARNING: safety findings missing"

# 改进后（强验证）
test -f "$SESSION_DIR/findings-safety.md" && \
  grep -q '### \[P\|无发现\|未发现问题' "$SESSION_DIR/findings-safety.md" || \
  echo "WARNING: safety findings incomplete"
```

---

## 输入/输出全链路契约

```
用户输入
  /go-code-review [--branch X] [--base Y] [--resume]
          │
          ▼
SKILL.md（路由）
  → 读 workflows/full-review.md
          │
          ▼ Step 1
  classify-diff.py → classification.json（JSON, exit 0/1）
          │
          ▼ Step 2
  assemble-context.py → context-package.md（Markdown, exit 0/2）
                      → metadata（JSON to stderr）
          │
          ▼ Step 3
  [可选] scan-architecture.py → architecture-context.json
          │
          ▼ Step 4
  run-go-tools.sh / golangci-lint → diagnostics.json（JSON）
  scan-rules.sh → rule-hits.json（JSON）
          │
          ▼ Step 5（顺序执行）
  Agent safety → findings-safety.md（Markdown, format: templates/report.md）
  Agent data   → findings-data.md
  ...（按 agent_roster 顺序）
          │
          ▼ Step 6
  aggregate-findings.py → review-{timestamp}.md（Markdown）
          │
          ▼ 终端输出
  cat review-{timestamp}.md
```

每个节点：
- **确定性脚本**（Python/Shell）处理文件读写、格式转换、错误检测
- **Claude/Agent**（LLM）只做代码分析和自然语言输出
- **文件**是唯一的节点间通信方式，不依赖对话上下文

---

## 实施步骤

| 步骤 | 工作 | 影响范围 |
|------|------|---------|
| 1 | 创建 `templates/report.md`，从 SKILL.md Output Format 节提取 | 新文件 |
| 2 | 创建 `templates/context-package.md`，明确 token 预算 | 新文件 |
| 3 | 创建 `workflows/full-review.md`，从 SKILL.md 步骤 1-6 迁移 | 新文件 |
| 4 | 改写 SKILL.md 为路由器（120 行以内） | 修改现有文件 |
| 5 | 给每个 agent frontmatter 补充 `output_file` + `required_sections` | 修改 9 个 agent 文件 |
| 6 | 创建 `workflows/lite-review.md`（Lite 档简化版） | 新文件 |

Python 脚本和 Shell 工具**不需要改动**，现有实现已经符合工程化模式。
