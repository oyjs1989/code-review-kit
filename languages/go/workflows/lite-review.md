# Go Code Review — Lite Workflow

> Lite 档：适用于 diff < 400 行且文件数 < 5 的变更。
> 运行 3 个 Agent（safety、quality、observability），跳过架构预扫描和 Loop 模式。
>
> 输出格式见 `templates/report.md`；Context Package 格式见 `templates/context-package.md`。

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
echo "[1-3/5] 准备阶段（确定性）..."

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
AGENT_ROSTER=$(echo "$TASK_LIST" | python3 -c "import sys,json; print(' '.join(t['agent'] for t in json.load(sys.stdin)['tasks']))")
echo "✓ 准备完成：tier=$TIER，agents=$AGENT_ROSTER"
```

---

## Step 4: 执行审查（3 Agents，无 Loop 模式）

**Lite 档固定 Agent 列表：safety、quality、observability**

**Output written:** `$SESSION_DIR/findings-{agent}.md`

```bash
echo "[4/5] 执行审查..."

# Tier 1 扫描
# 优先使用 make lint-inc（fscan-toolchain），降级到 run-go-tools.sh
LINT_OUTPUT="$SESSION_DIR/lint-results.txt"
LINT_STDERR="$SESSION_DIR/lint-stderr.txt"

if [ -f "Makefile" ] && grep -q 'lint-inc' Makefile; then
  # 使用项目的 make lint-inc（fscan-toolchain）
  if make lint-inc > "$LINT_OUTPUT" 2>"$LINT_STDERR"; then
    echo "  ✓ make lint-inc 完成"
  else
    LINT_EXIT=$?
    if [ "$LINT_EXIT" -eq 1 ] && [ -s "$LINT_OUTPUT" ]; then
      echo "  ✓ make lint-inc 完成（发现问题）"
    else
      echo "  ⚠ make lint-inc 失败（exit=$LINT_EXIT）"
      cat "$LINT_STDERR" >&2
    fi
  fi
else
  cat "$SESSION_DIR/files.txt" | bash languages/go/tools/run-go-tools.sh > "$SESSION_DIR/diagnostics.json" 2>&1 || true
  echo "  ✓ go vet/build 完成（make lint-inc 不可用，使用降级路径）"
fi

# Tier 2 规则扫描
cat "$SESSION_DIR/files.txt" | bash languages/go/tools/scan-rules.sh > "$SESSION_DIR/rule-hits.json" 2>/dev/null || true
echo "  ✓ Tier 2 规则扫描完成"

CONTEXT_PACKAGE=$(cat "$SESSION_DIR/context-package.md")
RULE_HITS=$(cat "$SESSION_DIR/rule-hits.json")
```

对 `safety`、`quality`、`observability` 三个 Agent **依次**执行：

1. 读取 `languages/go/agents/{agent}.md` 内容
2. 调用 `Agent(prompt=<agent.md内容 + context-package.md内容>)`
3. Agent 将 findings 写入 `$SESSION_DIR/findings-{agent}.md`

**Agent 输入说明：**
- **safety** — Context Package + diagnostics.json（若存在）+ rule-hits.json SAFE-* 命中
- **quality** — Context Package + diagnostics.json large_files + rule-hits.json QUAL-* 命中
- **observability** — Context Package + rule-hits.json OBS-* 命中

**Checkpoint（每个 agent 后）：**
```bash
test -f "$SESSION_DIR/findings-{agent}.md" && \
  grep -q '### \[P\|无发现\|未发现问题' "$SESSION_DIR/findings-{agent}.md" || \
  echo "WARNING: {agent} findings incomplete or missing"
```

> Lite 档不运行 Verifier。

---

## Step 5: 聚合与输出（确定性，由 orchestrate-review.py 执行）

```bash
echo "[5/5] 聚合与输出..."

python3 languages/go/tools/orchestrate-review.py --mode aggregate \
  --session-dir "$SESSION_DIR" \
  ${OUTPUT_FILE:+--output "$OUTPUT_FILE"}
```
