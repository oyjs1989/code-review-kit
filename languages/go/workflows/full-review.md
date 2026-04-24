# Go Code Review — Full Workflow (Full & Lite Tiers)

> 此文件被 `SKILL.md` 路由器引用。包含完整的步骤 1–6 + `--resume` 处理。
>
> **关键约束**：
> - `SESSION_DIR` 和 `$$` PID 在此文件中定义，不在路由器中
> - `ASSEMBLE_EXIT=2` 的 LITE 降级逻辑在此文件的 Step 3 中处理
> - `AGENT_ROSTER` 从 `classification.json` 读取，不硬编码
> - 输出格式见 `templates/report.md`；Context Package 格式见 `templates/context-package.md`

---

## 参数解析

Claude 从 skill 调用参数中提取以下值（若未提供则使用默认值）：

```bash
# 默认值
SOURCE_BRANCH=$(git branch --show-current)
BASE_BRANCH="main"
OUTPUT_FILE=""
RESUME=false

# 从 slash command 参数覆盖：
# /go-code-review --branch feat/xxx --base develop --output report.md --resume
```

---

## --resume 处理（在所有步骤前执行）

**Input:** `.review/workflow-state.json`（必须存在）

如果 `RESUME=true`：

```bash
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
COMPLETED=$(python3 -c "import json; d=json.load(open('.review/workflow-state.json')); print(len(d['completed_tasks']))")
echo "恢复中断审查（已完成 $COMPLETED 个 tasks，剩余 $PENDING 个）..."
# 跳过步骤 1-3，从 pending_tasks 继续步骤 4 Loop
```

---

## Step 1: 获取代码变更

**Input:** `$SOURCE_BRANCH`、`$BASE_BRANCH`（来自参数解析）

**Output written:**
- `$SESSION_DIR/diff.txt` — git diff 内容
- `$SESSION_DIR/files.txt` — 变更的 .go 文件列表
- `$SESSION_DIR/gitlog.txt` — 最近 5 条 commit

**Exit:** 0=成功；1=diff 为空或无 Go 文件变更

```bash
echo "[1/6] 获取代码变更..."

# 确认分支存在
git rev-parse "$BASE_BRANCH" > /dev/null 2>&1 || { echo "ERROR: base branch '$BASE_BRANCH' not found"; exit 1; }
git rev-parse "$SOURCE_BRANCH" > /dev/null 2>&1 || { echo "ERROR: source branch '$SOURCE_BRANCH' not found"; exit 1; }

HEAD_SHA=$(git rev-parse "$SOURCE_BRANCH" | head -c 8)
SESSION_DIR=".review/run-${HEAD_SHA}-$$"
mkdir -p "$SESSION_DIR"

# 获取 diff 和文件列表
git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --diff-filter=AM > "$SESSION_DIR/diff.txt"
git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --name-only --diff-filter=AM | grep '\.go$' > "$SESSION_DIR/files.txt"

# git log（用于 Intent 节）
git log --oneline -5 "${BASE_BRANCH}..${SOURCE_BRANCH}" > "$SESSION_DIR/gitlog.txt" 2>/dev/null || true

# 统计
DIFF_LINES=$(wc -l < "$SESSION_DIR/diff.txt")
FILES_CHANGED=$(wc -l < "$SESSION_DIR/files.txt")
```

**Checkpoint 1：**
```bash
test -s "$SESSION_DIR/diff.txt" || { echo "ERROR: diff is empty"; rm -rf "$SESSION_DIR"; exit 1; }
test -s "$SESSION_DIR/files.txt" || { echo "ERROR: no Go files changed"; rm -rf "$SESSION_DIR"; exit 1; }
echo "✓ diff=$DIFF_LINES 行，Go 文件=$FILES_CHANGED 个"
```

---

## Step 2: 变更分流（Triage）

**Input:** `$SESSION_DIR/diff.txt`、`$SESSION_DIR/files.txt`、`$DIFF_LINES`、`$FILES_CHANGED`

**Output written:**
- `$SESSION_DIR/classification.json` — tier、agent_roster、rules_source、rules_file

**Exit:** 0=成功（含 TRIVIAL 早退）

```bash
echo "[2/6] 变更分流..."

CLASSIFICATION=$(python3 languages/go/tools/classify-diff.py \
  --diff-lines "$DIFF_LINES" \
  --files-changed "$FILES_CHANGED" \
  --files "$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')" \
  --diff-file "$SESSION_DIR/diff.txt")

echo "$CLASSIFICATION" > "$SESSION_DIR/classification.json"

TIER=$(echo "$CLASSIFICATION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tier'])")
RULES_SOURCE=$(echo "$CLASSIFICATION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['rules_source'])")
RULES_FILE=$(echo "$CLASSIFICATION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('rules_file',''))")

echo "✓ $TIER 档，规则来源：$RULES_SOURCE"
```

