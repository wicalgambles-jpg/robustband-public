# SPDX-License-Identifier: MIT
"""Task suitability notes for existing text protocols; scoring stays frozen."""

TEXT_CAUTIONS = (
    ("metrics", ("contains",), "substring", {
        "en": "Substring matching accepts 142 for reference 42. Select it only when substring presence matches your task's criterion.",
        "zh": "包含匹配会把参考答案 42、输出 142 判对。仅在任务本来就以子串出现为判据时选择。"}),
    ("aggs", ("median",), "binary-median", {
        "en": "Median binary correctness can tie 60% and 90% accuracy at 1. It measures a different target from mean accuracy.",
        "zh": "二元正确性的中位数可将 60% 与 90% 正确率都汇总为 1；它与平均正确率衡量不同的目标。"}),
    ("parses", ("first_num", "last_num", "last_line_num", "boxed"), "number-format", {
        "en": "Legacy number extraction splits 1,234 into 1 and 234; boxed falls back to last-number extraction. Check thousands separators and answer formatting before selecting these rules.",
        "zh": "现有数字提取会把 1,234 拆为 1 和 234；框内提取失败时回退到末数提取。选择前请核对千位分隔符与答案格式。"}),
)


def text_rule_cautions(family):
    """Return independent bilingual notes for exactly the selected rules."""
    return [{"id": name, "message": dict(message)}
            for axis, values, name, message in TEXT_CAUTIONS
            if any(value in family.get(axis, ()) for value in values)]
