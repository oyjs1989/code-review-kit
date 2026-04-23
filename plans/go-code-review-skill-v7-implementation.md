# Go Code Review Skill — v7.0.0 完整实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**目标：** 按 `design.md` 的完整规范实现 Go Code Review Skill v7.0.0，将当前 v6.0.0（纯内联 Bash 编排）升级为 Python helper script 驱动的分层架构，新增架构预扫描、Loop 模式、`--resume`、CLI 参数、Checkpoint 验证、Review Coordinator Agent。

**参考文档：** `design.md`（系统完整规范，49.8kB）

---

## 当前状态 vs 目标状态

| 组件 | 当前状态 | 目标状态 |
|------|---------|---------|
| `languages/go/SKILL.md` | v6.0.0（内联 Bash 编排，347 行） | v7.0.0（调用 Python scripts，支持全部 CLI 参数） |
| `tools/classify-diff.py` | ❌ 不存在 | ✅ 创建 |
| `tools/assemble-context.py` | ❌ 不存在 | ✅ 创建 |
| `tools/scan-architecture.py` | ❌ 不存在 | ✅ 创建（Step 3.5 全新功能） |
| `tools/aggregate-findings.py` | ❌ 不存在 | ✅ 创建 |
| `agents/coordinator.md` | ❌ 不存在 | ✅ 创建 |
| `agents/verifier.md` | ✅ 存在（基础版） | 更新输入格式匹配新设计 |
| `agents/safety.md` 等 6 个 | ✅ 存在，但引用 `/tmp/` | 修复为 `$SESSION_DIR` |
| golangci-lint 集成 | ❌ 使用 go vet/staticcheck 分开跑 | 作为 Tier 1 主扫描器 |
| Loop 模式 | ❌ 不存在 | ✅ workflow-state.json + 任务包分拆 |
| `--resume` 标志 | ❌ 不存在 | ✅ 读取 workflow-state.json 续跑 |
| 架构预扫描（Step 3.5） | ❌ 不存在 | ✅ module_map + high_risk_modules |
| Checkpoint 验证 | ❌ 不存在 | ✅ 每步执行后验证输出文件存在 |

---

## 实现范围外（不实现）

- 任何外部 API 或网络请求
- 向量相似度计算（去重用精确规则）
- `python-unidiff` 等第三方库（所有脚本只用 Python stdlib）
- CI/CD 集成（仅本地 Claude Code 触发）

---

## 关键技术决策

### 1. golangci-lint vs 独立工具

设计要求用 `golangci-lint run --output.json.path=stdout ./...` 替代当前分开跑的 `go build`/`go vet`/`staticcheck`。

**决策：** 使用 golangci-lint 作为 Tier 1 **主扫描器**，但在 golangci-lint 未安装时降级为当前 `run-go-tools.sh`（已有）。`run-go-tools.sh` 保留作为兜底，不删除。

理由：golangci-lint 输出统一 JSON（`Issues[].FromLinter`），`aggregate-findings.py` 只需一个 parser；单独工具需维护多个解析逻辑。

**golangci-lint 最小配置：**
```yaml
# languages/go/tools/.golangci.yml（新建）
version: "2"
run:
  timeout: 5m
  tests: false
linters:
  default: none
  enable: [errcheck, govet, staticcheck, ineffassign, unused, gosec, gocognit, misspell]
  settings:
    gocognit:
      min-complexity: 15
exclusions:
  generated: strict
output:
  formats:
    json:
      path: stdout
```

### 2. Python Scripts 依赖方针

所有 `.py` 脚本**只使用 Python stdlib**（json、re、subprocess、sys、os、pathlib、argparse）。不 pip install 任何包。原因：code review tool 应零外部依赖。

### 3. Loop 模式的任务包边界

`aggregate-findings.py` 不做 AST 分析（需 Go 工具链）。任务包边界用简化策略：**按目录分组**，同目录的变更文件作为一个任务包，上限 150 行 diff；超出则按行数拆分。AST 调用关系图省略（YAGNI，精度够用）。

### 4. 顺序还是并行 Agent 执行

设计 §4.3 明确要求**顺序执行**（Skill 规范约束 Claude 依次调用 Agent tool）。与 v6.0.0 的批量/并行模式不同，v7 不并行派发多 Agent。

---

## 阶段一：Python Helper Scripts

> 这四个脚本是整个升级的基础，其他所有任务依赖它们。

### Task 1.1 — 创建 `classify-diff.py`

**文件：** `languages/go/tools/classify-diff.py`

**功能：** 接收 diff 统计，输出分流结果 JSON。

**CLI：**
```bash
python3 classify-diff.py \
  --diff-lines <int> \
  --files-changed <int> \
  --files "src/auth/login.go src/service/order.go" \
  [--diff-file /path/to/diff.txt]   # 可选，用于检测注释变更
```

