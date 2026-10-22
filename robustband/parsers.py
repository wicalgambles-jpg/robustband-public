# SPDX-License-Identifier: MIT
"""解析轴（parse）：从模型原始输出 raw 中抽取候选答案 candidate（字符串）。
沿 A 档（仅计分）冻结的 5 种合法抽取协议。
"""
import re

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def p_strict_exact(raw):
    """严格：整串即答案（不做任何抽取）。"""
    return (raw or "").strip()


def p_first_num(raw):
    """取串中第一个数。"""
    m = _NUM.search(raw or "")
    return m.group(0) if m else (raw or "").strip()


def p_last_num(raw):
    """取串中最后一个数。"""
    ms = _NUM.findall(raw or "")
    return ms[-1] if ms else (raw or "").strip()


def p_last_line_num(raw):
    """取最后一个非空行里的最后一个数。"""
    lines = [l for l in (raw or "").splitlines() if l.strip()]
    if not lines:
        return ""
    return p_last_num(lines[-1])


def p_boxed(raw):
    """取 \\boxed{...} 内容；否则退化为 last_num。"""
    m = re.search(r"\\boxed\{([^{}]*)\}", raw or "")
    if m:
        return m.group(1).strip()
    return p_last_num(raw)


PARSE = {
    "strict_exact": p_strict_exact,
    "first_num": p_first_num,
    "last_num": p_last_num,
    "last_line_num": p_last_line_num,
    "boxed": p_boxed,
}
