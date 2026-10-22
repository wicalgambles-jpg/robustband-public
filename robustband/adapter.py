# SPDX-License-Identifier: MIT
"""基准适配器：把外部数据源规范化为引擎消费的 preds 结构。
preds = {model: {"items": [(raw, gold, meta), ...]}}
"""
import json
from pathlib import Path


class BenchmarkAdapter:
    """基类。子类实现 load() -> (models, items_by_model)。"""

    name = "base"

    def load(self):
        raise NotImplementedError


class JSONLAdapter(BenchmarkAdapter):
    """每个模型一个 JSONL 文件，行 = {"raw":..., "gold":..., "meta":{...}}。
    目录命名 = 模型名。gold 亦可在首个模型文件里统一，此处要求每行自带 gold。
    """

    def __init__(self, root, name="jsonl", models=None):
        self.root = Path(root)
        self.name = name
        self._models = models

    def load(self):
        preds = {}
        for f in sorted(self.root.glob("*.jsonl")):
            model = f.stem
            if self._models and model not in self._models:
                continue
            items = []
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                o = json.loads(line)
                items.append((o.get("raw", ""), o.get("gold", ""), o.get("meta") or {}))
            preds[model] = {"items": items}
        return preds


class InMemoryAdapter(BenchmarkAdapter):
    """直接由内存字典构造，供自检/演示使用。"""

    def __init__(self, preds, name="in_memory"):
        self._preds = preds
        self.name = name

    def load(self):
        return self._preds