**输出 JSON（stdout）：**
```json
{
  "tier": "FULL",
  "trigger_reason": "diff_lines=620",
  "agent_roster": ["safety", "data", "design", "quality", "observability", "business", "naming"],
  "rules_source": "project_redlines",
  "has_redlines": true
}
```

**分流逻辑（按 design.md §2.1 步骤 2）：**
1. **Trivial：** `diff_lines < 20` 且所有文件均为文档/配置类型 **或** `.go` 文件变更行 100% 为注释行
   - 文档类型：`.md`, `.txt`, `.rst`
   - 配置类型：`.yml`, `.yaml`, `.toml`, `.json`, `.ini`, `.env.example`
   - 注释检测（如传入 `--diff-file`）：`grep '^+'` 非 `+++` 行，过滤掉以 `//` 或 `/*` 开头的行，若结果为空 → 纯注释
2. **Lite：** `20 <= diff_lines < 400` 且 `files_changed < 5` 且未触及敏感路径
3. **Full：** `diff_lines >= 400` 或 `files_changed >= 5` 或匹配敏感路径

**敏感路径正则：** `(auth|crypto|payment|permission|admin)/`

**规范文件查找（rules_source 逻辑）：**
按顺序查找，找到即停止：
1. `.claude/review-rules.md` → `project_redlines`，`has_redlines=true`
2. `AGENTS.md` / `CLAUDE.md` / `docs/` 下 `*style*`/`*rule*`/`*convention*` md → `project_rules`
3. 均无 → `built_in`

**agent_roster 逻辑：**
- Trivial：`[]`
- Lite：`["safety", "quality", "observability"]`
- Full：`["safety", "data", "design", "quality", "observability", "business", "naming"]`

---

### Task 1.2 — 创建 `assemble-context.py`

**文件：** `languages/go/tools/assemble-context.py`

**功能：** 从 diff、git log、规范文件组装 Context Package。

**CLI：**
```bash
python3 assemble-context.py \
  --diff /tmp/diff.txt \
  --rules-source project_redlines \
  --rules-file .claude/review-rules.md \
  --git-log /tmp/gitlog.txt \
  [--architecture-context /tmp/architecture-context.json]  # Step 3.5 可选追加
```

**输出：** `stdout`（Markdown Context Package）+ stderr 输出元数据 JSON

**Context Package 格式（design.md §2 步骤 3）：**
```markdown
## [Intent]
{git log 最近 5 条提交摘要}

## [Rules]
{规范文件内容，超 300 行时截取与变更模块相关段落}

## [Change Set]
{完整 diff 原文}

## [Context]
{变更函数签名 + 直接调用方（通过 git show 或 grep 提取）}

（如传入 --architecture-context，追加：）
## [Architecture Context]
{architecture_context 字段内容}
```

**截断规则：**
- `[Change Set]` 优先保留全文（不截断）
- `[Rules]` 超 300 行 → 保留与变更文件路径相关的段落（按文件名/包名匹配）
- `[Context]` 超 200 行 → 只保留函数签名（去掉函数体）
- 整体估算 token：中文约 1.5 字符/token，英文约 4 字符/token；总限 16000 token
- 若 `[Change Set]` 被截断 → stderr 输出 `TRUNCATION_WARNING: change_set` 供 SKILL.md 检测

**元数据（stderr JSON）：**
```json
{
  "estimated_tokens": 8200,
  "token_limit": 16000,
  "sections_included": ["intent", "rules", "change_set", "context"],
  "truncated_sections": []
}
```

**变更函数提取策略（无外部 AST 工具）：**
1. 从 diff 中提取变更行号（`+` 行）
2. 对每个变更文件，用 `grep -n "^func "` 定位函数边界
3. 找到包含变更行的函数，提取完整函数定义（从 `func` 到对应 `}`）
4. 每个函数最多提取 80 行；超限则只提取签名行

---

### Task 1.3 — 创建 `scan-architecture.py`

**文件：** `languages/go/tools/scan-architecture.py`

**功能：** Full 档架构预扫描，提取模块结构和高风险模块。

**CLI：**
```bash
python3 scan-architecture.py \
  --files "src/auth/login.go src/service/order.go" \
  [--gomod go.mod]
```

**输出 JSON（stdout，design.md §2 步骤 3.5）：**
```json
{
  "module_map": {
    "auth": ["login.go", "middleware.go"],
    "service": ["order.go"]
  },
  "high_risk_modules": ["auth"],
  "key_interfaces": [
    "type AuthService interface { Login(...) }",
    "type OrderRepository interface { FindByID(...) }"
  ],
  "architecture_context": "分层架构：handler → service → repository，auth 为核心安全模块",
  "skipped_files": []
}
```