**Trivial 档早退：**
```bash
if [ "$TIER" = "TRIVIAL" ]; then
  echo "变更为文档/配置/注释类，无需深度审查。"
  echo "变更摘要："
  cat "$SESSION_DIR/gitlog.txt" | head -5
  rm -rf "$SESSION_DIR"
  exit 0
fi
```

---

## Step 3: 上下文组装

**Input:** `$SESSION_DIR/diff.txt`、`$SESSION_DIR/gitlog.txt`、`$RULES_SOURCE`、`$RULES_FILE`

**Output written:**
- `$SESSION_DIR/context-package.md` — Context Package（格式见 `templates/context-package.md`）
- `$SESSION_DIR/context-meta.json` — 组装元数据（来自 stderr）

**Exit:** 0=成功；2=`[Change Set]` 被截断 → `TIER` 降级为 LITE

```bash
echo "[3/6] 组装上下文..."

python3 languages/go/tools/assemble-context.py \
  --diff "$SESSION_DIR/diff.txt" \
  --rules-source "$RULES_SOURCE" \
  ${RULES_FILE:+--rules-file "$RULES_FILE"} \
  --git-log "$SESSION_DIR/gitlog.txt" \
  > "$SESSION_DIR/context-package.md" \
  2> "$SESSION_DIR/context-meta.json"

ASSEMBLE_EXIT=$?

# 检测 change_set 截断警告（exit code 2）
if [ "$ASSEMBLE_EXIT" -eq 2 ]; then
  echo "WARNING: [Change Set] 被截断，降档为 Lite 处理"
  TIER="LITE"
fi

echo "✓ Context Package 组装完成"
```

---

## Step 3.5: 架构预扫描（Full 档专属）

**Input:** `$SESSION_DIR/files.txt`（仅 TIER=FULL 时执行）

**Output written:**
- `$SESSION_DIR/architecture-context.json` — 模块依赖关系（可选，失败不阻断）
- `$SESSION_DIR/context-package.md` — 若扫描成功，重新组装含 [Architecture Context]

```bash
if [ "$TIER" = "FULL" ]; then
  echo "[3.5/6] 架构预扫描（Full 档）..."
  FILES_LIST=$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')

  timeout 30 python3 languages/go/tools/scan-architecture.py \
    --files "$FILES_LIST" \
    --gomod "go.mod" \
    > "$SESSION_DIR/architecture-context.json" 2>/dev/null

  if [ $? -eq 0 ] && [ -s "$SESSION_DIR/architecture-context.json" ]; then
    MODULE_COUNT=$(python3 -c "import json; d=json.load(open('$SESSION_DIR/architecture-context.json')); print(len(d['module_map']))")
    HIGH_RISK=$(python3 -c "import json; d=json.load(open('$SESSION_DIR/architecture-context.json')); print(','.join(d.get('high_risk_modules',[])))")

    # 重新组装 Context Package（加入 Architecture Context）
    python3 languages/go/tools/assemble-context.py \
      --diff "$SESSION_DIR/diff.txt" \
      --rules-source "$RULES_SOURCE" \
      ${RULES_FILE:+--rules-file "$RULES_FILE"} \
      --git-log "$SESSION_DIR/gitlog.txt" \
      --architecture-context "$SESSION_DIR/architecture-context.json" \
      > "$SESSION_DIR/context-package.md" \
      2> "$SESSION_DIR/context-meta.json"

    echo "✓ 识别 $MODULE_COUNT 个模块，高风险：${HIGH_RISK:-无}"
  else
    echo "⚠ 架构预扫描超时或跳过，继续执行"
  fi
fi
```

---

## Step 4: 执行审查

**Input:** `$SESSION_DIR/context-package.md`、`$SESSION_DIR/diff.txt`、`$TIER`、`$AGENT_ROSTER`

**Output written:**
- `$SESSION_DIR/findings-lint.md` 或 `$SESSION_DIR/diagnostics.json` — Tier 1 结果
- `$SESSION_DIR/rule-hits.json` — Tier 2 规则命中
- `$SESSION_DIR/findings-{agent}.md` — 各 Agent 输出（格式见 `templates/report.md`）
- `$SESSION_DIR/verifier-results.md` — Verifier 输出（Full 档，P0/P1 存在时）

```bash
echo "[4/6] 执行审查..."
```

### Tier 1 扫描

