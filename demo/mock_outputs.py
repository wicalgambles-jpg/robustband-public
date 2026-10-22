# SPDX-License-Identifier: MIT
"""半合成 mock 输出（仅用于验证 harness 管线端到端可跑；标注为 synthetic）。
锚定真实 GSM8K gold；两个"模型"以不同正确率 + 不同 CoT 结尾格式作答，制造 parse 敏感。
真实演示请用 gen_outputs.py 生成真实模型输出。
"""

# 控制台健壮性：Windows 传统控制台默认 GBK，无法编码中文/−/✔ 等字形会直接崩溃。
# 强制 UTF-8 输出（现代终端正确渲染；无法编码的字符以替代符输出，绝不崩溃）。
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import os
import json
import random

HERE = os.path.dirname(os.path.abspath(__file__))


def make(raw_wrong, gold, rng, style):
    if style == "####":
        return f"Let me solve step by step.\n...some reasoning...\n#### {gold}"
    if style == "boxed":
        return f"Reasoning: ...\nTherefore \\boxed{{{gold}}}"
    if style == "sentence":
        return f"After computing, the answer is {gold}."
    return f"...\n{gold}"


def emit(name, p_correct, rng, items, style_pool):
    rows = []
    for it in items:
        gold = it["gold"]
        try:
            g = float(gold)
        except ValueError:
            g = None
        if rng.random() < p_correct and g is not None:
            val = gold
        else:
            val = str(int(g) + rng.choice([-2, -1, 1, 2, 5])) if g is not None else "0"
        style = rng.choice(style_pool)
        raw = make(None, val, rng, style)
        rows.append({"raw": raw, "gold": gold, "meta": it["meta"]})
    path = os.path.join(HERE, "data", f"{name}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  {name}: {len(rows)} rows -> {path}")


def main():
    items = json.load(open(os.path.join(HERE, "data", "items.json"), encoding="utf-8"))[:300]
    rng_s = random.Random(7)
    rng_w = random.Random(11)
    print("[mock] 生成半合成输出（标注 synthetic，仅供管线验证）")
    emit("MOCK_strong", 0.72, rng_s, items, ["####", "boxed", "sentence"])
    emit("MOCK_weak", 0.55, rng_w, items, ["####", "boxed", "sentence"])


if __name__ == "__main__":
    main()