**实现逻辑：**
1. 读取 `go.mod` → 提取 `module` 名和主要依赖
2. 对每个变更文件，用正则提取 `package` 声明
3. 提取 `type ... interface` 和主要 `struct` 定义（不解析函数体，用正则匹配 `^type \w+ interface`）
4. 识别目录层级：`handler/` → handler 层，`service/` → service 层，`repository/` 或 `repo/` 或 `dal/` → repository 层
5. 生成自然语言 `architecture_context` 描述（分层关系 + 高风险模块）
6. 高风险模块：匹配 `(auth|crypto|payment|permission|admin)/`

**超时处理：** 脚本本身不设超时，由 SKILL.md 在调用时加 `timeout 30`；超时则 SKILL.md 跳过，`architecture_context` 置空。

---

### Task 1.4 — 创建 `aggregate-findings.py`

**文件：** `languages/go/tools/aggregate-findings.py`

**功能：** 读取所有 agent findings 文件，执行去重、误报过滤、排序、截断，输出最终 Markdown 报告。

**CLI：**
```bash
python3 aggregate-findings.py \
  --findings-dir .review/run-abc123-1234 \
  [--redlines-file .claude/review-rules.md] \
  [--review-ignore-flags "security:src/auth.go:45,performance:src/service.go:88"] \
  --max-output 15 \
  --output .review/results/review-$(date +%Y%m%d-%H%M%S).md
```

**输出：** 最终 Markdown 审查报告（含 Appendix）+ stdout 输出终端摘要

**Pipeline（design.md §2 步骤 5）：**
1. **解析：** 读取 `$findings_dir/findings-*.md`，解析每条 `### [Px] RULE-NNN · file:line` 格式的 finding
2. **去重：**
   - 相同文件 + 相同行号 + 相同 rule category → 合并，取最高严重等级
   - 相同文件 + 相邻行（±3 行）+ 相同 category → 合并
3. **红线优先：** 若 `--redlines-file` 存在，匹配其中规则的 findings 强制 severity >= P1，跳过置信度过滤
4. **review:ignore 过滤：** 从 `--review-ignore-flags` 解析跳过列表
5. **置信度过滤：** 保留 confidence >= 0.75（红线 findings 豁免）
6. **模糊发现截断：** 同 category 内 confidence < 0.85 的最多保留 3 条，超出合并为 P3 摘要
7. **排序：** Severity（P0→P3）→ Confidence 降序 → 文件路径
8. **截断：** 输出前 `--max-output` 条（默认 15），剩余写入 Appendix

**Finding 解析格式（与 agents 输出格式对应）：**
```
### [P0] SAFE-003 · src/auth.go:42-47
**confidence:** 0.98
**needs_clarification:** null
...
```

**输出报告格式：** 参考 `design.md §2 步骤 6` 的 Markdown 模板（含 Summary 表、Review Assumptions、Findings 节、Appendix）。

**注意：** `aggregate-findings.py` 不调用 AI，完全确定性。Review Assumptions 由 Coordinator Agent 生成（Task 3.2），然后 `aggregate-findings.py` 插入到报告中。

**实际处理顺序：** SKILL.md 先运行 `aggregate-findings.py`（纯过滤），再调 Coordinator Agent 生成 Assumptions，最后合并输出最终报告。

---

## 阶段二：SKILL.md 完整重写（v7.0.0）

### Task 2.1 — 重写 SKILL.md frontmatter 和架构说明

**文件：** `languages/go/SKILL.md`

**frontmatter 更新：**
```yaml
---
name: go-code-review
description: 'Use when the user asks to "review Go code", "check Go code quality", "review this PR", "code review", or mentions Go error handling, concurrency safety, GORM patterns, UNIX principles, naming conventions. Orchestrates Go code review: golangci-lint + YAML rules + 7 domain-expert AI agents. Supports --branch, --base, --output, --resume flags.'
version: 7.0.0
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
  - Agent
  - Read
  - Write
---
```

---

### Task 2.2 — 重写 Step 1：代码获取（含 CLI 参数解析）

**参数解析块（SKILL.md 最顶部）：**

说明如何从 slash command 参数解析 `--branch`、`--base`、`--output`、`--resume`：

```bash
# 参数解析（Claude 从 skill 调用参数中提取）
# 默认值
SOURCE_BRANCH=$(git branch --show-current)
BASE_BRANCH="main"
OUTPUT_FILE=""
RESUME=false

# 从参数覆盖（Claude 解析 slash command 参数）
# /go-code-review --branch feat/xxx --base develop --output report.md
```

**Step 1 操作（对应 design.md §2 步骤 1）：**

