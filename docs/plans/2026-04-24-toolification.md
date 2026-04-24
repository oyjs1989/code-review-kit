# Toolification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 减少 Go 代码审查工作流对 AI 的依赖，把确定性步骤变成真实脚本，AI 只做代码分析。

**Architecture:** 分两阶段实施。先做方向 B（改 `aggregate-findings.py`，用规则替换 Verifier agent、用模板替换 Coordinator agent），再做方向 A（新建 `orchestrate-review.py` 封装编排逻辑，简化 `full-review.md`/`lite-review.md`）。

**Tech Stack:** Python 3.11+, pytest, uv（`uv run pytest`）

---

## Task 1: 搭建测试框架

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/go_tools/__init__.py`
- Create: `tests/go_tools/test_aggregate_findings.py`

**Step 1: 创建测试目录结构**

```bash
mkdir -p tests/go_tools
touch tests/__init__.py tests/go_tools/__init__.py
```

**Step 2: 写一个冒烟测试验证测试框架可用**

新建 `tests/go_tools/test_aggregate_findings.py`：

```python
import sys
from pathlib import Path

# 让 tests 能 import languages/go/tools 中的模块
sys.path.insert(0, str(Path(__file__).parents[2] / "languages/go/tools"))

from aggregate_findings import Finding, SEVERITY_ORDER


def test_finding_sort_key():
    f = Finding("SAFE-001", "P0", "main.go", 10)
    assert f.sort_key[0] == 0  # P0 → 0


def test_severity_order_complete():
    assert set(SEVERITY_ORDER.keys()) == {"P0", "P1", "P2", "P3"}
```

**Step 3: 验证测试失败（因为 aggregate_findings 用连字符，需要重命名）**

```bash
uv run pytest tests/go_tools/test_aggregate_findings.py -v
```

注意：`aggregate-findings.py` 文件名含连字符无法直接 import，需要通过 `importlib` 加载。修改测试文件开头：

```python
import importlib.util, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "aggregate_findings",
    Path(__file__).parents[2] / "languages/go/tools/aggregate-findings.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Finding = mod.Finding
SEVERITY_ORDER = mod.SEVERITY_ORDER
```

**Step 4: 运行测试，确认 PASS**

```bash
uv run pytest tests/go_tools/test_aggregate_findings.py -v
```

Expected: 2 passed

**Step 5: Commit**

```bash
git add tests/
git commit -m "test: scaffold test framework for go tools"
```

---

## Task 2: B2 — 模板化 Coordinator（`build_review_assumptions`）

**Files:**
- Modify: `languages/go/tools/aggregate-findings.py`
- Modify: `tests/go_tools/test_aggregate_findings.py`

### 背景
当前 `full-review.md` Step 5 调用一个 Coordinator AI agent 生成"审查说明"报告头。这部分内容完全来自已有的 JSON 元数据，无需 AI。

### Step 1: 写失败测试

在 `tests/go_tools/test_aggregate_findings.py` 追加：

```python
def test_build_review_assumptions_full_tier():
    classification = {
        "tier": "FULL",
        "trigger_reason": "diff_lines=500",
        "rules_source": "built_in",
        "agent_roster": ["safety", "data", "quality"],
    }
    context_meta = {
        "estimated_tokens": 12000,
        "token_limit": 16000,
        "truncated_sections": [],
    }
    result = mod.build_review_assumptions(classification, context_meta)
    assert "FULL" in result
    assert "safety, data, quality" in result
    assert "12000" in result
    assert "截断节：无" in result


def test_build_review_assumptions_with_truncation():
    classification = {
        "tier": "LITE",
        "trigger_reason": "diff_lines=100",
        "rules_source": "project_rules",
        "agent_roster": ["safety"],
    }
    context_meta = {
        "estimated_tokens": 14000,
        "token_limit": 16000,
        "truncated_sections": ["change_set"],
    }
    result = mod.build_review_assumptions(classification, context_meta)
    assert "change_set" in result
