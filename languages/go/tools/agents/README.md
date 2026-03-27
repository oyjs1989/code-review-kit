# Agent 工具库

这里存放 code review agents 在历次审查中沉淀下来的可复用分析脚本。

## 使用约定

每个 agent 在执行分析前，应先查看本目录是否已有合适的工具：

```bash
ls skills/go-code-review/tools/agents/
```

如果已有合适的工具，直接调用：

```bash
# Shell 脚本
bash skills/go-code-review/tools/agents/<tool-name>.sh <go-files...>

# Python 脚本
python3 skills/go-code-review/tools/agents/<tool-name>.py <go-files...>
```

如果没有，写完分析逻辑后，**将其保存为新工具**供后续复用。

## 工具命名规范

- 格式：`<domain>-<what-it-checks>.<ext>`，扩展名为 `.sh` 或 `.py`
- 示例：`safety-goroutine-leak.sh`、`data-n-plus-one.py`、`quality-long-func.sh`
- 用 Python 的场景：需要 AST 解析、复杂数据处理、JSON 输出格式化等

## 工具文件头模板

Shell：
```bash
#!/usr/bin/env bash
# 用途：<一句话描述检查什么>
# 适用 Agent：<safety|data|design|quality|observability|business>
# 输入：Go 文件路径列表（stdin 或参数）
# 输出：发现的问题，每行一条
# 创建时间：<YYYY-MM-DD>
```

Python：
```python
#!/usr/bin/env python3
# 用途：<一句话描述检查什么>
# 适用 Agent：<safety|data|design|quality|observability|business>
# 输入：Go 文件路径列表（命令行参数）
# 输出：发现的问题，每行一条
# 创建时间：<YYYY-MM-DD>
```

## 已有工具

（首次使用时为空，随 review 逐步积累）