```bash
# 确认分支存在
git rev-parse "$BASE_BRANCH" > /dev/null 2>&1 || { echo "ERROR: base branch '$BASE_BRANCH' not found"; exit 1; }
git rev-parse "$SOURCE_BRANCH" > /dev/null 2>&1 || { echo "ERROR: source branch '$SOURCE_BRANCH' not found"; exit 1; }

# 获取 SHA
BASE_SHA=$(git rev-parse "$BASE_BRANCH")
HEAD_SHA=$(git rev-parse "$SOURCE_BRANCH" | head -c 8)

# 建立 session 目录
SESSION_DIR=".review/run-${HEAD_SHA}-$$"
mkdir -p "$SESSION_DIR"

# 获取 diff
git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --diff-filter=AM > "$SESSION_DIR/diff.txt"
git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --name-only --diff-filter=AM | grep '\.go$' > "$SESSION_DIR/files.txt"

# git log
git log --oneline -5 "${BASE_BRANCH}..${SOURCE_BRANCH}" > "$SESSION_DIR/gitlog.txt"

# 统计
DIFF_LINES=$(wc -l < "$SESSION_DIR/diff.txt")
FILES_CHANGED=$(wc -l < "$SESSION_DIR/files.txt")
```

**Checkpoint 1：**
```bash
# Claude 验证：
test -s "$SESSION_DIR/diff.txt" || { echo "ERROR: diff is empty"; rm -rf "$SESSION_DIR"; exit 1; }
test -s "$SESSION_DIR/files.txt" || { echo "ERROR: no Go files changed"; rm -rf "$SESSION_DIR"; exit 1; }
```

---

### Task 2.3 — 重写 Step 2：变更分流（调用 classify-diff.py）

```bash
echo "[2/6] 变更分流..."
CLASSIFICATION=$(python3 languages/go/tools/classify-diff.py \
  --diff-lines "$DIFF_LINES" \
  --files-changed "$FILES_CHANGED" \
  --files "$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')" \
  --diff-file "$SESSION_DIR/diff.txt")

TIER=$(echo "$CLASSIFICATION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tier'])")
RULES_SOURCE=$(echo "$CLASSIFICATION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['rules_source'])")
echo "$CLASSIFICATION" > "$SESSION_DIR/classification.json"
echo "✓ $TIER 档，规则来源：$RULES_SOURCE"
```

**Trivial 档早退：**
```bash
if [ "$TIER" = "TRIVIAL" ]; then
  echo "变更为文档/配置/注释类，无需深度审查。"
  echo "变更摘要：$(cat "$SESSION_DIR/gitlog.txt" | head -3)"
  rm -rf "$SESSION_DIR"
  exit 0
fi
```

---

### Task 2.4 — 重写 Step 3：上下文组装（调用 assemble-context.py）

确定规范文件路径逻辑（按查找顺序）：

```bash
echo "[3/6] 组装上下文..."
RULES_FILE=""
for f in ".claude/review-rules.md" "AGENTS.md" "CLAUDE.md"; do
  [ -f "$f" ] && RULES_FILE="$f" && break
done
# 若均无，检查 docs/ 下命名规范文件
if [ -z "$RULES_FILE" ]; then
  RULES_FILE=$(find docs/ -name "*style*" -o -name "*rule*" -o -name "*convention*" 2>/dev/null | grep '\.md$' | head -1)
fi

python3 languages/go/tools/assemble-context.py \
  --diff "$SESSION_DIR/diff.txt" \
  --rules-source "$RULES_SOURCE" \
  ${RULES_FILE:+--rules-file "$RULES_FILE"} \
  --git-log "$SESSION_DIR/gitlog.txt" \
  > "$SESSION_DIR/context-package.md" \
  2> "$SESSION_DIR/context-meta.json"
```

**Checkpoint 3：**
```bash
# 检测 change_set 截断警告
if grep -q "change_set" "$SESSION_DIR/context-meta.json"; then
  echo "WARNING: [Change Set] 被截断，降档为 Lite 处理"
  TIER="LITE"
fi
```

---

### Task 2.5 — 新增 Step 3.5：架构预扫描（仅 Full 档）

```bash
if [ "$TIER" = "FULL" ]; then
  echo "[3.5/6] 架构预扫描（Full 档）..."
  FILES_LIST=$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')
  
  timeout 30 python3 languages/go/tools/scan-architecture.py \
    --files "$FILES_LIST" \
    --gomod "go.mod" \
    > "$SESSION_DIR/architecture-context.json" 2>/dev/null
  
  if [ $? -eq 0 ] && [ -s "$SESSION_DIR/architecture-context.json" ]; then
    ARCH_CONTEXT=$(python3 -c "import sys,json; d=json.load(open('$SESSION_DIR/architecture-context.json')); print(d.get('architecture_context',''))")
    HIGH_RISK=$(python3 -c "import sys,json; d=json.load(open('$SESSION_DIR/architecture-context.json')); print(','.join(d.get('high_risk_modules',[])))")
    
    # 将 architecture_context 追加到 Context Package
    python3 languages/go/tools/assemble-context.py \
      --diff "$SESSION_DIR/diff.txt" \
      --rules-source "$RULES_SOURCE" \
      ${RULES_FILE:+--rules-file "$RULES_FILE"} \
      --git-log "$SESSION_DIR/gitlog.txt" \
      --architecture-context "$SESSION_DIR/architecture-context.json" \
      > "$SESSION_DIR/context-package.md" \
      2> "$SESSION_DIR/context-meta.json"
    
    echo "✓ 识别 $(cat "$SESSION_DIR/architecture-context.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['module_map']))") 个模块，高风险：$HIGH_RISK"
  else
    echo "⚠ 架构预扫描超时或跳过，继续执行"
  fi
fi
```

