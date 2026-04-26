# Go Code Review — Full Workflow (Full & Lite Tiers)

> 此文件被 `SKILL.md` 路由器引用。包含完整的步骤 1–6 + `--resume` 处理。
>
> **关键约束**：
> - `SESSION_DIR` 和 `$$` PID 在此文件中定义，不在路由器中
> - `loop_mode` 由 `orchestrate-review.py` 在 prepare 阶段写入 `task-list.json`，workflow 直接读取，不再重新推导
> - `AGENT_ROSTER` 从 `classification.json` 读取，不硬编码
> - 输出格式见 `templates/report.md`；Context Package 格式见 `templates/context-package.md`

---

## 参数解析

```bash
SOURCE_BRANCH=$(git branch --show-current)
BASE_BRANCH="main"
OUTPUT_FILE=""
RESUME=false

# 从 slash command 参数覆盖：
# /go-code-review --branch feat/xxx --base develop --output report.md --resume
```

---

## --resume 处理

如果 `RESUME=true`，跳过准备阶段，直接从 `$SESSION_DIR/task-list.json` 读取 pending tasks。

---

## Steps 1-3+T1+T2: 准备（确定性，由 orchestrate-review.py 执行）

```bash
echo "[1-3/6] 准备阶段（确定性）..."

python3 languages/go/tools/orchestrate-review.py --mode prepare \
  --branch "$SOURCE_BRANCH" \
  --base "$BASE_BRANCH" \
  ${SESSION_DIR:+--session-dir "$SESSION_DIR"}

PREPARE_EXIT=$?
[ "$PREPARE_EXIT" -eq 2 ] && exit 0   # TRIVIAL — no review needed
[ "$PREPARE_EXIT" -ne 0 ] && exit 1   # fatal error

SESSION_DIR=$(cat .review/last-session-dir 2>/dev/null)
if [ -z "$SESSION_DIR" ]; then
  echo "ERROR: session_dir not found (.review/last-session-dir missing)"
  exit 1
fi

TASK_LIST=$(cat "$SESSION_DIR/task-list.json")
TIER=$(echo "$TASK_LIST" | python3 -c "import sys,json; print(json.load(sys.stdin)['tier'])")
LOOP_MODE=$(echo "$TASK_LIST" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('loop_mode', False)).lower())")
AGENT_ROSTER=$(echo "$TASK_LIST" | python3 -c "import sys,json; print(' '.join(t['agent'] for t in json.load(sys.stdin)['tasks']))")
echo "✓ 准备完成：tier=$TIER，loop_mode=$LOOP_MODE，agents=$AGENT_ROSTER"
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
# 优先使用 make lint-inc（fscan-toolchain），降级到 run-go-tools.sh
LINT_OUTPUT="$SESSION_DIR/lint-results.txt"
LINT_STDERR="$SESSION_DIR/lint-stderr.txt"

if [ -f "Makefile" ] && grep -q 'lint-inc' Makefile; then
  # 使用项目的 make lint-inc（fscan-toolchain）
  # 输出格式：file:line:col: message（文本格式）
  if make lint-inc > "$LINT_OUTPUT" 2>"$LINT_STDERR"; then
    echo "  ✓ make lint-inc 完成"
  else
    LINT_EXIT=$?
    # exit code 1 = 发现问题（正常），其他 = 运行错误
    if [ "$LINT_EXIT" -eq 1 ] && [ -s "$LINT_OUTPUT" ]; then
      echo "  ✓ make lint-inc 完成（发现问题）"
    else
      echo "  ⚠ make lint-inc 失败（exit=$LINT_EXIT）"
      cat "$LINT_STDERR" >&2
    fi
  fi
else
  # 降级：使用现有独立工具链
  cat "$SESSION_DIR/files.txt" | bash languages/go/tools/run-go-tools.sh > "$SESSION_DIR/diagnostics.json" 2>&1 || true
  echo "  ✓ go vet/build 完成（make lint-inc 不可用，使用降级路径）"
fi

# Tier 2 规则扫描（始终执行）
cat "$SESSION_DIR/files.txt" | bash languages/go/tools/scan-rules.sh > "$SESSION_DIR/rule-hits.json" 2>/dev/null || true
echo "  ✓ Tier 2 规则扫描完成"
```

### Loop 模式判断

`loop_mode` 已由 `orchestrate-review.py` 在准备阶段写入 `task-list.json`，此处直接读取，无需重新推导。

```bash
# LOOP_MODE 已在上方从 task-list.json 读取（true/false）
if [ "$LOOP_MODE" = "true" ]; then
  echo "  → Loop 模式（由 orchestrate-review.py 决策，见 task-list.json）"
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
2. 读取任务包的 `files` 列表，从 `diff.txt` 提取该批文件的 sub-diff：
   ```bash
   PACK_FILES=$(python3 -c "
   import json
   packs = json.load(open('$SESSION_DIR/task-packs.json'))
   t = next(t for t in packs['tasks'] if t['task_id'] == '$TASK_ID')
   print(' '.join(t['files']))
   ")
   python3 -c "
   files = set('$PACK_FILES'.split())
   out, capture = [], False
   for line in open('$SESSION_DIR/diff.txt'):
       if line.startswith('diff --git'):
           capture = any(f in line for f in files)
       if capture:
           out.append(line)
   open('$SESSION_DIR/sub-diff-$PACK_INDEX.txt', 'w').writelines(out)
   "
   ```
3. 用 sub-diff 为该批次组装独立的 Context Package（不使用全局截断版本）：
   ```bash
   python3 languages/go/tools/assemble-context.py \
     --diff "$SESSION_DIR/sub-diff-$PACK_INDEX.txt" \
     --rules-source "$RULES_SOURCE" \
     ${RULES_FILE:+--rules-file "$RULES_FILE"} \
     --git-log "$SESSION_DIR/gitlog.txt" \
     > "$SESSION_DIR/context-pack-$PACK_INDEX.md" \
     2>/dev/null || true
   ```
4. 调用对应 Agent（`task_id` 格式 `task-{pack}:{agent}`），传入 `context-pack-$PACK_INDEX.md`
5. Agent 输出追加到 `$SESSION_DIR/findings-{agent}.md`
6. 更新 `workflow-state.json`：移至 `completed`（失败则移至 `skipped`，最多重试 2 次）

### Verifier（已工具化）

> Verifier 逻辑已合并至 `aggregate-findings.py --rule-hits-file`，无需单独 AI agent 调用。

---

## Step 5-6: 聚合与输出（确定性，由 orchestrate-review.py 执行）

```bash
echo "[5-6/6] 聚合与输出..."

python3 languages/go/tools/orchestrate-review.py --mode aggregate \
  --session-dir "$SESSION_DIR" \
  ${OUTPUT_FILE:+--output "$OUTPUT_FILE"}
```