```

**Step 2: 运行测试，确认 FAIL**

```bash
uv run pytest tests/go_tools/test_aggregate_findings.py::test_build_review_assumptions_full_tier -v
```

Expected: FAIL with `AttributeError: module ... has no attribute 'build_review_assumptions'`

**Step 3: 在 `aggregate-findings.py` 实现函数**

在文件末尾的 `generate_report()` 函数之前插入（约在第 453 行之前）：

```python
def build_review_assumptions(classification: dict, context_meta: dict) -> str:
    """Generate deterministic review assumptions section from metadata."""
    tier = classification.get('tier', 'UNKNOWN')
    trigger = classification.get('trigger_reason', '')
    rules_source = classification.get('rules_source', 'built_in')
    agents = classification.get('agent_roster', [])
    estimated = context_meta.get('estimated_tokens', 0)
    limit = context_meta.get('token_limit', 16000)
    truncated = context_meta.get('truncated_sections', [])

    lines = [
        '## 审查说明\n',
        f'- **处理档位**: {tier}（{trigger}）',
        f'- **规则来源**: {rules_source}',
        f'- **运行 Agents**: {", ".join(agents) if agents else "（无）"}',
        f'- **Token 估算**: {estimated} / {limit}',
        f'- **截断节**: {", ".join(truncated) if truncated else "无"}',
        '',
    ]
    return '\n'.join(lines)
```

**Step 4: 运行测试，确认 PASS**

```bash
uv run pytest tests/go_tools/test_aggregate_findings.py -v
```

Expected: all passed

**Step 5: 把 `build_review_assumptions` 接入 `generate_report()`**

在 `generate_report()` 函数签名中加入可选参数（在 `languages/go/tools/aggregate-findings.py` 约第 454 行）：

```python
def generate_report(
    findings: list,
    total_raw: int,
    total_after_dedup: int,
    total_filtered: int,
    max_output: int,
    output_file: str,
    classification: dict | None = None,      # 新增
    context_meta: dict | None = None,         # 新增
) -> None:
```

在报告生成的开头（`lines = ['# Go 代码审查报告\n']` 之后）插入：

```python
    # Review assumptions (replaces Coordinator agent)
    if classification and context_meta:
        lines.append(build_review_assumptions(classification, context_meta))
```

**Step 6: 在 `aggregate()` 函数中读取 JSON 并传入（约第 525 行）**

在 `aggregate()` 函数签名加参数：

```python
def aggregate(
    findings_dir: str,
    redlines_file: str | None,
    review_ignore_flags: str,
    max_output: int,
    output_file: str,
    classification_file: str | None = None,   # 新增
    context_meta_file: str | None = None,     # 新增
) -> None:
```

在 `generate_report(...)` 调用前加载 JSON：

```python
    classification = None
    context_meta = None
    if classification_file and Path(classification_file).exists():
        try:
            classification = json.loads(Path(classification_file).read_text())
        except json.JSONDecodeError:
            pass
    if context_meta_file and Path(context_meta_file).exists():
        try:
            context_meta = json.loads(Path(context_meta_file).read_text())
        except json.JSONDecodeError:
            pass
```

更新 `generate_report(...)` 调用，传入新参数：

```python
    generate_report(
        findings, total_raw, total_after_dedup, total_filtered,
        max_output, output_file,
        classification=classification,
        context_meta=context_meta,
    )
```

**Step 7: 在 `main()` 的 CLI 中加入两个新参数（约第 596 行）**

```python
    parser.add_argument('--classification-file', default='',
                        help='Path to classification.json from classify-diff.py')
    parser.add_argument('--context-meta-file', default='',
                        help='Path to context-meta.json from assemble-context.py')
```

并在 `aggregate()` 调用中传入：

```python
    aggregate(
        findings_dir=args.findings_dir,
        redlines_file=args.redlines_file or None,
        review_ignore_flags=args.review_ignore_flags,
        max_output=args.max_output,
        output_file=args.output,
        classification_file=args.classification_file or None,
        context_meta_file=args.context_meta_file or None,
    )