---

### Task 2.6 — 重写 Step 4：Tier 1 golangci-lint + Agent 执行

**Tier 1（golangci-lint 优先，降级为 run-go-tools.sh）：**

```bash
echo "[4/6] 执行审查..."
if command -v golangci-lint > /dev/null 2>&1; then
  FILES_LIST=$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')
  golangci-lint run --output.json.path="$SESSION_DIR/lint-results.json" \
    --config languages/go/tools/.golangci.yml \
    $FILES_LIST 2>/dev/null || true
  # 将 golangci-lint JSON 转换为 findings-lint.md 格式
  python3 languages/go/tools/aggregate-findings.py \
    --lint-json "$SESSION_DIR/lint-results.json" \
    --output "$SESSION_DIR/findings-lint.md" 2>/dev/null || true
else
  # 降级：使用现有 run-go-tools.sh + scan-rules.sh
  cat "$SESSION_DIR/files.txt" | bash languages/go/tools/run-go-tools.sh > "$SESSION_DIR/diagnostics.json"
  cat "$SESSION_DIR/files.txt" | bash languages/go/tools/scan-rules.sh > "$SESSION_DIR/rule-hits.json"
fi
```

**大型变更判断（是否进入 Loop 模式）：**

```bash
if [ "$TIER" = "FULL" ] && [ "$DIFF_LINES" -ge 400 ]; then
  LOOP_MODE=true
  echo "  → Loop 模式（diff_lines=$DIFF_LINES >= 400）"
else
  LOOP_MODE=false
fi
```

**普通变更（非 Loop）— 顺序执行 Agents：**

从 `$SESSION_DIR/classification.json` 读取 `agent_roster`，**顺序**（非并行）调用：

```
对 agent_roster 中每个 agent，依次：
1. Agent(agents/{agent}.md, prompt=<agent.md内容 + $SESSION_DIR/context-package.md内容>)
2. Agent 将 findings 写入 $SESSION_DIR/findings-{agent}.md
3. Bash 验证文件存在（Checkpoint）：
   test -f "$SESSION_DIR/findings-{agent}.md" || { echo "ERROR: {agent} findings missing"; exit 1; }
```

**Loop 模式（大型变更）：**

```bash
# 生成任务包
python3 languages/go/tools/classify-diff.py \
  --generate-task-packs \
  --diff-file "$SESSION_DIR/diff.txt" \
  --agent-roster "$(cat "$SESSION_DIR/classification.json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(d['agent_roster']))")" \
  > "$SESSION_DIR/task-packs.json"

# 初始化 workflow-state.json
python3 -c "
import json, sys
packs = json.load(open('$SESSION_DIR/task-packs.json'))
state = {
  'head_sha': '$(git rev-parse HEAD)',
  'completed_tasks': [],
  'in_progress_tasks': [],
  'pending_tasks': [p['task_id'] for p in packs['tasks']],
  'skipped_tasks': []
}
json.dump(state, open('.review/workflow-state.json', 'w'), ensure_ascii=False, indent=2)
"
```

Loop 执行：对每个任务包，Claude 写入 `in_progress`，派发对应 Agent，写入 `completed` 或 `skipped`（最多重试 2 次）。

**Verifier（Full 档，所有 Agent 完成后）：**

```bash
cat "$SESSION_DIR"/findings-*.md > "$SESSION_DIR/all-findings.md"

# 只有存在 P0/P1 时才调 Verifier
P0P1_COUNT=$(grep -c '\[P0\]\|\[P1\]' "$SESSION_DIR/all-findings.md" || echo 0)
if [ "$P0P1_COUNT" -gt 0 ]; then
  Agent(agents/verifier.md, prompt=<verifier.md内容 + context-package.md内容 + all-findings.md中P0/P1条目>)
  # Verifier 将结果写入 $SESSION_DIR/verifier-results.md
  # Claude 根据 confirm/downgrade/dismiss 更新 all-findings.md
fi
```

---

### Task 2.7 — 重写 Step 5：调用 aggregate-findings.py

