# SPDX-License-Identifier: MIT
# -*- coding: utf-8 -*-
"""共享测试夹具：一个确定性的「计分协议翻转」最小装置。

设计（冻结）：
  gold = "42"
  cot   raw = "the answer is 7 but really 42"  （首个数字 7 / 末个数字 42）
  plain raw = "42 no wait 7"                    （首个数字 42 / 末个数字 7）

  parse=first_num  → cot=7(错) plain=42(对) → margin(cot-plain) = -1
  parse=last_num   → cot=42(对) plain=7(错) → margin(cot-plain) = +1

  故在族 {first_num,last_num}×{exact_match}×{micro} 上 δ=(-1,+1) 含 0 ⟹ UNIDENTIFIABLE。
  这是一个**已知数值**的合成装置：测试断言用的是可手算的精确值，不依赖浮点偶然。
"""
import os
import sys
import threading

import pytest

from robustband import local_ui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

COT_RAW = "the answer is 7 but really 42"
PLAIN_RAW = "42 no wait 7"
GOLD = "42"
META = {"class": "c0", "len_bucket": 0}


@pytest.fixture
def flip_items():
    """返回 (cot_items, plain_items)。"""
    cot = [(COT_RAW, GOLD, dict(META))]
    plain = [(PLAIN_RAW, GOLD, dict(META))]
    return cot, plain


@pytest.fixture
def flip_preds(flip_items):
    """引擎消费的 preds 结构：{model: {"items": [...]}}。"""
    cot, plain = flip_items
    return {"cot": {"items": cot}, "plain": {"items": plain}}


@pytest.fixture
def server():
    """Start the real local UI server on a free loopback port for one test."""
    instance = local_ui.create_server()
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    thread.join(timeout=5)
    instance.server_close()
