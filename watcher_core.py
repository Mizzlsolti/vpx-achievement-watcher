"""Backward-compatible re-exports for watcher_core."""
import sys, os
_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
from vpx_achievement_watcher.core import *
from vpx_achievement_watcher.core.helpers import *
from vpx_achievement_watcher.core.paths import *
from vpx_achievement_watcher.core.config import *
from vpx_achievement_watcher.input import *
from vpx_achievement_watcher.core.watcher import Watcher
from vpx_achievement_watcher.core.cloud_sync import CloudSync
from vpx_achievement_watcher.utils.json_io import *
from vpx_achievement_watcher.utils.version import *
