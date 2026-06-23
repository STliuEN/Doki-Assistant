"""Pytest 引导：把 backend 根目录加入 sys.path，使 `app.*` 可导入。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