```bash
echo "[5/6] 聚合与过滤..."

# 收集 review:ignore 标记
IGNORE_FLAGS=$(git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --diff-filter=AM -- '*.go' | \
  grep '^+' | grep 'review:ignore' | \
  sed 's/.*review:ignore \([a-z]*\).*/\1/' | \
  tr '\n' ',')

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE=".review/results/review-${TIMESTAMP}.md"
mkdir -p .review/results

python3 languages/go/tools/aggregate-findings.py \
  --findings-dir "$SESSION_DIR" \
  ${RULES_FILE:+--redlines-file "$RULES_FILE"} \
  ${IGNORE_FLAGS:+--review-ignore-flags "$IGNORE_FLAGS"} \
  --max-output 15 \
  --output "$REPORT_FILE"
```

**Checkpoint 5：**
```bash
test -f "$REPORT_FILE" || { echo "ERROR: report generation failed"; exit 1; }
FINDING_COUNT=$(grep -c '^### \[P' "$REPORT_FILE" || echo 0)
echo "✓ 过滤后 $FINDING_COUNT 条（覆盖 $(wc -l < "$SESSION_DIR/files.txt") 个文件）"
```

---

### Task 2.8 — 重写 Step 6：输出 + 清理

```bash
echo "[6/6] 输出结果..."

# 终端格式化输出（从 REPORT_FILE 提取摘要）
python3 -c "
import sys, re
content = open('$REPORT_FILE').read()
# 提取 Summary 表和前 15 条 findings
# 输出 design.md §2 步骤 6 中的终端格式
print(content[:3000])  # 简化：直接输出报告前段
"

# 如果指定了 --output 参数，复制完整报告到目标路径
if [ -n "$OUTPUT_FILE" ]; then
  cp "$REPORT_FILE" "$OUTPUT_FILE"
  echo "完整报告：$OUTPUT_FILE"
fi

echo "完整报告：$REPORT_FILE"

# 清理 session 目录
rm -rf "$SESSION_DIR"
```

---

### Task 2.9 — 新增 `--resume` 支持

**在 SKILL.md 最顶部（参数解析后立即处理）：**

```bash
if [ "$RESUME" = "true" ]; then
  if [ ! -f ".review/workflow-state.json" ]; then
    echo "ERROR: 无中断审查可恢复（.review/workflow-state.json 不存在）"
    exit 1
  fi
  
  SAVED_SHA=$(python3 -c "import json; d=json.load(open('.review/workflow-state.json')); print(d['head_sha'])")
  CURRENT_SHA=$(git rev-parse HEAD)
  
  if [ "$SAVED_SHA" != "$CURRENT_SHA" ]; then
    echo "ERROR: 代码已变更（saved=$SAVED_SHA, current=$CURRENT_SHA），请重新执行完整审查"
    exit 1
  fi
  
  PENDING=$(python3 -c "import json; d=json.load(open('.review/workflow-state.json')); print(len(d['pending_tasks']))")
  if [ "$PENDING" -eq 0 ]; then
    echo "INFO: 无未完成任务，直接执行步骤 5 聚合"
  fi
  
  echo "恢复中断审查（已完成 tasks: $COMPLETED，剩余: $PENDING）..."
  # 跳过步骤 1-3，直接从 pending_tasks 继续步骤 4 Loop
fi
```

---

### Task 2.10 — 进度输出

在每个主步骤前加进度行：
```bash
echo "[1/6] 获取代码变更..."
echo "[2/6] 变更分流..."
echo "[3/6] 组装上下文..."
echo "[3.5/6] 架构预扫描（Full 档）..."  # 仅 Full 档
echo "[4/6] 执行审查..."
echo "[5/6] 聚合与过滤..."
echo "[6/6] 输出结果..."
```

---

## 阶段三：Agent 文件更新

### Task 3.1 — 修复 6 个 Agent 的 /tmp/ 路径引用

**涉及文件：**
- `languages/go/agents/safety.md` — `/tmp/diagnostics.json` → `$SESSION_DIR/diagnostics.json`（约 3 处）
- `languages/go/agents/data.md` — 同上
- `languages/go/agents/quality.md` — `/tmp/diagnostics.json` + `/tmp/metrics.json` → `$SESSION_DIR/diagnostics.json`
- `languages/go/agents/observability.md` — `/tmp/metrics.json` → `$SESSION_DIR/diagnostics.json`

**操作：** 在每个文件中，将所有 `/tmp/diagnostics.json`、`/tmp/rule-hits.json`、`/tmp/metrics.json` 替换为 `$SESSION_DIR/` 前缀的对应文件。

**注意：** 上述路径在 agent prompt 中作为指令文本出现，不是真实 shell 代码。替换时保持上下文含义不变（即"从 `$SESSION_DIR/diagnostics.json` 读取工具分析结果"）。

