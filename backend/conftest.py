"""Pytest 引导：把 backend 根目录加入 sys.path，使 `app.*` 可导入。"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent
REPO_ROOT = BACKEND_ROOT.parent

sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(REPO_ROOT))