```

**Step 8: 运行全量测试**

```bash
uv run pytest tests/ -v
```

Expected: all passed

**Step 9: Commit**

```bash
git add languages/go/tools/aggregate-findings.py tests/go_tools/test_aggregate_findings.py
git commit -m "feat: add build_review_assumptions to replace Coordinator agent"
```

---

## Task 3: B1 — 自动 Verifier（`auto_verify`）

**Files:**
- Modify: `languages/go/tools/aggregate-findings.py`
- Modify: `tests/go_tools/test_aggregate_findings.py`

### 背景
Verifier agent 读取所有 P0/P1 findings，用 AI 判断是否 false positive，然后 confirm/downgrade/dismiss。核心逻辑是：有 Tier2 规则命中支撑的 finding 更可信；没有命中的更可疑。

### Step 1: 写失败测试

追加到 `tests/go_tools/test_aggregate_findings.py`：

```python
def test_auto_verify_confirms_with_rule_hit():
    f = mod.Finding("SAFE-003", "P0", "auth/login.go", 42, confidence=0.85)
    rule_hits = {
        "hits": [
            {"rule_id": "SAFE-003", "file": "auth/login.go", "line": 42}
        ]
    }
    mod.auto_verify([f], rule_hits)
    assert f.confidence == 1.0


def test_auto_verify_downgrades_without_hit():
    f = mod.Finding("SAFE-005", "P0", "service/user.go", 10, confidence=0.85)
    rule_hits = {"hits": []}
    original_confidence = f.confidence
    mod.auto_verify([f], rule_hits)
    assert f.confidence < original_confidence


def test_auto_verify_skips_high_confidence():
    f = mod.Finding("DATA-001", "P1", "repo/db.go", 5, confidence=0.95)
    rule_hits = {"hits": []}
    mod.auto_verify([f], rule_hits)
    assert f.confidence == 0.95  # unchanged — already high


def test_auto_verify_skips_p2():
    f = mod.Finding("QUAL-001", "P2", "util/helper.go", 20, confidence=0.8)
    rule_hits = {"hits": []}
    mod.auto_verify([f], rule_hits)
    assert f.confidence == 0.8  # P2 not affected
```

**Step 2: 运行测试，确认 FAIL**

```bash
uv run pytest tests/go_tools/test_aggregate_findings.py -k "auto_verify" -v
```

Expected: FAIL with `AttributeError`

**Step 3: 实现 `auto_verify()`**

在 `aggregate-findings.py` 的 `apply_fuzzy_cap()` 函数之后插入：

```python
def auto_verify(findings: list, rule_hits: dict) -> None:
    """
    Deterministic verifier: adjust confidence based on Tier2 rule hit correlation.
    Only affects P0/P1 findings with confidence < 0.92 (high-confidence are left alone).
    Mutates findings in-place.
    """
    CONFIDENCE_CEILING = 0.92  # findings above this are already "confirmed"
    DOWNGRADE_AMOUNT = 0.10
    SAFE_DATA_PREFIXES = ('SAFE-', 'DATA-')

    # Build a lookup: {(rule_id, filepath): [line_numbers]}
    hit_index: dict[tuple, list[int]] = {}
    for hit in rule_hits.get('hits', []):
        key = (hit.get('rule_id', ''), hit.get('file', ''))
        hit_index.setdefault(key, []).append(hit.get('line', 0))

    for f in findings:
        # Only adjust P0/P1
        if f.severity not in ('P0', 'P1'):
            continue
        # Skip already-confirmed findings
        if f.confidence >= CONFIDENCE_CEILING:
            continue

        key = (f.rule_id, f.filepath)
        matched_lines = hit_index.get(key, [])

        if matched_lines:
            # Direct rule hit at same/adjacent location → confirm
            if any(abs(f.line_start - ln) <= ADJACENT_LINE_THRESHOLD for ln in matched_lines):
                f.confidence = 1.0
        elif any(f.rule_id.startswith(p) for p in SAFE_DATA_PREFIXES):
            # SAFE/DATA finding with no Tier2 support → soft downgrade
            f.confidence = max(0.0, f.confidence - DOWNGRADE_AMOUNT)
