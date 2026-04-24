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

## --resume 处理（在所有步骤前执行）

如果 `RESUME=true`，与 full-review.md 相同：检查 `.review/workflow-state.json` 存在且 `head_sha` 匹配当前 HEAD。

---

## Step 1: 获取代码变更

**Output written:** `$SESSION_DIR/diff.txt`、`$SESSION_DIR/files.txt`、`$SESSION_DIR/gitlog.txt`

```bash
echo "[1/5] 获取代码变更..."

git rev-parse "$BASE_BRANCH" > /dev/null 2>&1 || { echo "ERROR: base branch '$BASE_BRANCH' not found"; exit 1; }
git rev-parse "$SOURCE_BRANCH" > /dev/null 2>&1 || { echo "ERROR: source branch '$SOURCE_BRANCH' not found"; exit 1; }

HEAD_SHA=$(git rev-parse "$SOURCE_BRANCH" | head -c 8)
SESSION_DIR=".review/run-${HEAD_SHA}-$$"
mkdir -p "$SESSION_DIR"

git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --diff-filter=AM > "$SESSION_DIR/diff.txt"
git diff "${BASE_BRANCH}...${SOURCE_BRANCH}" --name-only --diff-filter=AM | grep '\.go$' > "$SESSION_DIR/files.txt"
git log --oneline -5 "${BASE_BRANCH}..${SOURCE_BRANCH}" > "$SESSION_DIR/gitlog.txt" 2>/dev/null || true

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

**Output written:** `$SESSION_DIR/classification.json`

```bash
echo "[2/5] 变更分流..."

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
  cat "$SESSION_DIR/gitlog.txt" | head -5
  rm -rf "$SESSION_DIR"
  exit 0
fi
```

---

## Step 3: 上下文组装

> Lite 档跳过架构预扫描（Step 3.5）。

**Output written:** `$SESSION_DIR/context-package.md`、`$SESSION_DIR/context-meta.json`

```bash
echo "[3/5] 组装上下文..."

python3 languages/go/tools/assemble-context.py \
  --diff "$SESSION_DIR/diff.txt" \
  --rules-source "$RULES_SOURCE" \
  ${RULES_FILE:+--rules-file "$RULES_FILE"} \
  --git-log "$SESSION_DIR/gitlog.txt" \
  > "$SESSION_DIR/context-package.md" \
  2> "$SESSION_DIR/context-meta.json"

ASSEMBLE_EXIT=$?
if [ "$ASSEMBLE_EXIT" -eq 2 ]; then
  echo "WARNING: [Change Set] 被截断"
fi

echo "✓ Context Package 组装完成"
```

---

## Step 4: 执行审查（3 Agents，无 Loop 模式）

**Lite 档固定 Agent 列表：safety、quality、observability**

**Output written:** `$SESSION_DIR/findings-{agent}.md`

```bash
echo "[4/5] 执行审查..."

# Tier 1 扫描
if command -v golangci-lint > /dev/null 2>&1; then
  FILES_LIST=$(cat "$SESSION_DIR/files.txt" | tr '\n' ' ')
  golangci-lint run \
    --output.json.path="$SESSION_DIR/lint-results.json" \
    --config languages/go/tools/.golangci.yml \
    $FILES_LIST 2>/dev/null || true

  python3 languages/go/tools/aggregate-findings.py \
    --lint-json "$SESSION_DIR/lint-results.json" \
    --output "$SESSION_DIR/findings-lint.md" 2>/dev/null || true

  echo "  ✓ golangci-lint 完成"
else
  cat "$SESSION_DIR/files.txt" | bash languages/go/tools/run-go-tools.sh > "$SESSION_DIR/diagnostics.json" 2>/dev/null || true
  echo "  ✓ go vet/build 完成（降级路径）"
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

## Step 5: 聚合、过滤与输出

**Output written:** `.review/results/review-{timestamp}.md`

```bash
echo "[5/5] 聚合与输出..."

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
  --rule-hits-file "$SESSION_DIR/rule-hits.json" \
  --classification-file "$SESSION_DIR/classification.json" \
  --context-meta-file "$SESSION_DIR/context-meta.json" \
  --max-output 15 \
  --output "$REPORT_FILE"

test -f "$REPORT_FILE" || { echo "ERROR: report generation failed"; exit 1; }
FINDING_COUNT=$(grep -c '^### \[P' "$REPORT_FILE" 2>/dev/null || echo 0)
echo "✓ 过滤后 $FINDING_COUNT 条（覆盖 $FILES_CHANGED 个文件）"

# 输出报告
cat "$REPORT_FILE"

if [ -n "$OUTPUT_FILE" ]; then
  cp "$REPORT_FILE" "$OUTPUT_FILE"
  echo "完整报告已保存：$OUTPUT_FILE"
fi

echo "完整报告：$REPORT_FILE"

# 清理
rm -rf "$SESSION_DIR"
```