---

### Task 3.2 — 创建 Review Coordinator Agent

**文件：** `languages/go/agents/coordinator.md`

**功能：** 生成 Review Assumptions 节 + 将过滤后 findings 格式化为最终报告（不做过滤/去重/排序）。

**frontmatter：**
```yaml
---
name: coordinator
description: |
  Review Coordinator: generates Review Assumptions section describing review coverage,
  skipped files, loaded rules version, and architectural assumptions. Use after aggregate-findings.py
  has already filtered and sorted findings. Do NOT use for code analysis.
model: inherit
color: gray
tools: ["Read"]
---
```

**输入（由 SKILL.md 传入）：**
```markdown
## [Context Package]
{context-package.md 内容}

## [Filtered Findings]
{aggregate-findings.py 输出的过滤后 findings（已去重、排序、截断至 ≤15 条）}

## [Coverage Summary]
files_reviewed: 12 / 14
skipped: src/gen/pb.go（auto_generated）, src/legacy/migrate.go（context_overflow）
rules_source: project_redlines（v1.2.0）
```

**Coordinator 职责：**
1. 根据 Context Package 中的架构信息生成 `## Review Assumptions` 节（覆盖边界、跳过原因、规则版本、架构假设）
2. 将 Filtered Findings 原样格式化到报告中，**不修改、不过滤、不重新排序**

**Prompt 约束：**
```
不要自行分析代码，不要增减 findings，不要修改严重等级。
只做两件事：1) 生成 Review Assumptions 2) 格式化已有 findings
```

---

### Task 3.3 — 更新 Agent Findings 输出格式

当前各 agent 的 finding 格式缺少 `confidence` 和 `needs_clarification` 字段（design.md §4.1 要求）。

**目标格式（在各 agent 的 Output 格式说明中更新）：**
```markdown
### [P0] SAFE-003 · src/auth.go:42-47

**SQL Injection vulnerability in user_login()**

**建议：** 使用参数化查询替代字符串拼接
**置信度：** 0.98
**needs_clarification：** null
```

**涉及文件：** 所有 7 个专家 agent 的输出格式说明段落（每个文件约 20 行的 output format 说明）。

**特别说明：**
- `needs_clarification`：当 agent 无法独立判定时填写问题描述；确定成立则为 `null`
- 终端输出时 `needs_clarification` 非 null 的 finding 前加 `[?]` 标记

---

### Task 3.4 — 更新 Verifier Agent 输入格式

当前 `verifier.md` 从 `$SESSION_DIR/all-findings.md` 读取（已正确），需补充说明接受 Context Package 格式输入。

**更新内容（verifier.md 的 ## 输入格式 节）：**
```markdown
## 输入格式

Verifier 接收两部分输入（由 SKILL.md 在 prompt 中拼接传入）：

### 1. Context Package
完整的代码上下文（来自 `$SESSION_DIR/context-package.md`），包含：
- `[Intent]`：变更意图
- `[Change Set]`：完整 diff
- `[Context]`：变更函数定义
- `[Architecture Context]`（Full 档）：架构背景

### 2. P0/P1 Findings to Verify
来自 `$SESSION_DIR/all-findings.md` 中所有 `[P0]` 和 `[P1]` 条目。
```

---

## 阶段四：规则文件与配置

### Task 4.1 — 添加 `golangci-lint` 配置文件

**文件：** `languages/go/tools/.golangci.yml`（新建）

内容见 Task 2.1 中的 golangci-lint 配置。

---

### Task 4.2 — 更新 SKILL.md 规则数量引用

当前 SKILL.md 写"38 deterministic regex rules"，实际为 57 条（safety×14 + data×14 + quality×18 + observability×11）。

更新位置：SKILL.md `### Tier 2 — YAML 规则扫描` 节：
```
Scans against 57 deterministic regex rules across four YAML files:
- rules/safety.yaml — SAFE-001 to SAFE-014 (14 rules)
- rules/data.yaml — DATA-001 to DATA-014 (14 rules)
- rules/quality.yaml — QUAL-001 to QUAL-018 (18 rules)
- rules/observability.yaml — OBS-001 to OBS-011 (11 rules)
```

---

### Task 4.3 — 检查并补全 QUAL-017

当前 `rules/quality.yaml` 中 QUAL-017 可能缺失或为多行规则（repo 研究标注"gap"）。

**操作：**
1. 读取 `rules/quality.yaml`，确认 QUAL-017 是否存在
2. 若不存在，添加：
   ```yaml
   - id: QUAL-017
     severity: P2
     pattern:
       match: 'switch\s+\w+\s*\{'
     message: "枚举型 switch 应考虑 map 数据驱动替代（Rule of Extensibility）"
   ```
   注：此规则是建议性的（P2），正则只是触发检查，需 AI agent 做语义确认。

