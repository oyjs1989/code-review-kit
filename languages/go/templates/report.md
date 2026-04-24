# Go 代码审查报告 — 输出格式模板

> **重要**：所有审查输出必须使用中文。
>
> 此文件是 `aggregate-findings.py` 和所有 Agent 的输出格式契约。
> `### [P` 是 finding 边界标记，`aggregate-findings.py` 用它计数和解析。

---

## 报告结构

```markdown
# Go 代码审查报告

## 审查摘要

| 指标 | 数量 |
|------|------|
| P0（必须修复） | X 个 |
| P1（强烈建议） | X 个 |
| P2（建议优化） | X 个 |

## P0（必须修复）

### [P0] {rule_id} · {file}:{line}
**来源**: {agent}
**置信度**: {confidence}
**needs_clarification**: {null | "具体问题"}

**问题描述**: <中文说明，解释问题原因和潜在后果>

**修改建议**:
```go
// 修复代码
```

---

## P1（强烈建议）

### [P1] {rule_id} · {file}:{line}
**来源**: {agent}
**置信度**: {confidence}
**needs_clarification**: {null | "具体问题"}

**问题描述**: <中文说明>

**修改建议**:
```go
// 修复代码
```

---

## P2（建议优化）

### [P2] {rule_id} · {file}:{line}
**来源**: {agent}
**置信度**: {confidence}
**needs_clarification**: {null | "具体问题"}

**问题描述**: <中文说明>

**修改建议**:
```go
// 修复代码
```

---

## Appendix
*（若总 findings > 15，将剩余条目放入此节）*
```

若总 findings 超过 15 条，终端摘要行添加：
`（另有 N 条问题因数量限制未显示，完整报告见 {REPORT_FILE}）`

---

## Finding 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `rule_id` | string | 规则 ID，如 `SAFE-003`、`DATA-007`、`QUAL-012` |
| `file` | string | 相对路径，如 `internal/service/user.go` |
| `line` | int | 行号（目标文件行号，非 diff 行号） |
| `agent` | string | 来源 Agent 名称，如 `safety`、`data` |
| `confidence` | float | 置信度 0.00–1.00，低于 0.75 的 finding 被 aggregate-findings.py 过滤 |
| `needs_clarification` | null \| string | 若无法独立判定需填具体问题；确定成立填 `null` |

## 严重级别定义

| 级别 | 含义 | 处理要求 |
|------|------|---------|
| P0 | 必须修复 — 会导致崩溃、数据损坏、安全漏洞 | 合并前必须修复 |
| P1 | 强烈建议 — 明显的质量问题，影响可维护性 | 应在近期修复 |
| P2 | 建议优化 — 代码改进建议 | 可酌情处理 |
| P3 | 参考信息 — 仅供参考，不计入主报告 | 放入 Appendix |
