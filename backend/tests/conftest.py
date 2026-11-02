import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EGT_NO_AUTOCHECK", "1")       # a verificação automática dos tradutores usaria a rede
os.environ.setdefault("EGT_CONFIG_DIR", tempfile.mkdtemp(prefix="egt_test_cfg_"))
