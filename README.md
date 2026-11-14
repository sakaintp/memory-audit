# memory-audit

给 Agent 的长期记忆做一次**只读体检**：哪些记忆缺来源、哪些已经过期、哪些常驻在上下文里、大概每次会话要花多少 token。

## 用法

先在内置示例上试跑（示例是虚构数据，不涉及任何人）：

```bash
git clone https://github.com/sakaintp/memory-audit.git
cd memory-audit
python3 audit.py examples/sample-persona
```

再对你自己的记忆库运行：

```bash
python3 audit.py /path/to/persona
python3 audit.py /path/to/persona --format markdown
python3 audit.py /path/to/persona --today 2026-11-14
```

输出为文本或 Markdown 报告。无记忆条目时退出码为 2。
只需要 Python 3.8+ 标准库，不用安装任何依赖。

## 示例输出

对内置示例运行后（节选）：

```text
检查日期 2026-11-14｜记忆 5 条｜常驻 5 条｜常驻约 120 tokens/次

## 高置信度但无证据（1）
  - val-002

## 已过复核期（2）
  - val-002 — 2025-12
  - con-002 — 2026-09

## 同 key 多条（可能需要 supersedes）（1）
  - values.craft — ['val-001', 'val-002']

## 取代链稀疏（1）
  - 5 条中仅 0 条声明过 supersedes
```

注意报告里**只有条目 id 和统计，没有记忆原文**。

## 安全承诺

- **只读**：不修改、删除或写回任何记忆数据
- **不输出记忆原文**：报告只含条目 id、分类与统计
- **不联网**：纯本地读取与计算
- token 为粗略估算（CJK 约 1 token/字，其余约 4 字符/token），只用于比较相对开销，不作为计费依据

## 检查项

- 高置信度但无证据
- 缺少原始表述锚点
- 无备注也无冲突说明
- secret 级条目
- 常驻上下文但敏感级偏高
- 已过复核期
- 同 key 多条
- 取代链稀疏（声明过 supersedes 的条目比例过低）

## 设计说明

解析层与检查规则分离。当前只支持 `dsh-persona/v1`，
其他格式可在 `LOADERS` 中增加适配器，不必改动检查规则。

## 下一步

- `--since` 只检查新增条目
- 按严重度排序与建议动作
- 常驻条目的"长期未使用"统计（需要读取实际会话日志）