```

**Step 4: 运行测试，确认 PASS**

```bash
uv run pytest tests/go_tools/test_aggregate_findings.py -k "auto_verify" -v
```

Expected: 4 passed

**Step 5: 把 `auto_verify` 接入 `aggregate()` pipeline**

在 `aggregate()` 函数签名新增参数：

```python
def aggregate(
    findings_dir: str,
    redlines_file: str | None,
    review_ignore_flags: str,
    max_output: int,
    output_file: str,
    classification_file: str | None = None,
    context_meta_file: str | None = None,
    rule_hits_file: str | None = None,        # 新增
) -> None:
```

在 Step 3（Redline priority）之后、Step 4（review:ignore）之前插入：

```python
    # Step 2.5: Auto-verify (replaces Verifier agent)
    if rule_hits_file and Path(rule_hits_file).exists():
        try:
            rule_hits = json.loads(Path(rule_hits_file).read_text())
            auto_verify(findings, rule_hits)
        except json.JSONDecodeError:
            pass
```

**Step 6: 在 `main()` CLI 中加入参数**

```python
    parser.add_argument('--rule-hits-file', default='',
                        help='Path to rule-hits.json from scan-rules.sh (enables auto-verify)')
```

在 `aggregate()` 调用中传入：

```python
        rule_hits_file=args.rule_hits_file or None,
```

**Step 7: 运行全量测试**

```bash
uv run pytest tests/ -v
```

Expected: all passed

**Step 8: Commit**

```bash
git add languages/go/tools/aggregate-findings.py tests/go_tools/test_aggregate_findings.py
git commit -m "feat: add auto_verify to replace Verifier agent"
```

---

## Task 4: 更新 `full-review.md` 和 `lite-review.md`

**Files:**
- Modify: `languages/go/workflows/full-review.md`
- Modify: `languages/go/workflows/lite-review.md`

### Step 1: 更新 `full-review.md` Step 4 的 Verifier 部分

找到 Step 4 的 Verifier 块（约第 379-390 行），替换为：

```markdown
### Auto-Verifier（Tier2 关联校验）

```bash
# auto-verify 已内置在 aggregate-findings.py --rule-hits-file 参数中
# 无需单独步骤
```

> Verifier 逻辑已工具化：aggregate-findings.py 使用 --rule-hits-file 自动完成。
```

### Step 2: 更新 `full-review.md` Step 5 的 aggregate-findings 调用

找到 `python3 languages/go/tools/aggregate-findings.py` 调用（约第 425 行），替换为：

```bash
python3 languages/go/tools/aggregate-findings.py \
  --findings-dir "$SESSION_DIR" \
  ${RULES_FILE:+--redlines-file "$RULES_FILE"} \
  ${IGNORE_FLAGS:+--review-ignore-flags "$IGNORE_FLAGS"} \
  --rule-hits-file "$SESSION_DIR/rule-hits.json" \
  --classification-file "$SESSION_DIR/classification.json" \
  --context-meta-file "$SESSION_DIR/context-meta.json" \
  --max-output 15 \
  --output "$REPORT_FILE"
```

### Step 3: 移除 full-review.md 中的 Coordinator Agent 块

找到 Step 5 的 "Coordinator Agent" 部分（约第 441-462 行），删除整个块（约 22 行），替换为注释：

```markdown
> Coordinator 已工具化：审查说明由 aggregate-findings.py 的 --classification-file 和 --context-meta-file 参数自动生成。
```

### Step 4: 对 `lite-review.md` 做同样的 Step 5 更新

找到 `python3 languages/go/tools/aggregate-findings.py` 调用，更新为同样加入三个新参数（`--rule-hits-file`、`--classification-file`、`--context-meta-file`）。

### Step 5: Commit

```bash
git add languages/go/workflows/full-review.md languages/go/workflows/lite-review.md
git commit -m "docs: remove Verifier/Coordinator agent calls, use toolified versions"
```

---

## Task 5: 新建 `orchestrate-review.py`（方向 A）

**Files:**
- Create: `languages/go/tools/orchestrate-review.py`
- Create: `tests/go_tools/test_orchestrate_review.py`

### Step 1: 写失败测试

新建 `tests/go_tools/test_orchestrate_review.py`：

```python
import importlib.util, json, tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "orchestrate_review",
    Path(__file__).parents[2] / "languages/go/tools/orchestrate-review.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr("sys.argv", ["orchestrate-review.py", "--mode", "prepare"])
    args = mod.parse_args()
    assert args.mode == "prepare"
    assert args.base == "main"
    assert args.session_dir == ""