```bash
if command -v golangci-lint > /dev/null 2>&1; then
  FILES_LIST=$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')
  golangci-lint run \
    --output.json.path="$SESSION_DIR/lint-results.json" \
    --config languages/go/tools/.golangci.yml \
    $FILES_LIST 2>/dev/null || true

  # 将 golangci-lint JSON 转换为 findings-lint.md
  python3 languages/go/tools/aggregate-findings.py \
    --lint-json "$SESSION_DIR/lint-results.json" \
    --output "$SESSION_DIR/findings-lint.md" 2>/dev/null || true

  echo "  ✓ golangci-lint 完成"
else
  # 降级：使用现有独立工具链
  cat "$SESSION_DIR/files.txt" | bash languages/go/tools/run-go-tools.sh > "$SESSION_DIR/diagnostics.json" 2>/dev/null || true
  echo "  ✓ go vet/build 完成（golangci-lint 未安装，使用降级路径）"
fi

# Tier 2 规则扫描（始终执行）
cat "$SESSION_DIR/files.txt" | bash languages/go/tools/scan-rules.sh > "$SESSION_DIR/rule-hits.json" 2>/dev/null || true
echo "  ✓ Tier 2 规则扫描完成"
```

### Loop 模式判断

```bash
if [ "$TIER" = "FULL" ] && [ "$DIFF_LINES" -ge 400 ]; then
  LOOP_MODE=true
  echo "  → Loop 模式（diff_lines=$DIFF_LINES >= 400）"
else
  LOOP_MODE=false
fi
```

### 读取变更代码内容（供 Agent 分析）

```bash
DIFF_CONTENT=$(cat "$SESSION_DIR/diff.txt")
CONTEXT_PACKAGE=$(cat "$SESSION_DIR/context-package.md")
RULE_HITS=$(cat "$SESSION_DIR/rule-hits.json")
AGENT_ROSTER=$(echo "$CLASSIFICATION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(d['agent_roster']))")
```

### 顺序执行 Agents（普通模式，LOOP_MODE=false）

对 `AGENT_ROSTER` 中每个 agent，**依次**执行以下步骤：

1. 读取 `languages/go/agents/{agent}.md` 内容
2. 调用 `Agent(agents/{agent}.md, prompt=<agent.md内容 + context-package.md内容>)`
3. Agent 将 findings 写入 `$SESSION_DIR/findings-{agent}.md`（格式见 `templates/report.md`）
4. **Checkpoint**：验证文件存在且包含 finding 内容

```bash
# 对每个 agent（示例展示 safety，其余同理）：
# Agent 接收：agent.md 内容 + Context Package
# Agent 输出：$SESSION_DIR/findings-{agent}.md

# Checkpoint（每个 agent 后执行，内容感知验证）：
test -f "$SESSION_DIR/findings-{agent}.md" && \
  grep -q '### \[P\|无发现\|未发现问题' "$SESSION_DIR/findings-{agent}.md" || \
  echo "WARNING: {agent} findings incomplete or missing"
```

**具体 agent 输入说明：**

- **safety agent** — Context Package + `$SESSION_DIR/diagnostics.json`（若存在）中的 build_errors/vet_issues + rule-hits.json 中 SAFE-001~014 命中
- **data agent** — Context Package + rule-hits.json 中 DATA-001~014 命中
- **design agent** — Context Package（无 Tier 2 规则）
- **quality agent** — Context Package + `$SESSION_DIR/diagnostics.json` 中的 large_files + rule-hits.json 中 QUAL-001~018 命中
- **observability agent** — Context Package + rule-hits.json 中 OBS-001~011 命中
- **business agent** — Context Package（读取变更文件完整内容，非仅 diff）
- **naming agent** — Context Package + rule-hits.json 中 QUAL-001/008/010 命名相关命中

### Loop 模式（LOOP_MODE=true，大型变更）

```bash
# 生成任务包
python3 languages/go/tools/classify-diff.py \
  --generate-task-packs \
  --diff-file "$SESSION_DIR/diff.txt" \
  --agent-roster "$AGENT_ROSTER" \
  > "$SESSION_DIR/task-packs.json"

# 初始化 workflow-state.json
python3 -c "
import json
packs = json.load(open('$SESSION_DIR/task-packs.json'))
state = {
  'head_sha': '$(git rev-parse HEAD)',
  'session_dir': '$SESSION_DIR',
  'completed_tasks': [],
  'in_progress_tasks': [],
  'pending_tasks': [t['task_id'] for t in packs['tasks']],
  'skipped_tasks': []
}
json.dump(state, open('.review/workflow-state.json', 'w'), ensure_ascii=False, indent=2)
"

echo "  → 共 $(python3 -c "import json; d=json.load(open('$SESSION_DIR/task-packs.json')); print(d['total_tasks'])") 个任务包"
```

