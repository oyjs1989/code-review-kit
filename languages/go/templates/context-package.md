# Context Package 格式规范

> 此文件是 `assemble-context.py` 输出格式的单一事实来源。
> Agent 通过此文件了解 Context Package 的结构；修改段落名时必须同步更新 `assemble-context.py`。

---

## 段落结构与 Token 预算（总限 16,000 tokens）

| 段落 | 内容来源 | 预算 | 截断优先级 |
|------|---------|------|-----------|
| `[Intent]` | `gitlog.txt` 最近 5 条 commit | ~500 tokens | 永不截断 |
| `[Rules]` | `rules/*.yaml` 或项目规则文件 | ~2,400 tokens | 按关键词过滤不相关节 |
| `[Change Set]` | `diff.txt` git diff 内容 | ~8,800 tokens | 优先截断（触发 exit 2）|
| `[Context]` | 变更函数完整体（来自源文件） | ~3,200 tokens | 超限降为签名模式 |
| `[Architecture Context]` | `scan-architecture.py` 输出 | ~1,600 tokens | Full 档专属，Lite 档省略 |

截断优先顺序（超出总预算时）：
1. `[Architecture Context]` → 先省略（最低优先级）
2. `[Change Set]` → 截断尾部，`assemble-context.py` exit code 2
3. `[Context]` → 超过 `FUNC_MAX_LINES=80` 的函数降为签名
4. `[Rules]` → 按变更文件关键词过滤不相关节
5. `[Intent]` → 永不截断

---

## 段落格式（load-bearing 标头，不得修改大小写或标点）

以下标头字符串被 `aggregate-findings.py` 解析，**必须完全一致**：

```markdown
## [Intent]
{git log 内容，最近 5 条 commit message}

## [Rules]
{项目规则文件内容，或 built_in 默认规则说明}

## [Change Set]
\`\`\`diff
{git diff 内容}
\`\`\`

## [Context]
\`\`\`go
{变更函数完整体或签名}
\`\`\`

## [Architecture Context]
{模块依赖关系，仅 Full 档包含此节}
```

---

## 实现常量（assemble-context.py）

```python
TOKEN_LIMIT      = 16000   # 总 token 预算
RULES_MAX_LINES  = 300     # [Rules] 最大行数，超出按关键词过滤
CONTEXT_MAX_LINES = 200    # [Context] 总行数上限
FUNC_MAX_LINES   = 80      # 单函数最大行数，超出降为签名
```

---

## Exit Code 语义（assemble-context.py）

| Exit Code | 含义 | 调用方处理 |
|-----------|------|-----------|
| `0` | 正常组装完成 | 继续执行 |
| `2` | `[Change Set]` 被截断 | `TIER` 降级为 `LITE`，以 `TRUNCATION_WARNING` 标记 |

stderr 同时输出 metadata JSON（写入 `$SESSION_DIR/context-meta.json`）：
```json
{
  "estimated_tokens": 14200,
  "token_limit": 16000,
  "sections_included": ["intent", "rules", "change_set", "context"],
  "truncated_sections": ["change_set"]
}
```

---

## 规则来源优先级（classify-diff.py 检测）

| 优先级 | 来源 | 路径 |
|--------|------|------|
| 1 | 项目 redlines | `.claude/review-rules.md` |
| 2 | 项目规则文件 | `AGENTS.md` / `CLAUDE.md` |
| 3 | docs/ 下规则文档 | `docs/*style*.md` / `docs/*rule*.md` |
| 4 | 内置规则 | `languages/go/rules/*.yaml`（38 条规则） |
