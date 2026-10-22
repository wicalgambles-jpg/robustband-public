# SPDX-License-Identifier: MIT
"""主张（claim）：定义在「计分表 table = {model: score}」上的可证伪断言。
"""


class RankClaim:
    """主张：better 模型优于 worse 模型（table[better] > table[worse]）。"""

    kind = "rank"

    def __init__(self, better, worse, name=None):
        self.better = better
        self.worse = worse
        self.name = name or f"{better}>{worse}"

    def holds(self, table):
        return table[self.better] > table[self.worse]

    def margin(self, table):
        return table[self.better] - table[self.worse]


class ScoreClaim:
    """主张：模型 model 的分数 >（或 <）阈值 threshold。"""

    kind = "score"

    def __init__(self, model, threshold, greater=True, name=None):
        self.model = model
        self.threshold = threshold
        self.greater = greater
        op = ">" if greater else "<"
        self.name = name or f"{model}{op}{threshold}"

    def holds(self, table):
        v = table[self.model]
        return (v > self.threshold) if self.greater else (v < self.threshold)

    def margin(self, table):
        v = table[self.model] - self.threshold
        return v if self.greater else -v
