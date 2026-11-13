#!/usr/bin/env python3
"""memory-audit: 只读体检 Agent 长期记忆库。

设计原则：
1. 只读。绝不修改、删除、写回任何记忆数据。
2. 默认不输出记忆原文，只输出条目 id、类型与统计，避免把隐私写进报告。
3. 检查规则与数据格式分离，便于以后适配其他记忆格式。

用法：
    python3 audit.py <记忆库目录>
    python3 audit.py <记忆库目录> --format markdown
    python3 audit.py <记忆库目录> --today 2026-11-14
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import json
import os
import sys

# ---------- 数据加载层：与检查规则分离 ----------

def load_dsh_persona(root: str) -> list[dict]:
    """读取 dsh-persona/v1 结构。返回事实列表，每条带 _source 文件名。"""
    facts: list[dict] = []
    patterns = ("core/*.json", "context/*.json")
    for pat in patterns:
        for path in sorted(glob.glob(os.path.join(root, pat))):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                raise SystemExit(f"无法读取 {path}: {exc}")
            for fact in data.get("facts", []):
                fact["_source"] = os.path.basename(path)
                facts.append(fact)
    return facts


LOADERS = {"dsh-persona/v1": load_dsh_persona}


# ---------- 成本估算 ----------

def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。

    经验规则：CJK 字符约 1 token/字，其他字符约 4 字符/token。
    只用于比较不同记忆库的相对开销，不作为计费依据。
    """
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return round(cjk + other / 4)


def fact_tokens(fact: dict) -> int:
    parts = [str(fact.get("statement", "")), " ".join(fact.get("anchors") or [])]
    return estimate_tokens(" ".join(parts))


# ---------- 检查规则 ----------

def check(facts: list[dict], today: datetime.date) -> dict[str, list]:
    issues: dict[str, list] = collections.defaultdict(list)

    for fact in facts:
        fid = fact.get("id", "<无 id>")
        if fact.get("confidence", 0) >= 0.85 and not fact.get("evidence"):
            issues["高置信度但无证据"].append(fid)
        if not fact.get("anchors"):
            issues["缺少原始表述锚点"].append(fid)
        if not fact.get("notes") and not fact.get("conflicts"):
            issues["无备注也无冲突说明"].append(fid)
        if fact.get("sensitivity") == "secret":
            issues["secret 级条目"].append(fid)
        if fact.get("l0") and fact.get("sensitivity") in ("private", "secret"):
            issues["l0 常驻但敏感级偏高"].append((fid, fact["sensitivity"]))

        review = fact.get("review_after")
        if review:
            try:
                iso = review if len(review) > 7 else review + "-01"
                if datetime.date.fromisoformat(iso) < today:
                    issues["已过复核期"].append((fid, review))
            except (ValueError, TypeError):
                issues["复核日期无法解析"].append((fid, review))

    by_key = collections.defaultdict(list)
    for fact in facts:
        by_key[fact.get("key", "<无 key>")].append(fact.get("id"))
    for key, ids in by_key.items():
        if len(ids) > 1:
            issues["同 key 多条（可能需要 supersedes）"].append((key, ids))

    superseded = [f.get("id") for f in facts if f.get("supersedes")]
    if facts and len(superseded) * 10 < len(facts):
        issues["取代链稀疏"].append(
            f"{len(facts)} 条中仅 {len(superseded)} 条声明过 supersedes"
        )

    return issues


# ---------- 报告 ----------

def render_markdown(facts: list[dict], issues: dict[str, list], today: datetime.date) -> str:
    l0 = [f for f in facts if f.get("l0")]
    l0_tokens = sum(fact_tokens(f) for f in l0)
    all_tokens = sum(fact_tokens(f) for f in facts)

    lines = [
        "# 记忆库体检报告",
        "",
        f"- 检查日期：{today.isoformat()}",
        f"- 记忆条目：{len(facts)} 条",
        f"- 常驻上下文（l0）：{len(l0)} 条",
        f"- 常驻记忆估算开销：约 {l0_tokens} tokens / 次会话",
        f"- 全库估算开销：约 {all_tokens} tokens",
        "",
        "> token 为粗略估算（CJK 约 1 token/字，其余约 4 字符/token），仅用于比较相对开销。",
        "> 本报告只包含条目 id 与统计，不包含记忆原文。",
        "",
        "## 发现",
        "",
    ]
    if not issues:
        lines.append("未发现问题。")
    for name, items in issues.items():
        lines.append(f"### {name}（{len(items)}）")
        lines.append("")
        for item in items[:10]:
            lines.append(f"- `{item}`" if not isinstance(item, tuple) else f"- `{item[0]}` — {item[1]}")
        if len(items) > 10:
            lines.append(f"- …… 另有 {len(items) - 10} 条")
        lines.append("")
    return "\n".join(lines)


def render_text(facts, issues, today) -> str:
    l0 = [f for f in facts if f.get("l0")]
    out = [
        f"检查日期 {today.isoformat()}｜记忆 {len(facts)} 条｜常驻 {len(l0)} 条"
        f"｜常驻约 {sum(fact_tokens(f) for f in l0)} tokens/次"
    ]
    for name, items in issues.items():
        out.append(f"\n## {name}（{len(items)}）")
        for item in items[:5]:
            out.append("  - " + (f"{item[0]} — {item[1]}" if isinstance(item, tuple) else str(item)))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="只读体检 Agent 长期记忆库")
    ap.add_argument("root", help="记忆库目录")
    ap.add_argument("--format", choices=("text", "markdown"), default="text")
    ap.add_argument("--today", help="以指定日期判断过期（YYYY-MM-DD），默认今天")
    args = ap.parse_args(argv)

    facts = load_dsh_persona(args.root)
    if not facts:
        print(f"在 {args.root} 下没有找到记忆条目", file=sys.stderr)
        return 2

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    issues = check(facts, today)
    print(render_markdown(facts, issues, today) if args.format == "markdown"
          else render_text(facts, issues, today))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