---

### Task 4.4 — 更新 .gitignore（如需要）

确认 `.review/results/` 和 `.review/run-*/` 在 `.gitignore` 中（`.review/workflow-state.json` 按需添加）。

---

## 阶段五：集成验证

### Task 5.1 — Trivial 档冒烟测试

```bash
# 准备：只改 README.md
echo "test" >> README.md
git add README.md
# 触发 skill，应该输出变更摘要然后退出，不调用任何 Agent
```

期望：`[1/6]... [2/6] ✓ TRIVIAL 档` → 输出摘要 → 退出，无 Agent 调用。

---

### Task 5.2 — Lite 档冒烟测试

```bash
# 准备：修改非敏感 Go 文件，diff < 400 行
# 触发：/go-code-review
```

期望：执行 Tier 1 + 顺序调用 3 个 Agent（safety/quality/observability），输出 ≤15 条 findings。

---

### Task 5.3 — Full 档冒烟测试（含架构预扫描）

```bash
# 准备：修改包含 auth/ 路径的文件，或 diff >= 400 行
# 触发：/go-code-review --output report.md
```

期望：执行 Step 3.5 架构预扫描 → 7 个 Agent 顺序执行 → Verifier → aggregate → 生成 report.md。

---

### Task 5.4 — Loop 模式 + --resume 测试

```bash
# 准备：大型 diff（>= 400 行）
# 模拟中断：在 Loop 进行中手动停止
# 恢复：/go-code-review --resume
```

期望：`workflow-state.json` 中 pending_tasks 被正确消费，最终 findings 合并完整。

---

## 关键文件路径汇总

```
languages/go/
├── SKILL.md                    ← 修改（v6.0.0 → v7.0.0，完整重写）
├── agents/
│   ├── coordinator.md          ← 新建
│   ├── verifier.md             ← 修改（输入格式说明）
│   ├── safety.md               ← 修改（/tmp/ → $SESSION_DIR）
│   ├── data.md                 ← 修改（/tmp/ → $SESSION_DIR）
│   ├── quality.md              ← 修改（/tmp/ → $SESSION_DIR）
│   ├── observability.md        ← 修改（/tmp/ → $SESSION_DIR）
│   ├── design.md               ← 修改（findings 格式）
│   ├── business.md             ← 修改（findings 格式）
│   └── naming.md               ← 修改（findings 格式）
├── tools/
│   ├── classify-diff.py        ← 新建（Task 1.1）
│   ├── assemble-context.py     ← 新建（Task 1.2）
│   ├── scan-architecture.py    ← 新建（Task 1.3）
│   ├── aggregate-findings.py   ← 新建（Task 1.4）
│   ├── .golangci.yml           ← 新建（Task 4.1）
│   ├── run-go-tools.sh         ← 保留（golangci-lint 降级兜底）
│   └── scan-rules.sh           ← 保留（Tier 2）
└── rules/
    ├── quality.yaml            ← 检查补全 QUAL-017（Task 4.3）
    ├── safety.yaml             ← 不变
    ├── data.yaml               ← 不变
    └── observability.yaml      ← 不变
```

---

## 规范文档参考

| 规范要求来源 | 对应实现 |
|------------|---------|
| `design.md` §2 步骤 1-6 | SKILL.md Task 2.1–2.10 |
| `design.md` §2 步骤 2（分流） | `classify-diff.py` Task 1.1 |
| `design.md` §2 步骤 3（Context） | `assemble-context.py` Task 1.2 |
| `design.md` §2 步骤 3.5（架构预扫描） | `scan-architecture.py` Task 1.3 |
| `design.md` §2 步骤 5（聚合过滤） | `aggregate-findings.py` Task 1.4 |
| `design.md` §3.1（Coordinator） | `coordinator.md` Task 3.2 |
| `design.md` §4.3（编排原则） | SKILL.md Task 2.6（顺序执行） |
| `design.md` §6.3（--resume） | SKILL.md Task 2.9 |
| `design.md` §4.1（总分总） | 各 agent 的 ## 执行步骤 节 |

---

## 实现顺序建议

**优先级 1（基础层）：** Task 1.1 → 1.2 → 1.3 → 1.4（Python 脚本，零外部依赖）

**优先级 2（编排层）：** Task 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7 → 2.8（SKILL.md 各步骤）

**优先级 3（补全层）：** Task 2.9（--resume）、Task 2.10（进度输出）

**优先级 4（Agent 层）：** Task 3.1 → 3.2 → 3.3 → 3.4（Agent 文件更新）

**优先级 5（配置层）：** Task 4.1 → 4.2 → 4.3 → 4.4

**优先级 6（验证）：** Task 5.1 → 5.2 → 5.3 → 5.4
