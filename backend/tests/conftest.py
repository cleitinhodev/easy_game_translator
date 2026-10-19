import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EGT_CONFIG_DIR", tempfile.mkdtemp(prefix="egt_test_cfg_"))
