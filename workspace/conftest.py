import sys
from pathlib import Path

# 将 workspace 根目录加入 sys.path，使 examples/ 可被 import
_ws = str(Path(__file__).resolve().parent)
if _ws not in sys.path:
    sys.path.insert(0, _ws)

# 忽略 uploads/ 目录中的测试文件（避免模块名冲突）
collect_ignore_glob = ["uploads/*"]