def test_prepare_creates_session_dir(tmp_path, monkeypatch):
    """prepare phase creates session_dir and writes task-list.json."""
    # We test the directory creation logic in isolation
    session_dir = tmp_path / "run-abc123-1234"
    mod.ensure_session_dir(str(session_dir))
    assert session_dir.exists()
```

**Step 2: 运行测试，确认 FAIL**

```bash
uv run pytest tests/go_tools/test_orchestrate_review.py -v
```

Expected: FAIL (module not found)

**Step 3: 创建 `orchestrate-review.py` 的骨架**

```python
#!/usr/bin/env python3
"""
orchestrate-review.py — Go Code Review Skill v8.0.0
Deterministic orchestrator for all non-AI workflow steps.

Usage:
  python3 orchestrate-review.py --mode prepare \
    [--branch feat/xxx] [--base main] [--session-dir .review/run-abc-1234]

  python3 orchestrate-review.py --mode aggregate \
    --session-dir .review/run-abc-1234 [--output report.md]

Exit codes:
  0 = success
  1 = fatal error (missing branch, empty diff, etc.)
  2 = TRIVIAL tier (no review needed)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ── Helpers ─────────────────────────────────────────────────────────────────────

def ensure_session_dir(session_dir: str) -> Path:
    p = Path(session_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=check)


# ── CLI ──────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Orchestrate deterministic Go review steps')
    parser.add_argument('--mode', required=True, choices=['prepare', 'aggregate'])
    parser.add_argument('--branch', default='', help='Source branch (default: current branch)')
    parser.add_argument('--base', default='main', help='Base branch')
    parser.add_argument('--session-dir', default='', help='Session directory path')
    parser.add_argument('--output', default='', help='Output report path (aggregate mode)')
    parser.add_argument('--resume', action='store_true', help='Resume interrupted review')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.mode == 'prepare':
        sys.exit(phase_prepare(args))
    else:
        sys.exit(phase_aggregate(args))


def phase_prepare(args) -> int:
    print("placeholder prepare")
    return 0


def phase_aggregate(args) -> int:
    print("placeholder aggregate")
    return 0


if __name__ == '__main__':
    main()
```

**Step 4: 运行测试，确认 PASS**

```bash
uv run pytest tests/go_tools/test_orchestrate_review.py -v
```

Expected: 2 passed

**Step 5: Commit 骨架**

```bash
git add languages/go/tools/orchestrate-review.py tests/go_tools/test_orchestrate_review.py
git commit -m "feat: add orchestrate-review.py skeleton with parse_args and ensure_session_dir"
```

---

## Task 6: 实现 `phase_prepare()` — Step 1-2（git + classify）

**Files:**
- Modify: `languages/go/tools/orchestrate-review.py`
- Modify: `tests/go_tools/test_orchestrate_review.py`

### Step 1: 写失败测试

追加到 `tests/go_tools/test_orchestrate_review.py`：

```python
def test_step1_collect_diff(tmp_path):
    """collect_diff writes diff.txt, files.txt, gitlog.txt."""
    # We need a real git repo to test this properly; use a fixture
    # For now, test that the function exists and has the right signature
    import inspect
    sig = inspect.signature(mod.collect_diff)
    params = list(sig.parameters.keys())
    assert 'source_branch' in params
    assert 'base_branch' in params
    assert 'session_dir' in params


def test_step2_triage_calls_classify(tmp_path):
    """triage() calls classify-diff.py and returns classification dict."""
    import inspect
    sig = inspect.signature(mod.triage)
    params = list(sig.parameters.keys())
    assert 'diff_lines' in params
    assert 'files_changed' in params
    assert 'session_dir' in params
```

**Step 2: 运行，确认 FAIL**

```bash
uv run pytest tests/go_tools/test_orchestrate_review.py -k "step1 or step2" -v
```

**Step 3: 实现 `collect_diff()` 和 `triage()`**

在 `orchestrate-review.py` 中替换 `phase_prepare()` 骨架，添加：

```python
TOOLS_DIR = Path(__file__).parent


def collect_diff(source_branch: str, base_branch: str, session_dir: str) -> dict:
    """Step 1: collect git diff and file list. Returns metadata dict."""
    sd = ensure_session_dir(session_dir)

    diff_result = run(['git', 'diff', f'{base_branch}...{source_branch}', '--diff-filter=AM'])
    (sd / 'diff.txt').write_text(diff_result.stdout)

    files_result = run(['git', 'diff', f'{base_branch}...{source_branch}',
                        '--name-only', '--diff-filter=AM'])
    go_files = [f for f in files_result.stdout.splitlines() if f.endswith('.go')]
    (sd / 'files.txt').write_text('\n'.join(go_files) + '\n')

    log_result = run(['git', 'log', '--oneline', '-5', f'{base_branch}..{source_branch}'],
                     check=False)
    (sd / 'gitlog.txt').write_text(log_result.stdout)

    diff_lines = len(diff_result.stdout.splitlines())
    return {'diff_lines': diff_lines, 'files_changed': len(go_files), 'go_files': go_files}


def triage(diff_lines: int, files_changed: int, session_dir: str) -> dict:
    """Step 2: classify diff tier. Returns classification dict."""
    sd = Path(session_dir)
    files_str = ' '.join((sd / 'files.txt').read_text().splitlines())

    result = run([
        'python3', str(TOOLS_DIR / 'classify-diff.py'),
        '--diff-lines', str(diff_lines),
        '--files-changed', str(files_changed),
        '--files', files_str,
        '--diff-file', str(sd / 'diff.txt'),
    ])

    classification = json.loads(result.stdout)
    (sd / 'classification.json').write_text(json.dumps(classification, ensure_ascii=False, indent=2))
    return classification


def phase_prepare(args) -> int:
    # Resolve branches
    source_branch = args.branch or run(['git', 'branch', '--show-current']).stdout.strip()
    base_branch = args.base

    # Resolve session dir
    if args.session_dir:
        session_dir = args.session_dir
    else:
        head_sha = run(['git', 'rev-parse', source_branch]).stdout.strip()[:8]
        session_dir = f'.review/run-{head_sha}-{os.getpid()}'

    print(f'[orchestrate] session_dir={session_dir}')

    # Step 1
    meta = collect_diff(source_branch, base_branch, session_dir)
    print(f'[1/3] diff={meta["diff_lines"]} lines, go_files={meta["files_changed"]}')

    if not meta['go_files']:
        print('ERROR: no Go files changed')
        return 1

    # Step 2
    classification = triage(meta['diff_lines'], meta['files_changed'], session_dir)
    tier = classification['tier']
    print(f'[2/3] tier={tier}')

    if tier == 'TRIVIAL':
        print('TRIVIAL: 变更为文档/配置类，无需审查')
        return 2

    # Write partial task-list (to be completed in step 3)
    task_list = {'tier': tier, 'session_dir': session_dir, 'tasks': [], 'status': 'preparing'}
    Path(session_dir, 'task-list.json').write_text(json.dumps(task_list, ensure_ascii=False, indent=2))

    print(f'[orchestrate] prepare step 1-2 complete. Run steps 3+ manually or call with --mode prepare-full.')
    return 0
```

**Step 4: 运行测试，确认 PASS**

```bash
uv run pytest tests/go_tools/test_orchestrate_review.py -v
```

Expected: all passed

**Step 5: Commit**

```bash
git add languages/go/tools/orchestrate-review.py tests/go_tools/test_orchestrate_review.py
git commit -m "feat: implement collect_diff and triage in orchestrate-review.py"
```

---

## Task 7: 实现 `phase_prepare()` 完整版（Steps 3+3.5+Tier1+Tier2）

**Files:**
- Modify: `languages/go/tools/orchestrate-review.py`
- Modify: `tests/go_tools/test_orchestrate_review.py`

### Step 1: 写失败测试

```python
def test_build_task_list_lite():
    """build_task_list returns one task per agent for LITE tier."""
    classification = {
        "tier": "LITE",
        "agent_roster": ["safety", "quality", "observability"],
        "rules_source": "built_in",
        "rules_file": "",
    }
    tasks = mod.build_task_list(classification, session_dir="/tmp/fake-session")
    assert len(tasks) == 3
    assert tasks[0]["agent"] == "safety"
    assert "context_file" in tasks[0]
    assert "output_file" in tasks[0]


def test_build_task_list_full():
    classification = {
        "tier": "FULL",
        "agent_roster": ["safety", "data", "design", "quality", "observability", "business", "naming"],
        "rules_source": "built_in",
        "rules_file": "",
    }
    tasks = mod.build_task_list(classification, session_dir="/tmp/fake-session")
    assert len(tasks) == 7
```

**Step 2: 确认 FAIL**

```bash
uv run pytest tests/go_tools/test_orchestrate_review.py -k "task_list" -v
```

**Step 3: 实现 `assemble_context()`、`run_tier1()`、`run_tier2()`、`build_task_list()`**

```python
def assemble_context(classification: dict, session_dir: str) -> int:
    """Step 3: assemble context package. Returns exit code (2=truncated)."""
    sd = Path(session_dir)
    rules_file = classification.get('rules_file', '')
    rules_source = classification.get('rules_source', 'built_in')

    cmd = [
        'python3', str(TOOLS_DIR / 'assemble-context.py'),
        '--diff', str(sd / 'diff.txt'),
        '--rules-source', rules_source,
        '--git-log', str(sd / 'gitlog.txt'),
    ]
    if rules_file:
        cmd += ['--rules-file', rules_file]

    result = subprocess.run(cmd, capture_output=True, text=True)
    (sd / 'context-package.md').write_text(result.stdout)
    (sd / 'context-meta.json').write_text(result.stderr.split('\n')[0])  # first line is JSON
    return result.returncode


def run_architecture_scan(files: list[str], session_dir: str) -> bool:
    """Step 3.5 (FULL only): architecture pre-scan. Returns True on success."""
    sd = Path(session_dir)
    files_str = ' '.join(files)
    result = subprocess.run(
        ['python3', str(TOOLS_DIR / 'scan-architecture.py'), '--files', files_str],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0 and result.stdout.strip():
        (sd / 'architecture-context.json').write_text(result.stdout)
        return True
    return False


def run_tier1(files: list[str], session_dir: str) -> None:
    """Tier 1: run Go build tools."""
    sd = Path(session_dir)
    files_input = '\n'.join(files)
    result = subprocess.run(
        ['bash', str(TOOLS_DIR / 'run-go-tools.sh')],
        input=files_input, capture_output=True, text=True
    )
    (sd / 'diagnostics.json').write_text(result.stdout or '{}')


def run_tier2(files: list[str], session_dir: str) -> None:
    """Tier 2: scan YAML rules."""
    sd = Path(session_dir)
    files_input = '\n'.join(files)
    result = subprocess.run(
        ['bash', str(TOOLS_DIR / 'scan-rules.sh')],
        input=files_input, capture_output=True, text=True
    )
    (sd / 'rule-hits.json').write_text(result.stdout or '{"hits":[],"summary":{}}')


def build_task_list(classification: dict, session_dir: str) -> list[dict]:
    """Build the list of AI agent tasks from classification."""
    agent_roster = classification.get('agent_roster', [])
    tasks = []
    for agent in agent_roster:
        tasks.append({
            'agent': agent,
            'context_file': str(Path(session_dir) / 'context-package.md'),
            'rule_hits_file': str(Path(session_dir) / 'rule-hits.json'),
            'diagnostics_file': str(Path(session_dir) / 'diagnostics.json'),
            'output_file': str(Path(session_dir) / f'findings-{agent}.md'),
        })
    return tasks
```

然后更新 `phase_prepare()` 调用新函数，完成 Steps 3+3.5+Tier1+Tier2，并写入最终的 `task-list.json`。

**Step 4: 运行测试，确认 PASS**

```bash
uv run pytest tests/go_tools/test_orchestrate_review.py -v
```

**Step 5: Commit**

```bash
git add languages/go/tools/orchestrate-review.py tests/go_tools/test_orchestrate_review.py
git commit -m "feat: implement full phase_prepare in orchestrate-review.py"
```

---

## Task 8: 实现 `phase_aggregate()` + 更新 SKILL.md

**Files:**
- Modify: `languages/go/tools/orchestrate-review.py`
- Modify: `languages/go/SKILL.md`
- Modify: `languages/go/workflows/full-review.md`
- Modify: `languages/go/workflows/lite-review.md`

### Step 1: 实现 `phase_aggregate()`

```python
def phase_aggregate(args) -> int:
    from datetime import datetime

    sd = Path(args.session_dir)
    if not sd.exists():
        print(f'ERROR: session_dir not found: {args.session_dir}')
        return 1

    classification_file = sd / 'classification.json'
    context_meta_file = sd / 'context-meta.json'
    rule_hits_file = sd / 'rule-hits.json'

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    output_file = args.output or f'.review/results/review-{timestamp}.md'
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        'python3', str(TOOLS_DIR / 'aggregate-findings.py'),
        '--findings-dir', str(sd),
        '--max-output', '15',
        '--output', output_file,
    ]
    if classification_file.exists():
        cmd += ['--classification-file', str(classification_file)]
    if context_meta_file.exists():
        cmd += ['--context-meta-file', str(context_meta_file)]
    if rule_hits_file.exists():
        cmd += ['--rule-hits-file', str(rule_hits_file)]

    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        print('ERROR: aggregate-findings.py failed')
        return 1

    print(f'[orchestrate] report: {output_file}')
    return 0
```

### Step 2: 运行测试

```bash
uv run pytest tests/ -v
```

### Step 3: 简化 `full-review.md`

将 Steps 1-3+3.5+Tier1+Tier2 的所有 bash 片段替换为一次调用：

```bash
echo "[1-3/6] 准备阶段（确定性）..."
python3 languages/go/tools/orchestrate-review.py --mode prepare \
  --branch "$SOURCE_BRANCH" --base "$BASE_BRANCH" \
  --session-dir "$SESSION_DIR"
PREPARE_EXIT=$?
[ $PREPARE_EXIT -eq 2 ] && exit 0   # TRIVIAL
[ $PREPARE_EXIT -ne 0 ] && exit 1   # error

TASK_LIST=$(cat "$SESSION_DIR/task-list.json")
AGENT_ROSTER=$(echo "$TASK_LIST" | python3 -c "import sys,json; print(' '.join(t['agent'] for t in json.load(sys.stdin)['tasks']))")
```

Step 4 保留 AI agents 调用部分（不变），Step 5-6 替换为：

```bash
echo "[5-6/6] 聚合与输出（确定性）..."
python3 languages/go/tools/orchestrate-review.py --mode aggregate \
  --session-dir "$SESSION_DIR" \
  ${OUTPUT_FILE:+--output "$OUTPUT_FILE"}
```

### Step 4: 对 `lite-review.md` 做同样简化

### Step 5: Commit

```bash
git add languages/go/tools/orchestrate-review.py \
        languages/go/workflows/full-review.md \
        languages/go/workflows/lite-review.md
git commit -m "feat: complete orchestrate-review.py, simplify workflow markdowns"
```

---

## Task 9: 全流程验证

**Files:**
- Read: `.review/scanner-results/aggregated-*.json`（已有数据）

### Step 1: 在现有 test repo 运行端到端验证

```bash
# 确认 Python 工具可单独运行
python3 languages/go/tools/orchestrate-review.py --help

# 运行 prepare（如果当前 repo 有 Go 文件）
python3 languages/go/tools/orchestrate-review.py --mode prepare \
  --branch main --base main \
  --session-dir /tmp/test-session-$$
```

### Step 2: 运行全量测试套件

```bash
uv run pytest tests/ -v --tb=short
```

Expected: all passed

### Step 3: Commit（如有修复）

```bash
git add -A
git commit -m "fix: e2e validation fixes"
```

---

## 完成标准

- [ ] `uv run pytest tests/ -v` 全部通过
- [ ] `aggregate-findings.py --help` 显示 `--rule-hits-file`、`--classification-file`、`--context-meta-file` 三个新参数
- [ ] `orchestrate-review.py --mode prepare` 能独立运行并输出 `task-list.json`
- [ ] `full-review.md` Steps 1-3+3.5+Tier1+Tier2 替换为单次 `orchestrate-review.py` 调用
- [ ] `full-review.md` 中 Verifier / Coordinator agent 调用已移除
