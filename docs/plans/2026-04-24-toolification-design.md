# 工具化设计：减少 AI 依赖

**日期**: 2026-04-24  
**目标**: 把当前工作流中由 Claude 执行的确定性步骤提取为真实脚本，AI 只负责代码分析。

---

## 背景

当前 Go 代码审查工作流（`full-review.md` / `lite-review.md`）以"AI 指令文档"形式存在：Claude 读取 markdown，逐步执行 bash 片段，调用 Python 脚本，再调用子 agent，全程占用对话上下文。

**问题**：Steps 1-3、3.5、Tier1/Tier2、Step 5-6 都是确定性操作，本不需要 AI 参与，却消耗大量 token 用于编排。

**AI 依赖分布**：

| 步骤 | 当前实现 | 是否可工具化 |
|------|---------|-------------|
| Step 1: git diff/log | shell 命令（由 Claude 执行） | ✅ 可提取 |
| Step 2: classify-diff.py | Python 脚本（由 Claude 调用） | ✅ 可提取 |
| Step 3: assemble-context.py | Python 脚本（由 Claude 调用） | ✅ 可提取 |
| Step 3.5: scan-architecture.py | Python 脚本（由 Claude 调用） | ✅ 可提取 |
| Step 4 Tier1: golangci-lint/go vet | 工具（由 Claude 调用） | ✅ 可提取 |
| Step 4 Tier2: scan-rules.sh | bash 脚本（由 Claude 调用） | ✅ 可提取 |
| Step 4: 3-7 AI Agents | Claude 子 agent 分析 | ❌ 核心价值，保留 |
| Step 4: Verifier agent | Claude AI 校验 P0/P1 | ⚠️ 可替换为规则 |
| Step 5: aggregate-findings.py | Python 脚本（由 Claude 调用） | ✅ 可提取 |
| Step 5: Coordinator agent | Claude AI 生成报告头 | ⚠️ 可替换为模板 |
| Step 6: 输出 | shell 命令（由 Claude 执行） | ✅ 可提取 |

---

## 方向 A：Python 编排器

### 目标
新建 `languages/go/tools/orchestrate-review.py`，封装所有确定性步骤。SKILL.md 只保留 AI 分析部分。

### 接口设计

```bash
# 阶段 1：准备（Steps 1-3+3.5+Tier1+Tier2）
python3 languages/go/tools/orchestrate-review.py --mode prepare \
  --branch feat/xxx --base main \
  --session-dir .review/run-abc123-$$

# 输出：
# - $SESSION_DIR/context-package.md
# - $SESSION_DIR/task-list.json  （每个 agent 的 {agent, context_file, rule_hits}）
# - $SESSION_DIR/classification.json
# - 退出码：0=成功, 1=无 Go 文件, 2=TRIVIAL 早退

# 阶段 2：聚合（Step 5-6）
python3 languages/go/tools/orchestrate-review.py --mode aggregate \
  --session-dir .review/run-abc123-$$ \
  [--output report.md]

# 输出：最终报告到 .review/results/review-{timestamp}.md
```

### task-list.json 格式

```json
{
  "tier": "FULL",
  "session_dir": ".review/run-abc123-1234",
  "tasks": [
    {
      "agent": "safety",
      "context_file": ".review/run-abc123-1234/context-package.md",
      "rule_hits_file": ".review/run-abc123-1234/rule-hits.json",
      "diagnostics_file": ".review/run-abc123-1234/diagnostics.json",
      "output_file": ".review/run-abc123-1234/findings-safety.md"
    }
  ]
}
```

### SKILL.md 变化（简化后）

```markdown
## Step 1: 准备（确定性）
Bash: python3 languages/go/tools/orchestrate-review.py --mode prepare ...
读取 task-list.json

## Step 2: AI 分析
对每个 task，读取对应 agent.md + context_file，调用 Agent，写入 output_file

## Step 3: 聚合（确定性）
Bash: python3 languages/go/tools/orchestrate-review.py --mode aggregate ...
```

### 收益
- Token 减少约 60-70%（编排步骤不再消耗对话上下文）
- 工作流行为可测试（单元测试 orchestrate-review.py）
- 错误更清晰（Python 异常 vs Claude 报错）

---

## 方向 B：Verifier + Coordinator 工具化

### B1：自动 Verifier（`--auto-verify` 选项）

在 `aggregate-findings.py` 新增 `auto_verify(findings, rule_hits)` 函数：

**规则**：
1. finding 的 `rule_id` 在 `rule-hits.json` 中有直接命中 → confidence 提升至 1.0（confirm）
2. SAFE/DATA 类 finding 但 Tier2 完全无同类命中 → confidence 降低 0.1（soft downgrade）
3. 已有的 `deduplicate()` 处理多 agent 重叠

**接口**：
```bash
python3 aggregate-findings.py \
  --findings-dir $SESSION_DIR \
  --auto-verify $SESSION_DIR/rule-hits.json \
  --output report.md
```

### B2：模板化 Coordinator

在 `aggregate-findings.py` 的 `generate_report()` 中加入 `build_review_assumptions()`，从 JSON 元数据生成报告头：

```python
def build_review_assumptions(classification, context_meta, agent_roster):
    return f"""## 审查说明
- 规则来源：{classification['rules_source']}
- 处理档位：{classification['tier']}（{classification['trigger_reason']}）
- 运行 Agents：{', '.join(agent_roster)}
- Token 估算：{context_meta['estimated_tokens']} / {context_meta['token_limit']}
- 截断节：{', '.join(context_meta.get('truncated_sections', [])) or '无'}
"""
```

### 收益
- 每次 Full 档减少 2 个 AI agent 调用（约 3k-8k tokens）
- 报告头内容更稳定、可预期

---

## 实施顺序

1. **方向 B 先行**（改动小，风险低）
   - B2 Coordinator 替换：改 `aggregate-findings.py`，约 50 行
   - B1 Verifier 替换：改 `aggregate-findings.py`，约 80 行
   - 更新 `full-review.md` 移除 Coordinator/Verifier 调用步骤

2. **方向 A 后续**（改动大，独立新文件）
   - 新建 `orchestrate-review.py`，迁移 Steps 1-3+3.5+Tier1+Tier2+5-6 逻辑
   - 简化 `full-review.md` / `lite-review.md`
   - 更新 `SKILL.md` routing

---

## 成功标准

- `orchestrate-review.py --mode prepare` 在 30 秒内完成所有确定性步骤
- SKILL.md 中 Claude 执行的步骤数从约 20 步减少到 5 步以内
- Verifier/Coordinator 输出与 AI 版本结果一致率 ≥ 90%（通过 reviewer-eval 验证）
