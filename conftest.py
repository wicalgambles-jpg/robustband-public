# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""pytest 根 conftest：把协议轨根目录置于 sys.path，使 `import robustband` 在
未安装（源码树）状态下即可工作。安装后（pip install -e . 或 pip install .）本文件
仍安全：仅在被收集时把根目录前置一次。
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