**Loop 执行**（对每个 `pending_tasks` 中的 task_id）：

1. 更新 `workflow-state.json`：移至 `in_progress`
2. 读取任务包的 `files` 列表，生成该批文件的 sub-diff
3. 调用对应 Agent（`task_id` 格式 `task-{pack}:{agent}`）
4. Agent 输出追加到 `$SESSION_DIR/findings-{agent}.md`
5. 更新 `workflow-state.json`：移至 `completed`（失败则移至 `skipped`，最多重试 2 次）

### Verifier（仅 Full 档，所有 Agent 完成后）

```bash
cat "$SESSION_DIR"/findings-*.md > "$SESSION_DIR/all-findings.md"

P0P1_COUNT=$(grep -c '\[P0\]\|\[P1\]' "$SESSION_DIR/all-findings.md" 2>/dev/null || echo 0)
if [ "$P0P1_COUNT" -gt 0 ]; then
  echo "  → 派发 Verifier（P0/P1 共 $P0P1_COUNT 条）..."
  # 读取 verifier.md + context-package.md + all-findings.md 中 P0/P1 条目
  # Agent(agents/verifier.md, prompt=<合并内容>)
  # Verifier 输出写入 $SESSION_DIR/verifier-results.md
  # 根据 confirm/downgrade/dismiss 更新 all-findings.md
  echo "  ✓ Verifier 完成"
fi
```

---

## Step 5: 聚合与过滤

**Input:** `$SESSION_DIR/findings-*.md`、`$REPORT_FILE`（目标路径）

**Output written:**
- `.review/results/review-{timestamp}.md` — 最终报告（≤15 条 findings）
- `$SESSION_DIR/final-report.md` — Coordinator 输出（若存在则覆盖上方文件）

**Exit:** 0=成功；1=报告生成失败

```bash
echo "[5/6] 聚合与过滤..."

# 收集 review:ignore 标记（格式：category:file:line）
IGNORE_FLAGS=$(git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --diff-filter=AM -- '*.go' | \
  grep '^+' | grep 'review:ignore' | \
  python3 -c "
import sys, re
lines = sys.stdin.read().splitlines()
flags = []
for line in lines:
    m = re.search(r'review:ignore\s+(\w+)', line)
    if m:
        flags.append(m.group(1))
print(','.join(flags))
" 2>/dev/null || true)

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
FINDING_COUNT=$(grep -c '^### \[P' "$REPORT_FILE" 2>/dev/null || echo 0)
echo "✓ 过滤后 $FINDING_COUNT 条（覆盖 $FILES_CHANGED 个文件）"
```

### Coordinator Agent（生成 Review Assumptions）

```bash
CONTEXT_PACKAGE=$(cat "$SESSION_DIR/context-package.md")
FILTERED_FINDINGS=$(cat "$REPORT_FILE")
COVERAGE_SUMMARY="files_reviewed: $FILES_CHANGED / $FILES_CHANGED
skipped: 无
rules_source: $RULES_SOURCE${RULES_FILE:+（$RULES_FILE）}
tier: $TIER"

# Agent(agents/coordinator.md, prompt=<三部分内容>):
# 1. [Context Package]   → $CONTEXT_PACKAGE
# 2. [Filtered Findings] → $FILTERED_FINDINGS
# 3. [Coverage Summary]  → $COVERAGE_SUMMARY
# Coordinator 输出写入 $SESSION_DIR/final-report.md

if [ -f "$SESSION_DIR/final-report.md" ]; then
  cp "$SESSION_DIR/final-report.md" "$REPORT_FILE"
  echo "  ✓ Coordinator 生成 Review Assumptions 完成"
else
  echo "  ⚠ Coordinator 未输出，使用聚合报告"
fi
```

---

## Step 6: 输出结果与清理

**Input:** `$REPORT_FILE`

**Output:** 终端打印报告；可选写入 `$OUTPUT_FILE`

```bash
echo "[6/6] 输出结果..."

# 终端输出报告内容
cat "$REPORT_FILE"

# 如果指定了 --output，复制完整报告到目标路径
if [ -n "$OUTPUT_FILE" ]; then
  cp "$REPORT_FILE" "$OUTPUT_FILE"
  echo ""
  echo "完整报告已保存：$OUTPUT_FILE"
fi

echo "完整报告：$REPORT_FILE"

# 清理 session 目录
rm -rf "$SESSION_DIR"

# Loop 模式：清理 workflow-state.json
if [ "$LOOP_MODE" = "true" ]; then
  rm -f ".review/workflow-state.json"
fi
```
