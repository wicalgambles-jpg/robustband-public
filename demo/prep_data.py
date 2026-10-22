# SPDX-License-Identifier: MIT
"""把 GSM8K(test) parquet 规范化为 items.json：
每项 = {"q":..., "gold":..., "meta":{...}}。gold = '#### N' 后的数。
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
import re
import json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def extract_gold(ans):
    m = re.search(r"####\s*([-+]?\d[\d,]*\.?\d*)", ans)
    if m:
        return m.group(1).replace(",", "").strip()
    nums = re.findall(r"[-+]?\d[\d,]*\.?\d*", ans.replace(",", ""))
    return nums[-1] if nums else ""


def main():
    df = pd.read_parquet(os.path.join(HERE, "data", "gsm8k_test.parquet"))
    items = []
    for i, row in df.iterrows():
        gold = extract_gold(str(row["answer"]))
        q = str(row["question"])
        nsteps = str(row["answer"]).count("\n")
        items.append({
            "q": q,
            "gold": gold,
            "meta": {"class": f"steps_{min(nsteps, 8)}", "len_bucket": min(len(q) // 120, 4)},
        })
    out = os.path.join(HERE, "data", "items.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    print(f"items={len(items)} -> {out}")
    print("sample gold:", [it["gold"] for it in items[:5]])
    print("gold empty:", sum(1 for it in items if it["gold"] == ""))


if __name__ == "__main__":
    main()
